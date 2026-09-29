"""Revisions written from table definitions rather than from a comparison.

A dump of an existing database, or a diff "from an empty schema", both come
down to one revision creating every table — and its downgrade dropping them
again — written through the same renderer a compared diff uses.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from alembic.operations.ops import (
    CreateIndexOp,
    CreateTableOp,
    DowngradeOps,
    DropIndexOp,
    DropTableOp,
    UpgradeOps,
)
from sqlalchemy import MetaData

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from sqlalchemy import Index, Table

__all__ = ["creating", "matching", "tables_of"]


def tables_of(metadata: MetaData | Sequence[MetaData] | None) -> list[Table]:
    """Return every table ``metadata`` defines, each after the tables it refers to."""
    if metadata is None:
        return []
    each = [metadata] if isinstance(metadata, MetaData) else metadata
    return [table for one in each for table in one.sorted_tables]


def matching(tables: Iterable[Table], patterns: Sequence[str]) -> list[Table]:
    """Return the ``tables`` whose name one of ``patterns`` finds; all of them with none."""
    if not patterns:
        return list(tables)
    compiled = [re.compile(pattern) for pattern in patterns]
    return [table for table in tables if any(each.search(table.name) for each in compiled)]


def creating(tables: Sequence[Table]) -> tuple[UpgradeOps, DowngradeOps]:
    """Return operations creating ``tables`` with their indexes, and dropping them again."""
    indexes = [index for table in tables for index in _indexes(table)]
    upgrade = UpgradeOps(
        [
            *(CreateTableOp.from_table(table) for table in tables),
            *(CreateIndexOp.from_index(index) for index in indexes),
        ],
    )
    downgrade = DowngradeOps(
        [
            *(DropIndexOp.from_index(index) for index in reversed(indexes)),
            *(DropTableOp.from_table(table) for table in reversed(tables)),
        ],
    )
    return upgrade, downgrade


def _indexes(table: Table) -> list[Index]:
    return sorted(table.indexes, key=lambda index: str(index.name))
