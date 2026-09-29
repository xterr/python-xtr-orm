"""Unit tests for ``orm:migrations:rollup``."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from xtr_console import ExitCode

from tests.support.console import output
from tests.support.database import rows
from tests.support.revisions import write_revision

if TYPE_CHECKING:
    from pathlib import Path

    from sqlalchemy.ext.asyncio import AsyncEngine
    from xtr_console import ApplicationTester

pytestmark = pytest.mark.anyio

VERSIONS = "select version_num from alembic_version order by version_num"


async def test_it_records_the_single_revision(
    tester: ApplicationTester, migrations_directory: Path, engine: AsyncEngine
) -> None:
    _ = write_revision(migrations_directory, "squashed")

    assert await tester.execute(["orm:migrations:rollup"]) == ExitCode.SUCCESS
    assert 'Rolled up migrations to version "squashed".' in output(tester)
    assert await rows(engine, VERSIONS) == [("squashed",)]


async def test_no_revision_fails_the_run(tester: ApplicationTester) -> None:
    assert await tester.execute(["orm:migrations:rollup"]) == ExitCode.FAILURE
    assert "No migrations found." in output(tester)
