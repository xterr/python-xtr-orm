"""``orm_close_connection``: a worker gives its database connections back after each message."""

from __future__ import annotations

from collections.abc import Sequence
from typing import final

from typing_extensions import override
from xtr_messenger import (
    Envelope,
    MiddlewareInterface,
    ReceivedStamp,
    StackInterface,
    as_middleware,
)

from xtr_orm.connection_registry import ConnectionRegistry
from xtr_orm.exception import UnknownConnectionError

__all__ = ["CloseConnectionMiddleware"]


@final
@as_middleware("orm_close_connection")
class CloseConnectionMiddleware(MiddlewareInterface):
    """Closes connections once a message a worker consumed is handled, saving connections.

    A worker waiting for its next message then holds none open; the next
    one connects again. A message dispatched in the process that sends it
    closes nothing.

    A worker handling several messages at once closes them once the last of
    those still being handled is done: closing drops the pool, and dropping
    it after each message would make every other one in flight connect anew.
    """

    __slots__ = ("_connection_names", "_connections", "_consumed")

    def __init__(
        self,
        connections: ConnectionRegistry,
        connection_names: str | Sequence[str] = (),
    ) -> None:
        """Close ``connection_names`` — every connection in use when none is given."""
        self._connections = connections
        self._consumed = 0
        self._connection_names = (
            (connection_names,) if isinstance(connection_names, str) else tuple(connection_names)
        )

    @override
    async def handle(self, envelope: Envelope, stack: StackInterface, /) -> Envelope:
        """Run the rest of the chain, then close the connections if a worker consumed it.

        Closing waits for every consumed message this middleware is handling
        to be done with.

        Raises:
            UnknownConnectionError: When a connection named is not registered.
        """
        for name in self._connection_names:
            if not self._connections.has(name):
                raise UnknownConnectionError(name, self._connections.names())
        if envelope.last(ReceivedStamp) is None:
            return await stack.next().handle(envelope, stack)
        # Counted per instance, on one event loop: no lock needed.
        self._consumed += 1
        try:
            return await stack.next().handle(envelope, stack)
        finally:
            self._consumed -= 1
            if self._consumed == 0:
                for name in self._connection_names or self._connections.in_use():
                    await self._connections.close(name)
