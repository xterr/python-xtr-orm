"""The history table: a row per revision applied, beside the version table's current ones.

The version table holds only the revisions a database is *at*; the migration
runner rewrites it as it goes. The history table keeps what that table
forgets — every revision applied, when, and how long it took — so a report
can name each applied revision, including one whose file is gone.

A row is written by the step that applies its revision, in the same
transaction, so the two tables agree wherever the database's transactions
reach.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import TYPE_CHECKING, Final, cast, final

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    delete,
    func,
    insert,
    select,
)
from sqlalchemy import inspect as inspect_connection
from sqlalchemy.schema import CreateTable

from .direction import Direction
from .execution_result import ExecutionResult

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from alembic.runtime.migration import MigrationContext, MigrationInfo
    from sqlalchemy.engine import Connection

__all__ = ["HistoryRecorder", "HistoryTable"]

_VERSION_LENGTH: Final = 255
_MILLISECONDS: Final = 1000


@final
class HistoryTable:
    """The history table of one database: its definition, and how it is read and written."""

    __slots__ = ("table",)

    table: Table

    def __init__(self, name: str, schema: str | None) -> None:
        """Describe the table ``name`` in ``schema``."""
        self.table = Table(
            name,
            MetaData(),
            Column("version", String(_VERSION_LENGTH), primary_key=True),
            Column("executed_at", DateTime(timezone=True), nullable=True),
            Column("execution_time", Integer, nullable=True),
            schema=schema,
        )

    def exists(self, connection: Connection) -> bool:
        """Whether the database has the table."""
        return inspect_connection(connection).has_table(self.table.name, self.table.schema)

    def read(self, connection: Connection) -> dict[str, tuple[datetime | None, float | None]]:
        """Return when each recorded revision was applied and how long it took, in seconds."""
        if not self.exists(connection):
            return {}
        columns = self.table.c
        rows = connection.execute(
            select(columns.version, columns.executed_at, columns.execution_time),
        )
        found: dict[str, tuple[datetime | None, float | None]] = {}
        for row in rows:
            version, executed_at, execution_time = cast(
                "tuple[str, object, int | None]", tuple(row)
            )
            found[version] = (
                _as_datetime(executed_at),
                None if execution_time is None else execution_time / _MILLISECONDS,
            )
        return found

    def ensure(self, context: MigrationContext, connection: Connection) -> None:
        """Create the table through ``context`` unless ``connection`` shows it exists.

        Through the context, so in SQL-only mode the statement is written
        with the others instead of run.
        """
        if not self.exists(connection):
            context.execute(CreateTable(self.table))

    def add(self, context: MigrationContext, version: str, duration: float | None) -> None:
        """Record ``version`` as applied now, having taken ``duration`` seconds."""
        self.remove(context, (version,))
        context.execute(
            insert(self.table).values(
                version=version,
                executed_at=func.current_timestamp(),
                execution_time=None if duration is None else round(duration * _MILLISECONDS),
            ),
        )

    def remove(self, context: MigrationContext, versions: Iterable[str]) -> None:
        """Forget ``versions``."""
        for version in versions:
            context.execute(delete(self.table).where(self.table.c.version == version))

    def clear(self, context: MigrationContext) -> None:
        """Forget every revision."""
        context.execute(delete(self.table))


@final
class HistoryRecorder:
    """Writes a history row for every step the runner applies, and times each one.

    The runner calls it after each step, inside the step's transaction. The
    steps it times are handed out through :meth:`started`, which the planned
    steps' generator calls just before giving the runner each one.
    """

    __slots__ = ("_history", "_marking", "_results", "_started")

    _history: HistoryTable
    _marking: bool
    _results: list[ExecutionResult]
    _started: float

    def __init__(self, history: HistoryTable, *, marking: bool = False) -> None:
        """Record into ``history``; ``marking`` steps change the tables without running."""
        self._history = history
        self._marking = marking
        self._results = []
        self._started = time.perf_counter()

    @property
    def results(self) -> tuple[ExecutionResult, ...]:
        """Every step recorded so far, in the order it ran."""
        return tuple(self._results)

    def started(self) -> None:
        """Note that the next step starts now."""
        self._started = time.perf_counter()

    def __call__(
        self,
        *,
        ctx: MigrationContext,
        step: MigrationInfo,
        heads: set[str],
        run_args: Mapping[str, object],
    ) -> None:
        """Record ``step``, which the runner has just applied."""
        del heads, run_args
        duration = time.perf_counter() - self._started
        versions = step.up_revision_ids
        if step.is_upgrade:
            for version in versions:
                self._history.add(ctx, version, None if self._marking else duration)
        else:
            self._history.remove(ctx, versions)
        direction = Direction.UP if step.is_upgrade else Direction.DOWN
        self._results.extend(ExecutionResult(version, direction, duration) for version in versions)


def _as_datetime(value: object) -> datetime | None:
    """Read a timestamp column, which some drivers hand back as text."""
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))
