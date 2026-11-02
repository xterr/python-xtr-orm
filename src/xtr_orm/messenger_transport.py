"""Building the ``orm://`` transport factory from the container's services.

The orm bundle registers it when the messenger bundle is active and
xtr-orm-messenger is installed: the factory needs this package's connections,
which only this package's bundle holds. Importing this module therefore needs
both xtr-messenger and xtr-orm-messenger; the bundle imports it only once it
has found them, and nothing scans it.
"""

from __future__ import annotations

from xtr_messenger import SerializerInterface
from xtr_orm_messenger import OrmTransportFactory

from xtr_orm.connection_registry import ConnectionRegistry

__all__ = ["OrmTransportFactory", "orm_transport_factory"]


def orm_transport_factory(
    registry: ConnectionRegistry, serializer: SerializerInterface
) -> OrmTransportFactory:
    """Build the factory on the application's connections, with the messenger's serializer."""
    return OrmTransportFactory(registry, serializer)
