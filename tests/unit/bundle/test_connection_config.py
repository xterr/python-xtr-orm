"""Unit tests for :class:`xtr_orm.bundle.ConnectionConfig`."""

from __future__ import annotations

from dataclasses import replace

import pytest
from xtr_dependency_injection import env

from xtr_orm.bundle import ConnectionConfig
from xtr_orm.exception import InvalidArgumentError


def test_it_reads_its_url_from_the_environment_by_default() -> None:
    config = ConnectionConfig()

    assert config.url == "%env(DATABASE_URL)%"
    assert config.migrations is None
    assert config.bind_key is None


def test_a_url_from_the_environment_is_left_unread() -> None:
    config = ConnectionConfig(url=env("SOME_DATABASE_URL"))

    assert repr(config.url) == "env(SOME_DATABASE_URL)"


def test_an_empty_url_is_refused() -> None:
    with pytest.raises(InvalidArgumentError, match="URL must not be empty"):
        _ = ConnectionConfig(url="")


@pytest.mark.parametrize(
    ("field", "option"),
    [
        ("engine_options", "pool_sise"),
        ("session_options", "expire_on_comit"),
        ("alchemy_options", "connection_string"),
    ],
)
def test_an_unknown_option_is_refused_with_the_known_ones(field: str, option: str) -> None:
    with pytest.raises(InvalidArgumentError, match=f'Unknown .* option "{option}"'):
        _ = replace(ConnectionConfig(), **{field: {option: 1}})


def test_known_options_are_accepted() -> None:
    config = ConnectionConfig(
        engine_options={"echo": True, "pool_size": 5},
        session_options={"expire_on_commit": False},
        alchemy_options={"enable_touch_updated_timestamp_listener": False},
    )

    assert config.engine_options["pool_size"] == 5


def test_replicas_are_named_urls() -> None:
    config = ConnectionConfig(replicas={"replica1": env("REPLICA_URL")}, keep_replica=True)

    assert list(config.replicas) == ["replica1"]
    assert config.keep_replica


def test_an_unnamed_replica_is_refused() -> None:
    with pytest.raises(InvalidArgumentError, match="replica needs a non-empty name"):
        _ = ConnectionConfig(replicas={"": "sqlite://"})


def test_a_replica_without_a_url_is_refused() -> None:
    with pytest.raises(InvalidArgumentError, match='"replica1" replica\'s URL must not be empty'):
        _ = ConnectionConfig(replicas={"replica1": ""})


def test_the_routing_is_set_through_the_replicas_not_the_layer_s_options() -> None:
    with pytest.raises(InvalidArgumentError, match='Unknown alchemy option "routing_config"'):
        _ = ConnectionConfig(alchemy_options={"routing_config": None})


def test_url_options_are_merged_over_the_configured_ones() -> None:
    config = ConnectionConfig(
        url="postgresql+asyncpg://app:s3cret@db/shop?pool_size=20&expire_on_commit=false"
        "&echo=debug&pool_timeout=2.5&keep_replica=yes&ssl=require",
        engine_options={"pool_size": 5, "pool_pre_ping": True},
        session_options={"autoflush": False},
    )

    merged = config.with_url_options()

    assert merged.url == "postgresql+asyncpg://app:s3cret@db/shop?ssl=require"
    assert merged.engine_options == {
        "pool_size": 20,
        "pool_pre_ping": True,
        "echo": "debug",
        "pool_timeout": 2.5,
    }
    assert merged.session_options == {"autoflush": False, "expire_on_commit": False}
    assert merged.keep_replica
    assert config.engine_options == {"pool_size": 5, "pool_pre_ping": True}


def test_a_url_with_only_driver_options_is_left_as_it_is() -> None:
    config = ConnectionConfig(url="sqlite+aiosqlite:///app.sqlite?check_same_thread=false")

    assert config.with_url_options() is config


def test_a_repeated_url_option_takes_its_last_value() -> None:
    merged = ConnectionConfig(url="sqlite+aiosqlite://?pool_size=1&pool_size=3").with_url_options()

    assert merged.engine_options == {"pool_size": 3}
    assert merged.url == "sqlite+aiosqlite://"


@pytest.mark.parametrize(
    ("query", "reason"),
    [
        ("pool_size=many", 'The URL option "pool_size" must be a whole number, got "many".'),
        ("pool_timeout=soon", 'The URL option "pool_timeout" must be a number, got "soon".'),
        ("expire_on_commit=maybe", 'The URL option "expire_on_commit" must be a flag'),
        ("keep_replica=2", 'The URL option "keep_replica" must be a flag'),
    ],
)
def test_a_url_option_that_cannot_be_read_is_refused(query: str, reason: str) -> None:
    config = ConnectionConfig(url=f"sqlite+aiosqlite://?{query}")

    with pytest.raises(InvalidArgumentError) as raised:
        _ = config.with_url_options()

    assert raised.value.reason.startswith(reason)
