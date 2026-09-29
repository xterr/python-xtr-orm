"""Where the orm commands find the connections they act on."""

from __future__ import annotations

from typing import ClassVar, Final, final

from xtr_orm.connection_registry import ConnectionRegistry

__all__ = ["NO_CONNECTIONS", "UNSET", "resolve_connections", "use_connections"]

UNSET: Final = ConnectionRegistry()
"""The default of every command's ``connections`` parameter, meaning "no container gave one".

Typed as what a container fills the parameter with, so the engine still
matches it; ``ConnectionRegistry | None`` is a different type and never would be.
"""

NO_CONNECTIONS: Final = (
    "No database connections: wire a container, or call xtr_orm.command.use_connections()."
)


@final
class _Process:
    """The connections commands use where no container supplies them."""

    connections: ClassVar[ConnectionRegistry | None] = None


def use_connections(connections: ConnectionRegistry | None) -> None:
    """Have every orm command act on ``connections`` wherever no container supplies them."""
    _Process.connections = connections


def resolve_connections(given: ConnectionRegistry) -> ConnectionRegistry | None:
    """Return the connections a command was given, or those set with :func:`use_connections`."""
    return given if given is not UNSET else _Process.connections
