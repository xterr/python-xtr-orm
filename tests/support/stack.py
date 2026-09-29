"""A middleware chain for a middleware under test: the rest of it is a function of the envelope."""

from __future__ import annotations

from typing import TYPE_CHECKING, final

from typing_extensions import override
from xtr_messenger import Envelope, MiddlewareInterface, StackInterface

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


@final
class _Rest(MiddlewareInterface):
    def __init__(self, run: Callable[[Envelope], Awaitable[Envelope]]) -> None:
        self._run = run

    @override
    async def handle(self, envelope: Envelope, stack: StackInterface, /) -> Envelope:
        return await self._run(envelope)


@final
class Then(StackInterface):
    """A stack whose next middleware is ``run`` — what handling the envelope does."""

    def __init__(self, run: Callable[[Envelope], Awaitable[Envelope]]) -> None:
        self._rest = _Rest(run)

    @override
    def next(self) -> MiddlewareInterface:
        return self._rest
