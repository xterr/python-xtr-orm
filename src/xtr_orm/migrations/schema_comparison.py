"""What a comparison of the database with the table definitions found."""

from __future__ import annotations

from typing import TYPE_CHECKING, final

from alembic.operations.ops import DropTableOp

if TYPE_CHECKING:
    from collections.abc import Sequence

    from alembic.operations.ops import MigrateOperation

__all__ = ["SchemaComparison"]


@final
class SchemaComparison:
    """What a comparison of the database with the table definitions found.

    Nothing was written, run or recorded to find it; what it found runs
    through the migrator, and reads here as a count, the tables that would
    be dropped, and the operations themselves.
    """

    __slots__ = ("_changes", "_dropped_tables", "_ops")

    _changes: int
    _dropped_tables: tuple[str, ...]
    _ops: tuple[MigrateOperation, ...]

    def __init__(self, changes: int, ops: Sequence[MigrateOperation]) -> None:
        """Hold the ``changes`` counted in the comparison and the operations behind them."""
        self._changes = changes
        self._ops = tuple(ops)
        self._dropped_tables = tuple(
            f"{op.schema}.{op.table_name}" if op.schema is not None else op.table_name
            for op in self._ops
            if isinstance(op, DropTableOp)
        )

    @property
    def is_empty(self) -> bool:
        """Whether the comparison found nothing to do."""
        return not self._ops

    @property
    def changes(self) -> int:
        """Every change the comparison found, counted flat."""
        return self._changes

    @property
    def dropped_tables(self) -> tuple[str, ...]:
        """The schema-qualified names of the tables the comparison would drop."""
        return self._dropped_tables

    @property
    def ops(self) -> tuple[MigrateOperation, ...]:
        """The operations the comparison holds; applied through the migrator."""
        return self._ops
