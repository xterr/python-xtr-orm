"""Message handlers writing through the orm, on a kernel running both bundles, wired by nothing.

Every handler asks for ``Injected[AsyncSession]``; the bus lists ``orm_close_connection``,
``orm_transaction`` and ``orm_open_transaction_logger``. Messages are handled in process, or
queued on ``in-memory://`` and handled by a worker.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from xtr_dependency_injection import Injected, Kernel, bind_callable
from xtr_logging import TestHandler
from xtr_logging.handler.handler_interface import HandlerInterface
from xtr_logging_contracts import Level
from xtr_messenger import (
    Envelope,
    HandledStamp,
    HandlersFailedError,
    MessageBusInterface,
    MiddlewareInterface,
    WorkerFactory,
)

from tests.fixtures.app_orm_messenger.messages import QueuedNote, WriteNote
from tests.fixtures.app_orm_messenger.services import Sessions
from tests.support.database import rows
from tests.support.schema import METADATA
from xtr_orm.messenger import (
    CloseConnectionMiddleware,
    OpenTransactionLoggerMiddleware,
    TransactionMiddleware,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

    from xtr_dependency_injection import BootedKernel

pytestmark = pytest.mark.anyio

NAMES = "select name from author order by name"


@pytest.fixture
async def booted(tmp_path: Path, engine: AsyncEngine) -> AsyncIterator[BootedKernel]:
    async with engine.begin() as connection:
        await connection.run_sync(METADATA.create_all)
    kernel = Kernel(
        "tests.fixtures.app_orm_messenger",
        env="test",
        environ={
            "ORM_TEST_URL": f"sqlite+aiosqlite:///{tmp_path / 'app.sqlite'}",
            "ORM_TEST_MIGRATIONS": str(tmp_path / "migrations"),
        },
    )
    async with await kernel.boot() as started:
        yield started


async def _names(engine: AsyncEngine) -> list[object]:
    return [row[0] for row in await rows(engine, NAMES)]


async def test_the_middleware_are_registered_by_name(booted: BootedKernel) -> None:
    container = booted.container

    transaction = await container.get(MiddlewareInterface, "orm_transaction")
    close = await container.get(MiddlewareInterface, "orm_close_connection")
    logger = await container.get(MiddlewareInterface, "orm_open_transaction_logger")

    assert isinstance(transaction, TransactionMiddleware)
    assert isinstance(close, CloseConnectionMiddleware)
    assert isinstance(logger, OpenTransactionLoggerMiddleware)


async def test_every_handler_of_a_message_shares_one_session_and_commits_together(
    booted: BootedKernel, engine: AsyncEngine
) -> None:
    bus = await booted.container.get(MessageBusInterface)
    sessions = await booted.container.get(Sessions)

    _ = await bus.dispatch(Envelope(WriteNote("a")))
    _ = await bus.dispatch(Envelope(WriteNote("b")))

    assert await _names(engine) == [
        "first:a",
        "first:b",
        "second:a",
        "second:b",
        "third:a",
        "third:b",
    ]
    seen = sessions.seen
    assert seen["first:a"] is seen["second:a"] is seen["third:a"]
    assert seen["first:a"] is not seen["first:b"]


async def test_a_message_dispatched_by_a_command_shares_the_command_s_session(
    booted: BootedKernel, engine: AsyncEngine
) -> None:
    sessions = await booted.container.get(Sessions)
    given: list[AsyncSession] = []

    async def command(session: Injected[AsyncSession], bus: Injected[MessageBusInterface]) -> None:
        given.append(session)
        _ = await bus.dispatch(Envelope(WriteNote("c")))

    _ = await bind_callable(booted.container, command, per_call_scope=True)()

    assert sessions.seen["first:c"] is given[0]
    assert await _names(engine) == ["first:c", "second:c", "third:c"]


async def test_a_worker_run_by_a_command_gives_each_message_a_session_of_its_own(
    booted: BootedKernel, engine: AsyncEngine
) -> None:
    bus = await booted.container.get(MessageBusInterface)
    sessions = await booted.container.get(Sessions)
    given: list[AsyncSession] = []

    async def consume(session: Injected[AsyncSession], workers: Injected[WorkerFactory]) -> None:
        given.append(session)
        await workers.worker(["jobs"]).run()

    _ = await bus.dispatch(Envelope(QueuedNote("h")))
    _ = await bus.dispatch(Envelope(QueuedNote("i")))
    _ = await bind_callable(booted.container, consume, per_call_scope=True)()

    first, second = sessions.seen["queued:h"], sessions.seen["queued:i"]
    assert first is not second
    assert given[0] is not first
    assert given[0] is not second
    assert await _names(engine) == ["queued:h", "queued:i"]


async def test_one_failing_handler_rolls_back_every_handler(
    booted: BootedKernel, engine: AsyncEngine
) -> None:
    bus = await booted.container.get(MessageBusInterface)

    with pytest.raises(HandlersFailedError) as raised:
        _ = await bus.dispatch(Envelope(WriteNote("b", fail=True)))

    assert await _names(engine) == []
    assert set(raised.value.errors) == {"third"}
    assert raised.value.envelope.all(HandledStamp) == ()


async def test_a_message_dispatched_while_another_is_handled_shares_its_transaction(
    booted: BootedKernel, engine: AsyncEngine
) -> None:
    bus = await booted.container.get(MessageBusInterface)
    sessions = await booted.container.get(Sessions)

    _ = await bus.dispatch(Envelope(WriteNote("c", nested=True)))

    assert "nested:c" in await _names(engine)
    assert sessions.seen["nested:c"] is sessions.seen["first:c"]


async def test_a_nested_message_failing_rolls_back_the_message_that_dispatched_it(
    booted: BootedKernel, engine: AsyncEngine
) -> None:
    bus = await booted.container.get(MessageBusInterface)

    with pytest.raises(HandlersFailedError):
        _ = await bus.dispatch(Envelope(WriteNote("d", nested=True, fail=True)))

    assert await _names(engine) == []


async def test_a_nested_message_failing_is_rolled_back_alone_when_its_failure_is_caught(
    booted: BootedKernel, engine: AsyncEngine
) -> None:
    bus = await booted.container.get(MessageBusInterface)

    _ = await bus.dispatch(Envelope(WriteNote("i", nested=True, fail=True, catch_nested=True)))

    assert await _names(engine) == ["first:i", "second:i", "third:i"]


async def test_a_message_held_back_until_the_current_one_runs_after_its_commit(
    booted: BootedKernel, engine: AsyncEngine
) -> None:
    bus = await booted.container.get(MessageBusInterface)
    sessions = await booted.container.get(Sessions)

    _ = await bus.dispatch(Envelope(WriteNote("j", nested=True, after=True)))

    assert await _names(engine) == ["first:j", "nested:j", "second:j", "third:j"]
    assert sessions.seen["nested:j"] is not sessions.seen["first:j"]


async def test_a_message_held_back_is_never_dispatched_when_the_current_one_rolls_back(
    booted: BootedKernel, engine: AsyncEngine
) -> None:
    bus = await booted.container.get(MessageBusInterface)
    sessions = await booted.container.get(Sessions)

    with pytest.raises(HandlersFailedError):
        _ = await bus.dispatch(Envelope(WriteNote("k", nested=True, after=True, refuse=True)))

    assert await _names(engine) == []
    assert "nested:k" not in sessions.seen


async def test_a_queued_message_is_written_when_a_worker_handles_it(
    booted: BootedKernel, engine: AsyncEngine
) -> None:
    bus = await booted.container.get(MessageBusInterface)
    workers = await booted.container.get(WorkerFactory)
    orm_engine = await booted.container.get(AsyncEngine)

    _ = await bus.dispatch(Envelope(QueuedNote("e")))
    assert await _names(engine) == []

    pool = orm_engine.pool
    await workers.worker(["jobs"]).run()

    assert await _names(engine) == ["queued:e"]
    assert orm_engine.pool is not pool  # closed after the message the worker consumed


async def test_a_queued_message_whose_handler_fails_is_rejected_with_nothing_written(
    booted: BootedKernel, engine: AsyncEngine
) -> None:
    bus = await booted.container.get(MessageBusInterface)
    workers = await booted.container.get(WorkerFactory)

    _ = await bus.dispatch(Envelope(QueuedNote("f", fail=True)))
    _ = await bus.dispatch(Envelope(QueuedNote("g")))
    await workers.worker(["jobs"]).run()

    assert await _names(engine) == ["queued:g"]


async def test_a_transaction_a_handler_left_open_is_logged(
    booted: BootedKernel, engine: AsyncEngine
) -> None:
    bus = await booted.container.get(MessageBusInterface)
    handler = await booted.container.get(HandlerInterface, "main")
    assert isinstance(handler, TestHandler)

    _ = await bus.dispatch(Envelope(WriteNote("h", leave_open=True)))

    [record] = [each for each in handler.records if each.level is Level.ERROR]
    assert record.message == "A handler opened a transaction but did not close it."
    assert record.context["connections"] == ["default"]
    assert "third:h" in await _names(engine)
