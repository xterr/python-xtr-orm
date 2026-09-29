"""A database server was asked for something this library cannot do on it."""

from __future__ import annotations

from .orm_error import OrmError

__all__ = ["UnsupportedDatabaseError"]


class UnsupportedDatabaseError(OrmError):
    """A database server was asked for something this library cannot do on it.

    Creating or dropping a database takes a statement of the server's own;
    a server whose statement is not known here is refused rather than sent a
    guess.

    Attributes:
        backend: The kind of server the URL names, such as ``"oracle"``.
        operation: What was asked, such as ``"create"``.
    """

    backend: str
    operation: str

    def __init__(self, backend: str, operation: str) -> None:
        """Record which server was asked for what."""
        self.backend = backend
        self.operation = operation
        super().__init__(f'Cannot {operation} a database on "{backend}": it is not supported.')
