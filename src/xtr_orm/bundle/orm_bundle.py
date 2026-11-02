"""The xtr-orm bundle: an engine, sessions and a migrator per configured connection.

An application listing :class:`OrmBundle` gets, for every connection of its
:class:`OrmConfig`, each qualified by the connection's name:

- the database layer's :class:`~advanced_alchemy.config.SQLAlchemyAsyncConfig`,
  for its repositories and services;
- an :class:`~sqlalchemy.ext.asyncio.AsyncEngine` on the primary database;
- an ``async_sessionmaker[AsyncSession]`` — or, for a connection with
  replicas, a :class:`~advanced_alchemy.routing.RoutingAsyncSessionMaker`
  sending reads to them and writes to the primary;
- an :class:`~sqlalchemy.ext.asyncio.AsyncSession` per unit of work — a
  request, a message, a command — closed when the unit ends;
- a :class:`~xtr_orm.migrations.Migrator` and a
  :class:`~xtr_orm.database.DatabaseManager`, both on the primary;

and the default connection's without a qualifier too. Every engine is
disposed when the container closes. When the console bundle is active, the
``orm:*`` commands are registered; when the messenger bundle is, the
``orm_transaction``, ``orm_close_connection`` and
``orm_open_transaction_logger`` middleware are, for a bus to list; when the
logging bundle is, an ``orm`` channel is added and every migrator logs there.

With the messenger bundle active and xtr-orm-messenger installed, the
``orm://`` transport is registered with the messenger too, built on these
connections, and each connection's migrator writes the messages tables of the
``orm://`` transports on it.

Nothing connects until a service is first used, and a URL given as
``env(...)`` is read only then.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from functools import partial
from importlib.util import find_spec
from operator import contains
from typing import Final, TypeVar, cast, final

from advanced_alchemy.base import metadata_registry
from advanced_alchemy.config import AsyncSessionConfig, EngineConfig, SQLAlchemyAsyncConfig
from advanced_alchemy.config.routing import EngineConfig as ReplicaEngine
from advanced_alchemy.config.routing import RoutingConfig, RoutingStrategy
from advanced_alchemy.routing import RoutingAsyncSessionMaker, stick_to_primary_var
from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from typing_extensions import override
from xtr_dependency_injection import (
    Bundle,
    ContainerBuilder,
    ServiceConfigurator,
    as_bundle,
    bundle_active,
    current_unit_of_work,
    named_factory,
    optional_service,
    qualified_name,
    required_bundle,
)
from xtr_logging_contracts import LoggerInterface
from xtr_service_contracts import ContainerInterface

from xtr_orm.connection_registry import ConnectionRegistry
from xtr_orm.database import DatabaseManager
from xtr_orm.exception import InvalidArgumentError, SessionUnavailableError
from xtr_orm.migrations import MigrationsConfig, Migrator

from .connection_config import ConnectionConfig
from .orm_config import OrmConfig

__all__ = ["ORM_CHANNEL", "OrmBundle"]

_T = TypeVar("_T")

_SessionMaker = type[async_sessionmaker[AsyncSession]] | type[RoutingAsyncSessionMaker]
"""Which session maker a connection is given, and so which service a session comes from."""

ORM_CHANNEL: Final = "orm"
"""The logging channel migrators write to."""

_MESSENGER_TRANSPORT: Final = "xtr_orm_messenger"
"""The package of the ``orm://`` transport, registered with the messenger when installed."""

_PER_CONNECTION: Final[tuple[type, ...]] = (
    SQLAlchemyAsyncConfig,
    AsyncEngine,
    AsyncSession,
    Migrator,
    DatabaseManager,
)


@final
@required_bundle("xtr_logging.bundle:LoggingBundle", ignore_on_invalid=True)
@required_bundle("xtr_console.bundle:ConsoleBundle", ignore_on_invalid=True)
@as_bundle("orm", config=OrmConfig)
class OrmBundle(Bundle[OrmConfig]):
    """Turns an :class:`OrmConfig` into an engine, sessions and a migrator per connection."""

    @override
    def prepend_extension(self, builder: ContainerBuilder) -> None:
        """When ``logging`` is active, add the ``orm`` channel to its config."""
        if not bundle_active(builder, "logging"):
            return
        # Logging is an optional peer, importable only once it is active.
        from xtr_logging.bundle import LoggingConfig  # noqa: PLC0415 — optional peer

        def add_orm_channel(config: LoggingConfig) -> LoggingConfig:
            return config.with_channels(ORM_CHANNEL)

        builder.prepend_extension_config(LoggingConfig, add_orm_channel)

    @override
    def load_extension(
        self,
        config: OrmConfig,
        services: ServiceConfigurator,
        builder: ContainerBuilder,
    ) -> None:
        """Register every connection's services under its name, the registry, the commands."""
        messenger = bundle_active(builder, "messenger")
        transport = messenger and find_spec(_MESSENGER_TRANSPORT) is not None
        for name, connection in config.connections.items():
            maker_type: _SessionMaker = (
                RoutingAsyncSessionMaker
                if connection.replicas
                else async_sessionmaker[AsyncSession]
            )
            factories = (
                (_alchemy_factory(name, connection), "alchemy"),
                (_engine_factory(name), "engine"),
                (
                    _routing_maker_factory(name)
                    if connection.replicas
                    else _session_maker_factory(name),
                    "session_maker",
                ),
                (
                    _migrator_factory(
                        name,
                        connection,
                        default=config.default_connection,
                        messages_tables=transport,
                    ),
                    "migrator",
                ),
                (_database_factory(connection), "database"),
            )
            for factory, kind in factories:
                _ = services.set(named_factory(factory, f"orm_{kind}_{name}"), qualifier=name)
            _ = services.set(
                named_factory(
                    _session_factory(name, maker_type),
                    f"orm_session_{name}",
                ),
                qualifier=name,
                lifetime="scoped",
            )
            if name == config.default_connection:
                for service in (*_PER_CONNECTION, maker_type):
                    services.alias(service, service, target_qualifier=name)

        _ = services.set(_ConnectionsInUse)
        routed = {
            name: bool(connection.replicas) for name, connection in config.connections.items()
        }
        _ = services.set(_connection_registry_factory(config.default_connection, routed))

        if bundle_active(builder, "console"):
            services.load("xtr_orm.command")
        if messenger:
            services.load("xtr_orm.messenger")
        if transport:
            _register_orm_transport(services)


def _register_orm_transport(services: ServiceConfigurator) -> None:
    """Register the ``orm://`` transport factory with the messenger, built on these connections.

    Registered under the messenger's transport factory interface and tagged
    with its transport factory tag, which is how the messenger consults a
    factory built from services ahead of the ones it discovers by DSN scheme.
    """
    # Optional peers: importable only once the messenger bundle is active and
    # the transport installed, which the caller checked.
    from xtr_messenger import TransportFactoryInterface  # noqa: PLC0415 — optional peer
    from xtr_messenger.bundle import TRANSPORT_FACTORY_TAG  # noqa: PLC0415 — optional peer

    from xtr_orm.messenger_transport import (  # noqa: PLC0415 — needs the optional peers
        OrmTransportFactory,
        orm_transport_factory,
    )

    qualifier = qualified_name(OrmTransportFactory)
    _ = services.set(orm_transport_factory, qualifier=qualifier).add_tag(TRANSPORT_FACTORY_TAG)
    services.alias(
        TransportFactoryInterface,
        OrmTransportFactory,
        alias_qualifier=qualifier,
        target_qualifier=qualifier,
    )


@final
class _ConnectionsInUse:
    """The connections whose database layer — and so engines — the container has built."""

    __slots__ = ("names",)

    def __init__(self) -> None:
        self.names: set[str] = set()


def _alchemy_factory(
    name: str, connection: ConnectionConfig
) -> Callable[[_ConnectionsInUse], AsyncIterator[SQLAlchemyAsyncConfig]]:
    """Build the factory of the connection ``name``'s database layer configuration.

    It owns every engine of the connection — the primary's, and each
    replica's — and disposes them when the container closes. Like every
    per-connection factory, it closes over its own connection's
    configuration: the container resolves the environment placeholders of
    that one alone, so a connection never reads another's variables.
    """

    async def alchemy(in_use: _ConnectionsInUse) -> AsyncIterator[SQLAlchemyAsyncConfig]:
        resolved = connection.with_url_options()
        # The options are forwarded by name, each checked against the target's
        # fields by ConnectionConfig; their values are the application's.
        engine = cast("Callable[..., EngineConfig]", EngineConfig)(**resolved.engine_options)
        session = cast("Callable[..., AsyncSessionConfig]", AsyncSessionConfig)(
            **resolved.session_options
        )
        built = cast("Callable[..., SQLAlchemyAsyncConfig]", SQLAlchemyAsyncConfig)(
            # With replicas, the primary is given through the routing instead.
            connection_string=None if resolved.replicas else resolved.url,
            routing_config=_routing(resolved) if resolved.replicas else None,
            engine_config=engine,
            session_config=session,
            bind_key=resolved.bind_key,
            **resolved.alchemy_options,
        )
        routing_maker: RoutingAsyncSessionMaker | None = None
        if resolved.replicas:
            routing_maker = cast("RoutingAsyncSessionMaker", built.create_session_maker())
            # One pool on the primary: the routing's, which migrations use too.
            built.engine_instance = routing_maker.primary_engine
        in_use.names.add(name)
        try:
            yield built
        finally:
            if routing_maker is not None:
                await routing_maker.close_all()
            elif built.engine_instance is not None:
                await built.engine_instance.dispose()

    return alchemy


def _routing(connection: ConnectionConfig) -> RoutingConfig:
    """Map the connection's replicas onto the database layer's read/write routing.

    Reads go to a replica picked at random; a write, a transaction and every
    read after them go to the primary, until a commit when ``keep_replica``.
    Built afresh for each container: that configuration completes itself when
    built.
    """
    return RoutingConfig(
        primary_connection_string=connection.url,
        read_replicas=[
            ReplicaEngine(connection_string=url, name=replica)
            for replica, url in connection.replicas.items()
        ],
        routing_strategy=RoutingStrategy.RANDOM,
        sticky_after_write=True,
        reset_stickiness_on_commit=connection.keep_replica,
    )


def _engine_factory(name: str) -> Callable[[ContainerInterface], Awaitable[AsyncEngine]]:
    """Build the factory of the connection ``name``'s engine, on its primary."""

    async def engine(container: ContainerInterface) -> AsyncEngine:
        return (await container.get(SQLAlchemyAsyncConfig, name)).get_engine()

    return engine


def _session_maker_factory(
    name: str,
) -> Callable[[ContainerInterface], Awaitable[async_sessionmaker[AsyncSession]]]:
    """Build the factory of the connection ``name``'s session maker, on its engine."""

    async def session_maker(container: ContainerInterface) -> async_sessionmaker[AsyncSession]:
        alchemy = await container.get(SQLAlchemyAsyncConfig, name)
        return cast("async_sessionmaker[AsyncSession]", alchemy.create_session_maker())

    return session_maker


def _routing_maker_factory(
    name: str,
) -> Callable[[ContainerInterface], Awaitable[RoutingAsyncSessionMaker]]:
    """Build the factory of the connection ``name``'s session maker, routing to its replicas."""

    async def routing_session_maker(container: ContainerInterface) -> RoutingAsyncSessionMaker:
        alchemy = await container.get(SQLAlchemyAsyncConfig, name)
        return cast("RoutingAsyncSessionMaker", alchemy.create_session_maker())

    return routing_session_maker


def _session_factory(
    name: str, maker_type: _SessionMaker
) -> Callable[[ContainerInterface], AsyncIterator[AsyncSession]]:
    """Build the factory of the connection ``name``'s session, closed when its unit ends.

    The session comes from ``maker_type``, the maker service registered for the
    connection, so every unit of work shares the pools the container owns and
    disposes — and an application that replaces that service is obeyed.

    Closing rolls back what was not committed: committing is the unit's job.
    With replicas, a unit starts reading from them whatever the unit before it
    wrote: sticking to the primary after a write is one unit's state, forgotten
    when the unit ends — not when another of its sessions opens, which would
    send the reads after a write to a replica.
    """
    routed = maker_type is RoutingAsyncSessionMaker

    async def session(container: ContainerInterface) -> AsyncIterator[AsyncSession]:
        maker = await container.get(maker_type, name)
        try:
            async with maker() as opened:
                yield opened
        finally:
            if routed:
                _ = stick_to_primary_var.set(False)

    return session


def _migrator_factory(
    name: str, connection: ConnectionConfig, *, default: str, messages_tables: bool
) -> Callable[[ContainerInterface], Awaitable[Migrator]]:
    """Build the factory of the connection ``name``'s migrator, logging to ``orm`` when it can.

    With ``messages_tables``, the messages tables of the ``orm://`` transports
    on this connection join its table definitions first, so a diff writes them
    like any of the application's own tables.
    """

    async def migrator(container: ContainerInterface) -> Migrator:
        resolved = connection.with_url_options()
        metadata = (
            resolved.metadata
            if resolved.metadata is not None
            else metadata_registry.get(resolved.bind_key)
        )
        if messages_tables:
            await _map_messages_tables(container, name, default, metadata)
        built = Migrator(
            await container.get(AsyncEngine, name),
            resolved.migrations or MigrationsConfig(),
            metadata,
            name=name,
        )
        logger = await optional_service(container, LoggerInterface, ORM_CHANNEL)
        if logger is not None:
            built.set_logger(logger)
        return built

    return migrator


async def _map_messages_tables(
    container: ContainerInterface,
    name: str,
    default: str,
    metadata: MetaData | Sequence[MetaData],
) -> None:
    """Add the messages table of every ``orm://`` transport on the connection ``name``.

    The transports are read from the bus configuration as the application
    resolved it, so a DSN given as ``env(...)`` is read here — when a migrator
    is first built.

    Raises:
        InvalidArgumentError: When a transport keeps a table on a connection
            that keeps several sets of table definitions.
    """
    # Optional peers: importable only once the messenger bundle is active and
    # the transport installed, which the bundle checked.
    from xtr_messenger import MessageBusConfig  # noqa: PLC0415 — optional peer
    from xtr_orm_messenger import (  # noqa: PLC0415 — optional peer
        MessagesTableDriver,
        messages_tables,
    )

    bus = await optional_service(container, MessageBusConfig)
    tables = messages_tables(bus, name, default) if bus is not None else ()
    if not tables:
        return
    if not isinstance(metadata, MetaData):
        raise InvalidArgumentError(
            f'The "{name}" connection keeps several sets of table definitions; the messages '
            f"tables of its orm:// transports need the one they belong to. Give that connection "
            f"a single MetaData.",
        )
    for table in tables:
        _ = MessagesTableDriver(table).load_metadata(metadata)


def _database_factory(connection: ConnectionConfig) -> Callable[[], DatabaseManager]:
    """Build the factory of ``connection``'s database manager."""

    def database() -> DatabaseManager:
        resolved = connection.with_url_options()
        connect_args = resolved.engine_options.get("connect_args")
        return DatabaseManager(
            resolved.url,
            connect_args=connect_args if isinstance(connect_args, dict) else None,  # pyright: ignore[reportUnknownArgumentType] -- an option mapping, read as given
        )

    return database


def _connection_registry_factory(
    default: str, routed: dict[str, bool]
) -> Callable[[ContainerInterface, _ConnectionsInUse], ConnectionRegistry]:
    """Build the factory of the registry of every connection — each ``routed`` or not, by name."""

    def connection_registry(
        container: ContainerInterface, in_use: _ConnectionsInUse
    ) -> ConnectionRegistry:
        """Name every connection for the commands and middleware, each piece built when needed.

        A connection's session is the one of the unit of work under way,
        closing it disposes every engine it has — its replicas' too — and it
        is in use once the container built its engines.
        """
        registry = ConnectionRegistry(default)
        for name, replicated in routed.items():
            registry.register(
                name,
                engine=_provider(container, AsyncEngine, name),
                migrator=_provider(container, Migrator, name),
                database=_provider(container, DatabaseManager, name),
                session=_unit_session(name),
                close=_closer(container, name, routed=replicated),
                in_use=partial(contains, in_use.names, name),
            )
        return registry

    return connection_registry


def _unit_session(name: str) -> Callable[[], Awaitable[AsyncSession]]:
    async def session() -> AsyncSession:
        unit = current_unit_of_work()
        if unit is None:
            raise SessionUnavailableError(name, "no unit of work is under way")
        return await unit.get(AsyncSession, name)

    return session


def _closer(
    container: ContainerInterface, name: str, *, routed: bool
) -> Callable[[], Awaitable[None]]:
    async def close() -> None:
        if routed:
            await (await container.get(RoutingAsyncSessionMaker, name)).close_all()
        else:
            await (await container.get(AsyncEngine, name)).dispose()

    return close


def _provider(
    container: ContainerInterface, service: type[_T], name: str
) -> Callable[[], Awaitable[_T]]:
    async def provide() -> _T:
        return await container.get(service, name)

    return provide
