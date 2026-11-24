"""Invoking the operations a comparison produced. Private to the package."""

from __future__ import annotations

from typing import TYPE_CHECKING

from alembic.operations.ops import ModifyTableOps
from sqlalchemy import MetaData, Table, inspect

if TYPE_CHECKING:
    from alembic.operations import Operations
    from sqlalchemy.engine import Connection

    from .schema_comparison import SchemaComparison

__all__ = ["invoke"]


def invoke(
    operations: Operations, comparison: SchemaComparison, connection: Connection, *, batch: bool
) -> None:
    """Invoke each operation ``comparison`` holds, batching a table's changes when ``batch``."""
    # ModifyTableOps is organizational only — unroll it. OpContainer exposes
    # .ops and defines no __iter__.
    for op in comparison.ops:
        if not isinstance(op, ModifyTableOps):
            operations.invoke(op)
        elif not batch:
            for inner in op.ops:
                operations.invoke(inner)
        else:
            with operations.batch_alter_table(
                op.table_name, schema=op.schema, copy_from=_reflected(connection, op)
            ) as batch_op:
                for inner in op.ops:
                    batch_op.invoke(inner)


def _reflected(connection: Connection, op: ModifyTableOps) -> Table | None:
    """Reflect the table a batch rebuilds, or None when it is not there.

    ``connection`` is the real one: a context rendering SQL wraps its own in
    a stub returning no rows, so reflection cannot go through it — and a batch
    recreate rendered without the table refuses to run.
    """
    if not inspect(connection).has_table(op.table_name, op.schema):
        return None
    return Table(op.table_name, MetaData(), schema=op.schema, autoload_with=connection)
