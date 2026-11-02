"""The application's root bundles: the orm and the message bus, and nothing else.

No bundle of the transport's own: the orm bundle registers it, having found it installed.
"""

from __future__ import annotations

from xtr_messenger.bundle import MessengerBundle

from xtr_orm.bundle import OrmBundle

BUNDLES = {OrmBundle: {"all": True}, MessengerBundle: {"all": True}}
