"""Unit tests for ``orm:migrations:list``."""

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


async def test_every_revision_is_listed_with_its_status(
    tester: ApplicationTester, migrations_directory: Path
) -> None:
    _ = write_revision(migrations_directory, "a1", message="first")
    _ = write_revision(migrations_directory, "b2", "a1", message="second")
    _ = await tester.execute(["orm:migrations:migrate", "a1", "-n"])

    assert await tester.execute(["orm:migrations:list"]) == ExitCode.SUCCESS
    rows = table_rows(tester)
    assert rows[0] == [
        "Migration Versions",
        "Status",
        "Migrated At",
        "Execution Time",
        "Description",
    ]
    assert rows[1][:2] == ["a1", "migrated"]
    assert rows[1][2] != ""
    assert rows[1][3].endswith("s")
    assert rows[1][4] == "first"
    assert rows[2] == ["b2", "not migrated", "", "", "second"]


async def test_an_applied_revision_without_a_file_is_listed_last(
    tester: ApplicationTester, migrations_directory: Path
) -> None:
    _ = write_revision(migrations_directory, "a1")
    _ = await tester.execute(["orm:migrations:migrate", "-n"])
    (migrations_directory / "a1.py").unlink()

    assert await tester.execute(["orm:migrations:list"]) == ExitCode.SUCCESS
    assert table_rows(tester)[1][:2] == ["a1", "migrated, not available"]


@pytest.mark.filterwarnings("ignore:Revision missing referenced")
async def test_unreadable_revisions_fail_the_run(
    tester: ApplicationTester, migrations_directory: Path
) -> None:
    _ = write_revision(migrations_directory, "b2", "missing")

    assert await tester.execute(["orm:migrations:list"]) == ExitCode.FAILURE
    assert "has no revision file" in output(tester)
