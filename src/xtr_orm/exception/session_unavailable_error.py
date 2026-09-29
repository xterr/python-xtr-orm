"""The session of the current unit of work was asked for where there is none."""

from __future__ import annotations

from .orm_error import OrmError

__all__ = ["SessionUnavailableError"]


class SessionUnavailableError(OrmError):
    """The session of the current unit of work was asked for where there is none.

    A connection reaches the session everything in a unit of work shares —
    a message's handlers, say — only inside one, and only when it was
    registered with a way to.

    Attributes:
        connection: The connection the session was asked of.
        reason: Why there is none.
    """

    connection: str
    reason: str

    def __init__(self, connection: str, reason: str) -> None:
        """Record which connection was asked, and why it has no session to give."""
        self.connection = connection
        self.reason = reason
        super().__init__(f'The "{connection}" connection has no session here: {reason}.')
