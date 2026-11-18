"""Unit tests for the orm's profiler wiring, ``xtr_orm.bundle._profiler``."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest
from advanced_alchemy.config import SQLAlchemyAsyncConfig
from advanced_alchemy.config.routing import EngineConfig, RoutingConfig
from sqlalchemy import text

from tests.support.profiling import profiled
from xtr_orm.bundle._profiler import _listened_alchemy, _orm_collector, _query_listener

if TYPE_CHECKING:
    from pathlib import Path

    from advanced_alchemy.routing import RoutingAsyncSessionMaker
    from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = pytest.mark.anyio


async def _select(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        _ = await connection.execute(text("select 1"))


async def test_the_primary_engine_of_a_connection_is_listened_to(tmp_path: Path) -> None:
    alchemy = SQLAlchemyAsyncConfig(connection_string=f"sqlite+aiosqlite:///{tmp_path / 'a.db'}")
    listener = _query_listener()

    decorated = _listened_alchemy("reports")(alchemy, listener)
    listener.trace.begin()
    await _select(decorated.get_engine())
    await decorated.get_engine().dispose()

    assert decorated is alchemy
    assert [query.connection for query in listener.trace.entries()] == ["reports"]


async def test_the_replica_engines_of_a_connection_are_listened_to(tmp_path: Path) -> None:
    alchemy = SQLAlchemyAsyncConfig(
        routing_config=RoutingConfig(
            primary_connection_string=f"sqlite+aiosqlite:///{tmp_path / 'primary.db'}",
            read_replicas=[
                EngineConfig(connection_string=f"sqlite+aiosqlite:///{tmp_path / 'replica.db'}")
            ],
        )
    )
    maker = cast("RoutingAsyncSessionMaker", alchemy.create_session_maker())
    alchemy.engine_instance = maker.primary_engine
    listener = _query_listener()

    _ = _listened_alchemy("main")(alchemy, listener)
    listener.trace.begin()
    for engine in (maker.primary_engine, *maker.replica_engines):
        await _select(engine)
    await maker.close_all()

    assert [query.connection for query in listener.trace.entries()] == ["main", "main"]


def test_the_collector_names_every_configured_connection() -> None:
    collector = _orm_collector(("default", "reports"))(_query_listener())

    assert collector.collect(profiled())["connections"] == ["default", "reports"]
