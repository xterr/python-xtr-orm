"""The application's root bundles: the orm, the console and logging, in every environment."""

from __future__ import annotations

from xtr_console.bundle import ConsoleBundle
from xtr_logging.bundle import LoggingBundle

from xtr_orm.bundle import OrmBundle

BUNDLES = {OrmBundle: {"all": True}, ConsoleBundle: {"all": True}, LoggingBundle: {"all": True}}
