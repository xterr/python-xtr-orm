"""The orm commands, run by an application's own console on the connections its kernel built."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from xtr_console import Application, ApplicationTester, ExitCode
from xtr_dependency_injection import Kernel

from tests.support.console import output, table_rows

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

pytestmark = pytest.mark.anyio


@pytest.fixture
async def tester(tmp_path: Path) -> AsyncIterator[ApplicationTester]:
    kernel = Kernel(
        "tests.fixtures.app_orm",
        env="test",
        environ={
            "ORM_TEST_URL": f"sqlite+aiosqlite:///{tmp_path / 'app.sqlite'}",
            "ORM_TEST_REPORTS_URL": f"sqlite+aiosqlite:///{tmp_path / 'reports.sqlite'}",
            "ORM_TEST_MIGRATIONS": str(tmp_path / "migrations"),
        },
    )
    async with await kernel.boot() as booted:
        application = await booted.container.get(Application)
        yield ApplicationTester(application, width=200)


async def test_a_database_is_created_diffed_migrated_and_reported(
    tester: ApplicationTester, tmp_path: Path
) -> None:
    assert await tester.execute(["orm:database:create"]) == ExitCode.SUCCESS
    assert await tester.execute(["orm:migrations:diff", "--message", "catalogue"]) == (
        ExitCode.SUCCESS
    )
    assert await tester.execute(["orm:migrations:up-to-date"]) == ExitCode.FAILURE
    assert await tester.execute(["orm:migrations:migrate", "-n"]) == ExitCode.SUCCESS
    assert await tester.execute(["orm:migrations:up-to-date"]) == ExitCode.SUCCESS

    assert await tester.execute(["orm:migrations:list"]) == ExitCode.SUCCESS
    assert table_rows(tester)[1][1] == "migrated"
    assert await tester.execute(["orm:run-sql", "select count(*) as books from book"]) == (
        ExitCode.SUCCESS
    )
    assert table_rows(tester) == [["books"], ["0"]]
    assert (tmp_path / "app.sqlite").exists()


async def test_every_command_acts_on_the_connection_it_is_given(
    tester: ApplicationTester, tmp_path: Path
) -> None:
    code = await tester.execute(["orm:database:create", "--connection", "reports"])

    assert code == ExitCode.SUCCESS
    assert 'for connection named "reports"' in output(tester)
    assert (tmp_path / "reports.sqlite").exists()
    assert not (tmp_path / "app.sqlite").exists()
