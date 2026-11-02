"""The messages tables a migrator adds for the ``orm://`` transports on its connection."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast, final

import pytest
from sqlalchemy import MetaData
from xtr_messenger import MessageBusConfig, TransportConfig

from xtr_orm.bundle.orm_bundle import _map_messages_tables
from xtr_orm.exception import InvalidArgumentError

if TYPE_CHECKING:
    from collections.abc import Hashable

    from xtr_service_contracts import ContainerInterface

pytestmark = pytest.mark.anyio


@final
class FakeContainer:
    """Holds the bus configuration, or nothing."""

    def __init__(self, bus: MessageBusConfig | None) -> None:
        self._bus = bus

    def has(self, service: type[object], /, qualifier: Hashable | None = None) -> bool:
        del qualifier
        return service is MessageBusConfig and self._bus is not None

    async def get(self, service: type[object], /, qualifier: Hashable | None = None) -> object:
        del service, qualifier
        return self._bus


def _container(bus: MessageBusConfig | None) -> ContainerInterface:
    return cast("ContainerInterface", cast("object", FakeContainer(bus)))


_ORDERS = MessageBusConfig(transports={"orders": TransportConfig("orm://default")})


async def test_the_table_of_a_transport_on_the_connection_joins_its_definitions() -> None:
    metadata = MetaData()

    await _map_messages_tables(_container(_ORDERS), "default", "default", metadata)

    assert list(metadata.tables) == ["messenger_messages"]


async def test_a_transport_on_another_connection_adds_nothing() -> None:
    metadata = MetaData()

    await _map_messages_tables(_container(_ORDERS), "reports", "default", metadata)

    assert list(metadata.tables) == []


async def test_without_a_bus_configuration_nothing_is_added() -> None:
    metadata = MetaData()

    await _map_messages_tables(_container(None), "default", "default", metadata)

    assert list(metadata.tables) == []


async def test_a_connection_keeping_several_sets_of_definitions_is_refused() -> None:
    with pytest.raises(InvalidArgumentError, match="several sets of table definitions"):
        await _map_messages_tables(
            _container(_ORDERS), "default", "default", [MetaData(), MetaData()]
        )


async def test_several_sets_are_fine_for_a_connection_holding_no_transport() -> None:
    definitions = [MetaData(), MetaData()]

    await _map_messages_tables(_container(_ORDERS), "reports", "default", definitions)

    assert all(not metadata.tables for metadata in definitions)
