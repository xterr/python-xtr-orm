"""What every orm command shares: where the connections come from, and how it reports."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from xtr_console import ConsoleStyle, escape

from xtr_orm.connection_registry import ConnectionRegistry
from xtr_orm.exception import UnknownConnectionError

from .connections import NO_CONNECTIONS, UNSET, resolve_connections

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncEngine

    from xtr_orm.database import DatabaseManager
    from xtr_orm.migrations import AvailableMigration, ExecutionResult, MigrationPlan, Migrator

__all__ = ["ConnectionCommand"]


class ConnectionCommand:
    """An orm command, acting on the connections a container gives it, or ``use_connections()``.

    A container builds each command with the connections its bundle
    registered; without one, the console builds it bare, and it falls back to
    the connections set with :func:`~xtr_orm.command.use_connections`.
    """

    __slots__: ClassVar[tuple[str, ...]] = ("_connections",)

    _connections: ConnectionRegistry

    def __init__(self, connections: ConnectionRegistry = UNSET) -> None:
        """Act on ``connections``, or on those set with ``use_connections()`` when omitted."""
        self._connections = connections

    async def _migrator(self, io: ConsoleStyle, connection: str | None) -> Migrator | None:
        """Return the migrator of ``connection``, or say on ``io`` why there is none."""
        registry = self._registry(io, connection)
        return None if registry is None else await registry.migrator(connection)

    async def _database(self, io: ConsoleStyle, connection: str | None) -> DatabaseManager | None:
        """Return the database manager of ``connection``, or say on ``io`` why there is none."""
        registry = self._registry(io, connection)
        return None if registry is None else await registry.database(connection)

    async def _engine(self, io: ConsoleStyle, connection: str | None) -> AsyncEngine | None:
        """Return the engine of ``connection``, or say on ``io`` why there is none."""
        registry = self._registry(io, connection)
        return None if registry is None else await registry.engine(connection)

    def _name(self, connection: str | None) -> str:
        """The name ``connection`` stands for: itself, or the default connection's."""
        registry = resolve_connections(self._connections)
        return connection or (registry.default if registry is not None else "default")

    def _registry(self, io: ConsoleStyle, connection: str | None) -> ConnectionRegistry | None:
        registry = resolve_connections(self._connections)
        if registry is None:
            io.error(NO_CONNECTIONS)
            return None
        if not registry.has(connection):
            io.error(escape(str(UnknownConnectionError(self._name(connection), registry.names()))))
            return None
        return registry


def confirm_changes(io: ConsoleStyle, migrator: Migrator) -> bool:
    """Ask before a migration changes the database; a run asking nothing goes ahead."""
    return io.confirm(
        "WARNING! You are about to execute a migration on the "
        f'"{escape(migrator.name)}" connection that could result in schema changes and data '
        "loss. Are you sure you wish to continue?",
        default=True,
    )


def report_plan(io: ConsoleStyle, plans: Sequence[MigrationPlan]) -> None:
    """List what a dry run would do."""
    for plan in plans:
        verb = "++ migrating" if plan.direction.value == "up" else "-- reverting"
        io.text(f"  {verb} {escape(format_version(plan.version, plan.description))}")


def report_results(io: ConsoleStyle, results: Sequence[ExecutionResult]) -> None:
    """List what a migration did, each revision with the time it took."""
    for result in results:
        verb = "++ migrated" if result.direction.value == "up" else "-- reverted"
        io.text(f"  {verb} {escape(result.version)} ({result.duration:.3f}s)")


def save_sql(io: ConsoleStyle, target: str, sql: str) -> None:
    """Write ``sql`` to ``target`` — a file, or a directory to put a dated file in."""
    path = Path(target)
    if path.is_dir():
        path /= f"migration_{datetime.now().astimezone():%Y%m%d%H%M%S}.sql"
    _ = path.write_text(sql, encoding="utf-8")
    io.success(f'Wrote the migration SQL to "{escape(str(path))}".')


def report_written(
    io: ConsoleStyle, what: str, written: AvailableMigration, connection: str | None
) -> None:
    """Say where a new revision went, and how to run it alone and revert it."""
    option = f" --connection {escape(connection)}" if connection else ""
    version = escape(written.version)
    io.success(f'{what} "{escape(written.path)}"')
    io.text(
        "To run just this migration for testing purposes, you can use "
        f"orm:migrations:execute --up {version}{option}",
    )
    io.text(f"To revert the migration you can use orm:migrations:execute --down {version}{option}")


def report_count(io: ConsoleStyle, results: Sequence[ExecutionResult]) -> None:
    """Close a run with how many revisions ran, and how long they took together."""
    total = sum(result.duration for result in results)
    plural = "" if len(results) == 1 else "s"
    io.success(f"{len(results)} migration{plural} executed in {total:.3f}s.")


def format_version(version: str, description: str | None) -> str:
    """Render a version with its description, as the listing commands show it."""
    return f"{version}{_described(description)}"


def _described(description: str | None) -> str:
    return f" - {description}" if description else ""
