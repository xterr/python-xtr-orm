"""The ``orm://`` transport on a kernel listing only the orm and messenger bundles."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from xtr_dependency_injection import Kernel, qualified_name
from xtr_messenger import MessageBusInterface, TransportFactoryInterface, WorkerFactory
from xtr_orm_messenger import OrmTransportFactory

import xtr_orm.bundle.orm_bundle as orm_bundle_module
from tests.fixtures.app_orm_transport.handlers import Ledger
from tests.fixtures.app_orm_transport.messages import QueuedOrder
from xtr_orm import Migrator

if TYPE_CHECKING:
    from xtr_service_contracts import ContainerInterface

pytestmark = pytest.mark.anyio

_APP = "tests.fixtures.app_orm_transport"


def _kernel(root: Path) -> Kernel:
    root.mkdir(parents=True, exist_ok=True)
    return Kernel(
        _APP,
        env="test",
        environ={
            "ORM_TEST_URL": f"sqlite+aiosqlite:///{root / 'app.sqlite'}",
            "ORM_TEST_MIGRATIONS": str(root / "migrations"),
            "ORM_TEST_REPORTS_URL": f"sqlite+aiosqlite:///{root / 'reports.sqlite'}",
            "ORM_TEST_REPORTS_MIGRATIONS": str(root / "reports_migrations"),
        },
    )


async def _drain(container: ContainerInterface, expected: int) -> list[str]:
    """Run a worker on ``orders`` until it handled ``expected`` orders, then stop it."""
    ledger = await container.get(Ledger)
    worker = (await container.get(WorkerFactory)).worker(["orders"])
    running = asyncio.ensure_future(worker.run())
    try:
        async with asyncio.timeout(5):
            while len(ledger.orders) < expected:
                _ = await ledger.recorded.wait()
                ledger.recorded.clear()
    finally:
        worker.stop()
        await running
    return ledger.orders


async def _revision(container: ContainerInterface, connection: str) -> str:
    """Return the revision the connection's migrator writes, which must write one."""
    written = await (await container.get(Migrator, connection)).diff("messages")
    assert written is not None
    return Path(written.path).read_text(encoding="utf-8")


async def test_a_queued_message_is_handled_by_a_worker_and_leaves_the_table(
    tmp_path: Path,
) -> None:
    async with await _kernel(tmp_path).boot() as booted:
        container = booted.container
        bus = await container.get(MessageBusInterface)
        _ = await bus.dispatch(QueuedOrder("o-1"))
        _ = await bus.dispatch(QueuedOrder("o-2"))
        assert (await container.get(Ledger)).orders == []

        handled = await _drain(container, 2)

    assert handled == ["o-1", "o-2"]


async def test_each_connection_migrates_the_messages_tables_of_its_own_transports(
    tmp_path: Path,
) -> None:
    async with await _kernel(tmp_path).boot() as booted:
        default = await _revision(booted.container, "default")
        reports = await _revision(booted.container, "reports")

    assert "op.create_table('messenger_messages'" in default
    assert "messenger_messages_queue_name_idx" in default
    assert "report_messages" not in default
    assert "op.create_table('report_messages'" in reports
    assert "messenger_messages" not in reports


async def test_without_the_transport_installed_its_factory_is_not_registered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def nowhere(name: str) -> None:
        del name

    monkeypatch.setattr(orm_bundle_module, "find_spec", nowhere)

    async with await _kernel(tmp_path).boot() as booted:
        registered = booted.container.has(
            TransportFactoryInterface, qualified_name(OrmTransportFactory)
        )

    assert not registered
