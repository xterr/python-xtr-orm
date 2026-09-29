"""Unit tests for ``orm:migrations:generate``."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from xtr_console import ExitCode

from tests.support.console import output
from tests.support.revisions import write_revision

if TYPE_CHECKING:
    from pathlib import Path

    from xtr_console import ApplicationTester

pytestmark = pytest.mark.anyio

VERSIONS = "select version_num from alembic_version order by version_num"


async def test_it_writes_an_empty_revision_and_says_how_to_run_it(
    tester: ApplicationTester, migrations_directory: Path
) -> None:
    code = await tester.execute(["orm:migrations:generate", "--message", "add prices"])

    assert code == ExitCode.SUCCESS
    [written] = migrations_directory.glob("*.py")
    shown = output(tester)
    assert f'Wrote the new revision to "{written}"' in shown
    assert "orm:migrations:execute --up" in shown
    assert "orm:migrations:execute --down" in shown
    assert written.name.endswith("_add_prices.py")


async def test_it_names_the_connection_in_its_advice(tester: ApplicationTester) -> None:
    code = await tester.execute(["orm:migrations:generate", "--connection", "default"])

    assert code == ExitCode.SUCCESS
    assert "--connection default" in output(tester)


async def test_several_latest_revisions_fail_the_run(
    tester: ApplicationTester, migrations_directory: Path
) -> None:
    _ = write_revision(migrations_directory, "a1")
    _ = write_revision(migrations_directory, "left", "a1")
    _ = write_revision(migrations_directory, "right", "a1")

    assert await tester.execute(["orm:migrations:generate"]) == ExitCode.FAILURE
    assert "Multiple heads" in output(tester)
