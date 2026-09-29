"""Unit tests for :class:`xtr_orm.bundle.OrmConfig`."""

from __future__ import annotations

from typing import cast

import pytest

from xtr_orm.bundle import ConnectionConfig, MigrationsConfig, OrmConfig
from xtr_orm.exception import InvalidArgumentError


def test_it_builds_one_default_connection_with_no_arguments() -> None:
    config = OrmConfig()

    assert config.default_connection == "default"
    assert list(config.connections) == ["default"]
    migrations = config.connections["default"].migrations
    assert migrations is not None
    assert migrations.directory == "%kernel.project_dir%/migrations"


def test_every_other_connection_keeps_its_revisions_in_a_directory_of_its_own() -> None:
    config = OrmConfig(
        default_connection="main",
        connections={"reports": ConnectionConfig(url="sqlite://"), "main": ConnectionConfig()},
    )

    assert list(config.connections) == ["main", "reports"]
    reports = config.connections["reports"].migrations
    assert reports is not None
    assert reports.directory == "%kernel.project_dir%/migrations/reports"


def test_a_connection_s_own_migrations_settings_are_kept() -> None:
    own = MigrationsConfig(directory="db/revisions")

    config = OrmConfig(connections={"default": ConnectionConfig(migrations=own)})

    assert config.connections["default"].migrations is own


def test_no_connection_is_refused() -> None:
    with pytest.raises(InvalidArgumentError, match="at least one connection"):
        _ = OrmConfig(connections={})


def test_an_unnamed_connection_is_refused() -> None:
    with pytest.raises(InvalidArgumentError, match="non-empty name"):
        _ = OrmConfig(connections={"": ConnectionConfig()})


def test_a_connection_that_is_not_a_connection_config_is_refused() -> None:
    with pytest.raises(InvalidArgumentError, match="must be a ConnectionConfig"):
        # Cast: the mistake under test is one a type checker would catch first.
        _ = OrmConfig(connections=cast("dict[str, ConnectionConfig]", {"default": "sqlite://"}))


def test_a_default_connection_that_is_not_configured_is_refused() -> None:
    with pytest.raises(InvalidArgumentError, match='"main" is not configured'):
        _ = OrmConfig(default_connection="main")


def test_two_connections_sharing_a_migrations_directory_are_refused() -> None:
    shared = MigrationsConfig(directory="migrations")

    with pytest.raises(InvalidArgumentError, match="same directory"):
        _ = OrmConfig(
            connections={
                "default": ConnectionConfig(migrations=shared),
                "reports": ConnectionConfig(migrations=shared),
            },
        )
