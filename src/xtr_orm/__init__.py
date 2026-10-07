"""Databases for async applications: engines, sessions and versioned schema migrations.

A :class:`~xtr_orm.migrations.Migrator` runs one database's revisions, a
:class:`~xtr_orm.database.DatabaseManager` creates and drops the database
itself, and a :class:`ConnectionRegistry` names every connection an
application has. The bundle in :mod:`xtr_orm.bundle` builds all of them, and
the engines and sessions, from one configuration.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from .connection_registry import DEFAULT_CONNECTION, ConnectionRegistry
from .database import DatabaseManager
from .exception import (
    InvalidArgumentError,
    MigrationError,
    MissingDatabaseError,
    OrmError,
    SessionUnavailableError,
    UnknownConnectionError,
    UnsupportedDatabaseError,
)
from .migrations import (
    AvailableMigration,
    Direction,
    ExecutedMigration,
    ExecutionResult,
    MigrationPlan,
    MigrationsConfig,
    MigrationStatus,
    Migrator,
)

try:
    __version__ = version("xtr-orm")
except PackageNotFoundError:  # pragma: no cover
    # Imported from a source tree with no installed distribution: there is no
    # metadata to read. Having no version is better than refusing to import.
    __version__ = "0+unknown"

__all__ = [
    "DEFAULT_CONNECTION",
    "AvailableMigration",
    "ConnectionRegistry",
    "DatabaseManager",
    "Direction",
    "ExecutedMigration",
    "ExecutionResult",
    "InvalidArgumentError",
    "MigrationError",
    "MigrationPlan",
    "MigrationStatus",
    "MigrationsConfig",
    "Migrator",
    "MissingDatabaseError",
    "OrmError",
    "SessionUnavailableError",
    "UnknownConnectionError",
    "UnsupportedDatabaseError",
    "__version__",
]
