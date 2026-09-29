"""Unit tests for :mod:`xtr_orm.command.connections`."""

from __future__ import annotations

from xtr_orm import ConnectionRegistry
from xtr_orm.command.connections import UNSET, resolve_connections, use_connections


def test_a_command_given_connections_keeps_them() -> None:
    given = ConnectionRegistry()

    assert resolve_connections(given) is given


def test_a_command_given_none_reads_those_set_for_the_process() -> None:
    registry = ConnectionRegistry()
    use_connections(registry)
    try:
        assert resolve_connections(UNSET) is registry
    finally:
        use_connections(None)

    assert resolve_connections(UNSET) is None
