"""Where a database stands against its revision files."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .available_migration import AvailableMigration
    from .executed_migration import ExecutedMigration

__all__ = ["MigrationStatus"]


@dataclass(frozen=True, slots=True)
class MigrationStatus:
    """Where a database stands against its revision files, read in one go.

    Attributes:
        current: The revisions the version table holds; empty when nothing
            is applied.
        latest: The revisions no other follows.
        previous: The revisions the current ones follow.
        next: The revisions that could run next, their predecessors all
            applied.
        available: Every revision file, earliest first.
        executed: Every revision counted as applied — those with a file,
            earliest first, then those without. A revision is applied when
            the version table holds it or one following it, or the history
            table records it.
        new: The revisions with a file that are not applied.
        executed_unavailable: The revisions recorded as applied that have no
            file.
    """

    current: tuple[str, ...]
    latest: tuple[str, ...]
    previous: tuple[str, ...]
    next: tuple[str, ...]
    available: tuple[AvailableMigration, ...]
    executed: tuple[ExecutedMigration, ...]
    new: tuple[AvailableMigration, ...]
    executed_unavailable: tuple[ExecutedMigration, ...]

    @property
    def is_up_to_date(self) -> bool:
        """Whether every revision with a file is applied."""
        return not self.new
