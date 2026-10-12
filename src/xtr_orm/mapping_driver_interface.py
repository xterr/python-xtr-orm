"""What a library hands over to have the tables it builds in code migrated with a connection."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from sqlalchemy import MetaData

__all__ = ["MappingDriverInterface"]


@runtime_checkable
class MappingDriverInterface(Protocol):
    """Tables a library builds once its own configuration is read.

    A library shipping tables an application names — a prefix, which of them
    it keeps, which column type an identifier gets — cannot declare them when
    it is imported: it knows them only once configured. A driver is that
    build behind one call, so the tables can join the definitions of whichever
    connection the application picked.
    """

    def load_metadata(self, metadata: MetaData, /) -> tuple[str, ...]:
        """Add this driver's tables to ``metadata``, and return the names added.

        **Must be idempotent.** The definitions a connection migrates towards
        are often shared for the whole process — the ones advanced-alchemy
        registers per bind key are — so a driver may be loaded into the same
        ``MetaData`` twice: by a second kernel in one test run, or by a second
        library mapping the same table. Skip every name already in
        ``metadata.tables`` and leave it out of what is returned, so the
        second load changes nothing and says so.

        The argument is passed positionally, so an implementation may name it
        whatever reads best.
        """
        ...
