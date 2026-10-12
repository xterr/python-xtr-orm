"""The application's root bundles: the orm, and the library that maps nothing here."""

from __future__ import annotations

from tests.fixtures.orm_mappings_bundle import MappingsBundle
from xtr_orm.bundle import OrmBundle

BUNDLES = {OrmBundle: {"all": True}, MappingsBundle: {"all": True}}
