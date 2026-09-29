"""Shared test fixtures. Every database is a SQLite file under the test's own directory."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from tests.support.schema import METADATA
from xtr_orm.migrations import MigrationsConfig, Migrator

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def database_url(tmp_path: Path) -> str:
    return f"sqlite+aiosqlite:///{tmp_path / 'app.sqlite'}"


@pytest.fixture
def migrations_directory(tmp_path: Path) -> Path:
    return tmp_path / "migrations"


@pytest.fixture
async def engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    built = create_async_engine(database_url)
    yield built
    await built.dispose()


@pytest.fixture
def migrator(engine: AsyncEngine, migrations_directory: Path) -> Migrator:
    config = MigrationsConfig(directory=str(migrations_directory), render_as_batch=True)
    return Migrator(engine, config, METADATA)
