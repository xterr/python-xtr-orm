"""``orm:migrations:rollup``: record the single remaining revision as all there is."""

from __future__ import annotations

from typing import final

from xtr_console import ConsoleStyle, ExitCode, as_command, escape

from xtr_orm.exception import MigrationError

from .connection_command import ConnectionCommand

__all__ = ["MigrationsRollupCommand"]


@as_command("orm:migrations:rollup")
@final
class MigrationsRollupCommand(ConnectionCommand):
    """Records the single remaining revision as all the database has applied."""

    __slots__ = ()

    async def __call__(self, io: ConsoleStyle, *, connection: str | None = None) -> int:
        """Forget every applied revision, then record the single remaining one as applied.

        For after squashing every revision into one: the database is left as
        it is, recorded as being at that revision.

        Args:
            io: Where the command writes.
            connection: The connection to record on; the default one when left
                out.
        """
        migrator = await self._migrator(io, connection)
        if migrator is None:
            return ExitCode.FAILURE
        try:
            rolled = await migrator.rollup()
        except MigrationError as error:
            io.error(escape(error.reason))
            return ExitCode.FAILURE
        io.success(f'Rolled up migrations to version "{escape(rolled.version)}".')
        return ExitCode.SUCCESS
