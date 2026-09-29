"""The orm commands run without a container, on a connection given with ``use_connections``."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from xtr_console import Application, ApplicationTester

from xtr_orm import ConnectionRegistry, DatabaseManager
from xtr_orm.command import use_connections

if TYPE_CHECKING:
    from collections.abc import Generator

    from sqlalchemy.ext.asyncio import AsyncEngine

    from xtr_orm import Migrator


@pytest.fixture
def connections(
    engine: AsyncEngine, migrator: Migrator, database_url: str
) -> Generator[ConnectionRegistry, None, None]:
    """The one connection every command acts on, named "default"."""
    registry = ConnectionRegistry()
    registry.register(
        "default", engine=engine, migrator=migrator, database=DatabaseManager(database_url)
    )
    use_connections(registry)
    yield registry
    use_connections(None)


@pytest.fixture
def tester(connections: ConnectionRegistry) -> ApplicationTester:
    del connections  # requested so the commands have them
    return ApplicationTester(Application("test", catch_exceptions=False), width=200)
