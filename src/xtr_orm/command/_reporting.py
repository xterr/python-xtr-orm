"""How the orm commands report: the lines several of them print, written once.

Private to the package. A command imports what it prints from here; nothing
outside reads it, and the wording is free to change with the commands.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from xtr_console import ConsoleStyle, escape

if TYPE_CHECKING:
    from collections.abc import Sequence

    from xtr_orm.migrations import AvailableMigration, ExecutionResult, MigrationPlan, Migrator

__all__ = [
    "confirm_changes",
    "format_version",
    "report_count",
    "report_plan",
    "report_results",
    "report_written",
    "save_sql",
    "without_a_file",
]


def confirm_changes(io: ConsoleStyle, migrator: Migrator) -> bool:
    """Ask before a migration changes the database; a run asking nothing goes ahead."""
    return io.confirm(
        "WARNING! You are about to execute a migration on the "
        f'"{escape(migrator.name)}" connection that could result in schema changes and data '
        "loss. Are you sure you wish to continue?",
        default=True,
    )


def report_plan(io: ConsoleStyle, plans: Sequence[MigrationPlan]) -> None:
    """List what a dry run would do."""
    for plan in plans:
        verb = "++ migrating" if plan.direction.value == "up" else "-- reverting"
        io.text(f"  {verb} {escape(format_version(plan.version, plan.description))}")


def report_results(io: ConsoleStyle, results: Sequence[ExecutionResult]) -> None:
    """List what a migration did, each revision with the time it took."""
    for result in results:
        verb = "++ migrated" if result.direction.value == "up" else "-- reverted"
        io.text(f"  {verb} {escape(result.version)} ({result.duration:.3f}s)")


def save_sql(io: ConsoleStyle, target: str, sql: str) -> bool:
    """Write ``sql`` to ``target`` — a file, or a directory to put a dated file in.

    Returns whether it was written; when not, ``io`` says why.
    """
    path = Path(target)
    if path.is_dir():
        path /= f"migration_{datetime.now().astimezone():%Y%m%d%H%M%S}.sql"
    try:
        _ = path.write_text(sql, encoding="utf-8")
    except OSError as error:
        io.error(f'Could not write the migration SQL to "{escape(str(path))}": {error.strerror}')
        return False
    io.success(f'Wrote the migration SQL to "{escape(str(path))}".')
    return True


def report_written(
    io: ConsoleStyle, what: str, written: AvailableMigration, connection: str | None
) -> None:
    """Say where a new revision went, and how to run it alone and revert it."""
    option = f" --connection {escape(connection)}" if connection else ""
    version = escape(written.version)
    io.success(f'{what} "{escape(written.path)}"')
    io.text(
        "To run just this migration for testing purposes, you can use "
        f"orm:migrations:execute --up {version}{option}",
    )
    io.text(f"To revert the migration you can use orm:migrations:execute --down {version}{option}")


def report_count(io: ConsoleStyle, results: Sequence[ExecutionResult]) -> None:
    """Close a run with how many revisions ran, and how long they took together."""
    total = sum(result.duration for result in results)
    plural = "" if len(results) == 1 else "s"
    io.success(f"{len(results)} migration{plural} executed in {total:.3f}s.")


def without_a_file(count: int) -> str:
    """Say how many applied revisions have no revision file."""
    if count == 1:
        return "1 applied revision has no revision file."
    return f"{count} applied revisions have no revision file."


def format_version(version: str, description: str | None) -> str:
    """Render a version with its description, as the listing commands show it."""
    return f"{version}{_described(description)}"


def _described(description: str | None) -> str:
    return f" - {description}" if description else ""
