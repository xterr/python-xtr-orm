"""Which way a revision runs."""

from __future__ import annotations

from enum import Enum

__all__ = ["Direction"]


class Direction(Enum):
    """Which way a revision runs: its upgrade, or its downgrade."""

    UP = "up"
    DOWN = "down"
