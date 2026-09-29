"""``orm:migrations:diff``: write a revision from what the table definitions add."""

from __future__ import annotations

from typing import final

from xtr_console import ConsoleStyle, ExitCode, as_command, escape

from xtr_orm.exception import MigrationError

from .connection_command import ConnectionCommand, report_written

__all__ = ["MigrationsDiffCommand"]


@as_command("orm:migrations:diff")
@final
class MigrationsDiffCommand(ConnectionCommand):
    """Writes a revision of what differs between the database and the table definitions."""

    __slots__ = ()

    async def __call__(
        self,
        io: ConsoleStyle,
        *,
        message: str | None = None,
        allow_empty_diff: bool = False,
        from_empty_schema: bool = False,
        connection: str | None = None,
    ) -> int:
        """Compare the database with the table definitions, and write what differs as a revision.

        The database must be at the latest revisions, so the comparison sees
        what they leave out rather than what is not applied yet.

        Args:
            io: Where the command writes.
            message: What the revision does; it names the file too.
            allow_empty_diff: Write a revision even when nothing differs.
            from_empty_schema: Write every table, as if the database were
                empty.
            connection: The connection to compare; the default one when left
                out.
        """
        migrator = await self._migrator(io, connection)
        if migrator is None:
            return ExitCode.FAILURE
        try:
            written = await migrator.diff(
                message, allow_empty=allow_empty_diff, from_empty_schema=from_empty_schema
            )
        except MigrationError as error:
            io.error(escape(error.reason))
            return ExitCode.FAILURE
        if written is None:
            io.error("Nothing differs between the database and the table definitions.")
            return ExitCode.FAILURE
        report_written(io, "Wrote the new revision to", written, connection)
        return ExitCode.SUCCESS
