"""A configuration or a call was given something the library cannot work with."""

from __future__ import annotations

from .orm_error import OrmError

__all__ = ["InvalidArgumentError"]


class InvalidArgumentError(OrmError, ValueError):
    """A configuration or a call was given something the library cannot work with.

    Raised where the value is given — a connection without a name, a version
    table without a name — rather than when a database is first reached.

    Also a :class:`ValueError`, so code that already guards its configuration
    with ``except ValueError`` keeps working without learning a new exception.

    Attributes:
        reason: What is wrong with the value.
    """

    reason: str

    def __init__(self, reason: str) -> None:
        """Record what is wrong with the value."""
        self.reason = reason
        super().__init__(reason)
