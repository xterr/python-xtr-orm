"""A mapping driver a test hands over: one table per name it was built with, added once."""

from __future__ import annotations

from typing import TYPE_CHECKING, final

from sqlalchemy import Column, Integer, String, Table

if TYPE_CHECKING:
    from sqlalchemy import MetaData

__all__ = ["TableDriver"]


@final
class TableDriver:
    """Adds a table per name, skipping every one the definitions already hold.

    Stands in for the real thing a library ships: tables built in code once
    its configuration is read, rather than declared at import time.
    """

    __slots__ = ("_names",)

    def __init__(self, *names: str) -> None:
        """Add a table per name of ``names``, in that order."""
        self._names = names

    def load_metadata(self, metadata: MetaData, /) -> tuple[str, ...]:
        """Add the tables ``metadata`` does not hold yet, and name them."""
        added: list[str] = []
        for name in self._names:
            if name in metadata.tables:
                continue
            _ = Table(
                name,
                metadata,
                Column("id", Integer, primary_key=True),
                Column("label", String(100), nullable=False),
            )
            added.append(name)
        return tuple(added)
