"""Unit tests for :class:`xtr_orm.messenger.TransactionMiddleware`."""

from __future__ import annotations

import asyncio
import contextvars
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, insert, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from xtr_messenger import Envelope, HandledStamp, HandlersFailedError, ReceivedStamp

from tests.support.database import rows
from tests.support.sessions import Sessions
from tests.support.stack import Then
from xtr_orm import ConnectionRegistry, DatabaseManager
from xtr_orm.messenger import TransactionMiddleware, in_begun_transaction, transaction_middleware

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncEngine

    from xtr_orm import Migrator

pytestmark = pytest.mark.anyio

NOTE = Table("note", MetaData(), Column("id", Integer, primary_key=True), Column("text", String))


@pytest.fixture
async def sessions(engine: AsyncEngine, migrator: Migrator) -> AsyncIterator[Sessions]:
    async with engine.begin() as connection:
        await connection.run_sync(NOTE.metadata.create_all)
    built = Sessions(engine, migrator, "default", "reports")
    yield built
    await built.aclose()


def _writing(sessions: Sessions, text: str, *, then: Exception | None = None) -> Then:
    async def handle(envelope: Envelope) -> Envelope:
        _ = await sessions.by_name["default"].execute(insert(NOTE).values(text=text))
        if then is not None:
            raise then
        return envelope.with_stamps(HandledStamp("handler", None))

    return Then(handle)


async def test_what_the_handlers_did_is_committed_once_they_all_succeeded(
    sessions: Sessions, engine: AsyncEngine
) -> None:
    middleware = TransactionMiddleware(sessions.registry)

    _ = await middleware.handle(Envelope("message"), _writing(sessions, "kept"))

    assert await rows(engine, "select text from note") == [("kept",)]
    assert not sessions.by_name["default"].in_transaction()


async def test_a_failing_handler_rolls_back_every_handler_s_work(
    sessions: Sessions, engine: AsyncEngine
) -> None:
    middleware = TransactionMiddleware(sessions.registry)

    with pytest.raises(LookupError):
        _ = await middleware.handle(
            Envelope("message"), _writing(sessions, "lost", then=LookupError())
        )

    assert await rows(engine, "select text from note") == []
    assert not sessions.by_name["default"].in_transaction()


async def test_handlers_that_failed_leave_nothing_handled_so_a_retry_runs_them_all(
    sessions: Sessions, engine: AsyncEngine
) -> None:
    failed = HandlersFailedError(
        Envelope("message", (HandledStamp("first", None),)), {"second": LookupError()}
    )
    middleware = TransactionMiddleware(sessions.registry)

    with pytest.raises(HandlersFailedError) as raised:
        _ = await middleware.handle(Envelope("message"), _writing(sessions, "lost", then=failed))

    assert raised.value.envelope.all(HandledStamp) == ()
    assert set(raised.value.errors) == {"second"}
    assert raised.value.__cause__ is failed
    assert await rows(engine, "select text from note") == []


async def test_a_message_dispatched_during_another_runs_in_its_transaction(
    sessions: Sessions, engine: AsyncEngine
) -> None:
    middleware = TransactionMiddleware(sessions.registry)
    session = sessions.by_name["default"]
    inside: list[bool] = []

    async def outer(envelope: Envelope) -> Envelope:
        _ = await middleware.handle(Envelope("nested"), _writing(sessions, "nested"))
        inside.append(session.in_transaction())
        return envelope

    _ = await middleware.handle(Envelope("message"), Then(outer))

    assert inside == [True]
    assert await rows(engine, "select text from note") == [("nested",)]


async def test_a_transaction_runs_on_the_connection_it_is_given(sessions: Sessions) -> None:
    middleware = TransactionMiddleware(sessions.registry, connection_name="reports")
    reports = sessions.by_name["reports"]
    seen: list[bool] = []

    async def handle(envelope: Envelope) -> Envelope:
        seen.append(reports.in_transaction())
        _ = await reports.execute(select(1))
        return envelope

    _ = await middleware.handle(Envelope("message"), Then(handle))

    assert seen == [True]
    assert not reports.in_transaction()
    assert not sessions.by_name["default"].in_transaction()


async def test_a_session_counts_as_begun_only_while_its_transaction_runs(
    sessions: Sessions,
) -> None:
    middleware = TransactionMiddleware(sessions.registry)
    session = sessions.by_name["default"]
    seen: list[bool] = []

    async def handle(envelope: Envelope) -> Envelope:
        seen.append(in_begun_transaction(session))
        return envelope

    _ = await middleware.handle(Envelope("message"), Then(handle))

    assert seen == [True]
    assert not in_begun_transaction(session)


async def test_a_task_outliving_the_transaction_does_not_see_it(
    sessions: Sessions, engine: AsyncEngine
) -> None:
    middleware = TransactionMiddleware(sessions.registry)
    gate = asyncio.Event()
    outliving: list[asyncio.Task[Envelope]] = []

    async def later_on() -> Envelope:
        _ = await gate.wait()
        return await middleware.handle(Envelope("later"), _writing(sessions, "later"))

    async def spawn(envelope: Envelope) -> Envelope:
        outliving.append(asyncio.create_task(later_on()))
        return envelope

    _ = await middleware.handle(Envelope("message"), Then(spawn))
    gate.set()
    _ = await outliving[0]

    # Its own transaction, committed: not a savepoint of one long over.
    assert await rows(engine, "select text from note") == [("later",)]
    assert not sessions.by_name["default"].in_transaction()


async def test_a_new_session_reusing_a_freed_sessions_id_is_not_taken_for_begun(
    engine: AsyncEngine, migrator: Migrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(NOTE.metadata.create_all)
    handed: list[AsyncSession] = [AsyncSession(engine)]

    async def session() -> AsyncSession:
        return handed[0]

    async def close() -> None:
        return None

    registry = ConnectionRegistry("default")
    registry.register(
        "default",
        engine=engine,
        migrator=migrator,
        database=DatabaseManager("sqlite+aiosqlite://"),
        session=session,
        close=close,
        in_use=lambda: True,
    )
    middleware = TransactionMiddleware(registry)
    kept: list[contextvars.Context] = []

    async def keep(envelope: Envelope) -> Envelope:
        # What a task the handler started carries, running on after the message.
        kept.append(contextvars.copy_context())
        return envelope

    # Every session takes the address of the one freed before it, which the
    # allocator does when it pleases and a test cannot ask it to: the very
    # case an address standing for a session would answer wrongly.
    monkeypatch.setattr(transaction_middleware, "id", _one_address, raising=False)
    _ = await middleware.handle(Envelope("message"), Then(keep))
    await handed.pop().close()
    handed.append(AsyncSession(engine))

    async def write(envelope: Envelope) -> Envelope:
        _ = await handed[0].execute(insert(NOTE).values(text="later"))
        return envelope

    async def later() -> Envelope:
        return await middleware.handle(Envelope("later"), Then(write))

    _ = await asyncio.get_running_loop().create_task(later(), context=kept[0])

    # Its own transaction, begun and committed: not a savepoint of the freed one's.
    assert not handed[0].in_transaction()
    assert await rows(engine, "select text from note") == [("later",)]
    await handed[0].close()


def _one_address(_: object) -> int:
    return 1


# ── a caller's own transaction ──────────────────────────────────────────────


@pytest.fixture
async def caller(database_url: str, migrator: Migrator) -> AsyncIterator[Sessions]:
    """Sessions on an engine whose SQLite savepoints roll back on their own."""
    strict = create_async_engine(database_url, connect_args={"autocommit": False})
    async with strict.begin() as connection:
        await connection.run_sync(NOTE.metadata.create_all)
    built = Sessions(strict, migrator, "default")
    yield built
    await built.aclose()
    await strict.dispose()


async def test_a_failing_message_dispatched_after_its_caller_wrote_keeps_the_callers_work(
    caller: Sessions, engine: AsyncEngine
) -> None:
    session = caller.by_name["default"]
    _ = await session.execute(insert(NOTE).values(text="caller"))
    middleware = TransactionMiddleware(caller.registry)

    with pytest.raises(LookupError):
        _ = await middleware.handle(
            Envelope("message"), _writing(caller, "message", then=LookupError())
        )
    assert session.in_transaction()
    await session.commit()

    assert await rows(engine, "select text from note") == [("caller",)]


async def test_a_succeeding_message_does_not_commit_its_callers_pending_work(
    caller: Sessions, engine: AsyncEngine
) -> None:
    session = caller.by_name["default"]
    _ = await session.execute(insert(NOTE).values(text="caller"))
    middleware = TransactionMiddleware(caller.registry)

    _ = await middleware.handle(Envelope("message"), _writing(caller, "message"))

    assert session.in_transaction()
    await session.rollback()
    assert await rows(engine, "select text from note") == []


async def test_a_message_dispatched_after_an_unflushed_add_keeps_the_callers_object(
    caller: Sessions, engine: AsyncEngine
) -> None:
    session = caller.by_name["default"]
    _ = await session.execute(select(1))
    middleware = TransactionMiddleware(caller.registry)

    _ = await middleware.handle(Envelope("message"), _writing(caller, "message"))
    await session.commit()

    assert await rows(engine, "select text from note") == [("message",)]


async def test_a_received_message_commits_even_if_an_earlier_middleware_began_its_transaction(
    caller: Sessions, engine: AsyncEngine
) -> None:
    session = caller.by_name["default"]
    # What a middleware ahead of this one does: read before the handlers run.
    _ = await session.execute(select(1))
    middleware = TransactionMiddleware(caller.registry)

    _ = await middleware.handle(
        Envelope("message", (ReceivedStamp("jobs"),)), _writing(caller, "message")
    )

    assert not session.in_transaction()
    assert await rows(engine, "select text from note") == [("message",)]


async def test_cancelling_a_message_rolls_back_and_leaves_no_transaction(
    sessions: Sessions, engine: AsyncEngine
) -> None:
    middleware = TransactionMiddleware(sessions.registry)
    started = asyncio.Event()

    async def hang(envelope: Envelope) -> Envelope:
        _ = await sessions.by_name["default"].execute(insert(NOTE).values(text="cancelled"))
        started.set()
        _ = await asyncio.Event().wait()
        return envelope

    task = asyncio.create_task(middleware.handle(Envelope("message"), Then(hang)))
    _ = await started.wait()
    _ = task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert not sessions.by_name["default"].in_transaction()
    assert await rows(engine, "select text from note") == []
