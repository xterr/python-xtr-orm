"""What a mapping driver promises, checked against the driver the tests hand over."""

from __future__ import annotations

from sqlalchemy import MetaData

from tests.support.mappings import TableDriver
from xtr_orm import MappingDriverInterface


def test_a_driver_adding_tables_satisfies_the_contract() -> None:
    assert isinstance(TableDriver("toy_token"), MappingDriverInterface)


def test_loading_adds_the_tables_and_names_them() -> None:
    metadata = MetaData()

    added = TableDriver("toy_token", "toy_client").load_metadata(metadata)

    assert added == ("toy_token", "toy_client")
    assert set(metadata.tables) == {"toy_token", "toy_client"}


def test_loading_twice_adds_nothing_and_names_nothing() -> None:
    metadata = MetaData()
    driver = TableDriver("toy_token")
    _ = driver.load_metadata(metadata)

    added = driver.load_metadata(metadata)

    assert added == ()
    assert set(metadata.tables) == {"toy_token"}


def test_a_table_another_driver_already_defined_is_left_alone() -> None:
    metadata = MetaData()
    _ = TableDriver("toy_token").load_metadata(metadata)

    added = TableDriver("toy_token", "toy_client").load_metadata(metadata)

    assert added == ("toy_client",)
