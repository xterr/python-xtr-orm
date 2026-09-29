"""Unit tests for :class:`xtr_orm.bundle.OrmBundle`; every database is a SQLite file."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from typing import TYPE_CHECKING, Annotated, cast

import pytest
from advanced_alchemy.config import SQLAlchemyAsyncConfig
from advanced_alchemy.routing import RoutingAsyncSessionMaker
from sqlalchemy import Column, MetaData, String, Table, insert, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import QueuePool
from xtr_console import Application
from xtr_dependency_injection import (
    Injected,
    Kernel,
    Target,
    bind_callable,
    current_unit_of_work,
)
from xtr_dependency_injection.testing import assert_zero_config
from xtr_logging_contracts import NullLogger

from xtr_orm import ConnectionRegistry, DatabaseManager, Migrator
from xtr_orm.bundle import ORM_CHANNEL, OrmBundle

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.anyio


_WHERE = Table("location", MetaData(), Column("name", String))


def _replicated(tmp_path: Path) -> Kernel:
    """A kernel whose databases each hold a table naming the database it is in."""
    for name in ("primary", "replica"):
        with closing(sqlite3.connect(tmp_path / f"{name}.sqlite")) as database:
            _ = database.execute("create table location (name text)")
            _ = database.execute("insert into location values (?)", (name,))
            database.commit()
    return Kernel(
        "tests.fixtures.app_orm_named",
        env="test",
        environ={
            "ORM_TEST_URL": f"sqlite+aiosqlite:///{tmp_path / 'primary.sqlite'}",
            "ORM_TEST_REPLICA_URL": f"sqlite+aiosqlite:///{tmp_path / 'replica.sqlite'}",
        },
    )


async def _read(session: AsyncSession) -> str:
    """Name the database a read reaches: the one whose first row names itself."""
    return cast("str", (await session.execute(select(_WHERE.c.name).limit(1))).scalar_one())


def _kernel(tmp_path: Path, app: str = "tests.fixtures.app_orm") -> Kernel:
    return Kernel(
        app,
        env="test",
        environ={
            "ORM_TEST_URL": f"sqlite+aiosqlite:///{tmp_path / 'app.sqlite'}",
            "ORM_TEST_REPORTS_URL": f"sqlite+aiosqlite:///{tmp_path / 'reports.sqlite'}",
            "ORM_TEST_MIGRATIONS": str(tmp_path / "migrations"),
        },
    )


async def test_zero_config_builds_boots_and_shuts_down() -> None:
    await assert_zero_config(OrmBundle)


async def test_every_connection_is_provided_by_name_and_the_default_without_one(
    tmp_path: Path,
) -> None:
    async with await _kernel(tmp_path).boot() as booted:
        container = booted.container
        default = await container.get(AsyncEngine)
        reports = await container.get(AsyncEngine, "reports")

        assert default is await container.get(AsyncEngine, "default")
        assert reports is not default
        assert str(default.url).endswith("app.sqlite")
        assert str(reports.url).endswith("reports.sqlite")
        services: tuple[type[object], ...] = (SQLAlchemyAsyncConfig, Migrator, DatabaseManager)
        for service in services:
            assert await container.get(service) is await container.get(service, "default")
        maker = await container.get(async_sessionmaker[AsyncSession])
        assert maker is await container.get(async_sessionmaker[AsyncSession], "default")


async def test_a_connection_reads_only_its_own_environment_variables(tmp_path: Path) -> None:
    kernel = Kernel(
        "tests.fixtures.app_orm",
        env="test",
        environ={
            "ORM_TEST_URL": f"sqlite+aiosqlite:///{tmp_path / 'app.sqlite'}",
            "ORM_TEST_MIGRATIONS": str(tmp_path / "migrations"),
        },  # ORM_TEST_REPORTS_URL, the "reports" connection's, is not set
    )

    async def unit(session: Injected[AsyncSession]) -> int:
        return cast("int", (await session.execute(text("select 1"))).scalar_one())

    async with await kernel.boot() as booted:
        registry = await booted.container.get(ConnectionRegistry)

        assert (await registry.migrator()).name == "default"
        assert (await registry.database()).database.endswith("app.sqlite")
        assert await bind_callable(booted.container, unit, per_call_scope=True)() == 1


async def test_a_connection_is_in_use_once_its_engine_is_built(tmp_path: Path) -> None:
    async with await _kernel(tmp_path).boot() as booted:
        registry = await booted.container.get(ConnectionRegistry)
        assert registry.in_use() == ()

        _ = await booted.container.get(AsyncEngine, "reports")

        assert registry.in_use() == ("reports",)


async def test_the_engine_and_sessions_take_their_configured_options(tmp_path: Path) -> None:
    async with await _kernel(tmp_path).boot() as booted:
        engine = await booted.container.get(AsyncEngine)
        maker = await booted.container.get(async_sessionmaker[AsyncSession])

        assert engine.pool._pre_ping
        assert maker.kw["expire_on_commit"] is False
        assert maker.kw["bind"] is engine


async def test_a_session_lives_for_one_unit_of_work(tmp_path: Path) -> None:
    seen: list[AsyncSession] = []

    async def unit(session: Injected[AsyncSession]) -> int:
        seen.append(session)
        return cast("int", (await session.execute(text("select 1"))).scalar_one())

    async with await _kernel(tmp_path).boot() as booted:
        bound = bind_callable(booted.container, unit, per_call_scope=True)

        assert await bound() == 1
        assert await bound() == 1

    assert len(seen) == 2
    assert seen[0] is not seen[1]


async def test_the_migrator_reads_its_connection_s_revisions_and_tables(tmp_path: Path) -> None:
    async with await _kernel(tmp_path).boot() as booted:
        migrator = await booted.container.get(Migrator)
        reports = await booted.container.get(Migrator, "reports")

        written = await migrator.diff("create the catalogue")
        assert written is not None
        _ = await migrator.migrate()

        assert migrator.name == "default"
        assert migrator.config.directory == str(tmp_path / "migrations")
        assert migrator.config.render_as_batch
        assert reports.name == "reports"
        assert reports.config.directory.endswith("migrations/reports")


async def test_migrators_log_to_the_orm_channel(tmp_path: Path) -> None:
    async with await _kernel(tmp_path).boot() as booted:
        migrator = await booted.container.get(Migrator)

        assert not isinstance(migrator.logger, NullLogger)
        assert ORM_CHANNEL == "orm"


async def test_options_in_the_url_configure_the_engine_and_sessions(tmp_path: Path) -> None:
    kernel = Kernel(
        "tests.fixtures.app_orm",
        env="test",
        environ={
            "ORM_TEST_URL": f"sqlite+aiosqlite:///{tmp_path / 'app.sqlite'}"
            "?pool_pre_ping=false&expire_on_commit=true&isolation_level=SERIALIZABLE",
            "ORM_TEST_REPORTS_URL": f"sqlite+aiosqlite:///{tmp_path / 'reports.sqlite'}",
            "ORM_TEST_MIGRATIONS": str(tmp_path / "migrations"),
        },
    )
    async with await kernel.boot() as booted:
        engine = await booted.container.get(AsyncEngine)
        maker = await booted.container.get(async_sessionmaker[AsyncSession])
        database = await booted.container.get(DatabaseManager)

        assert str(engine.url) == f"sqlite+aiosqlite:///{tmp_path / 'app.sqlite'}"
        assert not engine.pool._pre_ping
        assert maker.kw["expire_on_commit"] is True
        assert database.database == str(tmp_path / "app.sqlite")
        async with engine.connect() as connection:
            assert await connection.get_isolation_level() == "SERIALIZABLE"


async def test_the_database_manager_reads_its_connection_s_url(tmp_path: Path) -> None:
    async with await _kernel(tmp_path).boot() as booted:
        database = await booted.container.get(DatabaseManager, "reports")

        assert database.database == str(tmp_path / "reports.sqlite")
        assert await database.create()


async def test_the_registry_names_every_connection_for_the_commands(tmp_path: Path) -> None:
    async with await _kernel(tmp_path).boot() as booted:
        registry = await booted.container.get(ConnectionRegistry)

        assert registry.names() == ("default", "reports")
        assert registry.default == "default"
        assert await registry.engine() is await booted.container.get(AsyncEngine)
        assert await registry.migrator("reports") is await booted.container.get(Migrator, "reports")
        assert await registry.database() is await booted.container.get(DatabaseManager)


async def test_the_commands_are_registered_when_the_console_is_active(tmp_path: Path) -> None:
    async with await _kernel(tmp_path).boot() as booted:
        application = await booted.container.get(Application)
        names = {command.name for command in application.commands.commands()}

        assert {"orm:migrations:migrate", "orm:database:create", "orm:run-sql"} <= names


async def test_the_default_connection_may_have_any_name(tmp_path: Path) -> None:
    async with await _replicated(tmp_path).boot() as booted:
        container = booted.container

        assert await container.get(AsyncEngine) is await container.get(AsyncEngine, "main")
        assert (await container.get(Migrator)).config.directory.endswith("migrations")
        assert (await container.get(Migrator, "kept")).config.directory.endswith("migrations/kept")


async def test_a_connection_with_replicas_routes_through_a_routing_session_maker(
    tmp_path: Path,
) -> None:
    async with await _replicated(tmp_path).boot() as booted:
        container = booted.container
        maker = await container.get(RoutingAsyncSessionMaker)

        assert maker is await container.get(RoutingAsyncSessionMaker, "main")
        assert not container.has(async_sessionmaker[AsyncSession], "main")
        assert await container.get(AsyncEngine) is maker.primary_engine
        assert str(maker.primary_engine.url).endswith("primary.sqlite")
        assert [str(each.url) for each in maker.replica_engines] == [
            f"sqlite+aiosqlite:///{tmp_path / 'replica.sqlite'}"
        ]


async def test_reads_go_to_a_replica_until_the_unit_writes(tmp_path: Path) -> None:
    async def unit(session: Injected[AsyncSession]) -> list[str]:
        seen = [await _read(session)]
        _ = await session.execute(insert(_WHERE).values(name="written"))
        seen.append(await _read(session))
        await session.commit()
        seen.append(await _read(session))
        return seen

    async with await _replicated(tmp_path).boot() as booted:
        bound = bind_callable(booted.container, unit, per_call_scope=True)

        assert await bound() == ["replica", "primary", "primary"]
        assert await bound() == ["replica", "primary", "primary"]


async def test_a_session_opened_after_a_write_leaves_the_unit_on_the_primary(
    tmp_path: Path,
) -> None:
    async def unit(session: Injected[AsyncSession]) -> str:
        _ = await session.execute(insert(_WHERE).values(name="written"))
        opened = current_unit_of_work()
        assert opened is not None
        _ = await opened.get(AsyncSession, "kept")
        return await _read(session)

    async with await _replicated(tmp_path).boot() as booted:
        assert await bind_callable(booted.container, unit, per_call_scope=True)() == "primary"


async def test_keep_replica_goes_back_to_the_replicas_after_a_commit(tmp_path: Path) -> None:
    async def kept(session: Annotated[AsyncSession, Target("kept")]) -> list[str]:
        _ = await session.execute(insert(_WHERE).values(name="written"))
        before = await _read(session)
        await session.commit()
        return [before, await _read(session)]

    async with await _replicated(tmp_path).boot() as booted:
        bound = bind_callable(booted.container, kept, per_call_scope=True)

        assert await bound() == ["primary", "replica"]


async def test_migrations_and_the_database_commands_use_the_primary(tmp_path: Path) -> None:
    async with await _replicated(tmp_path).boot() as booted:
        migrator = await booted.container.get(Migrator)
        database = await booted.container.get(DatabaseManager)

        assert str(migrator.engine.url).endswith("primary.sqlite")
        assert database.database.endswith("primary.sqlite")


async def test_engines_are_disposed_when_the_container_closes(tmp_path: Path) -> None:
    async with await _kernel(tmp_path).boot() as booted:
        engine = await booted.container.get(AsyncEngine)
        async with engine.connect() as connection:
            _ = await connection.execute(text("select 1"))
        pool = engine.pool
        assert isinstance(pool, QueuePool)
        assert pool.checkedin() == 1

    assert pool.checkedin() == 0
