"""A migration operation was refused, or its revisions could not be read."""

from __future__ import annotations

from .orm_error import OrmError

__all__ = ["MigrationError"]


class MigrationError(OrmError):
    """A migration operation was refused, or its revisions could not be read.

    Raised before anything is changed whenever it can be decided up front: a
    version that no revision answers to, a revision run out of order, a diff
    against a database that is behind its revisions. Nothing is written when
    it is raised from a check; a failing revision rolls back what the
    database lets it.

    Attributes:
        reason: Why the operation was refused.
    """

    reason: str

    def __init__(self, reason: str) -> None:
        """Record why the operation was refused."""
        self.reason = reason
        super().__init__(reason)
