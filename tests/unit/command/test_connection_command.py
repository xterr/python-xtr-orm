"""Where an orm command's connections come from, and what it says when a name is unknown."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from xtr_console import Application, ApplicationTester, ExitCode, MissingContainerError

from tests.support.console import output
from xtr_orm.command import MigrationsStatusCommand

if TYPE_CHECKING:
    from xtr_orm import ConnectionRegistry

pytestmark = pytest.mark.anyio


async def test_without_a_container_the_console_names_the_parameter_it_cannot_fill() -> None:
    # A plain application: no invoker builds the command, so the console falls
    # back to building it bare and finds the parameter it cannot fill.
    tester = ApplicationTester(Application("test", catch_exceptions=False), width=200)

    with pytest.raises(MissingContainerError, match="connections"):
        _ = await tester.execute(["orm:migrations:status"])


async def test_a_command_built_by_hand_acts_on_the_registry_it_was_given(
    connections: ConnectionRegistry,
) -> None:
    assert MigrationsStatusCommand(connections)._connections is connections


async def test_an_unknown_connection_is_named_with_the_known_ones(
    tester: ApplicationTester,
) -> None:
    assert await tester.execute(["orm:migrations:status", "--connection", "other"]) == (
        ExitCode.FAILURE
    )
    assert 'Unknown connection "other"; the connections are: "default".' in output(tester)
