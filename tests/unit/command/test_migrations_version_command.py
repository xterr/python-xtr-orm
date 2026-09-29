"""Unit tests for ``orm:migrations:version``."""

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
    _ = write_revision(directory, "a1", table="t_a1")
    _ = write_revision(directory, "b2", "a1", table="t_b2")


async def test_it_adds_a_version_without_running_it(
    tester: ApplicationTester, migrations_directory: Path, engine: AsyncEngine
) -> None:
    _chain(migrations_directory)

    assert await tester.execute(["orm:migrations:version", "a1", "--add", "-n"]) == (
        ExitCode.SUCCESS
    )
    assert "Added 1 version to the version table." in output(tester)
    assert await rows(engine, VERSIONS) == [("a1",)]
    assert "t_a1" not in await table_names(engine)


async def test_it_deletes_a_version_without_running_it(
    tester: ApplicationTester, migrations_directory: Path, engine: AsyncEngine
) -> None:
    _chain(migrations_directory)
    _ = await tester.execute(["orm:migrations:migrate", "-n"])

    assert await tester.execute(["orm:migrations:version", "b2", "--delete", "-n"]) == (
        ExitCode.SUCCESS
    )
    assert "Deleted b2" in output(tester)
    assert await rows(engine, VERSIONS) == [("a1",)]
    assert "t_b2" in await table_names(engine)


async def test_it_adds_and_deletes_every_version(
    tester: ApplicationTester, migrations_directory: Path, engine: AsyncEngine
) -> None:
    _chain(migrations_directory)

    assert await tester.execute(["orm:migrations:version", "--all", "--add", "-n"]) == (
        ExitCode.SUCCESS
    )
    assert "Added 2 versions" in output(tester)
    assert await rows(engine, VERSIONS) == [("b2",)]

    assert await tester.execute(["orm:migrations:version", "--all", "--delete", "-n"]) == (
        ExitCode.SUCCESS
    )
    assert "Every version was deleted from the version table." in output(tester)
    assert await rows(engine, VERSIONS) == []


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (["a1"], "--add or --delete"),
        (["a1", "--add", "--delete"], "--add or --delete"),
        (["--add"], "the version or use the --all argument"),
        (["a1", "--all", "--add"], "the version or use the --all argument"),
    ],
)
async def test_a_command_line_that_cannot_be_run_is_refused(
    tester: ApplicationTester, arguments: list[str], message: str
) -> None:
    assert await tester.execute(["orm:migrations:version", *arguments]) == ExitCode.INVALID
    assert message in output(tester)


async def test_it_asks_before_changing_the_version_table(
    tester: ApplicationTester, migrations_directory: Path, engine: AsyncEngine
) -> None:
    _chain(migrations_directory)

    code = await tester.execute(["orm:migrations:version", "a1", "--add"], inputs=["n"])

    assert code == ExitCode.FAILURE
    assert "alembic_version" not in await table_names(engine)


async def test_a_version_out_of_order_fails_the_run(
    tester: ApplicationTester, migrations_directory: Path
) -> None:
    _chain(migrations_directory)

    assert await tester.execute(["orm:migrations:version", "b2", "--add", "-n"]) == (
        ExitCode.FAILURE
    )
    assert 'follows "a1", which is not applied' in output(tester)
