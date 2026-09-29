"""Every error this library raises, all deriving from :class:`OrmError`."""

from __future__ import annotations

from .invalid_argument_error import InvalidArgumentError
from .migration_error import MigrationError
from .orm_error import OrmError
from .session_unavailable_error import SessionUnavailableError
from .unknown_connection_error import UnknownConnectionError
from .unsupported_database_error import UnsupportedDatabaseError

__all__ = [
    "InvalidArgumentError",
    "MigrationError",
    "OrmError",
    "SessionUnavailableError",
    "UnknownConnectionError",
    "UnsupportedDatabaseError",
]
