"""Unit tests for :class:`xtr_orm.messenger.CloseConnectionMiddleware`."""

from __future__ import annotations

from typing import TYPE_CHECKING

import anyio
import pytest
from xtr_messenger import Envelope, ReceivedStamp

from tests.support.sessions import Sessions
from tests.support.stack import Then
from xtr_orm import UnknownConnectionError
from xtr_orm.messenger import CloseConnectionMiddleware

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncEngine

    from xtr_orm import Migrator

pytestmark = pytest.mark.anyio

CONSUMED = Envelope("message", (ReceivedStamp("jobs"),))


@pytest.fixture
async def sessions(engine: AsyncEngine, migrator: Migrator) -> AsyncIterator[Sessions]:
    built = Sessions(engine, migrator, "default", "reports")
    yield built
    await built.aclose()


async def _handled(envelope: Envelope) -> Envelope:
    return envelope


async def _failing(envelope: Envelope) -> Envelope:
    raise LookupError(envelope)


async def test_a_consumed_message_closes_every_connection(sessions: Sessions) -> None:
    _ = await CloseConnectionMiddleware(sessions.registry).handle(CONSUMED, Then(_handled))

    assert sessions.closed == ["default", "reports"]


async def test_a_connection_not_in_use_is_not_closed(sessions: Sessions) -> None:
    sessions.in_use.discard("reports")

    _ = await CloseConnectionMiddleware(sessions.registry).handle(CONSUMED, Then(_handled))

    assert sessions.closed == ["default"]


async def test_a_connection_the_message_put_in_use_is_closed(sessions: Sessions) -> None:
    sessions.in_use.discard("reports")

    async def use_reports(envelope: Envelope) -> Envelope:
        sessions.in_use.add("reports")
        return envelope

    _ = await CloseConnectionMiddleware(sessions.registry).handle(CONSUMED, Then(use_reports))

    assert sessions.closed == ["default", "reports"]


async def test_only_the_connections_named_are_closed(sessions: Sessions) -> None:
    middleware = CloseConnectionMiddleware(sessions.registry, connection_names="reports")

    _ = await middleware.handle(CONSUMED, Then(_handled))

    assert sessions.closed == ["reports"]


async def test_a_message_the_process_dispatched_itself_closes_nothing(sessions: Sessions) -> None:
    _ = await CloseConnectionMiddleware(sessions.registry).handle(
        Envelope("message"), Then(_handled)
    )

    assert sessions.closed == []


async def test_connections_are_closed_even_when_handling_failed(sessions: Sessions) -> None:
    with pytest.raises(LookupError):
        _ = await CloseConnectionMiddleware(sessions.registry).handle(CONSUMED, Then(_failing))

    assert sessions.closed == ["default", "reports"]


async def test_messages_handled_at_once_close_the_connections_once_the_last_is_done(
    sessions: Sessions,
) -> None:
    middleware = CloseConnectionMiddleware(sessions.registry, connection_names="default")
    first_started, first_may_end = anyio.Event(), anyio.Event()
    closed_while_first_ran: list[list[str]] = []

    async def first(envelope: Envelope) -> Envelope:
        first_started.set()
        await first_may_end.wait()
        return envelope

    async def second(envelope: Envelope) -> Envelope:
        return envelope

    async with anyio.create_task_group() as group:
        _ = group.start_soon(middleware.handle, CONSUMED, Then(first))
        await first_started.wait()
        _ = await middleware.handle(CONSUMED, Then(second))
        closed_while_first_ran.append(list(sessions.closed))
        first_may_end.set()

    assert closed_while_first_ran == [[]]
    assert sessions.closed == ["default"]


async def test_an_unknown_connection_is_refused_before_handling(sessions: Sessions) -> None:
    handled: list[Envelope] = []

    async def handle(envelope: Envelope) -> Envelope:
        handled.append(envelope)
        return envelope

    middleware = CloseConnectionMiddleware(sessions.registry, connection_names=["nope"])

    with pytest.raises(UnknownConnectionError):
        _ = await middleware.handle(CONSUMED, Then(handle))

    assert handled == []
