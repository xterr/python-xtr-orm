"""Versioned schema changes for one database: read, planned, run and recorded."""

from __future__ import annotations

from io import StringIO
from typing import TYPE_CHECKING, Final, TypeVar, final

from alembic.autogenerate import RevisionContext
from alembic.config import Config
from sqlalchemy import Column, MetaData, String, Table, delete
from xtr_logging_contracts import LoggerAware

from xtr_orm.exception import MigrationError

from ._environment import Environment
from ._history import HistoryRecorder, HistoryTable
from ._revisions import (
    applied,
    available,
    known,
    mark_step,
    parents,
    plan,
    refusing,
    resolve,
)
from ._revisions import migration as describe
from ._revisions import step as revision_step
from ._schema import creating, matching, tables_of
from .direction import Direction
from .executed_migration import ExecutedMigration
from .migration_plan import MigrationPlan
from .migration_status import MigrationStatus
from .migrations_config import MigrationsConfig

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Sequence

    from alembic.operations.ops import MigrationScript
    from alembic.runtime.migration import MigrationContext, RevisionStep
    from alembic.script import Script, ScriptDirectory
    from sqlalchemy.engine import Connection
    from sqlalchemy.ext.asyncio import AsyncEngine

    from .available_migration import AvailableMigration
    from .execution_result import ExecutionResult

__all__ = ["Migrator"]

_T = TypeVar("_T")

_VERSION_LENGTH: Final = 32


@final
class Migrator(LoggerAware):
    """Reads, plans, runs and records one database's revisions.

    Revisions are ordinary migration files in the configured directory. The
    database keeps the revisions it is at in the version table, and a row per
    revision applied in the history table; every change to one is made to the
    other in the same transaction.

    Every method opens its own connection from the engine and returns once it
    is closed. What reads files only — :meth:`generate` — opens none.

    ```python
    migrator = Migrator(engine, MigrationsConfig(directory="migrations"), Base.metadata)

    await migrator.migrate()  # to the latest revisions
    status = await migrator.status()
    ```
    """

    _engine: AsyncEngine
    _config: MigrationsConfig
    _metadata: MetaData | Sequence[MetaData] | None
    _name: str
    _environment: Environment
    _history: HistoryTable

    def __init__(
        self,
        engine: AsyncEngine,
        config: MigrationsConfig | None = None,
        metadata: MetaData | Sequence[MetaData] | None = None,
        *,
        name: str = "default",
    ) -> None:
        """Manage the revisions ``config`` describes on ``engine``'s database.

        Args:
            engine: The database the revisions apply to.
            config: Where the revisions are and how they are recorded.
            metadata: The table definitions a diff compares the database
                with; a diff is refused without them.
            name: What reports call this database.
        """
        self._engine = engine
        self._config = config if config is not None else MigrationsConfig()
        self._metadata = metadata
        self._name = name
        self._environment = Environment(self._config, metadata)
        self._history = HistoryTable(self._config.history_table, self._config.version_table_schema)

    @property
    def name(self) -> str:
        """What reports call this database."""
        return self._name

    @property
    def engine(self) -> AsyncEngine:
        """The database the revisions apply to."""
        return self._engine

    @property
    def config(self) -> MigrationsConfig:
        """Where the revisions are and how they are recorded."""
        return self._config

    async def status(self) -> MigrationStatus:
        """Read where the database stands against the revision files."""
        return await self._connected(self._status)

    async def plan(self, target: str = "latest") -> tuple[MigrationPlan, ...]:
        """Return the revisions :meth:`migrate` would run to reach ``target``, without running them.

        Raises:
            MigrationError: When the target is unknown or cannot be reached.
        """

        def work(connection: Connection) -> tuple[MigrationPlan, ...]:
            directory = self._environment.directory()
            heads = self._environment.context(connection).get_current_heads()
            direction, steps = plan(directory, heads, target)
            return tuple(
                MigrationPlan(step.revision.revision, direction, (step.revision.doc or "").strip())
                for step in steps
            )

        return await self._connected(work)

    async def migrate(self, target: str = "latest") -> tuple[ExecutionResult, ...]:
        """Run every revision between where the database is and ``target``.

        ``target`` is a revision — a full or partial id, or a label — a
        relative one (``+1``, ``-2``, ``ae10+1``), or one of ``latest``,
        ``first`` (before every revision), ``next``, ``prev`` and ``current``.
        A revision already applied is migrated down to; one that is not, up
        to.

        Raises:
            MigrationError: When the target is unknown or cannot be reached.
        """
        results = await self._connected(lambda connection: self._migrate(connection, target))
        self._log_results(results)
        return results

    async def migrate_sql(self, target: str = "latest") -> str:
        """Return the SQL :meth:`migrate` would run, recording included, without running it.

        Raises:
            MigrationError: When the target is unknown or cannot be reached.
        """

        def work(connection: Connection) -> str:
            directory = self._environment.directory()
            heads = self._environment.context(connection).get_current_heads()
            _, steps = plan(directory, heads, target)
            return self._sql(connection, directory, heads, steps)

        return await self._connected(work)

    async def execute(
        self, versions: Sequence[str], direction: Direction = Direction.UP
    ) -> tuple[ExecutionResult, ...]:
        """Run exactly ``versions``, in order, each one way — and nothing before or after them.

        Going up, a revision must not be applied and must follow only applied
        ones; going down, it must be applied and followed by none that is.
        Each version is checked against the ones before it, so a revision and
        the one following it may be run together.

        Raises:
            MigrationError: When a version is unknown, or out of order.
        """
        results = await self._connected(
            lambda connection: self._apply(connection, versions, direction, marking=False)
        )
        self._log_results(results)
        return results

    async def plan_for_versions(
        self, versions: Sequence[str], direction: Direction = Direction.UP
    ) -> tuple[MigrationPlan, ...]:
        """Return what :meth:`execute` would run for ``versions``, without running it.

        Each version is resolved to the revision it names — a partial id to
        the full one — and checked as :meth:`execute` checks it.

        Raises:
            MigrationError: When a version is unknown, or out of order.
        """

        def work(connection: Connection) -> tuple[MigrationPlan, ...]:
            directory = self._environment.directory()
            heads = self._environment.context(connection).get_current_heads()
            return tuple(
                MigrationPlan(script.revision, direction, (script.doc or "").strip())
                for script in self._checked(directory, heads, versions, direction)
            )

        return await self._connected(work)

    async def execute_sql(
        self, versions: Sequence[str], direction: Direction = Direction.UP
    ) -> str:
        """Return the SQL :meth:`execute` would run, recording included, without running it.

        Raises:
            MigrationError: When a version is unknown, or out of order.
        """

        def work(connection: Connection) -> str:
            directory = self._environment.directory()
            heads = self._environment.context(connection).get_current_heads()
            scripts = self._checked(directory, heads, versions, direction)
            steps = [revision_step(directory, each, direction) for each in scripts]
            return self._sql(connection, directory, heads, steps)

        return await self._connected(work)

    def generate(self, message: str | None = None) -> AvailableMigration:
        """Write an empty revision following the latest one, and return it.

        Raises:
            MigrationError: When there are several latest revisions to follow.
        """
        directory = self._environment.directory()
        context = RevisionContext(Config(), directory, _command_args(message, autogenerate=False))
        written = self._written(context)
        if written is None:  # pragma: no cover — an empty revision is always written
            raise MigrationError("No revision was written.")
        return written

    async def diff(
        self,
        message: str | None = None,
        *,
        allow_empty: bool = False,
        from_empty_schema: bool = False,
    ) -> AvailableMigration | None:
        """Write a revision bringing the database to the table definitions, and return it.

        The database is compared with the table definitions, and what differs
        becomes the revision's upgrade. Nothing is written when nothing
        differs, unless ``allow_empty``.

        Args:
            message: The revision's message.
            allow_empty: Write a revision even when nothing differs.
            from_empty_schema: Write every table, as if the database were
                empty.

        Raises:
            MigrationError: With no table definitions to compare with, or when
                the database is not at the latest revisions.
        """
        if self._metadata is None:
            raise MigrationError(
                f'The "{self._name}" connection has no table definitions to compare with.',
            )
        tables = tables_of(self._metadata) if from_empty_schema else None
        hook = self._config.process_revision_directives

        def adjust(
            context: MigrationContext, revision: object, directives: list[MigrationScript]
        ) -> None:
            if tables is not None:
                directives[0].upgrade_ops, directives[0].downgrade_ops = creating(tables)
            if hook is not None:
                hook(context, revision, directives)
            if (
                not allow_empty
                and directives
                and directives[0].upgrade_ops is not None
                and directives[0].upgrade_ops.is_empty()
            ):
                directives.clear()

        def work(connection: Connection) -> AvailableMigration | None:
            directory = self._environment.directory()
            context = RevisionContext(
                Config(),
                directory,
                _command_args(message, autogenerate=True),
                process_revision_directives=adjust,
            )

            def steps(heads: tuple[str, ...], migration: MigrationContext) -> list[RevisionStep]:
                if tables is None:
                    context.run_autogenerate(heads, migration)
                else:
                    context.run_no_autogenerate(heads, migration)
                return []

            with refusing():
                self._environment.run(
                    connection, directory, steps, revision_context=context, read_only=True
                )
            return self._written(context)

        return await self._connected(work)

    async def dump_schema(
        self, message: str | None = None, *, table_filters: Sequence[str] = ()
    ) -> AvailableMigration:
        """Write a first revision creating every table the database has, and return it.

        For a database that predates its revisions: the revision is written,
        not applied — record it as applied with :meth:`rollup`.

        Args:
            message: The revision's message.
            table_filters: Regular expressions; only the tables whose name one
                of them finds are written. Every table with none.

        Raises:
            MigrationError: When revisions exist already, or the database has
                no table to write.
        """

        def work(connection: Connection) -> AvailableMigration:
            directory = self._environment.directory()
            if available(directory):
                raise MigrationError(
                    f'Delete the previous revisions in "{self._config.directory}" '
                    "before dumping the schema.",
                )
            reflected = MetaData()
            reflected.reflect(connection)
            internal = {self._config.version_table, self._config.history_table}
            tables = matching(
                (each for each in reflected.sorted_tables if each.name not in internal),
                table_filters,
            )
            if not tables:
                raise MigrationError("The database schema does not contain any tables.")

            hook = self._config.process_revision_directives

            def replace(
                context: MigrationContext, revision: object, directives: list[MigrationScript]
            ) -> None:
                directives[0].upgrade_ops, directives[0].downgrade_ops = creating(tables)
                if hook is not None:
                    hook(context, revision, directives)

            context = RevisionContext(
                Config(),
                directory,
                _command_args(message or "dump the existing schema", autogenerate=False),
                process_revision_directives=replace,
            )

            def steps(heads: tuple[str, ...], migration: MigrationContext) -> list[RevisionStep]:
                context.run_no_autogenerate(heads, migration)
                return []

            with refusing():
                self._environment.run(
                    connection, directory, steps, revision_context=context, read_only=True
                )
            written = self._written(context)
            if written is None:  # pragma: no cover — the operations above are never empty
                raise MigrationError("No revision was written.")
            return written

        return await self._connected(work)

    async def add_versions(self, versions: Sequence[str]) -> tuple[str, ...]:
        """Mark ``versions`` applied without running them, in order, and return them.

        Each must not be applied and must follow only applied revisions, as
        with :meth:`execute`.

        Raises:
            MigrationError: When a version is unknown, applied, or out of order.
        """
        results = await self._connected(
            lambda connection: self._apply(connection, versions, Direction.UP, marking=True)
        )
        return tuple(result.version for result in results)

    async def add_all_versions(self) -> tuple[str, ...]:
        """Mark every revision not yet applied as applied, without running any; return them."""

        def work(connection: Connection) -> tuple[ExecutionResult, ...]:
            directory = self._environment.directory()
            heads = self._environment.context(connection).get_current_heads()
            done = applied(directory, heads)
            pending = [each.revision for each in available(directory) if each.revision not in done]
            return self._apply(connection, pending, Direction.UP, marking=True)

        results = await self._connected(work)
        return tuple(result.version for result in results)

    async def delete_versions(self, versions: Sequence[str]) -> tuple[str, ...]:
        """Mark ``versions`` not applied without running them, in order, and return them.

        A version with a file must be applied and followed by no applied
        revision, as with :meth:`execute`. A version without one — a revision
        applied whose file is gone — is simply forgotten.

        Raises:
            MigrationError: When a version is not applied, or out of order.
        """
        return await self._connected(lambda connection: self._delete(connection, versions))

    async def delete_all_versions(self) -> None:
        """Mark every revision not applied, without running any."""

        def work(connection: Connection) -> None:
            def steps(_: tuple[str, ...], migration: MigrationContext) -> list[RevisionStep]:
                self._history.ensure(migration, connection)
                self._history.clear(migration)
                return []

            self._environment.run(connection, self._environment.directory(), steps, purge=True)

        await self._connected(work)

    async def rollup(self) -> AvailableMigration:
        """Forget every applied revision, then mark the single remaining one applied.

        For after squashing every revision into one: the database is left
        exactly as it is, recorded as being at that one revision.

        Raises:
            MigrationError: When there is no revision, or more than one.
        """

        def work(connection: Connection) -> AvailableMigration:
            directory = self._environment.directory()
            scripts = list(available(directory))
            if not scripts:
                raise MigrationError("No migrations found.")
            if len(scripts) > 1:
                raise MigrationError(
                    f"Too many migrations: {len(scripts)} found, a rollup needs exactly one.",
                )
            recorder = HistoryRecorder(self._history, marking=True)

            def steps(_: tuple[str, ...], migration: MigrationContext) -> Iterator[RevisionStep]:
                self._history.ensure(migration, connection)
                self._history.clear(migration)
                recorder.started()
                yield mark_step(directory, scripts[0], Direction.UP)

            self._environment.run(
                connection, directory, steps, purge=True, on_version_apply=recorder
            )
            return describe(scripts[0])

        return await self._connected(work)

    async def _connected(self, work: Callable[[Connection], _T]) -> _T:
        """Run ``work`` on a connection of its own, committing what it did."""
        async with self._engine.connect() as connection:
            result = await connection.run_sync(work)
            await connection.commit()
        return result

    def _status(self, connection: Connection) -> MigrationStatus:
        directory = self._environment.directory()
        heads = self._environment.context(connection).get_current_heads()
        history = self._history.read(connection)
        scripts = available(directory)
        by_version = {each.revision: each for each in scripts}
        # A head without a file hides what it followed; the history still names it.
        done = applied(directory, heads) | {version for version in history if version in by_version}
        migrations = tuple(describe(each) for each in scripts)
        executed = [
            ExecutedMigration(each.revision, *history.get(each.revision, (None, None)))
            for each in scripts
            if each.revision in done
        ]
        missing = [head for head in heads if head not in by_version]
        missing += [version for version in history if version not in by_version]
        unavailable = tuple(
            ExecutedMigration(version, *history.get(version, (None, None)))
            for version in dict.fromkeys(missing)
        )
        previous = [
            parent
            for head in heads
            if head in by_version
            for parent in parents(directory, by_version[head])
        ]
        new = tuple(each for each in migrations if each.version not in done)
        runnable = tuple(
            each.version
            for each in new
            if all(parent in done for parent in parents(directory, by_version[each.version]))
        )
        return MigrationStatus(
            current=heads,
            latest=tuple(each.version for each in migrations if each.is_head),
            previous=tuple(dict.fromkeys(previous)),
            next=runnable,
            available=migrations,
            executed=(*executed, *unavailable),
            new=new,
            executed_unavailable=unavailable,
        )

    def _migrate(self, connection: Connection, target: str) -> tuple[ExecutionResult, ...]:
        directory = self._environment.directory()
        recorder = HistoryRecorder(self._history)

        def steps(heads: tuple[str, ...], migration: MigrationContext) -> Iterator[RevisionStep]:
            self._history.ensure(migration, connection)
            _, planned = plan(directory, heads, target)
            for step in planned:
                recorder.started()
                yield step

        self._environment.run(connection, directory, steps, on_version_apply=recorder)
        return recorder.results

    def _apply(
        self,
        connection: Connection,
        versions: Sequence[str],
        direction: Direction,
        *,
        marking: bool,
    ) -> tuple[ExecutionResult, ...]:
        directory = self._environment.directory()
        recorder = HistoryRecorder(self._history, marking=marking)

        def steps(heads: tuple[str, ...], migration: MigrationContext) -> Iterator[RevisionStep]:
            scripts = self._checked(directory, heads, versions, direction)
            self._history.ensure(migration, connection)
            for each in scripts:
                recorder.started()
                yield (
                    mark_step(directory, each, direction)
                    if marking
                    else revision_step(directory, each, direction)
                )

        self._environment.run(connection, directory, steps, on_version_apply=recorder)
        return recorder.results

    def _delete(self, connection: Connection, versions: Sequence[str]) -> tuple[str, ...]:
        directory = self._environment.directory()
        heads = self._environment.context(connection).get_current_heads()
        with_file = set(known(directory, versions))
        recorded = self._history.read(connection)
        orphans = [version for version in versions if version not in with_file]
        for orphan in orphans:
            if orphan not in heads and orphan not in recorded:
                raise MigrationError(f'The version "{orphan}" is not applied.')
        version_table = Table(
            self._config.version_table,
            MetaData(),
            Column("version_num", String(_VERSION_LENGTH)),
            schema=self._config.version_table_schema,
        )
        recorder = HistoryRecorder(self._history, marking=True)

        def steps(current: tuple[str, ...], migration: MigrationContext) -> Iterator[RevisionStep]:
            scripts = self._checked(
                directory, current, [each for each in versions if each in with_file], Direction.DOWN
            )
            self._history.ensure(migration, connection)
            for orphan in orphans:
                migration.execute(
                    delete(version_table).where(version_table.c.version_num == orphan)
                )
            self._history.remove(migration, orphans)
            for each in scripts:
                yield mark_step(directory, each, Direction.DOWN)

        self._environment.run(connection, directory, steps, on_version_apply=recorder)
        done = {result.version for result in recorder.results}
        return tuple(version for version in versions if version in done or version in orphans)

    def _checked(
        self,
        directory: ScriptDirectory,
        heads: tuple[str, ...],
        versions: Sequence[str],
        direction: Direction,
    ) -> list[Script]:
        """Return the revisions ``versions`` name, checking each may run ``direction`` in turn."""
        done = applied(directory, heads)
        found: list[Script] = []
        for version in versions:
            script = resolve(directory, version)
            revision = script.revision
            if direction is Direction.UP:
                if revision in done:
                    raise MigrationError(f'The version "{revision}" is already applied.')
                missing = [parent for parent in parents(directory, script) if parent not in done]
                if missing:
                    raise MigrationError(
                        f'The version "{revision}" follows "{missing[0]}", which is not applied.',
                    )
                done.add(revision)
            else:
                if revision not in done:
                    raise MigrationError(f'The version "{revision}" is not applied.')
                followers = sorted(
                    each
                    for each in done
                    if revision in parents(directory, resolve(directory, each))
                )
                if followers:
                    raise MigrationError(
                        f'The version "{revision}" is followed by "{followers[0]}", '
                        "which is applied.",
                    )
                done.discard(revision)
            found.append(script)
        return found

    def _sql(
        self,
        connection: Connection,
        directory: ScriptDirectory,
        heads: tuple[str, ...],
        steps: Sequence[RevisionStep],
    ) -> str:
        """Write the SQL of ``steps`` from ``heads``, as the runner would run it."""
        output = StringIO()
        # Nothing runs, so nothing is timed: the recorded duration is left empty.
        recorder = HistoryRecorder(self._history, marking=True)

        def planned(_: tuple[str, ...], migration: MigrationContext) -> Sequence[RevisionStep]:
            self._history.ensure(migration, connection)
            return steps

        self._environment.run(
            connection,
            directory,
            planned,
            as_sql=True,
            output=output,
            starting_rev=heads,
            on_version_apply=recorder,
        )
        return output.getvalue()

    def _written(self, context: RevisionContext) -> AvailableMigration | None:
        with refusing():
            written = [each for each in context.generate_scripts() if each is not None]
        if not written:
            return None
        migration = describe(written[0])
        self.logger.info(
            "Wrote the revision {version} to {path}",
            {"connection": self._name, "version": migration.version, "path": migration.path},
        )
        return migration

    def _log_results(self, results: Sequence[ExecutionResult]) -> None:
        for result in results:
            self.logger.info(
                "Migrated {version} {direction} in {duration} s",
                {
                    "connection": self._name,
                    "version": result.version,
                    "direction": result.direction.value,
                    "duration": round(result.duration, 3),
                },
            )


def _command_args(message: str | None, *, autogenerate: bool) -> dict[str, object]:
    """What a revision is written from: its message, and where it goes in the history."""
    return {
        "message": message,
        "autogenerate": autogenerate,
        "sql": False,
        "head": "head",
        "splice": False,
        "branch_label": None,
        "version_path": None,
        "rev_id": None,
        "depends_on": None,
    }
