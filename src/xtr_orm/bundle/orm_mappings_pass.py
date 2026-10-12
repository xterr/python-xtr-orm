"""Puts the tables a library builds in code into one connection's table definitions."""

from __future__ import annotations

from typing import Final, final

from advanced_alchemy.base import metadata_registry
from sqlalchemy import MetaData
from xtr_dependency_injection import ContainerBuilder

from xtr_orm.exception import InvalidArgumentError
from xtr_orm.mapping_driver_interface import MappingDriverInterface

from .connection_config import ConnectionConfig
from .orm_config import OrmConfig

__all__ = ["OrmMappingsPass"]

_SHORTEST_REFERENCE: Final = len("%x%")
"""A reference carries a name between the signs; ``"%"`` and the escaped ``"%%"`` do not."""


@final
class OrmMappingsPass:
    """Loads a mapping driver's tables into the connection two parameters name.

    A library whose tables an application configures has them only once its
    own bundle read that configuration — too late to declare them, early
    enough for a compiler pass. Its bundle keeps one of these, registers it
    from ``build``, builds its driver in ``load_extension`` and hands it over with
    :meth:`set_driver`; the pass then adds the tables to the definitions the
    connection's migrations compare the database with, so
    ``orm:migrations:diff`` writes them like any of the application's own.

    ```python
    @final
    @required_bundle(OrmBundle)
    @as_bundle("invoicing", config=InvoicingConfig)
    class InvoicingBundle(Bundle[InvoicingConfig]):
        def __init__(self) -> None:
            self._mappings = OrmMappingsPass("invoicing.connection", "invoicing.persist")

        @override
        def build(self, builder: ContainerBuilder) -> None:
            builder.add_compiler_pass(self._mappings)

        @override
        def load_extension(
            self, config: InvoicingConfig, services: ServiceConfigurator, builder: ContainerBuilder
        ) -> None:
            builder.set_parameter("invoicing.connection", config.connection)
            builder.set_parameter("invoicing.persist", config.persist)
            if config.persist:
                self._mappings.set_driver(InvoicingDriver(config.table_prefix))
    ```

    That bundle must declare ``@required_bundle(OrmBundle)``, as the example
    does: the pass reads the orm's own configuration to learn which
    connections exist, so a build where no active bundle configures it fails
    with ``UnknownConfigTypeError`` instead.

    Both parameters are read while the container is compiled, before ``%name%``
    references are resolved and long before an ``env(...)`` one is: a bundle
    sets them from its own resolved configuration, which is a plain name and a
    plain flag by then. One still holding a reference is refused, naming it,
    rather than taken for a name or for truth.
    """

    __slots__ = ("_connection_parameter", "_driver", "_enabled_parameter")

    def __init__(
        self,
        connection_parameter: str,
        enabled_parameter: str,
        *,
        driver: MappingDriverInterface | None = None,
    ) -> None:
        """Load ``driver`` into the connection ``connection_parameter`` names.

        Args:
            connection_parameter: The parameter holding the name of the
                connection whose definitions the tables join.
            enabled_parameter: The parameter deciding whether they do; read
                for truth, and an unset one means no.
            driver: The driver, when the bundle already has it; otherwise
                handed over with :meth:`set_driver`.
        """
        self._connection_parameter = connection_parameter
        self._enabled_parameter = enabled_parameter
        self._driver = driver

    def set_driver(self, driver: MappingDriverInterface, /) -> None:
        """Hand the pass the driver to load, replacing any it was given before.

        A bundle calls this from ``load_extension``, where it first has the
        configuration its driver is built from; the pass runs after every
        bundle loaded.
        """
        self._driver = driver

    def process(self, builder: ContainerBuilder) -> None:
        """Add the driver's tables to the named connection's definitions, when enabled.

        Raises:
            InvalidArgumentError: When the mappings are enabled with no driver
                handed over, when either parameter still holds an unresolved
                ``%name%`` reference, when the connection parameter holds
                something that is not a name or names no configured
                connection, or when that connection keeps several sets of
                table definitions.
            ParameterNotFoundError: When the flag is set but the connection
                parameter is not, which the bundle sets beside it.
            UnknownConfigTypeError: When no active bundle configures the orm —
                the library's bundle forgot ``@required_bundle(OrmBundle)``.
        """
        if not self._is_enabled(builder):
            return
        if self._driver is None:
            raise InvalidArgumentError(
                f'The "{self._enabled_parameter}" parameter is set, but no mapping driver was '
                f"handed over; call set_driver from the bundle's load_extension.",
            )
        name, connection = self._connection_of(builder)
        added = self._driver.load_metadata(_definitions_of(name, connection))
        loaded = ", ".join(added) if added else "nothing new"
        builder.log(self, f'Loaded {loaded} into the "{name}" connection\'s table definitions.')

    def _connection_of(self, builder: ContainerBuilder) -> tuple[str, ConnectionConfig]:
        """Return the name the parameter holds, and the connection configured under it.

        Raises:
            InvalidArgumentError: When the parameter holds something that is
                not a name at all, or when no connection is configured under
                the name it holds.
        """
        named = builder.get_parameter(self._connection_parameter)
        connections = builder.get_extension_config(OrmConfig).connections
        if not isinstance(named, str):
            # Told apart from an unknown name, and never coerced: a connection
            # may be called "7", so an int 7 is a bundle publishing the wrong
            # value, not a name that needs converting.
            raise InvalidArgumentError(
                f'The "{self._connection_parameter}" parameter holds {named!r} '
                f"({type(named).__name__}), not the name of a connection; set it to the name "
                f"from the bundle's own resolved configuration.",
            )
        connection = connections.get(named)
        if connection is None:
            raise InvalidArgumentError(
                f'The "{self._connection_parameter}" parameter names {named!r}, which is not a '
                f"configured connection; the connections are: {', '.join(connections)}.",
            )
        return named, connection

    def _is_enabled(self, builder: ContainerBuilder) -> bool:
        """Tell whether the application left the mappings on.

        Read for truth: the flag is the bundle's own, set beside the
        connection's name, so an unset parameter means the bundle never got
        that far — nothing to map.

        Raises:
            InvalidArgumentError: When the flag still holds an unresolved
                ``%name%`` reference, which reads as on for being a non-empty
                string.
        """
        if not builder.has_parameter(self._enabled_parameter):
            return False
        flag = builder.get_parameter(self._enabled_parameter)
        if _is_reference(flag):
            raise InvalidArgumentError(
                f'The "{self._enabled_parameter}" parameter still holds the unresolved reference '
                f"{flag!r}; a pass runs before references are resolved, and every non-empty "
                f"string reads as on, so set it to the bundle's own resolved flag.",
            )
        return bool(flag)


def _is_reference(value: object) -> bool:
    """Tell whether ``value`` is a ``%name%`` reference nothing has resolved yet."""
    return (
        isinstance(value, str)
        and len(value) >= _SHORTEST_REFERENCE
        and value.startswith("%")
        and value.endswith("%")
    )


def _definitions_of(name: str, connection: ConnectionConfig) -> MetaData:
    """Return the table definitions ``connection``'s migrations compare the database with.

    Resolved the way the bundle's migrator resolves them: the connection's
    own when it has one set, else the ones advanced-alchemy registers for its
    bind key. The configuration is read as written rather than through
    ``with_url_options``: a URL is still an ``env(...)`` placeholder while the
    container compiles, and neither the definitions nor the bind key ride on
    it.

    Raises:
        InvalidArgumentError: When the connection keeps several sets.
    """
    definitions = connection.metadata
    if definitions is None:
        return metadata_registry.get(connection.bind_key)
    if isinstance(definitions, MetaData):
        return definitions
    raise InvalidArgumentError(
        f'The "{name}" connection keeps several sets of table definitions; a mapping driver '
        f"needs the one its tables belong to. Give that connection a single MetaData.",
    )
