"""``orm:database:drop``: drop a connection's database from its server."""

from __future__ import annotations

from typing import Annotated, final

from sqlalchemy.exc import SQLAlchemyError
from xtr_console import ConsoleStyle, ExitCode, Option, as_command, escape

from xtr_orm.exception import UnsupportedDatabaseError

from .connection_command import ConnectionCommand

__all__ = ["DatabaseDropCommand"]


@as_command("orm:database:drop")
@final
class DatabaseDropCommand(ConnectionCommand):
    """Drops a connection's database from its server."""

    __slots__ = ()

    async def __call__(
        self,
        io: ConsoleStyle,
        *,
        if_exists: bool = False,
        force: Annotated[bool, Option(alias="-f")] = False,
        connection: str | None = None,
    ) -> int:
        """Drop the configured database, and every table and row in it.

        Refused without --force, which is the confirmation that all of it may
        be lost.

        Args:
            io: Where the command writes.
            if_exists: Do nothing, successfully, when the database does not
                exist.
            force: Really drop it.
            connection: The connection whose database to drop; the default one
                when left out.
        """
        database = await self._database(io, connection)
        if database is None:
            return ExitCode.FAILURE
        name = escape(database.database)
        where = f'for connection named "{escape(self._name(connection))}"'
        if not force:
            io.error(
                f'This would drop the database "{name}" {where}, and all its data would be '
                "lost. Run the command again with --force to drop it.",
            )
            return ExitCode.INVALID
        try:
            dropped = await database.drop(if_exists=if_exists)
        except (SQLAlchemyError, OSError, UnsupportedDatabaseError) as error:
            io.error(f'Could not drop database "{name}" {where}: {escape(str(error))}')
            return ExitCode.FAILURE
        if not dropped:
            io.text(f'Database "{name}" {where} does not exist. Skipped.')
            return ExitCode.SUCCESS
        io.success(f'Dropped database "{name}" {where}.')
        return ExitCode.SUCCESS
