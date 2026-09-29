"""Creating and dropping the database a connection URL names."""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final, final

from sqlalchemy import URL, make_url, text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from xtr_orm.exception import InvalidArgumentError, UnsupportedDatabaseError

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Mapping

    from sqlalchemy.ext.asyncio import AsyncConnection

__all__ = ["DatabaseManager"]

_MEMORY: Final = frozenset({"", ":memory:"})


@dataclass(frozen=True, slots=True)
class _Server:
    """How to reach a kind of server without its database, and ask it about one."""

    maintenance_database: str | None
    exists: str


_SERVERS: Final[dict[str, _Server]] = {
    "postgresql": _Server("postgres", "SELECT 1 FROM pg_database WHERE datname = :name"),
    "mysql": _Server(None, "SELECT 1 FROM information_schema.schemata WHERE schema_name = :name"),
    "mariadb": _Server(None, "SELECT 1 FROM information_schema.schemata WHERE schema_name = :name"),
    "mssql": _Server("master", "SELECT 1 FROM sys.databases WHERE name = :name"),
}


@final
class DatabaseManager:
    """Creates and drops the database a connection URL names, on its server.

    A database cannot be created from a connection to itself, so the server
    is reached through its maintenance database — ``postgres`` on
    PostgreSQL, ``master`` on SQL Server, none on MySQL and MariaDB — with
    every statement committed as it runs. A SQLite database is its file.

    ```python
    manager = DatabaseManager("postgresql+asyncpg://app:secret@db/shop")
    await manager.create(if_not_exists=True)
    ```
    """

    __slots__ = ("_connect_args", "_url")

    _url: URL
    _connect_args: Mapping[str, object]

    def __init__(self, url: str | URL, *, connect_args: Mapping[str, object] | None = None) -> None:
        """Manage the database ``url`` names, connecting with ``connect_args``.

        Raises:
            InvalidArgumentError: When the URL names no database on a server.
        """
        self._url = make_url(url)
        self._connect_args = connect_args or {}
        if self.backend != "sqlite" and not self._url.database:
            raise InvalidArgumentError(
                f"The URL {self.safe_url} names no database to create or drop.",
            )

    @property
    def backend(self) -> str:
        """The kind of server, such as ``"postgresql"`` or ``"sqlite"``."""
        return self._url.get_backend_name()

    @property
    def database(self) -> str:
        """The database's name — for SQLite, its file."""
        return self._url.database or ""

    @property
    def safe_url(self) -> str:
        """The URL with its password hidden, fit for a message."""
        return self._url.render_as_string(hide_password=True)

    async def exists(self) -> bool:
        """Whether the database exists.

        Raises:
            UnsupportedDatabaseError: For a server this library cannot ask.
        """
        if self.backend == "sqlite":
            path = self._sqlite_path()
            return path is None or path.exists()
        server = self._server("check")
        async with self._maintenance() as connection:
            found = await connection.execute(text(server.exists), {"name": self.database})
            return found.first() is not None

    async def create(self, *, if_not_exists: bool = False) -> bool:
        """Create the database; return whether it was created.

        Args:
            if_not_exists: Leave an existing database alone and return
                ``False``, rather than let the server refuse.

        Raises:
            UnsupportedDatabaseError: For a server this library cannot ask.
        """
        if if_not_exists and await self.exists():
            return False
        if self.backend == "sqlite":
            self._create_file()
            return True
        _ = self._server("create")
        async with self._maintenance() as connection:
            name = connection.dialect.identifier_preparer.quote(self.database)
            _ = await connection.execute(text(f"CREATE DATABASE {name}"))
        return True

    async def drop(self, *, if_exists: bool = False) -> bool:
        """Drop the database; return whether it was dropped.

        Args:
            if_exists: Do nothing for a database that does not exist and
                return ``False``, rather than let the server refuse.

        Raises:
            UnsupportedDatabaseError: For a server this library cannot ask.
        """
        if if_exists and not await self.exists():
            return False
        if self.backend == "sqlite":
            self._remove_file()
            return True
        _ = self._server("drop")
        async with self._maintenance() as connection:
            name = connection.dialect.identifier_preparer.quote(self.database)
            _ = await connection.execute(text(f"DROP DATABASE {name}"))
        return True

    def _server(self, operation: str) -> _Server:
        server = _SERVERS.get(self.backend)
        if server is None:
            raise UnsupportedDatabaseError(self.backend, operation)
        return server

    @asynccontextmanager
    async def _maintenance(self) -> AsyncGenerator[AsyncConnection]:
        """Connect to the server's maintenance database, committing every statement."""
        server = _SERVERS[self.backend]
        url = self._url
        # ``set`` keeps a database it is given None for, so the URL is rebuilt.
        maintenance = URL.create(
            url.drivername,
            username=url.username,
            password=url.password,
            host=url.host,
            port=url.port,
            database=server.maintenance_database,
            query=url.query,
        )
        engine = create_async_engine(
            maintenance,
            poolclass=NullPool,
            isolation_level="AUTOCOMMIT",
            connect_args=dict(self._connect_args),
        )
        try:
            async with engine.connect() as connection:
                yield connection
        finally:
            await engine.dispose()

    def _sqlite_path(self) -> Path | None:
        """Return the SQLite file, or ``None`` for a database kept in memory."""
        if self.database in _MEMORY or self.database.startswith("file::memory:"):
            return None
        return Path(self.database.removeprefix("file:").split("?", 1)[0])

    def _create_file(self) -> None:
        """Create the SQLite file, refusing one that exists; nothing for one in memory."""
        path = self._sqlite_path()
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch(exist_ok=False)

    def _remove_file(self) -> None:
        """Remove the SQLite file; nothing for one in memory."""
        path = self._sqlite_path()
        if path is not None:
            path.unlink()
