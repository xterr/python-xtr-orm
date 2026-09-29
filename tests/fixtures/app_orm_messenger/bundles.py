"""The application's root bundles: the orm, the message bus, and logging."""

from __future__ import annotations

from xtr_logging.bundle import LoggingBundle
from xtr_messenger.bundle import MessengerBundle

from xtr_orm.bundle import OrmBundle

BUNDLES = {OrmBundle: {"all": True}, MessengerBundle: {"all": True}, LoggingBundle: {"all": True}}
