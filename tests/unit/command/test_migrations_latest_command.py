"""Unit tests for ``orm:migrations:latest``."""

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


async def test_it_prints_base_without_revisions(tester: ApplicationTester) -> None:
    assert await tester.execute(["orm:migrations:latest"]) == ExitCode.SUCCESS
    assert output(tester) == "base"


async def test_it_prints_every_latest_revision(
    tester: ApplicationTester, migrations_directory: Path
) -> None:
    _ = write_revision(migrations_directory, "a1")
    _ = write_revision(migrations_directory, "left", "a1", message="left side")
    _ = write_revision(migrations_directory, "right", "a1", message="right side")

    assert await tester.execute(["orm:migrations:latest"]) == ExitCode.SUCCESS
    assert "left - left side" in output(tester)
    assert "right - right side" in output(tester)
    assert "a1" not in output(tester)
