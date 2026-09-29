"""``orm_open_transaction_logger``: say so when a handler leaves a transaction open."""

from __future__ import annotations

from collections.abc import Sequence
from contextvars import ContextVar
from typing import TYPE_CHECKING, Final, final

from sqlalchemy.orm import SessionTransactionOrigin
from typing_extensions import override
from xtr_logging_contracts import LoggerInterface, NullLogger
from xtr_messenger import Envelope, MiddlewareInterface, StackInterface, as_middleware

from xtr_orm.connection_registry import ConnectionRegistry

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["OpenTransactionLoggerMiddleware"]

_OPENED: Final = frozenset({SessionTransactionOrigin.BEGIN, SessionTransactionOrigin.BEGIN_NESTED})
"""How a transaction a handler opened itself began; the session's own autobegin is not one."""

_DISCARD: Final = NullLogger()
"""Where findings go without a logger."""

# Set while a message is checked, so a message dispatched during it is not checked twice.
_handling: ContextVar[bool] = ContextVar("xtr_orm_open_transaction_logging", default=False)


@final
@as_middleware("orm_open_transaction_logger")
class OpenTransactionLoggerMiddleware(MiddlewareInterface):
    """Logs an error when a handler opened a transaction and did not close it.

    A transaction counts when a handler began it — ``begin()`` or
    ``begin_nested()`` on the unit of work's session — not when the session
    began one by itself for a query.
    """

    __slots__ = ("_connection_names", "_connections", "_logger")

    def __init__(
        self,
        connections: ConnectionRegistry,
        logger: LoggerInterface = _DISCARD,
        connection_names: str | Sequence[str] = (),
    ) -> None:
        """Check ``connection_names`` — every connection when none is given — logging to ``logger``.

        Under a container, ``logger`` is the application's logger when the
        logging bundle is active; otherwise what is found goes nowhere.
        """
        self._connections = connections
        self._logger = logger
        self._connection_names = (
            (connection_names,) if isinstance(connection_names, str) else tuple(connection_names)
        )

    @override
    async def handle(self, envelope: Envelope, stack: StackInterface, /) -> Envelope:
        """Run the rest of the chain, then log each connection left with a transaction open."""
        if _handling.get():
            return await stack.next().handle(envelope, stack)
        names = self._connection_names or self._connections.names()
        sessions = {name: await self._connections.session(name) for name in names}
        initial = {name: _opened(session) for name, session in sessions.items()}
        token = _handling.set(True)
        try:
            return await stack.next().handle(envelope, stack)
        finally:
            _handling.reset(token)
            left = [name for name, session in sessions.items() if _opened(session) > initial[name]]
            if left:
                self._logger.error(
                    "A handler opened a transaction but did not close it.",
                    {"connections": left, "message": envelope.message},
                )


def _opened(session: AsyncSession) -> int:
    """Count the transactions open on ``session`` that someone began explicitly."""
    sync = session.sync_session
    transaction = sync.get_nested_transaction() or sync.get_transaction()
    count = 0
    while transaction is not None:
        if transaction.is_active and transaction.origin in _OPENED:
            count += 1
        transaction = transaction.parent
    return count
