"""``orm_transaction``: every handler of a message in one database transaction."""

from __future__ import annotations

from contextvars import ContextVar
from typing import TYPE_CHECKING, final

from typing_extensions import override
from xtr_messenger import (
    Envelope,
    HandledStamp,
    HandlersFailedError,
    MiddlewareInterface,
    StackInterface,
    as_middleware,
)

from xtr_orm.connection_registry import ConnectionRegistry

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["TransactionMiddleware"]

# The sessions a transaction middleware has begun in this context: a message
# dispatched while another is handled runs inside the outer one's transaction.
_begun: ContextVar[frozenset[int]] = ContextVar("xtr_orm_transaction_begun", default=frozenset())


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
        begun = _begun.get()
        if id(session) in begun:
            return await _in_savepoint(session, envelope, stack)
        if not session.in_transaction():
            _ = await session.begin()
        token = _begun.set(begun | {id(session)})
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
