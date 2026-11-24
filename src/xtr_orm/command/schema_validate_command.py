"""``orm:schema:validate``: check the mapping and the schema against the table definitions."""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING, Final, final

from sqlalchemy import MetaData
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import configure_mappers
from xtr_console import ConsoleStyle, ExitCode, Verbosity, as_command, escape

from xtr_orm.exception import MigrationError

from .connection_command import ConnectionCommand

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = ["SchemaValidateCommand"]

_INVALID_MAPPING: Final = 1
"""The exit-code part of a mapping that does not validate."""
_OUT_OF_SYNC: Final = 2
"""The exit-code part of a schema not matching the table definitions."""


@as_command("orm:schema:validate")
@final
class SchemaValidateCommand(ConnectionCommand):
    """Checks the mapping and the database schema against the table definitions."""

    __slots__ = ()

    async def __call__(
        self,
        io: ConsoleStyle,
        *,
        skip_mapping: bool = False,
        skip_sync: bool = False,
        connection: str | None = None,
    ) -> int:
        """Check the mapping and the database schema; the exit code says what failed.

        The mapping check runs ``configure_mappers()`` — which configures
        every mapper in the process, not only this connection's — and names
        the tables the definitions hold more than once. The sync check
        compares the database with the table definitions as it is — the
        revisions it is at play no part — and, when they differ, shows the
        statements bringing it in sync at ``-v``. Each failing check adds to
        the exit code: 1 for the mapping, 2 for the schema — 3 for both.

        Args:
            io: Where the command writes.
            skip_mapping: Check the database schema only.
            skip_sync: Check the mapping only.
            connection: The connection to validate; the default one when
                left out.
        """
        migrator = await self._migrator(io, connection)
        if migrator is None:
            return ExitCode.FAILURE
        code = 0
        if not skip_mapping:
            valid = True
            for name in _duplicated_tables(migrator.metadata):
                io.error(escape(f'The table definitions name "{name}" more than once.'))
                valid = False
            try:
                configure_mappers()
            except SQLAlchemyError as error:
                io.error(escape(f"The mapping does not configure: {error}"))
                valid = False
            if valid:
                io.success("The mapping is valid.")
            else:
                code += _INVALID_MAPPING
        if not skip_sync:
            name = escape(self._name(connection))
            try:
                comparison = await migrator.compare()
            except MigrationError as error:
                io.error(escape(error.reason))
                code += _OUT_OF_SYNC
            else:
                if comparison.is_empty:
                    io.success(
                        f'The "{name}" connection\'s database schema is in sync '
                        "with the table definitions."
                    )
                else:
                    io.error(
                        f'The "{name}" connection\'s database schema is not in sync '
                        "with the table definitions."
                    )
                    code += _OUT_OF_SYNC
                    io.text(
                        escape(await migrator.apply_sql(comparison)),
                        verbosity=Verbosity.VERBOSE,
                    )
        return code


def _duplicated_tables(metadata: MetaData | Sequence[MetaData] | None) -> list[str]:
    """Return the qualified names the definitions hold more than once, sorted."""
    # Branching the union mirrors migrations/_schema.tables_of, which stays
    # private to its subpackage rather than widening the public API for these
    # three lines.
    each = [metadata] if isinstance(metadata, MetaData) else metadata or ()
    counts = Counter(table.fullname for one in each for table in one.sorted_tables)
    return sorted(name for name, count in counts.items() if count > 1)
