"""A driver's tables reach the connection the parameters name, once, and only when enabled."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import pytest
from advanced_alchemy.base import metadata_registry
from sqlalchemy import MetaData

from tests.support.builder import FakeBuilder, as_builder
from tests.support.mappings import TableDriver
from xtr_orm import InvalidArgumentError
from xtr_orm.bundle import ConnectionConfig, OrmConfig, OrmMappingsPass

if TYPE_CHECKING:
    from collections.abc import Mapping

    from xtr_orm import MappingDriverInterface

_CONNECTION: Final = "toy.connection"
_ENABLED: Final = "toy.enabled"
_ON: Final[Mapping[str, object]] = {_CONNECTION: "default", _ENABLED: True}


def _builder(connection: ConnectionConfig, parameters: Mapping[str, object] = _ON) -> FakeBuilder:
    """A builder holding one connection named ``default``, and the parameters given."""
    return FakeBuilder(OrmConfig(connections={"default": connection}), parameters)


def _pass(driver: MappingDriverInterface | None = None) -> OrmMappingsPass:
    """The pass a bundle registers, with ``driver`` handed over as its bundle would."""
    built = OrmMappingsPass(_CONNECTION, _ENABLED)
    if driver is not None:
        built.set_driver(driver)
    return built


def test_the_tables_go_into_the_connections_own_definitions() -> None:
    metadata = MetaData()
    builder = _builder(ConnectionConfig(metadata=metadata))

    _pass(TableDriver("toy_token", "toy_client")).process(as_builder(builder))

    assert set(metadata.tables) == {"toy_token", "toy_client"}
    assert builder.logged == [
        'Loaded toy_token, toy_client into the "default" connection\'s table definitions.'
    ]


def test_a_driver_given_to_the_constructor_is_used() -> None:
    metadata = MetaData()
    given = OrmMappingsPass(_CONNECTION, _ENABLED, driver=TableDriver("toy_token"))

    given.process(as_builder(_builder(ConnectionConfig(metadata=metadata))))

    assert set(metadata.tables) == {"toy_token"}


def test_without_its_own_definitions_the_tables_go_to_the_registry_of_the_bind_key() -> None:
    bind_key = "xtr_orm_test_mappings_pass"

    _pass(TableDriver("toy_token")).process(
        as_builder(_builder(ConnectionConfig(bind_key=bind_key)))
    )

    assert "toy_token" in metadata_registry.get(bind_key).tables


def test_loading_twice_leaves_one_set_of_tables_and_says_nothing_was_added() -> None:
    metadata = MetaData()
    builder = _builder(ConnectionConfig(metadata=metadata))
    given = _pass(TableDriver("toy_token"))
    given.process(as_builder(builder))

    given.process(as_builder(builder))

    assert set(metadata.tables) == {"toy_token"}
    assert builder.logged[1] == (
        'Loaded nothing new into the "default" connection\'s table definitions.'
    )


def test_a_disabled_pass_adds_nothing() -> None:
    metadata = MetaData()
    builder = _builder(
        ConnectionConfig(metadata=metadata), {_CONNECTION: "default", _ENABLED: False}
    )

    _pass(TableDriver("toy_token")).process(as_builder(builder))

    assert not metadata.tables
    assert builder.logged == []


def test_an_unset_enabled_parameter_adds_nothing() -> None:
    metadata = MetaData()
    builder = _builder(ConnectionConfig(metadata=metadata), {_CONNECTION: "default"})

    _pass(TableDriver("toy_token")).process(as_builder(builder))

    assert not metadata.tables


@pytest.mark.parametrize("flag", [False, 0, "", None])
def test_a_falsey_enabled_parameter_adds_nothing(flag: object) -> None:
    metadata = MetaData()
    builder = _builder(
        ConnectionConfig(metadata=metadata), {_CONNECTION: "default", _ENABLED: flag}
    )

    _pass(TableDriver("toy_token")).process(as_builder(builder))

    assert not metadata.tables


def test_being_enabled_without_a_driver_is_refused() -> None:
    builder = _builder(ConnectionConfig(metadata=MetaData()))

    with pytest.raises(InvalidArgumentError, match="set_driver"):
        _pass().process(as_builder(builder))


def test_a_parameter_naming_no_connection_is_refused_naming_it() -> None:
    builder = _builder(ConnectionConfig(metadata=MetaData()), {_CONNECTION: "reports", _ENABLED: 1})

    with pytest.raises(InvalidArgumentError, match="reports") as refused:
        _pass(TableDriver("toy_token")).process(as_builder(builder))

    assert "default" in refused.value.reason


def test_a_connection_parameter_that_is_not_a_name_is_refused_rather_than_coerced() -> None:
    # The only connection is called "7", so a pass coercing the value — looking
    # up str(named) — would find it and map the tables: the int is refused for
    # not being a name, not for naming nothing.
    metadata = MetaData()
    builder = FakeBuilder(
        OrmConfig(default_connection="7", connections={"7": ConnectionConfig(metadata=metadata)}),
        {_CONNECTION: 7, _ENABLED: True},
    )

    with pytest.raises(
        InvalidArgumentError, match=r"holds 7 \(int\), not the name of a connection"
    ):
        _pass(TableDriver("toy_token")).process(as_builder(builder))

    assert not metadata.tables


def test_an_enabled_parameter_still_holding_a_reference_is_refused_naming_it() -> None:
    metadata = MetaData()
    builder = _builder(
        ConnectionConfig(metadata=metadata), {_CONNECTION: "default", _ENABLED: "%toy.persist%"}
    )

    with pytest.raises(InvalidArgumentError, match=r"\"toy\.enabled\" parameter") as refused:
        _pass(TableDriver("toy_token")).process(as_builder(builder))

    assert "unresolved reference '%toy.persist%'" in refused.value.reason
    assert not metadata.tables


@pytest.mark.parametrize("flag", ["%", "%%"])
def test_a_percent_sign_is_a_value_the_flag_was_given_not_a_reference(flag: str) -> None:
    metadata = MetaData()
    builder = _builder(
        ConnectionConfig(metadata=metadata), {_CONNECTION: "default", _ENABLED: flag}
    )

    _pass(TableDriver("toy_token")).process(as_builder(builder))

    assert set(metadata.tables) == {"toy_token"}


def test_several_sets_of_definitions_are_refused_naming_the_connection() -> None:
    builder = _builder(ConnectionConfig(metadata=[MetaData(), MetaData()]))

    with pytest.raises(InvalidArgumentError, match="default") as refused:
        _pass(TableDriver("toy_token")).process(as_builder(builder))

    assert "several" in refused.value.reason
