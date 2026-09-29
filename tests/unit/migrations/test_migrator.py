"""Unit tests for :class:`xtr_orm.migrations.Migrator`, on real SQLite files and revisions."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, final

import pytest
from sqlalchemy import Column, Integer, MetaData, Table

from tests.support.database import rows, table_names
from tests.support.revisions import write_revision
from tests.support.schema import METADATA
from xtr_orm.exception import MigrationError
from xtr_orm.migrations import Direction, MigrationPlan, MigrationsConfig, Migrator

if TYPE_CHECKING:
    from alembic.operations.ops import MigrationScript
    from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = pytest.mark.anyio

HISTORY = (
    "select version, executed_at, execution_time from alembic_version_history order by version"
)
VERSIONS = "select version_num from alembic_version order by version_num"


def _chain(directory: Path, *versions: str) -> None:
    """Write ``versions`` as one chain, each creating a table named after itself."""
    down: str | None = None
    for version in versions:
        _ = write_revision(directory, version, down, table=f"t_{version}")
        down = version


async def _versions(engine: AsyncEngine) -> list[object]:
    return [row[0] for row in await rows(engine, VERSIONS)]


async def _recorded(engine: AsyncEngine) -> list[object]:
    return [row[0] for row in await rows(engine, HISTORY)]


async def test_an_empty_database_without_revisions_is_up_to_date(migrator: Migrator) -> None:
    status = await migrator.status()

    assert status.current == ()
    assert status.latest == ()
    assert status.available == ()
    assert status.executed == ()
    assert status.is_up_to_date


async def test_a_diff_writes_the_tables_the_database_lacks(
    migrator: Migrator, engine: AsyncEngine
) -> None:
    written = await migrator.diff("create the catalogue")

    assert written is not None
    assert written.description == "create the catalogue"
    assert written.down_versions == ()
    assert written.is_head
    source = (_read(written.path)).replace('"', "'")
    assert "op.create_table('author'" in source
    assert "op.create_table('book'" in source
    assert await table_names(engine) == set()


async def test_migrate_runs_every_new_revision_and_records_each(
    migrator: Migrator, engine: AsyncEngine
) -> None:
    written = await migrator.diff("create the catalogue")
    assert written is not None

    results = await migrator.migrate()

    assert [(result.version, result.direction) for result in results] == [
        (written.version, Direction.UP)
    ]
    assert {"author", "book"} <= await table_names(engine)
    assert await _versions(engine) == [written.version]
    [(version, executed_at, execution_time)] = await rows(engine, HISTORY)
    assert version == written.version
    assert executed_at is not None
    assert isinstance(execution_time, int)
    status = await migrator.status()
    assert status.is_up_to_date
    assert status.current == (written.version,)
    assert [each.version for each in status.executed] == [written.version]
    assert status.executed[0].executed_at is not None
    assert status.executed[0].execution_time is not None


async def test_a_diff_of_a_database_matching_its_tables_writes_nothing(migrator: Migrator) -> None:
    _ = await migrator.diff("create the catalogue")
    _ = await migrator.migrate()

    assert await migrator.diff("nothing") is None


async def test_a_diff_may_be_written_empty_when_asked(migrator: Migrator) -> None:
    _ = await migrator.diff("create the catalogue")
    _ = await migrator.migrate()

    written = await migrator.diff("nothing", allow_empty=True)

    assert written is not None
    assert "pass" in _read(written.path)


async def test_a_diff_leaves_the_history_table_out(migrator: Migrator) -> None:
    _ = await migrator.diff("create the catalogue")
    _ = await migrator.migrate()

    assert await migrator.diff("nothing") is None


async def test_a_diff_from_an_empty_schema_writes_every_table(migrator: Migrator) -> None:
    _ = await migrator.diff("create the catalogue")
    _ = await migrator.migrate()

    written = await migrator.diff("again", from_empty_schema=True)

    assert written is not None
    source = (_read(written.path)).replace('"', "'")
    assert "op.create_table('author'" in source
    assert "op.create_index" in source
    assert "op.drop_table('book')" in source


async def test_a_diff_refuses_a_database_behind_its_revisions(migrator: Migrator) -> None:
    _ = await migrator.diff("create the catalogue")

    with pytest.raises(MigrationError, match="not up to date"):
        _ = await migrator.diff("more")


async def test_a_diff_needs_table_definitions(
    engine: AsyncEngine, migrations_directory: Path
) -> None:
    bare = Migrator(engine, MigrationsConfig(directory=str(migrations_directory)))

    with pytest.raises(MigrationError, match="no table definitions"):
        _ = await bare.diff()


async def test_generate_writes_an_empty_revision_after_the_latest(migrator: Migrator) -> None:
    first = migrator.generate("first")
    second = migrator.generate("second")

    assert first.down_versions == ()
    assert second.down_versions == (first.version,)
    assert "def upgrade() -> None:\n    pass" in _read(second.path)


async def test_revision_files_are_named_by_the_file_template(
    engine: AsyncEngine, migrations_directory: Path
) -> None:
    config = MigrationsConfig(directory=str(migrations_directory), file_template="{rev}-{slug}")
    written = Migrator(engine, config).generate("Add Books")

    assert written.path.endswith(f"{written.version}-add_books.py")


async def test_a_custom_template_directory_renders_new_revisions(
    engine: AsyncEngine, migrations_directory: Path, tmp_path: Path
) -> None:
    templates = tmp_path / "templates"
    templates.mkdir()
    _ = (templates / "script.py.mako").write_text(
        '"""${message}"""\nrevision = ${repr(up_revision)}\n'
        "down_revision = ${repr(down_revision)}\n# custom template\n",
        encoding="utf-8",
    )
    config = MigrationsConfig(
        directory=str(migrations_directory), template_directory=str(templates)
    )

    written = Migrator(engine, config).generate("custom")

    assert "# custom template" in _read(written.path)


async def test_plan_lists_what_migrate_would_run_without_running_it(
    migrator: Migrator, engine: AsyncEngine, migrations_directory: Path
) -> None:
    _chain(migrations_directory, "a1", "b2")

    plans = await migrator.plan()

    assert [(each.version, each.direction) for each in plans] == [
        ("a1", Direction.UP),
        ("b2", Direction.UP),
    ]
    assert plans[0].description == "revision a1"
    assert "t_a1" not in await table_names(engine)


@pytest.mark.parametrize(
    ("start", "target", "applied"),
    [
        ("latest", "first", []),
        ("latest", "prev", ["b2"]),
        ("latest", "-2", ["a1"]),
        ("latest", "a1", ["a1"]),
        ("first", "next", ["a1"]),
        ("first", "+2", ["b2"]),
        ("first", "b2", ["b2"]),
        ("a1", "latest", ["c3"]),
        ("b2", "current", ["b2"]),
    ],
)
async def test_migrate_reaches_any_target_up_or_down(
    migrator: Migrator,
    engine: AsyncEngine,
    migrations_directory: Path,
    start: str,
    target: str,
    applied: list[str],
) -> None:
    _chain(migrations_directory, "a1", "b2", "c3")
    _ = await migrator.migrate(start)

    _ = await migrator.migrate(target)

    assert await _versions(engine) == applied


async def test_migrating_down_forgets_each_reverted_revision(
    migrator: Migrator, engine: AsyncEngine, migrations_directory: Path
) -> None:
    _chain(migrations_directory, "a1", "b2")
    _ = await migrator.migrate()

    results = await migrator.migrate("first")

    assert [(each.version, each.direction) for each in results] == [
        ("b2", Direction.DOWN),
        ("a1", Direction.DOWN),
    ]
    assert await _recorded(engine) == []
    assert "t_a1" not in await table_names(engine)


async def test_migrate_refuses_an_unknown_target(
    migrator: Migrator, migrations_directory: Path
) -> None:
    _chain(migrations_directory, "a1")

    with pytest.raises(MigrationError, match="nope"):
        _ = await migrator.migrate("nope")


async def test_migrate_sql_writes_the_statements_and_runs_none(
    migrator: Migrator, engine: AsyncEngine, migrations_directory: Path
) -> None:
    _chain(migrations_directory, "a1")

    sql = await migrator.migrate_sql()

    assert "CREATE TABLE t_a1" in sql
    assert "INSERT INTO alembic_version" in sql
    assert "INSERT INTO alembic_version_history" in sql
    assert await table_names(engine) == set()


async def test_migrate_sql_starts_from_where_the_database_is(
    migrator: Migrator, migrations_directory: Path
) -> None:
    _chain(migrations_directory, "a1", "b2")
    _ = await migrator.migrate("a1")

    sql = await migrator.migrate_sql()

    assert "CREATE TABLE t_b2" in sql
    assert "CREATE TABLE t_a1" not in sql


async def test_execute_runs_exactly_the_versions_given(
    migrator: Migrator, engine: AsyncEngine, migrations_directory: Path
) -> None:
    _chain(migrations_directory, "a1", "b2", "c3")

    results = await migrator.execute(["a1", "b2"])

    assert [each.version for each in results] == ["a1", "b2"]
    assert await _versions(engine) == ["b2"]
    assert await _recorded(engine) == ["a1", "b2"]
    assert "t_c3" not in await table_names(engine)


async def test_execute_down_reverts_only_the_version_given(
    migrator: Migrator, engine: AsyncEngine, migrations_directory: Path
) -> None:
    _chain(migrations_directory, "a1", "b2")
    _ = await migrator.migrate()

    _ = await migrator.execute(["b2"], Direction.DOWN)

    assert await _versions(engine) == ["a1"]
    assert await _recorded(engine) == ["a1"]
    assert "t_b2" not in await table_names(engine)


@pytest.mark.parametrize(
    ("applied", "versions", "direction", "reason"),
    [
        ("a1", ["a1"], Direction.UP, 'The version "a1" is already applied.'),
        ("first", ["b2"], Direction.UP, 'The version "b2" follows "a1", which is not applied.'),
        ("first", ["a1"], Direction.DOWN, 'The version "a1" is not applied.'),
        ("b2", ["a1"], Direction.DOWN, 'The version "a1" is followed by "b2", which is applied.'),
        ("first", ["zz"], Direction.UP, 'Unknown version "zz"'),
    ],
)
async def test_execute_refuses_a_version_out_of_order(
    migrator: Migrator,
    engine: AsyncEngine,
    migrations_directory: Path,
    applied: str,
    versions: list[str],
    direction: Direction,
    reason: str,
) -> None:
    _chain(migrations_directory, "a1", "b2")
    _ = await migrator.migrate(applied)
    before = await _versions(engine)

    with pytest.raises(MigrationError) as raised:
        _ = await migrator.execute(versions, direction)

    assert raised.value.reason.startswith(reason)
    assert await _versions(engine) == before


async def test_plan_for_versions_resolves_and_checks_them_and_runs_nothing(
    migrator: Migrator, engine: AsyncEngine, migrations_directory: Path
) -> None:
    _ = write_revision(migrations_directory, "ae1027a6acf", table="t_x", message="first")

    plans = await migrator.plan_for_versions(["ae10"])

    assert plans == (MigrationPlan("ae1027a6acf", Direction.UP, "first"),)
    assert "t_x" not in await table_names(engine)
    with pytest.raises(MigrationError):
        _ = await migrator.plan_for_versions(["ae10"], Direction.DOWN)


async def test_execute_sql_writes_the_statements_and_runs_none(
    migrator: Migrator, engine: AsyncEngine, migrations_directory: Path
) -> None:
    _chain(migrations_directory, "a1", "b2")

    sql = await migrator.execute_sql(["a1"])

    assert "CREATE TABLE t_a1" in sql
    assert "t_b2" not in sql
    assert await table_names(engine) == set()


async def test_added_versions_are_recorded_without_running(
    migrator: Migrator, engine: AsyncEngine, migrations_directory: Path
) -> None:
    _chain(migrations_directory, "a1", "b2")

    added = await migrator.add_versions(["a1"])

    assert added == ("a1",)
    assert await _versions(engine) == ["a1"]
    [(version, executed_at, execution_time)] = await rows(engine, HISTORY)
    assert (version, execution_time) == ("a1", None)
    assert executed_at is not None
    assert "t_a1" not in await table_names(engine)


async def test_adding_an_applied_version_is_refused(
    migrator: Migrator, migrations_directory: Path
) -> None:
    _chain(migrations_directory, "a1")
    _ = await migrator.add_versions(["a1"])

    with pytest.raises(MigrationError, match="already applied"):
        _ = await migrator.add_versions(["a1"])


async def test_deleted_versions_are_forgotten_without_running(
    migrator: Migrator, engine: AsyncEngine, migrations_directory: Path
) -> None:
    _chain(migrations_directory, "a1", "b2")
    _ = await migrator.migrate()

    deleted = await migrator.delete_versions(["b2"])

    assert deleted == ("b2",)
    assert await _versions(engine) == ["a1"]
    assert await _recorded(engine) == ["a1"]
    assert "t_b2" in await table_names(engine)


async def test_an_applied_version_without_a_file_can_be_deleted(
    migrator: Migrator, engine: AsyncEngine, migrations_directory: Path
) -> None:
    _chain(migrations_directory, "a1", "b2")
    _ = await migrator.migrate()
    (migrations_directory / "b2.py").unlink()

    deleted = await migrator.delete_versions(["b2"])

    assert deleted == ("b2",)
    assert await _versions(engine) == []
    assert await _recorded(engine) == ["a1"]


async def test_deleting_a_version_nothing_recorded_is_refused(
    migrator: Migrator, migrations_directory: Path
) -> None:
    _chain(migrations_directory, "a1")

    with pytest.raises(MigrationError, match='"gone" is not applied'):
        _ = await migrator.delete_versions(["gone"])


async def test_every_version_can_be_added_then_deleted_at_once(
    migrator: Migrator, engine: AsyncEngine, migrations_directory: Path
) -> None:
    _chain(migrations_directory, "a1", "b2", "c3")
    _ = await migrator.migrate("a1")

    assert await migrator.add_all_versions() == ("b2", "c3")
    assert await _versions(engine) == ["c3"]
    assert await _recorded(engine) == ["a1", "b2", "c3"]

    await migrator.delete_all_versions()

    assert await _versions(engine) == []
    assert await _recorded(engine) == []
    assert "t_a1" in await table_names(engine)


async def test_rollup_records_the_single_revision_as_all_there_is(
    migrator: Migrator, engine: AsyncEngine, migrations_directory: Path
) -> None:
    _chain(migrations_directory, "a1", "b2")
    _ = await migrator.migrate()
    for version in ("a1", "b2"):
        (migrations_directory / f"{version}.py").unlink()
    _ = write_revision(migrations_directory, "squashed")

    rolled = await migrator.rollup()

    assert rolled.version == "squashed"
    assert await _versions(engine) == ["squashed"]
    assert await _recorded(engine) == ["squashed"]


@pytest.mark.parametrize(("count", "reason"), [(0, "No migrations found"), (2, "Too many")])
async def test_rollup_needs_exactly_one_revision(
    migrator: Migrator, migrations_directory: Path, count: int, reason: str
) -> None:
    _chain(migrations_directory, *[f"r{index}" for index in range(count)])

    with pytest.raises(MigrationError, match=reason):
        _ = await migrator.rollup()


async def test_a_dump_writes_every_table_the_database_has(
    migrator: Migrator, engine: AsyncEngine
) -> None:
    await _create_catalogue(engine)

    written = await migrator.dump_schema()

    source = (_read(written.path)).replace('"', "'")
    assert written.description == "dump the existing schema"
    assert "op.create_table('author'" in source
    assert "op.create_table('book'" in source
    assert "op.create_index" in source
    assert "alembic_version" not in source


async def test_a_dump_keeps_only_the_tables_a_filter_finds(
    migrator: Migrator, engine: AsyncEngine
) -> None:
    await _create_catalogue(engine)

    written = await migrator.dump_schema("authors only", table_filters=["^auth"])

    source = (_read(written.path)).replace('"', "'")
    assert "op.create_table('author'" in source
    assert "'book'" not in source


async def test_a_dump_is_refused_once_revisions_exist(
    migrator: Migrator, engine: AsyncEngine, migrations_directory: Path
) -> None:
    await _create_catalogue(engine)
    _chain(migrations_directory, "a1")

    with pytest.raises(MigrationError, match="Delete the previous revisions"):
        _ = await migrator.dump_schema()


async def test_a_dump_of_an_empty_database_is_refused(migrator: Migrator) -> None:
    with pytest.raises(MigrationError, match="does not contain any tables"):
        _ = await migrator.dump_schema()


async def test_status_names_applied_revisions_whose_file_is_gone(
    migrator: Migrator, migrations_directory: Path
) -> None:
    _chain(migrations_directory, "a1", "b2", "c3")
    _ = await migrator.migrate("b2")
    (migrations_directory / "b2.py").unlink()
    # A new table name, so the file's size changes and no cached bytecode is read.
    _ = write_revision(migrations_directory, "c3", "a1", table="t_c3_after_a1")

    status = await migrator.status()

    assert [each.version for each in status.executed_unavailable] == ["b2"]
    assert [each.version for each in status.new] == ["c3"]
    assert [each.version for each in status.executed] == ["a1", "b2"]
    assert status.previous == ()
    assert status.next == ("c3",)


async def test_status_names_the_previous_next_and_latest_revisions(
    migrator: Migrator, migrations_directory: Path
) -> None:
    _chain(migrations_directory, "a1", "b2", "c3")
    _ = await migrator.migrate("b2")

    status = await migrator.status()

    assert status.current == ("b2",)
    assert status.previous == ("a1",)
    assert status.next == ("c3",)
    assert status.latest == ("c3",)
    assert not status.is_up_to_date


async def test_branches_are_run_side_by_side_and_merged(
    migrator: Migrator, engine: AsyncEngine, migrations_directory: Path
) -> None:
    _ = write_revision(migrations_directory, "a1", table="t_a1")
    _ = write_revision(migrations_directory, "left", "a1", table="t_left")
    _ = write_revision(migrations_directory, "right", "a1", table="t_right")

    _ = await migrator.execute(["a1", "left"])
    _ = await migrator.execute(["right"])
    assert await _versions(engine) == ["left", "right"]

    _ = await migrator.execute(["left"], Direction.DOWN)
    assert await _versions(engine) == ["right"]

    _ = write_revision(migrations_directory, "merge", ("left", "right"))
    _ = await migrator.migrate()
    assert await _versions(engine) == ["merge"]
    assert await _recorded(engine) == ["a1", "left", "merge", "right"]


async def test_a_revision_depending_on_another_waits_for_it(
    migrator: Migrator, migrations_directory: Path
) -> None:
    _ = write_revision(migrations_directory, "a1")
    _ = write_revision(migrations_directory, "other")
    _ = write_revision(migrations_directory, "b2", "a1", depends_on="other")
    _ = await migrator.execute(["a1"])

    with pytest.raises(MigrationError, match='follows "other"'):
        _ = await migrator.execute(["b2"])


async def test_a_revision_another_applied_one_depends_on_is_not_reverted_alone(
    migrator: Migrator, engine: AsyncEngine, migrations_directory: Path
) -> None:
    _ = write_revision(migrations_directory, "a1", table="t_a1")
    _ = write_revision(migrations_directory, "b2", depends_on="a1", table="t_b2")
    _ = await migrator.migrate()
    before = await _versions(engine)

    with pytest.raises(MigrationError) as raised:
        _ = await migrator.execute(["a1"], Direction.DOWN)

    assert raised.value.reason == 'The version "a1" is followed by "b2", which is applied.'
    assert await _versions(engine) == before


async def test_the_history_table_goes_where_it_is_told(
    engine: AsyncEngine, migrations_directory: Path
) -> None:
    config = MigrationsConfig(
        directory=str(migrations_directory),
        version_table="schema_version",
        history_table="schema_history",
    )
    _chain(migrations_directory, "a1")

    _ = await Migrator(engine, config).migrate()

    assert {"schema_version", "schema_history"} <= await table_names(engine)
    assert await rows(engine, "select version from schema_history") == [("a1",)]


async def test_a_custom_type_is_written_with_its_module_imported(
    engine: AsyncEngine, migrations_directory: Path
) -> None:
    metadata = MetaData()
    _ = Table("coin", metadata, Column("id", Integer, primary_key=True), Column("value", _Money()))
    migrator = Migrator(engine, MigrationsConfig(directory=str(migrations_directory)), metadata)

    written = await migrator.diff("coins")

    assert written is not None
    source = _read(written.path)
    assert f"import {__name__}" in source
    assert f"{__name__}._Money()" in source


async def test_a_configured_renderer_is_asked_first(
    engine: AsyncEngine, migrations_directory: Path
) -> None:
    def render(kind: str, value: object, context: object) -> str | bool:
        del context
        return "sa.Numeric()" if kind == "type" and isinstance(value, _Money) else False

    metadata = MetaData()
    _ = Table("coin", metadata, Column("id", Integer, primary_key=True), Column("value", _Money()))
    config = MigrationsConfig(directory=str(migrations_directory), render_item=render)

    written = await Migrator(engine, config, metadata).diff("coins")

    assert written is not None
    source = _read(written.path)
    assert "sa.Numeric()" in source
    assert f"import {__name__}" not in source


async def test_a_configured_name_filter_decides_what_a_diff_reads(
    engine: AsyncEngine, migrations_directory: Path
) -> None:
    await _create_catalogue(engine)

    def include_name(name: str | None, kind: str, parents: object) -> bool:
        del parents
        return kind != "table" or name != "book"

    config = MigrationsConfig(directory=str(migrations_directory), include_name=include_name)

    written = await Migrator(engine, config, MetaData()).diff("drop the rest")

    assert written is not None
    source = (_read(written.path)).replace('"', "'")
    assert "op.drop_table('author')" in source
    assert "'book'" not in source


async def test_the_migrator_names_its_engine_config_and_connection(
    migrator: Migrator, engine: AsyncEngine
) -> None:
    assert migrator.engine is engine
    assert migrator.name == "default"
    assert migrator.config.version_table == "alembic_version"


def _hooked(engine: AsyncEngine, directory: Path, seen: list[int]) -> Migrator:
    """A migrator whose revision hook names every revision "fixed", as an alembic hook would."""

    def name_it(context: object, revision: object, directives: list[MigrationScript]) -> None:
        del context, revision
        seen.append(len(directives))
        directives[0].rev_id = "fixed"

    config = MigrationsConfig(directory=str(directory), process_revision_directives=name_it)
    return Migrator(engine, config, METADATA)


async def test_the_revision_hook_adjusts_what_a_diff_writes(
    engine: AsyncEngine, migrations_directory: Path
) -> None:
    written = await _hooked(engine, migrations_directory, []).diff("create the catalogue")

    assert written is not None
    assert written.version == "fixed"


async def test_the_revision_hook_sees_a_diff_that_found_nothing_before_it_is_dropped(
    engine: AsyncEngine, migrations_directory: Path
) -> None:
    await _create_catalogue(engine)
    seen: list[int] = []

    written = await _hooked(engine, migrations_directory, seen).diff("nothing")

    assert written is None
    assert seen == [1]


async def test_a_migrator_built_without_config_reads_the_defaults(engine: AsyncEngine) -> None:
    assert Migrator(engine).config == MigrationsConfig()


@final
class _Money(Integer):
    """A type from outside the database library, as an application declares one."""

    cache_ok = True


async def _create_catalogue(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(METADATA.create_all)


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")
