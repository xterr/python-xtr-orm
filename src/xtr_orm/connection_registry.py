"""Every configured connection by name, each piece built only when first asked for."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, TypeVar, cast, final

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from xtr_orm.database import DatabaseManager
from xtr_orm.exception import (
    InvalidArgumentError,
    SessionUnavailableError,
    UnknownConnectionError,
)
from xtr_orm.migrations import Migrator

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

__all__ = ["DEFAULT_CONNECTION", "ConnectionRegistry"]

DEFAULT_CONNECTION: Final = "default"
"""The name of the connection used when none is named."""

_T = TypeVar("_T")


@dataclass(frozen=True, slots=True)
class _Connection:
    engine: Callable[[], Awaitable[AsyncEngine]]
    migrator: Callable[[], Awaitable[Migrator]]
    database: Callable[[], Awaitable[DatabaseManager]]
    session: Callable[[], Awaitable[AsyncSession]] | None
    close: Callable[[], Awaitable[None]] | None
    in_use: Callable[[], bool] | None


@final
class ConnectionRegistry:
    """Every connection by name: its engine, its migrator and its database manager.

    Each is given as the object itself, or as an async function building it —
    called only when that piece is first asked for, so a command touching one
    connection opens nothing of another's.

    A connection may also say how to reach the session of the current unit
    of work — the one every handler of a message shares — and how to close
    it, releasing every connection it holds; the message bus middleware use
    both.

    ```python
    registry = ConnectionRegistry()
    registry.register(
        "default",
        engine=engine,
        migrator=Migrator(engine, MigrationsConfig(directory="migrations")),
        database=DatabaseManager(url),
    )
    ```
    """

    __slots__ = ("_connections", "_default")

    _connections: dict[str, _Connection]
    _default: str

    def __init__(self, default: str = DEFAULT_CONNECTION) -> None:
        """Hold connections, answering for ``default`` when none is named."""
        self._connections = {}
        self._default = default

    @property
    def default(self) -> str:
        """The name of the connection used when none is named."""
        return self._default

    def register(  # noqa: PLR0913 — one keyword per piece of a connection
        self,
        name: str,
        *,
        engine: AsyncEngine | Callable[[], Awaitable[AsyncEngine]],
        migrator: Migrator | Callable[[], Awaitable[Migrator]],
        database: DatabaseManager | Callable[[], Awaitable[DatabaseManager]],
        session: Callable[[], Awaitable[AsyncSession]] | None = None,
        close: Callable[[], Awaitable[None]] | None = None,
        in_use: Callable[[], bool] | None = None,
    ) -> None:
        """Add the connection ``name``, or replace it.

        Args:
            name: What the connection is known by.
            engine: Its engine, or what builds it.
            migrator: Its migrator, or what builds it.
            database: Its database manager, or what builds it.
            session: What returns the session of the unit of work under way;
                without it, :meth:`session` is refused.
            close: What closes the connection; its engine is disposed when
                left out.
            in_use: Whether the connection is in use — its engine built;
                without it, the connection always is. See :meth:`in_use`.

        Raises:
            InvalidArgumentError: When ``name`` is empty.
        """
        if not name:
            raise InvalidArgumentError("A connection needs a non-empty name.")
        self._connections[name] = _Connection(
            engine=_provider(engine, AsyncEngine),
            migrator=_provider(migrator, Migrator),
            database=_provider(database, DatabaseManager),
            session=session,
            close=close,
            in_use=in_use,
        )

    def names(self) -> tuple[str, ...]:
        """Every connection's name, in the order registered."""
        return tuple(self._connections)

    def in_use(self) -> tuple[str, ...]:
        """The names of the connections in use, in the order registered.

        What the message bus middleware act on unless given names: a
        connection nothing has used has no session to check and no pool to
        close, and opening it to find out would read its configuration.
        """
        return tuple(
            name
            for name, connection in self._connections.items()
            if connection.in_use is None or connection.in_use()
        )

    def has(self, name: str | None = None) -> bool:
        """Whether the connection ``name`` — the default one when ``None`` — exists."""
        return (name or self._default) in self._connections

    async def engine(self, name: str | None = None) -> AsyncEngine:
        """Return the engine of the connection ``name``, the default one when ``None``.

        Raises:
            UnknownConnectionError: When no connection has that name.
        """
        return await self._get(name).engine()

    async def migrator(self, name: str | None = None) -> Migrator:
        """Return the migrator of the connection ``name``, the default one when ``None``.

        Raises:
            UnknownConnectionError: When no connection has that name.
        """
        return await self._get(name).migrator()

    async def database(self, name: str | None = None) -> DatabaseManager:
        """Return the database manager of the connection ``name``, the default one when ``None``.

        Raises:
            UnknownConnectionError: When no connection has that name.
        """
        return await self._get(name).database()

    async def session(self, name: str | None = None) -> AsyncSession:
        """Return the session of the current unit of work on the connection ``name``.

        Raises:
            UnknownConnectionError: When no connection has that name.
            SessionUnavailableError: When the connection was registered
                without a way to reach one.
        """
        wanted = name or self._default
        provide = self._get(name).session
        if provide is None:
            raise SessionUnavailableError(wanted, "it was registered without a session")
        return await provide()

    async def close(self, name: str | None = None) -> None:
        """Close the connection ``name``: release every database connection its pools hold.

        The engine stays usable; its next use connects again.

        Raises:
            UnknownConnectionError: When no connection has that name.
        """
        connection = self._get(name)
        if connection.close is not None:
            await connection.close()
            return
        await (await connection.engine()).dispose()

    def _get(self, name: str | None) -> _Connection:
        wanted = name or self._default
        found = self._connections.get(wanted)
        if found is None:
            raise UnknownConnectionError(wanted, self.names())
        return found


def _provider(
    given: _T | Callable[[], Awaitable[_T]], kind: type[_T]
) -> Callable[[], Awaitable[_T]]:
    """Return an async function giving ``given``: itself when it is one, else wrapping it."""
    if isinstance(given, kind):
        instance = given

        async def provide() -> _T:
            return instance

        return provide
    # Anything not of the built kind is the function building it, as the signature says.
    return cast("Callable[[], Awaitable[_T]]", given)
