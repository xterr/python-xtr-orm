"""One database, read from the environment, with its revisions under the test's directory."""

from __future__ import annotations

from xtr_dependency_injection import configure, env

from tests.support.schema import METADATA
from xtr_orm.bundle import ConnectionConfig, MigrationsConfig, OrmConfig


@configure
def orm() -> OrmConfig:
    return OrmConfig(
        connections={
            "default": ConnectionConfig(
                url=env("ORM_TEST_URL"),
                engine_options={"pool_pre_ping": True},
                session_options={"expire_on_commit": False},
                metadata=METADATA,
                migrations=MigrationsConfig(
                    directory=env("ORM_TEST_MIGRATIONS"), render_as_batch=True
                ),
            ),
            "reports": ConnectionConfig(url=env("ORM_TEST_REPORTS_URL")),
        },
    )
