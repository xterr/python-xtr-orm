"""Two databases with replicas, the default one named "main"; only "kept" goes back to them."""

from __future__ import annotations

from xtr_dependency_injection import configure, env

from xtr_orm.bundle import ConnectionConfig, OrmConfig


@configure
def orm() -> OrmConfig:
    return OrmConfig(
        default_connection="main",
        connections={
            "main": ConnectionConfig(
                url=env("ORM_TEST_URL"), replicas={"replica1": env("ORM_TEST_REPLICA_URL")}
            ),
            "kept": ConnectionConfig(
                url=env("ORM_TEST_URL"),
                replicas={"replica1": env("ORM_TEST_REPLICA_URL")},
                keep_replica=True,
            ),
        },
    )
