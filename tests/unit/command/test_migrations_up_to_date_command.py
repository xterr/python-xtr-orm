"""Unit tests for ``orm:migrations:up-to-date``."""

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


async def test_an_up_to_date_database_succeeds(
    tester: ApplicationTester, migrations_directory: Path
) -> None:
    _ = write_revision(migrations_directory, "a1")
    _ = await tester.execute(["orm:migrations:migrate", "-n"])

    assert await tester.execute(["orm:migrations:up-to-date"]) == ExitCode.SUCCESS
    assert "Up-to-date! No migrations to execute." in output(tester)


async def test_new_revisions_fail_the_run(
    tester: ApplicationTester, migrations_directory: Path
) -> None:
    _ = write_revision(migrations_directory, "a1")
    _ = write_revision(migrations_directory, "b2", "a1", message="second")

    assert await tester.execute(["orm:migrations:up-to-date", "-l"]) == ExitCode.FAILURE
    assert "Out-of-date! 2 migrations are available to execute." in output(tester)
    assert ["b2", "not migrated", "second"] in table_rows(tester)


async def test_one_new_revision_is_counted_in_the_singular(
    tester: ApplicationTester, migrations_directory: Path
) -> None:
    _ = write_revision(migrations_directory, "a1")

    assert await tester.execute(["orm:migrations:up-to-date"]) == ExitCode.FAILURE
    assert "Out-of-date! 1 migration is available to execute." in output(tester)


@pytest.mark.parametrize(("flags", "code"), [([], ExitCode.SUCCESS), (["-u"], 2)])
async def test_applied_revisions_without_a_file_fail_only_when_asked(
    tester: ApplicationTester, migrations_directory: Path, flags: list[str], code: int
) -> None:
    _ = write_revision(migrations_directory, "a1")
    _ = await tester.execute(["orm:migrations:migrate", "-n"])
    (migrations_directory / "a1.py").unlink()

    assert await tester.execute(["orm:migrations:up-to-date", "--list-migrations", *flags]) == code
    assert (
        "You have 1 previously executed migration in the database that is not a registered "
        "migration."
    ) in output(tester)
    assert ["a1", "migrated, not available", ""] in table_rows(tester)


@pytest.mark.filterwarnings("ignore:Revision missing referenced")
async def test_unreadable_revisions_fail_the_run(
    tester: ApplicationTester, migrations_directory: Path
) -> None:
    _ = write_revision(migrations_directory, "b2", "missing")

    assert await tester.execute(["orm:migrations:up-to-date"]) == ExitCode.FAILURE
    assert "has no revision file" in output(tester)
