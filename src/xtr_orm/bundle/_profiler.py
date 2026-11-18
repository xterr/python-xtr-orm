"""The orm's profiler panel, registered when the http kernel profiles requests.

Every factory here is read by the container, so the types its parameters
name are imported at runtime.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Final

from advanced_alchemy.config import SQLAlchemyAsyncConfig
from advanced_alchemy.routing import RoutingAsyncSessionMaker
from xtr_dependency_injection import AutowireDecorated, named_factory
from xtr_http_kernel.data_collector import DATA_COLLECTOR_TAG

from xtr_orm.data_collector import OrmDataCollector, QueryListener

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from xtr_dependency_injection import ServiceConfigurator

__all__ = ["register_profiler"]

_NAME: Final = "orm"
_TEMPLATE: Final = "@xtr_orm/collector/orm.html.j2"
_PRIORITY: Final = 260


def register_profiler(services: ServiceConfigurator, connections: Sequence[str]) -> None:
    """Register the query listener, the collector, and each connection's engines listened to.

    The listener is attached where a connection's database layer is built,
    by decorating it: every engine of the connection — the primary's and each
    replica's — is made there, so every session, connection and migration of
    it is seen, and nothing is attached in an application that never profiles.
    """
    names = tuple(connections)
    _ = services.set(_query_listener)
    _ = services.set(_orm_collector(names)).add_tag(
        DATA_COLLECTOR_TAG, name=_NAME, template=_TEMPLATE, priority=_PRIORITY
    )
    for name in names:
        # Registered under a key of its own; decoration then gives it the target's.
        _ = services.set(
            named_factory(_listened_alchemy(name), f"orm_listened_alchemy_{name}"),
            qualifier=f"orm_listened_alchemy_{name}",
        ).set_decorated_service(SQLAlchemyAsyncConfig, qualifier=name)


def _query_listener() -> QueryListener:
    """Build the listener on its own monotonic clock, never the application's."""
    return QueryListener()


def _orm_collector(connections: tuple[str, ...]) -> Callable[[QueryListener], OrmDataCollector]:
    """Build the factory of the collector naming the configured ``connections``."""

    def orm_collector(listener: QueryListener) -> OrmDataCollector:
        return OrmDataCollector(listener, connections)

    return orm_collector


def _listened_alchemy(
    name: str,
) -> Callable[[SQLAlchemyAsyncConfig, QueryListener], SQLAlchemyAsyncConfig]:
    """Build the decorator listening to every engine of the connection ``name``."""

    def listened_alchemy(
        alchemy: Annotated[SQLAlchemyAsyncConfig, AutowireDecorated()],
        listener: QueryListener,
    ) -> SQLAlchemyAsyncConfig:
        listener.listen(alchemy.get_engine(), name)
        maker = alchemy.session_maker
        if isinstance(maker, RoutingAsyncSessionMaker):
            for replica in maker.replica_engines:
                listener.listen(replica, name)
        return alchemy

    return listened_alchemy
