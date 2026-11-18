from __future__ import annotations

import json
from typing import cast

import anyio
import pytest
from anyio.lowlevel import checkpoint
from xtr_http_kernel.data_collector import (
    LateDataCollectorInterface,
    TracingDataCollectorInterface,
)

from tests.support.profiling import profiled
from xtr_orm.data_collector import OrmDataCollector, QueryListener, RecordedQuery

pytestmark = pytest.mark.anyio


def _query(statement: str, duration_ms: float = 1.0, error: str | None = None) -> RecordedQuery:
    return RecordedQuery(
        connection="default",
        statement=statement,
        parameters={},
        executemany=False,
        duration_ms=duration_ms,
        row_count=None,
        error=error,
    )


def _collector() -> tuple[OrmDataCollector, QueryListener]:
    listener = QueryListener()
    return OrmDataCollector(listener, ["default", "reports"]), listener


def test_the_collector_is_named_orm_and_traces_late() -> None:
    collector, _ = _collector()

    assert collector.name == "orm"
    assert isinstance(collector, TracingDataCollectorInterface)
    assert isinstance(collector, LateDataCollectorInterface)


def test_before_a_request_begins_nothing_is_collected() -> None:
    collector, _ = _collector()

    assert collector.collect(profiled()) == {
        "queries": [],
        "count": 0,
        "duration_ms": 0,
        "connections": ["default", "reports"],
        "repeated": [],
        "errors": 0,
    }


def test_every_statement_is_collected_with_the_totals() -> None:
    collector, listener = _collector()
    collector.begin_request()
    for query in (
        _query("select 1", 1.5),
        _query("select 2", 2.0),
        _query("select 2", 0.5),
        _query("select 3", 1.0, "OperationalError: locked"),
        _query("select 1", 1.0),
        _query("select 2", 1.0),
    ):
        listener.trace.record(query)

    data = collector.late_collect({}, profiled())

    queries = cast("list[dict[str, object]]", data["queries"])
    assert [query["statement"] for query in queries] == [
        "select 1",
        "select 2",
        "select 2",
        "select 3",
        "select 1",
        "select 2",
    ]
    assert data["count"] == 6
    assert data["duration_ms"] == pytest.approx(7.0)
    assert data["errors"] == 1
    assert data["repeated"] == [
        {"statement": "select 2", "count": 3},
        {"statement": "select 1", "count": 2},
    ]


def test_beginning_a_request_forgets_the_previous_one() -> None:
    collector, listener = _collector()
    collector.begin_request()
    listener.trace.record(_query("select 1"))

    collector.begin_request()

    assert collector.collect(profiled())["count"] == 0


def test_what_is_collected_is_json_safe() -> None:
    collector, listener = _collector()
    collector.begin_request()
    listener.trace.record(_query("select 1"))

    data = collector.collect(profiled())

    assert json.loads(json.dumps(data)) == data


async def test_concurrent_requests_each_collect_only_their_own_statements() -> None:
    collector, listener = _collector()
    collected: dict[str, object] = {}

    async def request(statement: str) -> None:
        collector.begin_request()
        listener.trace.record(_query(statement))
        await checkpoint()
        collected[statement] = collector.collect(profiled())["count"]

    async with anyio.create_task_group() as group:
        _ = group.start_soon(request, "select 1")
        _ = group.start_soon(request, "select 2")

    assert collected == {"select 1": 1, "select 2": 1}
