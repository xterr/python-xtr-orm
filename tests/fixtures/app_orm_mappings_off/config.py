"""One database under a bind key of its own, with the toy library told not to persist."""

from __future__ import annotations

from xtr_dependency_injection import configure, env

from tests.fixtures.orm_mappings_bundle import MappingsConfig
from xtr_orm.bundle import ConnectionConfig, MigrationsConfig, OrmConfig

BIND_KEY = "xtr_orm_test_app_mappings_off"
"""Its own, so no persisting kernel of this process has left tables in it."""


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
        },
    )


@configure
def toy_mappings() -> MappingsConfig:
    return MappingsConfig(persist=False)
