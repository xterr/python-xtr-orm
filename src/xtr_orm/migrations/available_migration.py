"""A revision file, as it was found in the migrations directory."""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["AvailableMigration"]


@dataclass(frozen=True, slots=True)
class AvailableMigration:
    """A revision file, as it was found in the migrations directory.

    Attributes:
        version: The revision's identifier.
        description: The first line of its message.
        down_versions: The revisions it follows; empty for a first revision,
            two or more for one merging branches.
        path: Where its file is.
        is_head: Whether no revision follows it.
    """

    version: str
    description: str
    down_versions: tuple[str, ...]
    path: str
    is_head: bool
