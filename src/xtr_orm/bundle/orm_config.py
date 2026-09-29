"""Configuration for :class:`~xtr_orm.bundle.orm_bundle.OrmBundle`."""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from dataclasses import dataclass, field

from xtr_orm.connection_registry import DEFAULT_CONNECTION
from xtr_orm.exception import InvalidArgumentError
from xtr_orm.migrations import MigrationsConfig

from .connection_config import ConnectionConfig

__all__ = ["OrmConfig"]

_MIGRATIONS_DIRECTORY = "%kernel.project_dir%/migrations"


def _one_connection() -> dict[str, ConnectionConfig]:
    return {DEFAULT_CONNECTION: ConnectionConfig()}


@dataclass(frozen=True, slots=True)
class OrmConfig:
    """Which databases the application uses, each by name.

    With no configuration there is one connection, ``default``, reading its
    URL from ``DATABASE_URL`` when first used, with its revisions in
    ``migrations`` in the project directory.

    ```python
    OrmConfig(
        connections={
            "default": ConnectionConfig(url=env("DATABASE_URL")),
            "reports": ConnectionConfig(url=env("REPORTS_URL"), bind_key="reports"),
        },
    )
    ```

    Attributes:
        default_connection: The connection provided without a qualifier, and
            used by every command not given ``--connection``.
        connections: Every connection, by name — the default first once
            built, each with its migrations settings decided.
    """

    default_connection: str = DEFAULT_CONNECTION
    connections: Mapping[str, ConnectionConfig] = field(default_factory=_one_connection)

    def __post_init__(self) -> None:
        """Refuse no connection, an unnamed one, or a default that is not one of them.

        Raises:
            InvalidArgumentError: When the configuration cannot be used.
        """
        if not self.connections:
            raise InvalidArgumentError("Configure at least one connection.")
        for name, connection in self.connections.items():
            if not isinstance(name, str) or not name:  # pyright: ignore[reportUnnecessaryIsInstance] -- configs are written by hand; the annotation is not enforced
                raise InvalidArgumentError(f"A connection needs a non-empty name, got {name!r}.")
            if not isinstance(connection, ConnectionConfig):  # pyright: ignore[reportUnnecessaryIsInstance] -- as above
                raise InvalidArgumentError(
                    f'The "{name}" connection must be a ConnectionConfig, got {connection!r}.',
                )
        if self.default_connection not in self.connections:
            raise InvalidArgumentError(
                f'The default connection "{self.default_connection}" is not configured.',
            )
        settled = _settled(self.default_connection, self.connections)
        directories: dict[str, str] = {}
        for name, connection in settled.items():
            directory = connection.migrations.directory if connection.migrations else ""
            if directory in directories:
                raise InvalidArgumentError(
                    f'The "{name}" and "{directories[directory]}" connections keep their '
                    f'migrations in the same directory, "{directory}".',
                )
            directories[directory] = name
        # Settled here, not when read, so the directory defaults take part in
        # parameter resolution like any value the application wrote.
        object.__setattr__(self, "connections", settled)


def _settled(
    default: str, connections: Mapping[str, ConnectionConfig]
) -> dict[str, ConnectionConfig]:
    """Return every connection, the default first, each with its migrations directory decided."""
    ordered = [default, *(name for name in connections if name != default)]
    settled: dict[str, ConnectionConfig] = {}
    for name in ordered:
        connection = connections[name]
        if connection.migrations is None:
            directory = (
                _MIGRATIONS_DIRECTORY if name == default else f"{_MIGRATIONS_DIRECTORY}/{name}"
            )
            connection = dataclasses.replace(
                connection, migrations=MigrationsConfig(directory=directory)
            )
        settled[name] = connection
    return settled
