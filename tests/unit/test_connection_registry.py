"""Unit tests for :class:`xtr_orm.ConnectionRegistry`."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from xtr_orm import (
    ConnectionRegistry,
    DatabaseManager,
    InvalidArgumentError,
    Migrator,
    SessionUnavailableError,
    UnknownConnectionError,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = pytest.mark.anyio


async def test_it_hands_back_what_it_was_given(engine: AsyncEngine, migrator: Migrator) -> None:
    database = DatabaseManager("sqlite+aiosqlite://")
    registry = ConnectionRegistry()
    registry.register("default", engine=engine, migrator=migrator, database=database)

    assert await registry.engine() is engine
    assert await registry.migrator("default") is migrator
    assert await registry.database() is database


async def test_it_builds_each_piece_only_when_asked(
    engine: AsyncEngine, migrator: Migrator
) -> None:
    asked: list[str] = []

    async def build_engine() -> AsyncEngine:
        asked.append("engine")
        return engine

    async def build_migrator() -> Migrator:
        asked.append("migrator")
        return migrator

    async def build_database() -> DatabaseManager:
        asked.append("database")
        return DatabaseManager("sqlite+aiosqlite://")

    registry = ConnectionRegistry("main")
    registry.register("main", engine=build_engine, migrator=build_migrator, database=build_database)

    assert asked == []
    assert await registry.migrator() is migrator
    assert asked == ["migrator"]


async def test_it_names_its_connections_in_the_order_registered(
    engine: AsyncEngine, migrator: Migrator
) -> None:
    database = DatabaseManager("sqlite+aiosqlite://")
    registry = ConnectionRegistry("reports")
    for name in ("reports", "main"):
        registry.register(name, engine=engine, migrator=migrator, database=database)

    assert registry.names() == ("reports", "main")
    assert registry.default == "reports"
    assert registry.has()
    assert registry.has("main")
    assert not registry.has("other")


async def test_it_names_the_connections_in_use_every_one_without_a_way_to_tell(
    engine: AsyncEngine, migrator: Migrator
) -> None:
    database = DatabaseManager("sqlite+aiosqlite://")
    registry = ConnectionRegistry()
    registry.register("main", engine=engine, migrator=migrator, database=database)
    registry.register(
        "idle", engine=engine, migrator=migrator, database=database, in_use=lambda: False
    )
    registry.register(
        "busy", engine=engine, migrator=migrator, database=database, in_use=lambda: True
    )

    assert registry.in_use() == ("main", "busy")


async def test_an_unknown_connection_is_refused_naming_the_known_ones(
    engine: AsyncEngine, migrator: Migrator
) -> None:
    registry = ConnectionRegistry()
    database = DatabaseManager("sqlite+aiosqlite://")
    registry.register("default", engine=engine, migrator=migrator, database=database)

    with pytest.raises(UnknownConnectionError) as raised:
        _ = await registry.engine("other")

    assert raised.value.known == ("default",)


async def test_a_connection_needs_a_name(engine: AsyncEngine, migrator: Migrator) -> None:
    database = DatabaseManager("sqlite+aiosqlite://")

    with pytest.raises(InvalidArgumentError, match="non-empty name"):
        ConnectionRegistry().register("", engine=engine, migrator=migrator, database=database)


async def test_the_session_comes_from_what_the_connection_was_registered_with(
    engine: AsyncEngine, migrator: Migrator
) -> None:
    session = AsyncSession(engine)

    async def current() -> AsyncSession:
        return session

    registry = ConnectionRegistry()
    registry.register(
        "default",
        engine=engine,
        migrator=migrator,
        database=DatabaseManager("sqlite+aiosqlite://"),
        session=current,
    )

    assert await registry.session() is session
    await session.close()


async def test_a_connection_registered_without_a_session_refuses_one(
    engine: AsyncEngine, migrator: Migrator
) -> None:
    registry = ConnectionRegistry()
    registry.register(
        "default", engine=engine, migrator=migrator, database=DatabaseManager("sqlite+aiosqlite://")
    )

    with pytest.raises(SessionUnavailableError) as raised:
        _ = await registry.session()

    assert raised.value.connection == "default"


async def test_closing_disposes_the_engine_unless_told_otherwise(
    engine: AsyncEngine, migrator: Migrator
) -> None:
    closed: list[str] = []

    async def close() -> None:
        closed.append("custom")

    registry = ConnectionRegistry()
    database = DatabaseManager("sqlite+aiosqlite://")
    registry.register("default", engine=engine, migrator=migrator, database=database)
    registry.register("other", engine=engine, migrator=migrator, database=database, close=close)
    async with engine.connect() as connection:
        _ = await connection.execute(text("select 1"))
    pool = engine.pool

    await registry.close()
    await registry.close("other")

    assert engine.pool is not pool
    assert closed == ["custom"]
