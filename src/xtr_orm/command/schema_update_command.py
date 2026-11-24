"""``orm:schema:update``: bring the database schema to the table definitions, without a revision."""

from __future__ import annotations

from typing import Annotated, final

from sqlalchemy.exc import SQLAlchemyError
from xtr_console import ConsoleStyle, ExitCode, Option, as_command, escape

from xtr_orm.exception import MigrationError

from .connection_command import ConnectionCommand

__all__ = ["SchemaUpdateCommand"]


@as_command("orm:schema:update")
@final
class SchemaUpdateCommand(ConnectionCommand):
    """Brings the database schema to the table definitions, without a revision."""

    __slots__ = ()

    async def __call__(  # noqa: PLR0911 — each way out says why it stopped
        self,
        io: ConsoleStyle,
        *,
        dump_sql: bool = False,
        force: Annotated[bool, Option(alias="-f")] = False,
        connection: str | None = None,
    ) -> int:
        """Compare the database with the table definitions, and print or run what differs.

        The database is compared as it is — the revisions it is at play no
        part — and nothing is written or recorded: no revision file, no row
        in the version or history tables. Tables the database has but the
        definitions do not are dropped; MigrationsConfig.include_object is
        the escape hatch keeping them.

        Args:
            io: Where the command writes.
            dump_sql: Print the statements bringing the database in sync,
                and run nothing.
            force: Run the statements.
            connection: The connection to update; the default one when left
                out.
        """
        migrator = await self._migrator(io, connection)
        if migrator is None:
            return ExitCode.FAILURE
        try:
            comparison = await migrator.compare()
        except MigrationError as error:
            io.error(escape(error.reason))
            return ExitCode.FAILURE
        name = escape(self._name(connection))
        if comparison.is_empty:
            io.success(
                f'Nothing to update: the "{name}" connection\'s database schema is in sync '
                "with the table definitions."
            )
            return ExitCode.SUCCESS
        changes = comparison.changes
        plural = "" if changes == 1 else "s"
        if dump_sql:
            io.text(escape(await migrator.apply_sql(comparison)))
        if force:
            try:
                await migrator.apply(comparison)
            except (MigrationError, SQLAlchemyError) as error:
                io.error(
                    f'Could not update the "{name}" connection\'s database schema: '
                    f"{escape(str(error))}"
                )
                return ExitCode.FAILURE
            io.success(
                f'Updated the "{name}" connection\'s database schema: '
                f"{changes} change{plural} applied."
            )
            return ExitCode.SUCCESS
        if dump_sql:
            return ExitCode.SUCCESS
        lines = [
            "This operation should not be executed in a production environment.",
            (
                f'The "{name}" connection\'s database schema is not in sync with the '
                f"table definitions: {changes} change{plural} would bring it in sync."
            ),
        ]
        if comparison.dropped_tables:
            dropped = ", ".join(f'"{escape(each)}"' for each in comparison.dropped_tables)
            lines.append(
                f"The tables the database has but the definitions do not would be "
                f"dropped: {dropped}."
            )
        lines.append("Re-run with --dump-sql to see the statements, or with --force to run them.")
        io.caution("\n".join(lines))
        return ExitCode.FAILURE
