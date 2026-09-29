"""Unit tests for ``orm:database:drop``."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from xtr_console import ExitCode

from tests.support.console import output

if TYPE_CHECKING:
    from pathlib import Path

    from xtr_console import ApplicationTester

pytestmark = pytest.mark.anyio


async def test_it_refuses_without_force(tester: ApplicationTester, tmp_path: Path) -> None:
    _ = await tester.execute(["orm:database:create"])

    assert await tester.execute(["orm:database:drop"]) == ExitCode.INVALID
    assert "with --force to drop it" in output(tester)
    assert (tmp_path / "app.sqlite").exists()


async def test_it_drops_the_database_with_force(tester: ApplicationTester, tmp_path: Path) -> None:
    _ = await tester.execute(["orm:database:create"])

    assert await tester.execute(["orm:database:drop", "--force"]) == ExitCode.SUCCESS
    assert "Dropped database" in output(tester)
    assert not (tmp_path / "app.sqlite").exists()


async def test_a_missing_database_is_skipped_when_asked(tester: ApplicationTester) -> None:
    assert await tester.execute(["orm:database:drop", "-f", "--if-exists"]) == ExitCode.SUCCESS
    assert "does not exist. Skipped." in output(tester)


async def test_a_missing_database_fails_the_run(tester: ApplicationTester) -> None:
    assert await tester.execute(["orm:database:drop", "--force"]) == ExitCode.FAILURE
    assert "Could not drop database" in output(tester)
