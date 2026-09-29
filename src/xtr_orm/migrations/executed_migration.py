"""A revision the database counts as applied."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

__all__ = ["ExecutedMigration"]


@dataclass(frozen=True, slots=True)
class ExecutedMigration:
    """A revision the database counts as applied.

    Applied means recorded in the version table, preceding a revision that
    is, or recorded in the history table. When and how long come from the
    history table: a revision applied before it existed has neither, and one
    only marked as applied has no duration.

    Attributes:
        version: The revision's identifier.
        executed_at: When it was applied, by the database's clock.
        execution_time: How long it took, in seconds.
    """

    version: str
    executed_at: datetime | None = None
    execution_time: float | None = None
