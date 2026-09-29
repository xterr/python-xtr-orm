"""``orm:migrations:generate``: write an empty revision."""

from __future__ import annotations

from typing import final

from xtr_console import ConsoleStyle, ExitCode, as_command, escape

from xtr_orm.exception import MigrationError

from .connection_command import ConnectionCommand, report_written

__all__ = ["MigrationsGenerateCommand"]


@as_command("orm:migrations:generate")
@final
class MigrationsGenerateCommand(ConnectionCommand):
    """Generate a blank migration class."""

    __slots__ = ()

    async def __call__(
        self,
        io: ConsoleStyle,
        *,
        message: str | None = None,
        connection: str | None = None,
    ) -> int:
        """Write an empty revision following the latest one, to fill in by hand.

        Args:
            io: Where the command writes.
            message: What the revision does; it names the file too.
            connection: The connection whose revisions to add to; the default
                one when left out.
        """
        migrator = await self._migrator(io, connection)
        if migrator is None:
            return ExitCode.FAILURE
        try:
            written = migrator.generate(message)
        except MigrationError as error:
            io.error(escape(error.reason))
            return ExitCode.FAILURE
        report_written(io, "Generated new migration class to", written, connection)
        return ExitCode.SUCCESS
