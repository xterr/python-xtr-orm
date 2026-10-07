"""What every orm command shares: the connections it acts on."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from xtr_console import ConsoleStyle, escape

from xtr_orm.connection_registry import ConnectionRegistry
from xtr_orm.exception import UnknownConnectionError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

    from xtr_orm.database import DatabaseManager
    from xtr_orm.migrations import Migrator

__all__ = ["ConnectionCommand"]


class ConnectionCommand:
    """An orm command, acting on the connections it was built with.

    The registry is how a command reaches a database, so it is required:
    a container builds each command with the one its bundle registered, and a
    console with no container to supply it reports the parameter it cannot
    fill. Built by hand, a command takes a registry of its own.
    """

    __slots__: ClassVar[tuple[str, ...]] = ("_connections",)

    _connections: ConnectionRegistry

    def __init__(self, connections: ConnectionRegistry) -> None:
        """Act on the databases ``connections`` names."""
        self._connections = connections

    async def _migrator(self, io: ConsoleStyle, connection: str | None) -> Migrator | None:
        """Return the migrator of ``connection``, or say on ``io`` why there is none."""
        if not self._known(io, connection):
            return None
        return await self._connections.migrator(connection)

    async def _database(self, io: ConsoleStyle, connection: str | None) -> DatabaseManager | None:
        """Return the database manager of ``connection``, or say on ``io`` why there is none."""
        if not self._known(io, connection):
            return None
        return await self._connections.database(connection)

    async def _engine(self, io: ConsoleStyle, connection: str | None) -> AsyncEngine | None:
        """Return the engine of ``connection``, or say on ``io`` why there is none."""
        if not self._known(io, connection):
            return None
        return await self._connections.engine(connection)

    def _name(self, connection: str | None) -> str:
        """The name ``connection`` stands for: itself, or the default connection's."""
        return connection or self._connections.default

    def _known(self, io: ConsoleStyle, connection: str | None) -> bool:
        """Whether ``connection`` is registered; when not, ``io`` names the ones that are."""
        if self._connections.has(connection):
            return True
        unknown = UnknownConnectionError(self._name(connection), self._connections.names())
        io.error(escape(str(unknown)))
        return False
