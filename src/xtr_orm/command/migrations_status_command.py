"""``orm:migrations:status``: where the database stands, in one table."""

from __future__ import annotations

from typing import final

from xtr_console import ConsoleStyle, ExitCode, as_command, escape

from xtr_orm.exception import MigrationError

from .connection_command import ConnectionCommand

__all__ = ["MigrationsStatusCommand"]


@as_command("orm:migrations:status")
@final
class MigrationsStatusCommand(ConnectionCommand):
    """Shows where the database stands against its revisions."""

    __slots__ = ()

    async def __call__(self, io: ConsoleStyle, *, connection: str | None = None) -> int:
        """Show where the revisions and their tables are, and where the database stands.

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
        config = migrator.config
        url = migrator.engine.url
        schema = config.version_table_schema
        rows = [
            ["Storage", "Version table", _qualified(schema, config.version_table)],
            ["", "History table", _qualified(schema, config.history_table)],
            ["Database", "Connection", migrator.name],
            ["", "Driver", f"{url.get_backend_name()}+{url.get_driver_name()}"],
            ["", "Name", url.database or ""],
            ["Versions", "Previous", _versions(status.previous) if status.current else "none"],
            ["", "Current", _versions(status.current)],
            ["", "Next", ", ".join(status.next) or "none"],
            ["", "Latest", _versions(status.latest)],
            ["Migrations", "Executed", str(len(status.executed))],
            ["", "Executed Unavailable", str(len(status.executed_unavailable))],
            ["", "Available", str(len(status.available))],
            ["", "New", str(len(status.new))],
            ["Migrations Directory", "", config.directory],
        ]
        io.table(["Configuration", "", ""], [[escape(cell) for cell in row] for row in rows])
        return ExitCode.SUCCESS


def _versions(versions: tuple[str, ...]) -> str:
    return ", ".join(versions) or "base"


def _qualified(schema: str | None, table: str) -> str:
    return f"{schema}.{table}" if schema else table
