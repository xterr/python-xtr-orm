"""One revision a migration would run, and which way."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .direction import Direction

__all__ = ["MigrationPlan"]


@dataclass(frozen=True, slots=True)
class MigrationPlan:
    """One revision a migration would run, and which way.

    Attributes:
        version: The revision's identifier.
        direction: Whether its upgrade or its downgrade runs.
        description: The first line of its message.
    """

    version: str
    direction: Direction
    description: str
