"""One revision a migration ran, and how long it took."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .direction import Direction

__all__ = ["ExecutionResult"]


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    """One revision a migration ran, and how long it took.

    Attributes:
        version: The revision's identifier.
        direction: Whether its upgrade or its downgrade ran.
        duration: How long it took, in seconds.
    """

    version: str
    direction: Direction
    duration: float
