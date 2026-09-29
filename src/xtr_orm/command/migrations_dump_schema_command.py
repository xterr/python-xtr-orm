"""``orm:migrations:dump-schema``: write a first revision from an existing database."""

from __future__ import annotations

from typing import final

from xtr_console import ConsoleStyle, ExitCode, as_command, escape

from xtr_orm.exception import MigrationError

from .connection_command import ConnectionCommand, report_written

__all__ = ["MigrationsDumpSchemaCommand"]


@as_command("orm:migrations:dump-schema")
@final
class MigrationsDumpSchemaCommand(ConnectionCommand):
    """Dump the schema for your database to a migration."""

    __slots__ = ()

    async def __call__(
        self,
        io: ConsoleStyle,
        *,
        message: str | None = None,
        filter_tables: list[str] | None = None,
        connection: str | None = None,
    ) -> int:
        """Write a first revision creating every table the database has.

        For a database that predates its revisions, so there must be none
        yet. The revision is written, not applied: record it as applied with
        orm:migrations:rollup.

        Args:
            io: Where the command writes.
            message: What the revision does; it names the file too.
            filter_tables: A regular expression; only the tables whose name it
                finds are dumped. Repeat for several.
            connection: The connection whose database to dump; the default one
                when left out.
        """
        migrator = await self._migrator(io, connection)
        if migrator is None:
            return ExitCode.FAILURE
        try:
            written = await migrator.dump_schema(message, table_filters=filter_tables or ())
        except MigrationError as error:
            io.error(escape(error.reason))
            return ExitCode.FAILURE
        report_written(io, "Dumped your schema to a new migration class at", written, connection)
        option = f" --connection {escape(connection)}" if connection else ""
        io.text(f"To use this as a rollup migration you can use orm:migrations:rollup{option}")
        return ExitCode.SUCCESS
