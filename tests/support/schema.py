"""The table definitions the tests migrate towards: two tables, a foreign key, an index."""

from __future__ import annotations

from sqlalchemy import Column, ForeignKey, Integer, MetaData, String, Table

METADATA = MetaData()

AUTHOR = Table(
    "author",
    METADATA,
    Column("id", Integer, primary_key=True),
    Column("name", String(100), nullable=False),
)

BOOK = Table(
    "book",
    METADATA,
    Column("id", Integer, primary_key=True),
    Column("title", String(200), nullable=False, index=True),
    Column("author_id", Integer, ForeignKey("author.id"), nullable=False),
)
