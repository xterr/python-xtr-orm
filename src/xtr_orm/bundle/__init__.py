"""The xtr-dependency-injection bundle for xtr-orm."""

from __future__ import annotations

from xtr_orm.migrations import MigrationsConfig

from .connection_config import ConnectionConfig
from .orm_bundle import ORM_CHANNEL, OrmBundle
from .orm_config import OrmConfig

__all__ = ["ORM_CHANNEL", "ConnectionConfig", "MigrationsConfig", "OrmBundle", "OrmConfig"]
