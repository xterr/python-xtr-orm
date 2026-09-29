"""Handlers writing through the session of the message's unit of work: functions and a class."""

from __future__ import annotations

from typing import final

from sqlalchemy import insert

# The container reads the handlers' annotations at runtime.
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002
from xtr_dependency_injection import Injected  # noqa: TC002
from xtr_messenger import (
    DispatchAfterCurrentBusStamp,
    HandlersFailedError,
    MessageBusInterface,
    as_message_handler,
)

from tests.support.schema import AUTHOR

from .messages import NestedNote, QueuedNote, WriteNote
from .services import Sessions  # noqa: TC001


async def _write(session: AsyncSession, sessions: Sessions, name: str) -> None:
    _ = await session.execute(insert(AUTHOR).values(name=name))
    sessions.seen[name] = session


@as_message_handler(WriteNote)
async def first(
    message: WriteNote, session: Injected[AsyncSession], sessions: Injected[Sessions]
) -> None:
    await _write(session, sessions, f"first:{message.text}")


@final
@as_message_handler(WriteNote)
class Second:
    """A class handler: built once, given the message's session on each call."""

    def __init__(self, sessions: Sessions, bus: MessageBusInterface) -> None:
        self._sessions = sessions
        self._bus = bus

    async def __call__(self, message: WriteNote, session: Injected[AsyncSession]) -> None:
        await _write(session, self._sessions, f"second:{message.text}")
        if message.nested:
            stamps = (DispatchAfterCurrentBusStamp(),) if message.after else ()
            try:
                _ = await self._bus.dispatch(NestedNote(message.text, fail=message.fail), *stamps)
            except HandlersFailedError:
                if not message.catch_nested:
                    raise
        if message.leave_open:
            _ = await session.begin_nested()


@as_message_handler(WriteNote)
async def third(
    message: WriteNote, session: Injected[AsyncSession], sessions: Injected[Sessions]
) -> None:
    await _write(session, sessions, f"third:{message.text}")
    if (message.fail and not message.nested) or message.refuse:
        raise LookupError(message.text)


@as_message_handler(NestedNote)
async def nested(
    message: NestedNote, session: Injected[AsyncSession], sessions: Injected[Sessions]
) -> None:
    await _write(session, sessions, f"nested:{message.text}")
    if message.fail:
        raise LookupError(message.text)


@as_message_handler(QueuedNote)
async def queued(
    message: QueuedNote, session: Injected[AsyncSession], sessions: Injected[Sessions]
) -> None:
    await _write(session, sessions, f"queued:{message.text}")
    if message.fail:
        raise LookupError(message.text)
