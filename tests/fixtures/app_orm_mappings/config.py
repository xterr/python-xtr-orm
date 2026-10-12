"""One database with no table definitions of its own, under a bind key only it uses."""

from __future__ import annotations

from xtr_dependency_injection import configure, env

from xtr_orm.bundle import ConnectionConfig, MigrationsConfig, OrmConfig

BIND_KEY = "xtr_orm_test_app_mappings"
"""Where the registered definitions live; its own, so no other test's tables join them."""


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
