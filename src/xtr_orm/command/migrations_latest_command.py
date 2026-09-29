"""``orm:migrations:latest``: the revisions no other follows."""

from __future__ import annotations

from typing import final

from xtr_console import ConsoleStyle, ExitCode, as_command, escape

from xtr_orm.exception import MigrationError

from .connection_command import ConnectionCommand, format_version

__all__ = ["MigrationsLatestCommand"]


@as_command("orm:migrations:latest")
@final
class MigrationsLatestCommand(ConnectionCommand):
    """Outputs the latest version."""

    __slots__ = ()

    async def __call__(self, io: ConsoleStyle, *, connection: str | None = None) -> int:
        """Print the revisions no other follows, one per line — base when there are none.

        Args:
            io: Where the command writes.
            connection: The connection whose revisions to read; the default one
                when left out.
        """
        migrator = await self._migrator(io, connection)
        if migrator is None:
            return ExitCode.FAILURE
        try:
            status = await migrator.status()
        except MigrationError as error:
            io.error(escape(error.reason))
            return ExitCode.FAILURE
        heads = [each for each in status.available if each.is_head]
        if not heads:
            io.text("base")
        for head in heads:
            io.text(escape(format_version(head.version, head.description)))
        return ExitCode.SUCCESS
