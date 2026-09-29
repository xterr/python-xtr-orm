"""Unit tests for ``orm:migrations:diff``."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from xtr_console import ExitCode

from tests.support.console import output

if TYPE_CHECKING:
    from pathlib import Path

    from xtr_console import ApplicationTester

pytestmark = pytest.mark.anyio

VERSIONS = "select version_num from alembic_version order by version_num"


async def test_it_writes_what_the_table_definitions_add(
    tester: ApplicationTester, migrations_directory: Path
) -> None:
    code = await tester.execute(["orm:migrations:diff", "--message", "catalogue"])

    assert code == ExitCode.SUCCESS
    [written] = migrations_directory.glob("*.py")
    assert "create_table" in written.read_text(encoding="utf-8")
    assert "Wrote the new revision to" in output(tester)


async def test_no_difference_fails_the_run_unless_allowed(tester: ApplicationTester) -> None:
    _ = await tester.execute(["orm:migrations:diff"])
    _ = await tester.execute(["orm:migrations:migrate", "-n"])

    assert await tester.execute(["orm:migrations:diff"]) == ExitCode.FAILURE
    assert "Nothing differs between the database and the table definitions." in output(tester)
    assert await tester.execute(["orm:migrations:diff", "--allow-empty-diff"]) == ExitCode.SUCCESS


async def test_from_an_empty_schema_it_writes_every_table(
    tester: ApplicationTester, migrations_directory: Path
) -> None:
    _ = await tester.execute(["orm:migrations:diff"])
    _ = await tester.execute(["orm:migrations:migrate", "-n"])

    code = await tester.execute(["orm:migrations:diff", "--from-empty-schema", "--message", "all"])

    assert code == ExitCode.SUCCESS
    [written] = migrations_directory.glob("*_all.py")
    assert "create_table" in written.read_text(encoding="utf-8")


async def test_a_database_behind_its_revisions_fails_the_run(tester: ApplicationTester) -> None:
    _ = await tester.execute(["orm:migrations:diff"])

    assert await tester.execute(["orm:migrations:diff"]) == ExitCode.FAILURE
    assert "not up to date" in output(tester)
