"""Unit tests for :class:`xtr_orm.messenger.OpenTransactionLoggerMiddleware`."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select
from xtr_logging import Logger, TestHandler
from xtr_logging_contracts import Level
from xtr_messenger import Envelope

from tests.support.sessions import Sessions
from tests.support.stack import Then
from xtr_orm.messenger import OpenTransactionLoggerMiddleware

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncEngine

    from xtr_orm import Migrator

pytestmark = pytest.mark.anyio


@pytest.fixture
async def sessions(engine: AsyncEngine, migrator: Migrator) -> AsyncIterator[Sessions]:
    built = Sessions(engine, migrator, "default", "reports")
    yield built
    await built.aclose()


def _logged() -> tuple[Logger, TestHandler]:
    handler = TestHandler()
    return Logger("app", [handler]), handler


async def test_a_transaction_a_handler_began_and_left_open_is_logged(sessions: Sessions) -> None:
    logger, handler = _logged()
    middleware = OpenTransactionLoggerMiddleware(sessions.registry, logger)

    async def leave_open(envelope: Envelope) -> Envelope:
        _ = await sessions.by_name["reports"].begin()
        return envelope

    _ = await middleware.handle(Envelope("message"), Then(leave_open))

    [record] = handler.records
    assert record.level is Level.ERROR
    assert record.message == "A handler opened a transaction but did not close it."
    assert record.context == {"connections": ["reports"], "message": "message"}


async def test_a_transaction_the_session_began_by_itself_is_not(sessions: Sessions) -> None:
    logger, handler = _logged()
    middleware = OpenTransactionLoggerMiddleware(sessions.registry, logger)

    async def query(envelope: Envelope) -> Envelope:
        _ = await sessions.by_name["default"].execute(select(1))
        return envelope

    _ = await middleware.handle(Envelope("message"), Then(query))

    assert handler.records == ()
    assert sessions.by_name["default"].in_transaction()


async def test_a_transaction_closed_before_the_end_is_not(sessions: Sessions) -> None:
    logger, handler = _logged()
    middleware = OpenTransactionLoggerMiddleware(sessions.registry, logger)

    async def commit(envelope: Envelope) -> Envelope:
        session = sessions.by_name["default"]
        async with session.begin():
            _ = await session.execute(select(1))
        return envelope

    _ = await middleware.handle(Envelope("message"), Then(commit))

    assert handler.records == ()


async def test_only_the_connections_named_are_checked(sessions: Sessions) -> None:
    logger, handler = _logged()
    middleware = OpenTransactionLoggerMiddleware(
        sessions.registry, logger, connection_names=["default"]
    )

    async def leave_open(envelope: Envelope) -> Envelope:
        _ = await sessions.by_name["reports"].begin()
        return envelope

    _ = await middleware.handle(Envelope("message"), Then(leave_open))

    assert handler.records == ()


async def test_a_message_dispatched_during_another_is_checked_once(sessions: Sessions) -> None:
    logger, handler = _logged()
    middleware = OpenTransactionLoggerMiddleware(sessions.registry, logger)

    async def leave_open(envelope: Envelope) -> Envelope:
        _ = await sessions.by_name["default"].begin()
        return envelope

    async def outer(envelope: Envelope) -> Envelope:
        _ = await middleware.handle(Envelope("nested"), Then(leave_open))
        return envelope

    _ = await middleware.handle(Envelope("message"), Then(outer))

    assert len(handler.records) == 1


async def test_without_a_logger_findings_go_nowhere(sessions: Sessions) -> None:
    async def leave_open(envelope: Envelope) -> Envelope:
        _ = await sessions.by_name["default"].begin()
        return envelope

    handled = await OpenTransactionLoggerMiddleware(sessions.registry).handle(
        Envelope("message"), Then(leave_open)
    )

    assert handled == Envelope("message")
