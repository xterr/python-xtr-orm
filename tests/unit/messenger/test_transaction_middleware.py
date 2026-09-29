"""Unit tests for :class:`xtr_orm.messenger.TransactionMiddleware`."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, insert, select
from xtr_messenger import Envelope, HandledStamp, HandlersFailedError

from tests.support.database import rows
from tests.support.sessions import Sessions
from tests.support.stack import Then
from xtr_orm.messenger import TransactionMiddleware

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
