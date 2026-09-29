"""Unit tests for :class:`xtr_orm.database.DatabaseManager`.

SQLite runs for real, on files under the test's directory. A server is
stood in for by a connection that records what it is sent and answers
whether the database exists, so every statement a server would receive is
checked without one.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, cast, final

import pytest
from sqlalchemy.dialects import mssql, mysql, postgresql

from xtr_orm.database import DatabaseManager, database_manager
from xtr_orm.exception import InvalidArgumentError, UnsupportedDatabaseError

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Awaitable, Callable
    from pathlib import Path

    from sqlalchemy import TextClause
    from sqlalchemy.engine import URL, Dialect

pytestmark = pytest.mark.anyio


@final
class _Answer:
    def __init__(self, found: bool) -> None:
        self._found = found

    def first(self) -> tuple[int] | None:
        return (1,) if self._found else None


@final
class _Server:
    """A server connection that records statements and knows whether the database exists."""

    def __init__(self, dialect: Dialect, *, exists: bool) -> None:
        self.dialect = dialect
        self.exists = exists
        self.sent: list[tuple[str, dict[str, object]]] = []

    async def execute(
        self, statement: TextClause, parameters: dict[str, object] | None = None
    ) -> _Answer:
        self.sent.append((str(statement), parameters or {}))
        return _Answer(self.exists)


@final
class _Engine:
    """An engine handing out ``server``, recording how it was built and whether it was disposed."""

    def __init__(self, server: _Server, url: URL, options: dict[str, object]) -> None:
        self.server = server
        self.url = url
        self.options = options
        self.disposed = False

    @asynccontextmanager
    async def connect(self) -> AsyncGenerator[_Server]:
        yield self.server

    async def dispose(self) -> None:
        self.disposed = True


def _served(server: _Server, monkeypatch: pytest.MonkeyPatch) -> list[_Engine]:
    """Have every engine the manager builds reach ``server``; return them as they are built."""
    built: list[_Engine] = []

    def create(url: URL, **options: object) -> _Engine:
        built.append(_Engine(server, url, options))
        return built[-1]

    monkeypatch.setattr(database_manager, "create_async_engine", create)
    return built


async def test_a_sqlite_database_is_its_file(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "app.sqlite"
    manager = DatabaseManager(f"sqlite+aiosqlite:///{path}")

    assert manager.backend == "sqlite"
    assert manager.database == str(path)
    assert not await manager.exists()
    assert await manager.create()
    assert path.exists()
    assert await manager.exists()
    assert await manager.drop()
    assert not path.exists()


async def test_creating_an_existing_sqlite_file_is_refused_unless_asked_to_skip(
    tmp_path: Path,
) -> None:
    manager = DatabaseManager(f"sqlite+aiosqlite:///{tmp_path / 'app.sqlite'}")
    _ = await manager.create()

    with pytest.raises(FileExistsError):
        _ = await manager.create()
    assert not await manager.create(if_not_exists=True)


async def test_dropping_a_missing_sqlite_file_is_refused_unless_asked_to_skip(
    tmp_path: Path,
) -> None:
    manager = DatabaseManager(f"sqlite+aiosqlite:///{tmp_path / 'app.sqlite'}")

    with pytest.raises(FileNotFoundError):
        _ = await manager.drop()
    assert not await manager.drop(if_exists=True)


async def test_a_sqlite_database_in_memory_always_exists() -> None:
    manager = DatabaseManager("sqlite+aiosqlite://")

    assert await manager.exists()
    assert await manager.create()
    assert await manager.drop()


async def test_a_file_url_names_its_path_without_the_query(tmp_path: Path) -> None:
    path = tmp_path / "app.sqlite"
    manager = DatabaseManager(f"sqlite+aiosqlite:///file:{path}?mode=rwc&uri=true")

    _ = await manager.create()

    assert path.exists()


@pytest.mark.parametrize(
    ("url", "dialect", "created", "exists_query", "maintenance"),
    [
        (
            "postgresql+asyncpg://app:secret@db/shop",
            postgresql.dialect(),
            "CREATE DATABASE shop",
            "pg_database",
            "postgres",
        ),
        (
            "mysql+asyncmy://app:secret@db/shop",
            mysql.dialect(),
            "CREATE DATABASE shop",
            "information_schema.schemata",
            None,
        ),
        (
            "mssql+aioodbc://app:secret@db/shop",
            mssql.dialect(),
            "CREATE DATABASE shop",
            "sys.databases",
            "master",
        ),
    ],
)
async def test_a_server_is_asked_through_its_maintenance_database(
    monkeypatch: pytest.MonkeyPatch,
    url: str,
    dialect: Dialect,
    created: str,
    exists_query: str,
    maintenance: str | None,
) -> None:
    manager = DatabaseManager(url)
    server = _Server(dialect, exists=False)
    engines = _served(server, monkeypatch)

    assert await manager.create(if_not_exists=True)
    assert not await manager.drop(if_exists=True)

    statements = [statement for statement, _ in server.sent]
    assert exists_query in statements[0]
    assert server.sent[0][1] == {"name": "shop"}
    assert statements[1] == created
    assert len(statements) == 3
    assert all(engine.disposed for engine in engines)
    assert engines[0].options["isolation_level"] == "AUTOCOMMIT"
    assert engines[0].url.database == maintenance


async def test_a_server_database_is_dropped_when_it_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = DatabaseManager("postgresql+asyncpg://app@db/Shop Data")
    server = _Server(postgresql.dialect(), exists=True)
    _ = _served(server, monkeypatch)

    assert not await manager.create(if_not_exists=True)
    assert await manager.drop()

    assert server.sent[-1][0] == 'DROP DATABASE "Shop Data"'


async def test_the_server_is_reached_with_every_connection_parameter_but_the_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = DatabaseManager(
        "postgresql+asyncpg://app:secret@db:6432/shop?ssl=require",
        connect_args={"timeout": 5},
    )
    engines = _served(_Server(postgresql.dialect(), exists=False), monkeypatch)

    _ = await manager.create()

    url = engines[0].url
    assert (url.username, url.password, url.host, url.port) == ("app", "secret", "db", 6432)
    assert url.database == "postgres"
    assert dict(url.query) == {"ssl": "require"}
    assert engines[0].options["connect_args"] == {"timeout": 5}


def test_the_url_is_shown_without_its_password() -> None:
    manager = DatabaseManager("postgresql+asyncpg://app:secret@db/shop")

    assert manager.safe_url == "postgresql+asyncpg://app:***@db/shop"


@pytest.mark.parametrize("operation", ["exists", "create", "drop"])
async def test_a_server_without_known_statements_is_refused(operation: str) -> None:
    manager = DatabaseManager("oracle+oracledb://app@db/shop")

    method = cast("Callable[[], Awaitable[object]]", getattr(manager, operation))

    with pytest.raises(UnsupportedDatabaseError) as raised:
        _ = await method()

    assert raised.value.backend == "oracle"


def test_a_server_url_without_a_database_is_refused() -> None:
    with pytest.raises(InvalidArgumentError, match="names no database"):
        _ = DatabaseManager("postgresql+asyncpg://app:secret@db")
