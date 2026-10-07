"""A database that had to exist does not."""

from __future__ import annotations

from .orm_error import OrmError

__all__ = ["MissingDatabaseError"]


class MissingDatabaseError(OrmError, FileNotFoundError):
    """A database was dropped that is not there — a SQLite file that does not exist.

    Also a :class:`FileNotFoundError`, as the missing file it stands for is.
    Ask for ``if_exists`` to leave a database that does not exist alone and be
    told so instead.

    Attributes:
        database: The database's name — for SQLite, its file.
        operation: What was asked, such as ``"drop"``.
    """

    database: str
    operation: str

    def __init__(self, database: str, operation: str) -> None:
        """Record which database was asked for what."""
        self.database = database
        self.operation = operation
        super().__init__(f'Cannot {operation} the database "{database}": it does not exist.')
