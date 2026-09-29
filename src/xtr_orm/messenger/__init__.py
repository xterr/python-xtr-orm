"""Message bus middleware for the connections: transactions, closing, and open transactions.

Importing this module declares them by name — ``orm_transaction``,
``orm_close_connection`` and ``orm_open_transaction_logger`` — for a bus
configuration to list. With a container, the orm bundle loads it when the
messenger bundle is active, and the messenger bundle registers each by that
name. Without one, build them with a :class:`~xtr_orm.ConnectionRegistry`
and put the instances in the configuration.

Needs the ``messenger`` extra: ``xtr-orm[messenger]``.
"""

from __future__ import annotations

from .close_connection_middleware import CloseConnectionMiddleware
from .open_transaction_logger_middleware import OpenTransactionLoggerMiddleware
from .transaction_middleware import TransactionMiddleware

__all__ = [
    "CloseConnectionMiddleware",
    "OpenTransactionLoggerMiddleware",
    "TransactionMiddleware",
]
