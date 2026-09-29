"""Unit tests for ``orm:migrations:execute``."""

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


async def test_it_runs_exactly_the_versions_given(
    tester: ApplicationTester, migrations_directory: Path, engine: AsyncEngine
) -> None:
    _chain(migrations_directory)

    assert await tester.execute(["orm:migrations:execute", "a1", "-n"]) == ExitCode.SUCCESS
    assert "++ migrated a1" in output(tester)
    assert "1 migration executed in" in output(tester)
    assert await rows(engine, VERSIONS) == [("a1",)]
    assert "t_b2" not in await table_names(engine)


async def test_it_runs_a_downgrade_alone(
    tester: ApplicationTester, migrations_directory: Path, engine: AsyncEngine
) -> None:
    _chain(migrations_directory)
    _ = await tester.execute(["orm:migrations:migrate", "-n"])

    code = await tester.execute(["orm:migrations:execute", "b2", "--down", "-n"])

    assert code == ExitCode.SUCCESS
    assert "-- reverted b2" in output(tester)
    assert await rows(engine, VERSIONS) == [("a1",)]


async def test_a_version_out_of_order_fails_the_run(
    tester: ApplicationTester, migrations_directory: Path
) -> None:
    _chain(migrations_directory)

    assert await tester.execute(["orm:migrations:execute", "b2", "-n"]) == ExitCode.FAILURE
    assert 'The version "b2" follows "a1", which is not applied.' in output(tester)


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (["a1", "--up", "--down"], "Give --up or --down, not both."),
        ([], "Name at least one version to execute."),
    ],
)
async def test_a_command_line_that_cannot_be_run_is_refused(
    tester: ApplicationTester, arguments: list[str], message: str
) -> None:
    assert await tester.execute(["orm:migrations:execute", *arguments]) == ExitCode.INVALID
    assert message in output(tester)


async def test_it_asks_before_changing_the_database(
    tester: ApplicationTester, migrations_directory: Path, engine: AsyncEngine
) -> None:
    _chain(migrations_directory)

    assert await tester.execute(["orm:migrations:execute", "a1"], inputs=["n"]) == (
        ExitCode.FAILURE
    )
    assert "t_a1" not in await table_names(engine)


async def test_a_dry_run_lists_and_runs_nothing(
    tester: ApplicationTester, migrations_directory: Path, engine: AsyncEngine
) -> None:
    _chain(migrations_directory)

    code = await tester.execute(["orm:migrations:execute", "a1", "b2", "--dry-run"])

    assert code == ExitCode.SUCCESS
    assert "++ migrating a1 - first ++ migrating b2 - second" in output(tester)
    assert "t_a1" not in await table_names(engine)


async def test_a_dry_run_names_the_revision_a_partial_id_stands_for(
    tester: ApplicationTester, migrations_directory: Path
) -> None:
    _ = write_revision(migrations_directory, "ae1027a6acf", table="t_x", message="first")

    code = await tester.execute(["orm:migrations:execute", "ae10", "--dry-run"])

    assert code == ExitCode.SUCCESS
    assert "++ migrating ae1027a6acf - first" in output(tester)


async def test_a_dry_run_of_a_version_out_of_order_fails(
    tester: ApplicationTester, migrations_directory: Path
) -> None:
    _chain(migrations_directory)

    code = await tester.execute(["orm:migrations:execute", "b2", "--dry-run"])

    assert code == ExitCode.FAILURE
    assert 'The version "b2" follows "a1", which is not applied.' in output(tester)


async def test_the_sql_is_written_to_a_file_and_nothing_runs(
    tester: ApplicationTester, migrations_directory: Path, engine: AsyncEngine, tmp_path: Path
) -> None:
    _chain(migrations_directory)
    target = tmp_path / "out.sql"

    code = await tester.execute(["orm:migrations:execute", "a1", "--write-sql", str(target)])

    assert code == ExitCode.SUCCESS
    assert "CREATE TABLE t_a1" in target.read_text(encoding="utf-8")
    assert "t_a1" not in await table_names(engine)


async def test_sql_that_cannot_be_written_fails_the_run(
    tester: ApplicationTester, migrations_directory: Path, tmp_path: Path
) -> None:
    _chain(migrations_directory)
    target = tmp_path / "missing" / "out.sql"

    code = await tester.execute(["orm:migrations:execute", "a1", "--write-sql", str(target)])

    assert code == ExitCode.FAILURE
    assert str(target) in output(tester)
