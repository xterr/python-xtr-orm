"""``orm:migrations:version``: record revisions as applied or not, without running them."""

from __future__ import annotations

from typing import Annotated, final

from xtr_console import ConsoleStyle, ExitCode, Option, as_command, escape

from xtr_orm.exception import MigrationError

from .connection_command import ConnectionCommand

__all__ = ["MigrationsVersionCommand"]


@as_command("orm:migrations:version")
@final
class MigrationsVersionCommand(ConnectionCommand):
    """Manually add and delete migration versions from the version table."""

    __slots__ = ()

    async def __call__(  # noqa: PLR0911 — each way out says why it stopped
        self,
        io: ConsoleStyle,
        version: str | None = None,
        *,
        add: bool = False,
        delete: bool = False,
        all_versions: Annotated[bool, Option(name="--all")] = False,
        connection: str | None = None,
    ) -> int:
        """Record the version as applied (--add) or not (--delete), running nothing.

        Adding, the revision must follow only applied ones; deleting, no
        applied revision may follow it. An applied revision whose file is gone
        can always be deleted. With --all, every revision is added, or every
        record deleted.

        Args:
            io: Where the command writes.
            version: The revision to record, by full or partial id.
            add: Record it as applied.
            delete: Record it as not applied.
            all_versions: Every revision, instead of one.
            connection: The connection to record on; the default one when left
                out.
        """
        if add == delete:
            io.error(
                "You must specify whether you want to --add or --delete the specified version."
            )
            return ExitCode.INVALID
        if (version is None) == (not all_versions):
            io.error("You must specify the version or use the --all argument, not both.")
            return ExitCode.INVALID
        migrator = await self._migrator(io, connection)
        if migrator is None:
            return ExitCode.FAILURE
        if not io.confirm(
            "WARNING! You are about to add, delete or synchronize migration versions from the "
            "version table that could result in data lost. Are you sure you wish to continue?",
            default=True,
        ):
            io.error("Migration cancelled!")
            return ExitCode.FAILURE
        try:
            if add:
                done = await (
                    migrator.add_versions([version])
                    if version is not None
                    else migrator.add_all_versions()
                )
            elif version is not None:
                done = await migrator.delete_versions([version])
            else:
                await migrator.delete_all_versions()
                io.success("Every version was deleted from the version table.")
                return ExitCode.SUCCESS
        except MigrationError as error:
            io.error(escape(error.reason))
            return ExitCode.FAILURE
        verb = "Added" if add else "Deleted"
        for each in done:
            io.text(f"  {verb} {escape(each)}")
        plural = "" if len(done) == 1 else "s"
        where = "to" if add else "from"
        io.success(f"{verb} {len(done)} version{plural} {where} the version table.")
        return ExitCode.SUCCESS
