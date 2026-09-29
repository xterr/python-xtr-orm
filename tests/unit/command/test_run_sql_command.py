"""Unit tests for ``orm:run-sql``."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from xtr_console import ExitCode

from tests.support.console import output

if TYPE_CHECKING:
    from xtr_console import ApplicationTester

pytestmark = pytest.mark.anyio


async def test_a_statement_changing_rows_says_how_many(tester: ApplicationTester) -> None:
    _ = await tester.execute(["orm:run-sql", "create table t (id integer, name text)"])

    code = await tester.execute(["orm:run-sql", "insert into t values (1, 'a'), (2, null)"])

    assert code == ExitCode.SUCCESS
    assert "2 rows affected." in output(tester)


async def test_a_statement_whose_rows_the_driver_cannot_count_says_it_ran(
    tester: ApplicationTester,
) -> None:
    code = await tester.execute(["orm:run-sql", "create table t (id integer)"])

    assert code == ExitCode.SUCCESS
    assert "The statement was executed." in output(tester)
    assert "-1" not in output(tester)


async def test_a_query_shows_its_rows(tester: ApplicationTester) -> None:
    _ = await tester.execute(["orm:run-sql", "create table t (id integer, name text)"])
    _ = await tester.execute(["orm:run-sql", "insert into t values (1, 'a'), (2, null)"])

    assert await tester.execute(["orm:run-sql", "select id, name from t"]) == ExitCode.SUCCESS
    shown = output(tester)
    assert "id" in shown
    assert "name" in shown
    assert "NULL" in shown


async def test_a_query_finding_nothing_says_so(tester: ApplicationTester) -> None:
    _ = await tester.execute(["orm:run-sql", "create table t (id integer)"])

    assert await tester.execute(["orm:run-sql", "select id from t"]) == ExitCode.SUCCESS
    assert "The query yielded an empty result set." in output(tester)


async def test_force_fetch_reads_a_statement_as_a_query(tester: ApplicationTester) -> None:
    code = await tester.execute(["orm:run-sql", "create table t (id integer)", "--force-fetch"])

    assert code == ExitCode.SUCCESS
    assert "The query yielded an empty result set." in output(tester)


async def test_a_failing_statement_fails_the_run(tester: ApplicationTester) -> None:
    assert await tester.execute(["orm:run-sql", "select * from nowhere"]) == ExitCode.FAILURE
    assert "no such table" in output(tester)
