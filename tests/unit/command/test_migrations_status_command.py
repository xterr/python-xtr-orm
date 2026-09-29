"""Unit tests for ``orm:migrations:status``."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from xtr_console import ExitCode

from tests.support.console import output, table_rows
from tests.support.revisions import write_revision

if TYPE_CHECKING:
    from pathlib import Path

    from xtr_console import ApplicationTester

pytestmark = pytest.mark.anyio


async def test_it_shows_where_the_database_stands(
    tester: ApplicationTester, migrations_directory: Path
) -> None:
    for version, down in (("a1", None), ("b2", "a1"), ("c3", "b2")):
        _ = write_revision(migrations_directory, version, down)
    _ = await tester.execute(["orm:migrations:migrate", "b2", "-n"])

    assert await tester.execute(["orm:migrations:status"]) == ExitCode.SUCCESS
    shown = {row[1]: row[2] for row in table_rows(tester)[1:]}
    assert shown["Version table"] == "alembic_version"
    assert shown["History table"] == "alembic_version_history"
    assert shown["Connection"] == "default"
    assert shown["Driver"] == "sqlite+aiosqlite"
    assert (shown["Previous"], shown["Current"], shown["Next"], shown["Latest"]) == (
        "a1",
        "b2",
        "c3",
        "c3",
    )
    assert (shown["Executed"], shown["Executed Unavailable"]) == ("2", "0")
    assert (shown["Available"], shown["New"]) == ("3", "1")
    assert shown[""] == str(migrations_directory)


async def test_nothing_applied_reads_as_base(tester: ApplicationTester) -> None:
    assert await tester.execute(["orm:migrations:status"]) == ExitCode.SUCCESS
    shown = {row[1]: row[2] for row in table_rows(tester)[1:]}
    assert (shown["Previous"], shown["Current"], shown["Next"], shown["Latest"]) == (
        "none",
        "base",
        "none",
        "base",
    )


@pytest.mark.filterwarnings("ignore:Revision missing referenced")
async def test_unreadable_revisions_fail_the_run(
    tester: ApplicationTester, migrations_directory: Path
) -> None:
    _ = write_revision(migrations_directory, "b2", "missing")

    assert await tester.execute(["orm:migrations:status"]) == ExitCode.FAILURE
    assert "has no revision file" in output(tester)
