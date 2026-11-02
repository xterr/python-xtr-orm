"""The handler recording every order a worker handled."""

from __future__ import annotations

import asyncio
from typing import final

from xtr_dependency_injection import Injected, as_service
from xtr_messenger import as_message_handler

from .messages import QueuedOrder


@final
@as_service
class Ledger:
    """Every order handled, in the order it was, and a signal each time one is."""

    def __init__(self) -> None:
        self.orders: list[str] = []
        self.recorded: asyncio.Event = asyncio.Event()

    def record(self, order: str) -> None:
        self.orders.append(order)
        self.recorded.set()


@as_message_handler(QueuedOrder)
async def record(message: QueuedOrder, ledger: Injected[Ledger]) -> None:
    ledger.record(message.order)
