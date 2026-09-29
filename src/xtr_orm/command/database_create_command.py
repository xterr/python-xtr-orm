"""``orm:database:create``: create a connection's database on its server."""

from __future__ import annotations

from typing import final

from sqlalchemy.exc import SQLAlchemyError
from xtr_console import ConsoleStyle, ExitCode, as_command, escape

from xtr_orm.exception import UnsupportedDatabaseError

from .connection_command import ConnectionCommand

__all__ = ["DatabaseCreateCommand"]


@as_command("orm:database:create")
@final
class DatabaseCreateCommand(ConnectionCommand):
    """Creates the configured database."""

    __slots__ = ()

    async def __call__(
        self,
        io: ConsoleStyle,
        *,
        if_not_exists: bool = False,
        connection: str | None = None,
    ) -> int:
        """Create the configured database.

        Args:
            io: Where the command writes.
            if_not_exists: Do nothing, successfully, when the database exists.
            connection: The connection whose database to create; the default
                one when left out.
        """
        database = await self._database(io, connection)
        if database is None:
            return ExitCode.FAILURE
        name = escape(database.database)
        where = f'for connection named "{escape(self._name(connection))}"'
        try:
            created = await database.create(if_not_exists=if_not_exists)
        except (SQLAlchemyError, OSError, UnsupportedDatabaseError) as error:
            io.error(f'Could not create database "{name}" {where}: {escape(str(error))}')
            return ExitCode.FAILURE
        if not created:
            io.text(f'Database "{name}" {where} already exists. Skipped.')
            return ExitCode.SUCCESS
        io.success(f'Created database "{name}" {where}.')
        return ExitCode.SUCCESS
