"""``orm:migrations:list``: every revision, and whether it is applied."""

from __future__ import annotations

from typing import final

from xtr_console import ConsoleStyle, ExitCode, as_command, escape

from xtr_orm.exception import MigrationError
from xtr_orm.migrations import ExecutedMigration

from .connection_command import ConnectionCommand

__all__ = ["MigrationsListCommand"]


@as_command("orm:migrations:list")
@final
class MigrationsListCommand(ConnectionCommand):
    """Lists every revision and whether it is applied."""

    __slots__ = ()

    async def __call__(self, io: ConsoleStyle, *, connection: str | None = None) -> int:
        """List every revision, earliest first, then the applied ones whose file is gone.

        Args:
            io: Where the command writes.
            connection: The connection to read; the default one when left out.
        """
        migrator = await self._migrator(io, connection)
        if migrator is None:
            return ExitCode.FAILURE
        try:
            status = await migrator.status()
        except MigrationError as error:
            io.error(escape(error.reason))
            return ExitCode.FAILURE
        executed = {each.version: each for each in status.executed}
        rows = [
            _row(each.version, executed.get(each.version), each.description, available=True)
            for each in status.available
        ]
        rows += [
            _row(each.version, each, "", available=False) for each in status.executed_unavailable
        ]
        io.table(
            ["Migration Versions", "Status", "Migrated At", "Execution Time", "Description"],
            rows,
        )
        return ExitCode.SUCCESS


def _row(
    version: str, executed: ExecutedMigration | None, description: str, *, available: bool
) -> list[str]:
    if executed is None:
        status = "not migrated"
    else:
        status = "migrated" if available else "migrated, not available"
    migrated_at = (
        f"{executed.executed_at:%Y-%m-%d %H:%M:%S}"
        if executed is not None and executed.executed_at is not None
        else ""
    )
    duration = (
        f"{executed.execution_time:.3f}s"
        if executed is not None and executed.execution_time is not None
        else ""
    )
    return [escape(version), status, migrated_at, duration, escape(description)]
