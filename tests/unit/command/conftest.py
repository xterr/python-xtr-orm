"""The orm commands under a console, each built with a registry as a container builds it."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast, final

import pytest
from typing_extensions import override
from xtr_console import Application, ApplicationTester, CommandInvokerInterface

from xtr_orm import ConnectionRegistry, DatabaseManager

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from sqlalchemy.ext.asyncio import AsyncEngine
    from xtr_console.command import CommandArguments, CommandDescriptor, CommandSignature

    from xtr_orm import Migrator
    from xtr_orm.command.connection_command import ConnectionCommand


@final
class _RegistryInvoker(CommandInvokerInterface):
    """Builds an orm command with the connections it acts on, as a container would."""

    def __init__(self, connections: ConnectionRegistry) -> None:
        self._connections = connections

    @override
    async def invoke(
        self,
        command: CommandDescriptor,
        signature: CommandSignature,
        arguments: CommandArguments,
    ) -> object:
        del signature
        command_type = cast("type[ConnectionCommand]", command.target)
        # The arguments come parsed off the command line, typed only as objects.
        call = cast("Callable[..., Awaitable[object]]", command_type(self._connections))
        return await call(*arguments.args, **arguments.kwargs)


@pytest.fixture
def connections(engine: AsyncEngine, migrator: Migrator, database_url: str) -> ConnectionRegistry:
    """The one connection every command acts on, named "default"."""
    registry = ConnectionRegistry()
    registry.register(
        "default", engine=engine, migrator=migrator, database=DatabaseManager(database_url)
    )
    return registry


@pytest.fixture
def tester(connections: ConnectionRegistry) -> ApplicationTester:
    application = Application("test", catch_exceptions=False)
    application.use_invoker(_RegistryInvoker(connections))
    # Wide enough that no table column is truncated before a test reads it.
    return ApplicationTester(application, width=200)
