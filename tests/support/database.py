"""Reading a test database back: its tables, and the rows a query finds."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import inspect, text

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine


async def table_names(engine: AsyncEngine) -> set[str]:
    """Every table the database has."""
    async with engine.connect() as connection:
        return set(await connection.run_sync(lambda sync: inspect(sync).get_table_names()))


async def rows(engine: AsyncEngine, sql: str) -> list[tuple[object, ...]]:
    """Every row ``sql`` reads, as plain tuples."""
    async with engine.connect() as connection:
        result = await connection.execute(text(sql))
        return [tuple(row) for row in result.all()]
