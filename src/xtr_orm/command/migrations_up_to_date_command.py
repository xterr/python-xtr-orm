"""``orm:migrations:up-to-date``: whether every revision is applied."""

from __future__ import annotations

from typing import Annotated, Final, final

from xtr_console import ConsoleStyle, ExitCode, Option, as_command, escape

from xtr_orm.exception import MigrationError

from .connection_command import ConnectionCommand

__all__ = ["MigrationsUpToDateCommand"]

_UNREGISTERED: Final = 2
"""The exit code for applied revisions without a file, with --fail-on-unregistered."""


@as_command("orm:migrations:up-to-date")
@final
class MigrationsUpToDateCommand(ConnectionCommand):
    """Tells you if your schema is up-to-date."""

    __slots__ = ()

    async def __call__(
        self,
        io: ConsoleStyle,
        *,
        fail_on_unregistered: Annotated[bool, Option(alias="-u")] = False,
        list_migrations: Annotated[bool, Option(alias="-l")] = False,
        connection: str | None = None,
    ) -> int:
        """Tell whether every revision is applied, exiting 1 when some are not.

        Applied revisions whose file is gone are reported too, and exit 2 with
        --fail-on-unregistered.

        Args:
            io: Where the command writes.
            fail_on_unregistered: Fail when applied revisions have no file.
            list_migrations: List the revisions not applied, and the applied
                ones without a file.
            connection: The connection to read; the default one when left out.
        """
        migrator = await self._migrator(io, connection)
        if migrator is None:
            return ExitCode.FAILURE
        try:
            status = await migrator.status()
        except MigrationError as error:
            io.error(escape(error.reason))
            return ExitCode.FAILURE
        new = len(status.new)
        unregistered = len(status.executed_unavailable)
        if not new and not unregistered:
            io.success("Up-to-date! No migrations to execute.")
            return ExitCode.SUCCESS
        code: int = ExitCode.SUCCESS
        if new:
            are = " is" if new == 1 else "s are"
            io.error(f"Out-of-date! {new} migration{are} available to execute.")
            code = ExitCode.FAILURE
        if unregistered:
            io.error(
                f"You have {unregistered} previously executed "
                f"migration{'' if unregistered == 1 else 's'} in the database that "
                f"{'is not a' if unregistered == 1 else 'are not'} registered "
                f"migration{'' if unregistered == 1 else 's'}.",
            )
            if fail_on_unregistered:
                code = _UNREGISTERED
        if list_migrations:
            rows = [
                [escape(each.version), "not migrated", escape(each.description)]
                for each in status.new
            ]
            rows += [
                [escape(each.version), "migrated, not available", ""]
                for each in status.executed_unavailable
            ]
            io.table(["Migration Versions", "Status", "Description"], rows)
        return code
