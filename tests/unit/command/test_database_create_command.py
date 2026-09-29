"""Unit tests for ``orm:database:create``."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from xtr_console import ExitCode

from tests.support.console import output

if TYPE_CHECKING:
    from pathlib import Path

    from xtr_console import ApplicationTester

pytestmark = pytest.mark.anyio


async def test_it_creates_the_database(tester: ApplicationTester, tmp_path: Path) -> None:
    assert await tester.execute(["orm:database:create"]) == ExitCode.SUCCESS

    assert (tmp_path / "app.sqlite").exists()
    assert 'Created database "' in output(tester)
    assert 'for connection named "default"' in output(tester)


async def test_an_existing_database_is_skipped_when_asked(tester: ApplicationTester) -> None:
    _ = await tester.execute(["orm:database:create"])

    assert await tester.execute(["orm:database:create", "--if-not-exists"]) == ExitCode.SUCCESS
    assert "already exists. Skipped." in output(tester)


async def test_an_existing_database_fails_the_run(tester: ApplicationTester) -> None:
    _ = await tester.execute(["orm:database:create"])

    assert await tester.execute(["orm:database:create"]) == ExitCode.FAILURE
    assert "Could not create database" in output(tester)
