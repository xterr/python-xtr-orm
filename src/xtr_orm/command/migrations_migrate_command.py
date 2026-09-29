"""``orm:migrations:migrate``: bring the database to a revision, up or down."""

from __future__ import annotations

from typing import Final, final

from xtr_console import ConsoleStyle, ExitCode, as_command, escape

from xtr_orm.exception import MigrationError

from .connection_command import (
    ConnectionCommand,
    confirm_changes,
    report_count,
    report_plan,
    report_results,
    save_sql,
)

__all__ = ["MigrationsMigrateCommand"]

_LATEST: Final = frozenset({"latest", "head", "heads"})


@as_command("orm:migrations:migrate")
@final
class MigrationsMigrateCommand(ConnectionCommand):
    """Execute a migration to a specified version or the latest available version."""

    __slots__ = ()

    async def __call__(  # noqa: C901, PLR0911 — each way out says why it stopped
        self,
        io: ConsoleStyle,
        version: str = "latest",
        *,
        dry_run: bool = False,
        write_sql: str | None = None,
        allow_no_migration: bool = False,
        connection: str | None = None,
    ) -> int:
        """Run every revision between where the database is and the version.

        The version is a revision — a full or partial id — a relative one
        (+1, -2), or one of latest, first (before every
        revision), next, prev and current. A revision already
        applied is migrated down to; one that is not, up to.

        Args:
            io: Where the command writes.
            version: Where to bring the database.
            dry_run: List what would run, and run nothing.
            write_sql: Write the SQL that would run to this file — or to a
                dated file in this directory — and run nothing.
            allow_no_migration: Succeed when there are no revisions at all.
            connection: The connection to migrate; the default one when left
                out.
        """
        migrator = await self._migrator(io, connection)
        if migrator is None:
            return ExitCode.FAILURE
        try:
            status = await migrator.status()
            if not status.available:
                if allow_no_migration:
                    io.warning("No migrations to execute.")
                    return ExitCode.SUCCESS
                io.error(
                    f'The version "{escape(version)}" couldn\'t be reached, '
                    "there are no registered migrations.",
                )
                return ExitCode.FAILURE
            unregistered = len(status.executed_unavailable)
            if unregistered:
                io.warning(
                    f"You have {unregistered} previously executed migrations in the database "
                    "that are not registered migrations.",
                )
                if not io.confirm("Are you sure you wish to continue?", default=True):
                    io.error("Migration cancelled!")
                    return ExitCode.FAILURE
            plans = await migrator.plan(version)
            if not plans:
                where = ", ".join(status.current) or "base"
                message = (
                    f'Already at the latest version ("{escape(where)}").'
                    if version in _LATEST
                    else f'Already at "{escape(version)}": no migrations to execute.'
                )
                io.success(message)
                return ExitCode.SUCCESS
            if write_sql is not None:
                save_sql(io, write_sql, await migrator.migrate_sql(version))
                return ExitCode.SUCCESS
            if dry_run:
                report_plan(io, plans)
                io.note("Dry run: nothing was executed.")
                return ExitCode.SUCCESS
            if not confirm_changes(io, migrator):
                io.error("Migration cancelled!")
                return ExitCode.FAILURE
            results = await migrator.migrate(version)
        except MigrationError as error:
            io.error(escape(error.reason))
            return ExitCode.FAILURE
        report_results(io, results)
        report_count(io, results)
        return ExitCode.SUCCESS
