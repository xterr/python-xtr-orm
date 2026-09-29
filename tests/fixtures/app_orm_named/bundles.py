"""The application's root bundles: only the orm."""

from __future__ import annotations

from xtr_orm.bundle import OrmBundle

BUNDLES = {OrmBundle: {"all": True}}
