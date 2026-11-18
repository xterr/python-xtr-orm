"""The orm panel, registered by a real kernel when the http kernel profiles requests."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from typing import TYPE_CHECKING, Annotated, cast

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002 — read at runtime by the container
from xtr_dependency_injection import Kernel, Target, bind_callable
from xtr_http_kernel.bundle import HttpKernelBundle
from xtr_http_kernel.profiler import Profiler

from tests.support.profiling import profiled
from xtr_orm.bundle import OrmBundle
from xtr_orm.data_collector import OrmDataCollector

if TYPE_CHECKING:
    from pathlib import Path

    from xtr_dependency_injection.bundle.bundle import AnyBundle

pytestmark = pytest.mark.anyio

_APPLICATION = "tests.fixtures.app_orm_named"
_PROFILER_ON = "tests.fixtures.profiler_on"


@pytest.fixture(autouse=True)
def _profiles(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROFILER_TEST_FOLDER", str(tmp_path / "profiles"))


def _kernel(tmp_path: Path, *resources: str) -> Kernel:
    """A kernel on a primary and a replica, each holding a table naming the database it is."""
    for name in ("primary", "replica"):
        with closing(sqlite3.connect(tmp_path / f"{name}.sqlite")) as database:
            _ = database.execute("create table location (name text)")
            _ = database.execute("insert into location values (?)", (name,))
            database.commit()
    bundles: dict[type[AnyBundle], dict[str, bool]] = {
        OrmBundle: {"all": True},
        HttpKernelBundle: {"all": True},
    }
    return Kernel(
        _APPLICATION,
        env="test",
        bundles=bundles,
        resources=(_APPLICATION, *resources),
        environ={
            "ORM_TEST_URL": f"sqlite+aiosqlite:///{tmp_path / 'primary.sqlite'}",
            "ORM_TEST_REPLICA_URL": f"sqlite+aiosqlite:///{tmp_path / 'replica.sqlite'}",
        },
    )


async def _unit(session: Annotated[AsyncSession, Target("main")]) -> None:
    _ = await session.execute(text("select name from location where name = :name"), {"name": "x"})
    _ = await session.execute(
        text("insert into location values (:password)"), {"password": "hunter2"}
    )
    _ = await session.execute(text("select name from location where name = :name"), {"name": "y"})
    with pytest.raises(Exception, match="no such table"):
        _ = await session.execute(text("select * from missing"))


async def test_with_the_profiler_on_the_orm_collector_is_registered(tmp_path: Path) -> None:
    async with await _kernel(tmp_path, _PROFILER_ON).boot() as booted:
        profiler = await booted.container.get(Profiler)

        assert profiler.has("orm")


async def test_a_profiled_request_records_every_statement_it_runs(tmp_path: Path) -> None:
    async with await _kernel(tmp_path, _PROFILER_ON).boot() as booted:
        collector = await booted.container.get(OrmDataCollector)
        collector.begin_request()

        _ = await bind_callable(booted.container, _unit, per_call_scope=True)()
        data = collector.late_collect(collector.collect(profiled()), profiled())

    queries = cast("list[dict[str, object]]", data["queries"])
    assert [query["statement"] for query in queries] == [
        "select name from location where name = ?",
        "insert into location values (?)",
        "select name from location where name = ?",
        "select * from missing",
    ]
    assert {query["connection"] for query in queries} == {"main"}
    assert queries[1]["parameters"] == {
        "kind": "mapping",
        "type": "dict",
        "items": [
            [
                {"kind": "str", "type": "str", "value": "password", "truncated": 0},
                {"kind": "str", "type": "str", "value": "******", "truncated": 0},
            ]
        ],
        "truncated": 0,
    }
    assert queries[1]["row_count"] == 1
    assert str(queries[3]["error"]).startswith("OperationalError: no such table")
    assert data["count"] == 4
    assert data["errors"] == 1
    assert data["connections"] == ["main", "kept"]
    assert data["repeated"] == [
        {"statement": "select name from location where name = ?", "count": 2}
    ]


async def test_reads_sent_to_a_replica_are_recorded_too(tmp_path: Path) -> None:
    async def read(session: Annotated[AsyncSession, Target("main")]) -> str:
        return cast("str", (await session.execute(text("select name from location"))).scalar())

    async with await _kernel(tmp_path, _PROFILER_ON).boot() as booted:
        collector = await booted.container.get(OrmDataCollector)
        collector.begin_request()

        where = await bind_callable(booted.container, read, per_call_scope=True)()
        data = collector.late_collect({}, profiled())

    assert where == "replica"
    assert data["count"] == 1


async def test_with_the_profiler_off_the_orm_collector_is_not_registered(tmp_path: Path) -> None:
    async with await _kernel(tmp_path).boot() as booted:
        assert not booted.container.has(OrmDataCollector)
