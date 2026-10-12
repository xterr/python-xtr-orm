"""A library bundle whose tables are built in code and mapped onto a configured connection.

Shaped like the real thing: a configuration says whether the tables are kept
and in which connection, the driver is built from it in ``load_extension``,
and the pass registered in ``build`` loads it once every bundle had its say.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, final

from typing_extensions import override
from xtr_dependency_injection import (
    Bundle,
    ContainerBuilder,
    ServiceConfigurator,
    as_bundle,
    required_bundle,
)

from tests.support.mappings import TableDriver
from xtr_orm import DEFAULT_CONNECTION
from xtr_orm.bundle import OrmBundle, OrmMappingsPass

CONNECTION_PARAMETER: Final = "toy_mappings.connection"
ENABLED_PARAMETER: Final = "toy_mappings.persist"

TABLES: Final = ("toy_token", "toy_client")
"""The tables the driver builds, in the order it adds them."""


@dataclass(frozen=True, slots=True)
class MappingsConfig:
    """Whether the toy library keeps its tables, and which connection holds them."""

    persist: bool = True
    connection: str = DEFAULT_CONNECTION


@final
@required_bundle(OrmBundle)
@as_bundle("toy_mappings", config=MappingsConfig)
class MappingsBundle(Bundle[MappingsConfig]):
    """Maps the toy tables onto the connection its configuration names."""

    def __init__(self) -> None:
        """Start with the pass, and no driver for it yet."""
        self._mappings = OrmMappingsPass(CONNECTION_PARAMETER, ENABLED_PARAMETER)

    @override
    def build(self, builder: ContainerBuilder) -> None:
        """Register the pass; only ``build`` may."""
        builder.add_compiler_pass(self._mappings)

    @override
    def load_extension(
        self,
        config: MappingsConfig,
        services: ServiceConfigurator,
        builder: ContainerBuilder,
    ) -> None:
        """Publish what the pass reads, and hand it the driver this configuration builds."""
        del services
        builder.set_parameter(CONNECTION_PARAMETER, config.connection)
        builder.set_parameter(ENABLED_PARAMETER, config.persist)
        if config.persist:
            self._mappings.set_driver(TableDriver(*TABLES))
