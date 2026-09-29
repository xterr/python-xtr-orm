"""Unit tests for :class:`xtr_orm.command.connection_command.ConnectionCommand`."""

from __future__ import annotations

import pytest
from xtr_console import Application, ApplicationTester, ExitCode

from tests.support.console import output

pytestmark = pytest.mark.anyio


async def test_without_connections_it_says_how_to_give_them() -> None:
    tester = ApplicationTester(Application("test", catch_exceptions=False), width=200)

    assert await tester.execute(["orm:migrations:status"]) == ExitCode.FAILURE
    assert "use_connections()" in output(tester)


async def test_an_unknown_connection_is_named_with_the_known_ones(
    tester: ApplicationTester,
) -> None:
    assert await tester.execute(["orm:migrations:status", "--connection", "other"]) == (
        ExitCode.FAILURE
    )
    assert 'Unknown connection "other"; the connections are: "default".' in output(tester)
