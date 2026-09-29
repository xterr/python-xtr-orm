"""Unit tests for :class:`xtr_orm.exception.MigrationError`."""

from __future__ import annotations

from xtr_orm.exception import MigrationError, OrmError


def test_migration_error_carries_its_reason() -> None:
    error = MigrationError("refused")

    assert isinstance(error, OrmError)
    assert error.reason == "refused"
