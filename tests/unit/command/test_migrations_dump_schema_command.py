"""Unit tests for ``orm:migrations:dump-schema``."""

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


async def test_it_writes_the_existing_tables_and_says_how_to_record_them(
    tester: ApplicationTester, migrations_directory: Path
) -> None:
    _ = await tester.execute(["orm:run-sql", "create table legacy (id integer primary key)"])
    _ = await tester.execute(["orm:run-sql", "create table other (id integer primary key)"])

    code = await tester.execute(["orm:migrations:dump-schema", "--filter-tables", "^leg"])

    assert code == ExitCode.SUCCESS
    [written] = migrations_directory.glob("*.py")
    source = written.read_text(encoding="utf-8")
    assert "legacy" in source
    assert "other" not in source
    shown = output(tester)
    assert "Wrote the schema to a new revision at" in shown
    assert "To use this as a rollup migration you can use orm:migrations:rollup" in shown


async def test_it_names_the_connection_in_its_advice(tester: ApplicationTester) -> None:
    _ = await tester.execute(["orm:run-sql", "create table legacy (id integer primary key)"])

    code = await tester.execute(["orm:migrations:dump-schema", "--connection", "default"])

    assert code == ExitCode.SUCCESS
    assert "orm:migrations:rollup --connection default" in output(tester)


async def test_an_empty_database_fails_the_run(tester: ApplicationTester) -> None:
    assert await tester.execute(["orm:migrations:dump-schema"]) == ExitCode.FAILURE
    assert "does not contain any tables" in output(tester)
