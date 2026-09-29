"""The sessions each handler was given, and the handler the logs are kept in."""

from __future__ import annotations

from typing import TYPE_CHECKING, final

from xtr_dependency_injection import as_service
from xtr_logging import TestHandler

# The container reads the factory's return annotation at runtime.
from xtr_logging.handler.handler_interface import HandlerInterface  # noqa: TC002

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@final
@as_service
class Sessions:
    """Every session a handler was given, by what the handler wrote."""

    def __init__(self) -> None:
        self.seen: dict[str, AsyncSession] = {}


@as_service(qualifier="main")
def main_handler() -> HandlerInterface:
    return TestHandler()
