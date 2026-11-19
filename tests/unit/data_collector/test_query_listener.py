from __future__ import annotations

import asyncio
import threading
from typing import TYPE_CHECKING, Self, cast, final

import anyio
import pytest
from anyio.lowlevel import checkpoint
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import create_async_engine
from xtr_clock import MockClock

from xtr_orm.data_collector import QueryListener

if TYPE_CHECKING:
    from datetime import tzinfo
    from pathlib import Path

    from sqlalchemy.ext.asyncio import AsyncEngine
    from xtr_clock import DatePoint

pytestmark = pytest.mark.anyio


@final
class _SteppingClock:
    """A frozen clock moving 2.5 ms on each reading, so every statement lasts exactly that."""

    __slots__ = ("_clock",)

    def __init__(self) -> None:
        self._clock = MockClock("2026-01-01 00:00:00")

    def now(self) -> DatePoint:
        reading = self._clock.now()
        self._clock.sleep(0.0025)
        return reading

    def sleep(self, seconds: float) -> None:
        self._clock.sleep(seconds)

    async def sleep_async(self, seconds: float) -> None:
        await self._clock.sleep_async(seconds)

    def with_timezone(self, timezone: str | tzinfo) -> Self:
        del timezone
        return self


@pytest.fixture
def listener(engine: AsyncEngine) -> QueryListener:
    listening = QueryListener(_SteppingClock())
    listening.listen(engine, "default")
    return listening


async def test_a_statement_is_recorded_with_its_connection_parameters_and_duration(
    engine: AsyncEngine, listener: QueryListener
) -> None:
    listener.trace.begin()

    async with engine.connect() as connection:
        _ = await connection.execute(text("select :answer"), {"answer": 42})

    (query,) = listener.trace.entries()
    assert query.connection == "default"
    assert query.statement == "select ?"
    assert query.parameters["kind"] == "mapping"
    assert query.parameters["items"] == [
        [
            {"kind": "str", "type": "str", "value": "answer", "truncated": 0},
            {"kind": "scalar", "type": "int", "value": 42},
        ]
    ]
    assert query.executemany is False
    assert query.duration_ms == pytest.approx(2.5)
    assert query.error is None


async def test_a_read_reports_no_row_count(engine: AsyncEngine, listener: QueryListener) -> None:
    listener.trace.begin()

    async with engine.connect() as connection:
        _ = await connection.execute(text("select 1"))

    assert listener.trace.entries()[0].row_count is None


async def test_a_credential_named_parameter_is_masked(
    engine: AsyncEngine, listener: QueryListener
) -> None:
    listener.trace.begin()

    async with engine.connect() as connection:
        _ = await connection.execute(text("select :user_password"), {"user_password": "hunter2"})

    items = listener.trace.entries()[0].parameters["items"]
    assert items == [
        [
            {"kind": "str", "type": "str", "value": "user_password", "truncated": 0},
            {"kind": "str", "type": "str", "value": "******", "truncated": 0},
        ]
    ]


async def test_a_statement_run_per_row_is_recorded_once_with_every_row(
    engine: AsyncEngine, listener: QueryListener
) -> None:
    async with engine.connect() as connection:
        _ = await connection.execute(text("create table book (title text)"))
        listener.trace.begin()
        _ = await connection.execute(
            text("insert into book values (:title)"), [{"title": "Dune"}, {"title": "Emma"}]
        )

    (query,) = listener.trace.entries()
    assert query.executemany is True
    assert query.row_count == 2
    rows = cast("list[dict[str, object]]", query.parameters["items"])
    assert query.parameters["kind"] == "sequence"
    assert [row["kind"] for row in rows] == ["mapping", "mapping"]


async def test_a_statement_sent_as_is_keeps_its_positional_parameters(
    engine: AsyncEngine, listener: QueryListener
) -> None:
    listener.trace.begin()

    async with engine.connect() as connection:
        _ = await connection.exec_driver_sql("select ?", ("hunter2",))

    query = listener.trace.entries()[0]
    assert query.statement == "select ?"
    assert query.parameters["kind"] == "sequence"
    assert query.parameters["type"] == "tuple"


async def test_a_failing_statement_is_recorded_with_its_error(
    engine: AsyncEngine, listener: QueryListener
) -> None:
    listener.trace.begin()

    async with engine.connect() as connection:
        with pytest.raises(OperationalError):
            _ = await connection.execute(text("select * from missing"))

    (query,) = listener.trace.entries()
    assert query.statement == "select * from missing"
    assert query.error == "OperationalError: no such table: missing"
    assert query.row_count is None
    assert query.duration_ms == pytest.approx(2.5)


async def test_nothing_is_recorded_outside_a_profiled_request(
    engine: AsyncEngine, listener: QueryListener
) -> None:
    async with engine.connect() as connection:
        _ = await connection.execute(text("select 1"))
        with pytest.raises(OperationalError):
            _ = await connection.execute(text("select * from missing"))

    assert listener.trace.entries() == ()


async def test_a_failure_to_connect_records_no_statement(tmp_path: Path) -> None:
    unreachable = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'absent' / 'app.sqlite'}")
    listener = QueryListener()
    listener.listen(unreachable, "default")
    listener.trace.begin()
    started = set(threading.enumerate())

    with pytest.raises(OperationalError):
        async with unreachable.connect():
            pass
    await unreachable.dispose()
    # aiosqlite stops the worker thread of a connection that failed to open without
    # waiting for it; finishing after this test's event loop closed, the thread would
    # raise in a later test. Waited for here, it answers a loop still running.
    for thread in set(threading.enumerate()) - started:
        await asyncio.to_thread(thread.join, 5)

    assert listener.trace.entries() == ()


async def test_concurrent_requests_each_see_only_their_own_statements(
    engine: AsyncEngine, listener: QueryListener
) -> None:
    seen: dict[str, list[str]] = {}

    async def request(name: str) -> None:
        listener.trace.begin()
        async with engine.connect() as connection:
            _ = await connection.execute(text(f"select '{name}'"))
            await checkpoint()
            _ = await connection.execute(text(f"select '{name}' as again"))
        seen[name] = [query.statement for query in listener.trace.entries()]

    async with anyio.create_task_group() as group:
        _ = group.start_soon(request, "first")
        _ = group.start_soon(request, "second")

    assert seen == {
        "first": ["select 'first'", "select 'first' as again"],
        "second": ["select 'second'", "select 'second' as again"],
    }
