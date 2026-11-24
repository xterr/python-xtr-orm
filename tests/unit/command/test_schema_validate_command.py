"""Unit tests for ``orm:schema:validate``."""

from __future__ import annotations

from io import StringIO
from typing import TYPE_CHECKING, final

import pytest
from sqlalchemy import Column, Integer, MetaData, Table
from sqlalchemy.orm import DeclarativeBase, Mapped, clear_mappers, mapped_column, relationship
from xtr_console import ConsoleStyle, ExitCode, Verbosity

from tests.support.console import output
from xtr_orm import ConnectionRegistry, DatabaseManager
from xtr_orm.command import SchemaValidateCommand
from xtr_orm.migrations import MigrationsConfig, Migrator

if TYPE_CHECKING:
    from pathlib import Path

    from sqlalchemy.ext.asyncio import AsyncEngine
    from xtr_console import ApplicationTester

pytestmark = pytest.mark.anyio


async def test_a_valid_mapping_and_in_sync_schema_exits_zero(tester: ApplicationTester) -> None:
    _ = await tester.execute(["orm:schema:update", "--force"])

    assert await tester.execute(["orm:schema:validate"]) == ExitCode.SUCCESS
    shown = output(tester)
    assert "The mapping is valid." in shown
    assert "in sync with the table definitions" in shown


async def test_out_of_sync_exits_two(tester: ApplicationTester) -> None:
    assert await tester.execute(["orm:schema:validate"]) == 2
    assert "not in sync with the table definitions" in output(tester)


async def test_out_of_sync_shows_the_statements_only_when_verbose(
    tester: ApplicationTester,
) -> None:
    assert await tester.execute(["orm:schema:validate"]) == 2
    assert "CREATE TABLE" not in tester.display

    assert await tester.execute(["orm:schema:validate"], verbosity=Verbosity.VERBOSE) == 2
    assert "CREATE TABLE author" in tester.display


async def test_skip_sync_ignores_the_database(tester: ApplicationTester) -> None:
    assert await tester.execute(["orm:schema:validate", "--skip-sync"]) == ExitCode.SUCCESS
    shown = output(tester)
    assert "The mapping is valid." in shown
    assert "in sync" not in shown


async def test_skip_mapping_ignores_the_mapping(tester: ApplicationTester) -> None:
    assert await tester.execute(["orm:schema:validate", "--skip-mapping"]) == 2
    assert "The mapping is valid." not in output(tester)


async def test_skipping_both_succeeds(tester: ApplicationTester) -> None:
    code = await tester.execute(["orm:schema:validate", "--skip-mapping", "--skip-sync"])

    assert code == ExitCode.SUCCESS


async def test_a_table_defined_twice_fails_the_mapping(
    engine: AsyncEngine, database_url: str, migrations_directory: Path
) -> None:
    registry = ConnectionRegistry()
    registry.register(
        "default",
        engine=engine,
        migrator=Migrator(
            engine,
            MigrationsConfig(directory=str(migrations_directory)),
            _duplicated_shared_metadata(),
        ),
        database=DatabaseManager(database_url),
    )
    shown = StringIO()

    code = await SchemaValidateCommand(registry)(
        ConsoleStyle(shown, StringIO(), decorated=False), skip_sync=True
    )

    assert code == 1
    assert 'name "shared" more than once' in " ".join(shown.getvalue().split())


async def test_a_failing_mapper_fails_the_mapping(tester: ApplicationTester) -> None:
    class Base(DeclarativeBase):
        pass

    @final
    class Broken(Base):
        __tablename__ = "broken"
        id: Mapped[int] = mapped_column(Integer, primary_key=True)
        missing: Mapped[object] = relationship("DoesNotExistAnywhere")

    try:
        code = await tester.execute(["orm:schema:validate", "--skip-sync"])
    finally:
        # configure_mappers() is process-global; a broken mapper left
        # registered fails every later configuration.
        clear_mappers()

    assert code == 1
    assert "does not configure" in output(tester)


async def test_a_bad_mapping_and_out_of_sync_adds_up(
    engine: AsyncEngine, database_url: str, migrations_directory: Path
) -> None:
    registry = ConnectionRegistry()
    registry.register(
        "default",
        engine=engine,
        migrator=Migrator(
            engine,
            MigrationsConfig(directory=str(migrations_directory)),
            _duplicated_shared_metadata(),
        ),
        database=DatabaseManager(database_url),
    )
    shown = StringIO()

    code = await SchemaValidateCommand(registry)(ConsoleStyle(shown, StringIO(), decorated=False))

    assert code == 3


async def test_without_table_definitions_the_sync_check_fails(
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

    code = await SchemaValidateCommand(registry)(ConsoleStyle(shown, StringIO(), decorated=False))

    displayed = " ".join(shown.getvalue().split())
    assert code == 2
    assert "no table definitions" in displayed
    assert "The mapping is valid." in displayed


def _duplicated_shared_metadata() -> list[MetaData]:
    """Two sets of table definitions, both naming a table "shared"."""
    first, second = MetaData(), MetaData()
    _ = Table("shared", first, Column("id", Integer, primary_key=True))
    _ = Table("shared", second, Column("id", Integer, primary_key=True))
    return [first, second]
