"""``orm_transaction``: every handler of a message in one database transaction."""

from __future__ import annotations

from contextvars import ContextVar
from typing import TYPE_CHECKING, Final, final, override
from weakref import WeakSet

from xtr_messenger import (
    Envelope,
    HandledStamp,
    HandlersFailedError,
    MiddlewareInterface,
    ReceivedStamp,
    StackInterface,
    as_middleware,
)

from xtr_orm.connection_registry import ConnectionRegistry

if TYPE_CHECKING:
    from collections.abc import Iterable

    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["DETACHED_VARIABLE", "TransactionMiddleware", "in_begun_transaction"]


@final
class _Begun:
    """The sessions transaction middleware began in this context, open until its message is done.

    The sessions themselves, held weakly — never their ids, which a session
    built after one was freed may take over.
    """

    __slots__ = ("open", "sessions")

    def __init__(self, sessions: Iterable[AsyncSession]) -> None:
        self.sessions: WeakSet[AsyncSession] = WeakSet(sessions)
        self.open = True


# The transactions under way in this context: a message dispatched while
# another is handled runs inside the outer one's. Each message sets a record of
# its own and closes it once done, so work outliving the message — a task its
# handler started — begins a transaction of its own.
_begun: ContextVar[_Begun | None] = ContextVar("xtr_orm_transaction_begun", default=None)

DETACHED_VARIABLE: Final = (_begun, None)
"""What a new connection starts without: the transactions an earlier request's messages began.

The orm bundle registers it with the container when the messenger bundle is
active.
"""


def in_begun_transaction(session: AsyncSession) -> bool:
    """Tell whether ``session`` is in a transaction a message handled here began.

    For what must not commit a transaction that is not its own: inside one,
    work joins it — in a savepoint — and leaves committing to whoever began it.
    """
    begun = _begun.get()
    if begun is None or not begun.open:
        return False
    return session in begun.sessions and session.in_transaction()


@final
@as_middleware("orm_transaction")
class TransactionMiddleware(MiddlewareInterface):
    """Wraps every handler of a message in a single transaction on one connection.

    The transaction is the session of the message's unit of work, the one
    every handler is given: it is committed — flushing what the handlers
    added — once they all succeeded, and rolled back otherwise. Handlers
    leave committing to it.

    When a handler fails, the handled stamps of the others are dropped from
    the error's envelope: their work was rolled back too, so a retry runs
    every handler again.

    A message dispatched while another is handled runs inside that one's
    transaction, in a savepoint of its own: if it fails, what its handlers
    wrote is rolled back to the savepoint — so a handler that catches the
    failure and carries on commits only its own work — and the failure goes
    on to the handler that dispatched it.

    So does a message dispatched by code that already has a transaction open
    on the session — a request that wrote, then dispatched: the transaction
    is the caller's, so the message neither commits nor rolls back what the
    caller did, and committing stays the caller's. A message received from a
    transport owns its transaction whatever an earlier middleware began on
    the session: nobody else is there to commit it.

    Dispatch the messages of one unit one after another: messages handled at
    once by tasks sharing the unit's session interleave on one transaction.
    """

    __slots__ = ("_connection_name", "_connections")

    def __init__(self, connections: ConnectionRegistry, connection_name: str | None = None) -> None:
        """Run transactions on ``connection_name``, the default connection when ``None``."""
        self._connections = connections
        self._connection_name = connection_name

    @override
    async def handle(self, envelope: Envelope, stack: StackInterface, /) -> Envelope:
        """Run the rest of the chain inside a transaction, committed once it all succeeded."""
        session = await self._connections.session(self._connection_name)
        if in_begun_transaction(session) or (
            session.in_transaction() and envelope.last(ReceivedStamp) is None
        ):
            return await _in_savepoint(session, envelope, stack)
        if not session.in_transaction():
            _ = await session.begin()
        inherited = _begun.get()
        held = inherited.sessions if inherited is not None and inherited.open else ()
        begun = _Begun([*held, session])
        token = _begun.set(begun)
        try:
            handled = await stack.next().handle(envelope, stack)
            await session.commit()
        except HandlersFailedError as error:
            await session.rollback()
            raise _unhandled(error) from error
        except BaseException:
            await session.rollback()
            raise
        finally:
            begun.open = False
            _begun.reset(token)
        return handled


async def _in_savepoint(
    session: AsyncSession, envelope: Envelope, stack: StackInterface
) -> Envelope:
    """Run the rest of the chain in a savepoint of the transaction under way."""
    savepoint = await session.begin_nested()
    try:
        handled = await stack.next().handle(envelope, stack)
    except HandlersFailedError as error:
        if savepoint.is_active:
            await savepoint.rollback()
        raise _unhandled(error) from error
    except BaseException:
        if savepoint.is_active:
            await savepoint.rollback()
        raise
    if savepoint.is_active:
        await savepoint.commit()
    return handled


def _unhandled(error: HandlersFailedError) -> HandlersFailedError:
    """Return ``error`` without the handled stamps of handlers whose work was rolled back."""
    return HandlersFailedError(error.envelope.without_stamps(HandledStamp), error.errors)
