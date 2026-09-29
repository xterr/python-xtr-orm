"""Unit tests for ``orm:migrations:current``."""

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


async def test_it_prints_base_before_any_revision_is_applied(tester: ApplicationTester) -> None:
    assert await tester.execute(["orm:migrations:current"]) == ExitCode.SUCCESS
    assert output(tester) == "base"


async def test_it_prints_the_current_revision_with_its_description(
    tester: ApplicationTester, migrations_directory: Path
) -> None:
    _ = write_revision(migrations_directory, "a1", message="create things")
    _ = await tester.execute(["orm:migrations:migrate", "-n"])

    assert await tester.execute(["orm:migrations:current"]) == ExitCode.SUCCESS
    assert output(tester) == "a1 - create things"


async def test_a_current_revision_without_a_file_is_marked(
    tester: ApplicationTester, migrations_directory: Path
) -> None:
    path = write_revision(migrations_directory, "a1")
    _ = await tester.execute(["orm:migrations:migrate", "-n"])
    path.unlink()

    assert await tester.execute(["orm:migrations:current"]) == ExitCode.SUCCESS
    assert output(tester) == "a1 - (not available)"


@pytest.mark.filterwarnings("ignore:Revision missing referenced")
async def test_unreadable_revisions_fail_the_run(
    tester: ApplicationTester, migrations_directory: Path
) -> None:
    _ = write_revision(migrations_directory, "b2", "missing")

    assert await tester.execute(["orm:migrations:current"]) == ExitCode.FAILURE
    assert "has no revision file" in output(tester)
