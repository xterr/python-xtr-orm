"""``orm:migrations:execute``: run chosen revisions alone, up or down."""

from __future__ import annotations

from typing import final

from xtr_console import ConsoleStyle, ExitCode, as_command, escape

from xtr_orm.exception import MigrationError
from xtr_orm.migrations import Direction

from .connection_command import (
    ConnectionCommand,
    confirm_changes,
    report_count,
    report_plan,
    report_results,
    save_sql,
)

__all__ = ["MigrationsExecuteCommand"]


@as_command("orm:migrations:execute")
@final
class MigrationsExecuteCommand(ConnectionCommand):
    """Execute one or more migration versions up or down manually."""

    __slots__ = ()

    async def __call__(  # noqa: PLR0911 — each way out says why it stopped
        self,
        io: ConsoleStyle,
        *versions: str,
        up: bool = False,
        down: bool = False,
        dry_run: bool = False,
        write_sql: str | None = None,
        connection: str | None = None,
    ) -> int:
        """Run exactly the versions, in order, each up (the default) or down, and nothing else.

        Going up, a revision must not be applied and must follow only applied
        ones; going down, it must be applied and followed by none that is.
        Use orm:migrations:version to record a revision without running it.

        Args:
            io: Where the command writes.
            versions: The revisions to run, by full or partial id.
            up: Run their upgrades.
            down: Run their downgrades.
            dry_run: List what would run, and run nothing.
            write_sql: Write the SQL that would run to this file — or to a
                dated file in this directory — and run nothing.
            connection: The connection to run them on; the default one when
                left out.
        """
        if up and down:
            io.error("Give --up or --down, not both.")
            return ExitCode.INVALID
        if not versions:
            io.error("Name at least one version to execute.")
            return ExitCode.INVALID
        direction = Direction.DOWN if down else Direction.UP
        migrator = await self._migrator(io, connection)
        if migrator is None:
            return ExitCode.FAILURE
        try:
            if write_sql is not None:
                save_sql(io, write_sql, await migrator.execute_sql(versions, direction))
                return ExitCode.SUCCESS
            planned = await migrator.plan_for_versions(versions, direction)
            if dry_run:
                report_plan(io, planned)
                io.note("Dry run: nothing was executed.")
                return ExitCode.SUCCESS
            if not confirm_changes(io, migrator):
                io.error("Migration cancelled!")
                return ExitCode.FAILURE
            results = await migrator.execute(versions, direction)
        except MigrationError as error:
            io.error(escape(error.reason))
            return ExitCode.FAILURE
        report_results(io, results)
        report_count(io, results)
        return ExitCode.SUCCESS
