"""``orm:migrations:current``: the revisions the database is at."""

from __future__ import annotations

from typing import final

from xtr_console import ConsoleStyle, ExitCode, as_command, escape

from xtr_orm.exception import MigrationError

from .connection_command import ConnectionCommand, format_version

__all__ = ["MigrationsCurrentCommand"]


@as_command("orm:migrations:current")
@final
class MigrationsCurrentCommand(ConnectionCommand):
    """Outputs the current version."""

    __slots__ = ()

    async def __call__(self, io: ConsoleStyle, *, connection: str | None = None) -> int:
        """Print the revisions the database is at, one per line — base for none.

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
        descriptions = {each.version: each.description for each in status.available}
        if not status.current:
            io.text("base")
        for version in status.current:
            description = descriptions.get(version, "(not available)")
            io.text(escape(format_version(version, description)))
        return ExitCode.SUCCESS
