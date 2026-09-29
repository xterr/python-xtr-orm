"""Unit tests for ``orm:migrations:migrate``."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from xtr_console import ExitCode

from tests.support.console import output
from tests.support.database import rows, table_names
from tests.support.revisions import write_revision

if TYPE_CHECKING:
    from pathlib import Path

    from sqlalchemy.ext.asyncio import AsyncEngine
    from xtr_console import ApplicationTester

pytestmark = pytest.mark.anyio

VERSIONS = "select version_num from alembic_version order by version_num"


def _chain(directory: Path) -> None:
    _ = write_revision(directory, "a1", table="t_a1", message="first")
    _ = write_revision(directory, "b2", "a1", table="t_b2", message="second")


async def test_it_runs_every_new_revision(
    tester: ApplicationTester, migrations_directory: Path, engine: AsyncEngine
) -> None:
    _chain(migrations_directory)

    assert await tester.execute(["orm:migrations:migrate", "-n"]) == ExitCode.SUCCESS
    shown = output(tester)
    assert "++ migrated a1" in shown
    assert "++ migrated b2" in shown
    assert "2 migrations executed in" in shown
    assert await rows(engine, VERSIONS) == [("b2",)]


async def test_it_migrates_down_to_a_target(
    tester: ApplicationTester, migrations_directory: Path, engine: AsyncEngine
) -> None:
    _chain(migrations_directory)
    _ = await tester.execute(["orm:migrations:migrate", "-n"])

    assert await tester.execute(["orm:migrations:migrate", "first", "-n"]) == ExitCode.SUCCESS
    assert "-- reverted b2" in output(tester)
    assert await rows(engine, VERSIONS) == []


async def test_it_asks_before_changing_the_database(
    tester: ApplicationTester, migrations_directory: Path, engine: AsyncEngine
) -> None:
    _chain(migrations_directory)

    code = await tester.execute(["orm:migrations:migrate"], inputs=["n"])

    assert code == ExitCode.FAILURE
    assert "Migration cancelled!" in output(tester)
    assert "t_a1" not in await table_names(engine)


async def test_already_at_the_latest_version_it_says_so(
    tester: ApplicationTester, migrations_directory: Path
) -> None:
    _chain(migrations_directory)
    _ = await tester.execute(["orm:migrations:migrate", "-n"])

    assert await tester.execute(["orm:migrations:migrate", "-n"]) == ExitCode.SUCCESS
    assert 'Already at the latest version ("b2").' in output(tester)
    assert await tester.execute(["orm:migrations:migrate", "b2", "-n"]) == ExitCode.SUCCESS
    assert 'Already at "b2": no migrations to execute.' in output(tester)


async def test_a_dry_run_lists_and_runs_nothing(
    tester: ApplicationTester, migrations_directory: Path, engine: AsyncEngine
) -> None:
    _chain(migrations_directory)

    assert await tester.execute(["orm:migrations:migrate", "--dry-run"]) == ExitCode.SUCCESS
    shown = output(tester)
    assert "++ migrating a1 - first" in shown
    assert "Dry run: nothing was executed." in shown
    assert "t_a1" not in await table_names(engine)


async def test_the_sql_is_written_to_a_file_and_nothing_runs(
    tester: ApplicationTester, migrations_directory: Path, engine: AsyncEngine, tmp_path: Path
) -> None:
    _chain(migrations_directory)
    target = tmp_path / "out.sql"

    code = await tester.execute(["orm:migrations:migrate", "--write-sql", str(target)])

    assert code == ExitCode.SUCCESS
    assert "CREATE TABLE t_a1" in target.read_text(encoding="utf-8")
    assert "t_a1" not in await table_names(engine)


async def test_the_sql_written_to_a_directory_gets_a_dated_file(
    tester: ApplicationTester, migrations_directory: Path, tmp_path: Path
) -> None:
    _chain(migrations_directory)
    directory = tmp_path / "sql"
    directory.mkdir()

    code = await tester.execute(["orm:migrations:migrate", "--write-sql", str(directory)])

    assert code == ExitCode.SUCCESS
    [written] = directory.glob("migration_*.sql")
    assert "CREATE TABLE t_b2" in written.read_text(encoding="utf-8")


async def test_sql_that_cannot_be_written_fails_the_run(
    tester: ApplicationTester, migrations_directory: Path, tmp_path: Path
) -> None:
    _chain(migrations_directory)
    target = tmp_path / "missing" / "out.sql"

    code = await tester.execute(["orm:migrations:migrate", "--write-sql", str(target)])

    assert code == ExitCode.FAILURE
    assert str(target) in output(tester)


async def test_no_revision_at_all_fails_unless_allowed(tester: ApplicationTester) -> None:
    assert await tester.execute(["orm:migrations:migrate", "-n"]) == ExitCode.FAILURE
    assert "there are no revision files" in output(tester)

    code = await tester.execute(["orm:migrations:migrate", "-n", "--allow-no-migration"])
    assert code == ExitCode.SUCCESS
    assert "No migrations to execute." in output(tester)


async def test_applied_revisions_without_a_file_are_confirmed_first(
    tester: ApplicationTester, migrations_directory: Path
) -> None:
    _chain(migrations_directory)
    _ = write_revision(migrations_directory, "c3", "b2", table="t_c3")
    _ = await tester.execute(["orm:migrations:migrate", "-n"])
    (migrations_directory / "c3.py").unlink()

    code = await tester.execute(["orm:migrations:migrate"], inputs=["n"])

    assert code == ExitCode.FAILURE
    shown = output(tester)
    assert "1 applied revision has no revision file." in shown
    assert "Migration cancelled!" in shown


async def test_an_unknown_target_fails_the_run(
    tester: ApplicationTester, migrations_directory: Path
) -> None:
    _chain(migrations_directory)

    assert await tester.execute(["orm:migrations:migrate", "zz", "-n"]) == ExitCode.FAILURE
    assert 'Unknown version "zz"' in output(tester)
