"""Databases for async applications: engines, sessions and versioned schema migrations.

A :class:`~xtr_orm.migrations.Migrator` runs one database's revisions, a
:class:`~xtr_orm.database.DatabaseManager` creates and drops the database
itself, and a :class:`ConnectionRegistry` names every connection an
application has. The bundle in :mod:`xtr_orm.bundle` builds all of them, and
the engines and sessions, from one configuration.
"""

from __future__ import annotations

from .connection_registry import DEFAULT_CONNECTION, ConnectionRegistry
from .database import DatabaseManager
from .exception import (
    InvalidArgumentError,
    MigrationError,
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
    "OrmError",
    "SessionUnavailableError",
    "UnknownConnectionError",
    "UnsupportedDatabaseError",
]
