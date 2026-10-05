"""One SQLite database; messages handled in process or queued, each in one transaction."""

from __future__ import annotations

from xtr_dependency_injection import configure, env
from xtr_logging.bundle import LoggingConfig
from xtr_logging.config import ServiceHandlerConfig
from xtr_messenger import MessageBusConfig, TransportConfig

from tests.support.schema import METADATA
from xtr_orm.bundle import ConnectionConfig, MigrationsConfig, OrmConfig

from .messages import QueuedNote


@configure
def orm() -> OrmConfig:
    return OrmConfig(
        connections={
            "default": ConnectionConfig(
                url=env("ORM_TEST_URL"),
                metadata=METADATA,
                migrations=MigrationsConfig(directory=env("ORM_TEST_MIGRATIONS")),
            ),
        },
    )


@configure
def messenger() -> MessageBusConfig:
    return MessageBusConfig(
        transports={"jobs": TransportConfig("in-memory://?serialize=true")},
        routing={QueuedNote: "jobs"},
        handle_unrouted=True,
        middleware=[
            "orm_close_connection",
            {"orm_transaction": {"connection_name": "default"}},
            {"orm_open_transaction_logger": {"connection_names": ["default"]}},
        ],
    )


@configure
def logging() -> LoggingConfig:
    return LoggingConfig(handlers={"main": ServiceHandlerConfig(id="main")})
