"""Unit tests for ``orm:schema:update``."""

from __future__ import annotations

from io import StringIO
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import Column, Integer, MetaData, Table, text
from xtr_console import ConsoleStyle, ExitCode

from tests.support.console import output
from tests.support.database import rows, table_names
from xtr_orm import ConnectionRegistry, DatabaseManager
from xtr_orm.command import SchemaUpdateCommand
from xtr_orm.migrations import MigrationsConfig, Migrator

if TYPE_CHECKING:
    from pathlib import Path

    from sqlalchemy.ext.asyncio import AsyncEngine
    from xtr_console import ApplicationTester

pytestmark = pytest.mark.anyio


async def test_an_in_sync_schema_needs_nothing(tester: ApplicationTester) -> None:
    _ = await tester.execute(["orm:schema:update", "--force"])

    assert await tester.execute(["orm:schema:update"]) == ExitCode.SUCCESS
    assert "Nothing to update" in output(tester)


async def test_without_a_flag_the_changes_are_only_named(
    tester: ApplicationTester, engine: AsyncEngine
) -> None:
    assert await tester.execute(["orm:schema:update"]) == ExitCode.FAILURE
    shown = output(tester)
    assert "This operation should not be executed in a production environment." in shown
    assert (
        'The "default" connection\'s database schema is not in sync with the table definitions'
        in shown
    )
    assert "Re-run with --dump-sql to see the statements, or with --force to run them." in shown
    assert await table_names(engine) == set()


async def test_the_caution_names_the_tables_that_would_be_dropped(
    tester: ApplicationTester, engine: AsyncEngine
) -> None:
    _ = await tester.execute(
        ["orm:run-sql", "create table legacy (id integer not null, primary key (id))"]
    )

    assert await tester.execute(["orm:schema:update"]) == ExitCode.FAILURE
    shown = output(tester)
    assert 'would be dropped: "legacy"' in shown
    assert await table_names(engine) == {"legacy"}


async def test_dump_sql_prints_the_statements_without_running(
    tester: ApplicationTester, engine: AsyncEngine
) -> None:
    assert await tester.execute(["orm:schema:update", "--dump-sql"]) == ExitCode.SUCCESS
    assert "CREATE TABLE author" in tester.display
    assert "CREATE TABLE book" in tester.display
    assert await table_names(engine) == set()


async def test_force_runs_the_statements_and_records_nothing(
    tester: ApplicationTester, engine: AsyncEngine
) -> None:
    assert await tester.execute(["orm:schema:update", "--force"]) == ExitCode.SUCCESS
    assert await table_names(engine) == {"author", "book"}
    assert "3 changes applied" in output(tester)


async def test_dump_sql_and_force_prints_then_runs(
    tester: ApplicationTester, engine: AsyncEngine
) -> None:
    code = await tester.execute(["orm:schema:update", "--dump-sql", "--force"])

    assert code == ExitCode.SUCCESS
    assert "CREATE TABLE author" in tester.display
    assert "CREATE TABLE book" in tester.display
    assert await table_names(engine) == {"author", "book"}


async def test_a_short_force_flag_works(tester: ApplicationTester, engine: AsyncEngine) -> None:
    assert await tester.execute(["orm:schema:update", "-f"]) == ExitCode.SUCCESS
    assert await table_names(engine) == {"author", "book"}


async def test_orphaned_tables_are_dropped(tester: ApplicationTester, engine: AsyncEngine) -> None:
    _ = await tester.execute(
        ["orm:run-sql", "create table legacy (id integer not null, primary key (id))"]
    )

    assert await tester.execute(["orm:schema:update", "--force"]) == ExitCode.SUCCESS
    assert await table_names(engine) == {"author", "book"}


async def test_a_column_leaving_the_definitions_is_dropped(
    tester: ApplicationTester, engine: AsyncEngine
) -> None:
    await _execute(
        engine,
        "create table author (id integer not null, name varchar(100) not null, primary key (id))",
        "create table book (id integer not null, title varchar(200) not null,"
        " author_id integer not null, legacy varchar(10), primary key (id),"
        " foreign key(author_id) references author (id))",
        "create index ix_book_title on book (title)",
    )

    assert await tester.execute(["orm:schema:update", "--force"]) == ExitCode.SUCCESS
    columns = [row[1] for row in await rows(engine, "pragma table_info(book)")]
    assert "title" in columns
    assert "legacy" not in columns


async def test_the_change_count_names_every_change(tester: ApplicationTester) -> None:
    assert await tester.execute(["orm:schema:update"]) == ExitCode.FAILURE
    assert "3 changes would bring it in sync" in output(tester)


async def test_without_table_definitions_the_run_fails(
    engine: AsyncEngine, database_url: str, migrations_directory: Path
) -> None:
    registry = ConnectionRegistry()
    registry.register(
        "default",
        engine=engine,
        migrator=Migrator(engine, MigrationsConfig(directory=str(migrations_directory))),
        database=DatabaseManager(database_url),
    )
    shown = StringIO()

    code = await SchemaUpdateCommand(registry)(ConsoleStyle(shown, StringIO(), decorated=False))

    assert code == ExitCode.FAILURE
    assert "no table definitions" in " ".join(shown.getvalue().split())


async def test_a_failing_update_reports_the_reason(
    tester: ApplicationTester, engine: AsyncEngine
) -> None:
    await _execute(
        engine,
        "create table author (id integer not null, primary key (id))",
        "insert into author (id) values (1)",
        "create table book (id integer not null, title varchar(200) not null,"
        " author_id integer not null, primary key (id),"
        " foreign key(author_id) references author (id))",
        "create index ix_book_title on book (title)",
    )

    assert await tester.execute(["orm:schema:update", "--force"]) == ExitCode.FAILURE
    shown = output(tester)
    assert "Could not update" in shown
    assert "Cannot add a NOT NULL column" in shown


async def test_a_table_defined_twice_fails_the_run_with_the_reason(
    engine: AsyncEngine, database_url: str, migrations_directory: Path
) -> None:
    first, second = MetaData(), MetaData()
    _ = Table("shared", first, Column("id", Integer, primary_key=True))
    _ = Table("shared", second, Column("id", Integer, primary_key=True))
    registry = ConnectionRegistry()
    registry.register(
        "default",
        engine=engine,
        migrator=Migrator(
            engine, MigrationsConfig(directory=str(migrations_directory)), [first, second]
        ),
        database=DatabaseManager(database_url),
    )
    shown = StringIO()

    code = await SchemaUpdateCommand(registry)(ConsoleStyle(shown, StringIO(), decorated=False))

    assert code == ExitCode.FAILURE
    assert "Duplicate table keys" in shown.getvalue()


async def _execute(engine: AsyncEngine, *statements: str) -> None:
    """Run raw DDL against the test database, committed, one statement at a time."""
    async with engine.begin() as connection:
        for statement in statements:
            _ = await connection.execute(text(statement))
