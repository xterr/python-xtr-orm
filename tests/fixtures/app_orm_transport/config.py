"""Two SQLite databases, a queue in a table on each, each table in its connection's migrations."""

from __future__ import annotations

from typing import Final

from xtr_dependency_injection import configure, env
from xtr_messenger import MessageBusConfig, TransportConfig

from xtr_orm.bundle import ConnectionConfig, MigrationsConfig, OrmConfig

from .messages import QueuedOrder, QueuedReport

BIND_KEY: Final = "xtr_orm_test_app_orm_transport"
"""Where the default connection's definitions live; its own, so no other test's tables join them."""

REPORTS_BIND_KEY: Final = "xtr_orm_test_app_orm_transport_reports"


@configure
def orm() -> OrmConfig:
    return OrmConfig(
        connections={
            "default": ConnectionConfig(
                url=env("ORM_TEST_URL"),
                bind_key=BIND_KEY,
                migrations=MigrationsConfig(
                    directory=env("ORM_TEST_MIGRATIONS"), render_as_batch=True
                ),
            ),
            "reports": ConnectionConfig(
                url=env("ORM_TEST_REPORTS_URL"),
                bind_key=REPORTS_BIND_KEY,
                migrations=MigrationsConfig(
                    directory=env("ORM_TEST_REPORTS_MIGRATIONS"), render_as_batch=True
                ),
            ),
        },
    )


@configure
def messenger() -> MessageBusConfig:
    return MessageBusConfig(
        transports={
            "orders": TransportConfig("orm://default?poll_interval=0.05"),
            "reports": TransportConfig("orm://reports?table_name=report_messages"),
        },
        routing={QueuedOrder: "orders", QueuedReport: "reports"},
    )
