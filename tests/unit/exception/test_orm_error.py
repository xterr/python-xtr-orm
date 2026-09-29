"""Unit tests for :class:`xtr_orm.exception.OrmError`."""

from __future__ import annotations

from xtr_orm.exception import (
    InvalidArgumentError,
    MigrationError,
    OrmError,
    UnknownConnectionError,
    UnsupportedDatabaseError,
)


def test_every_error_derives_from_the_package_error() -> None:
    for error in (
        InvalidArgumentError,
        MigrationError,
        UnknownConnectionError,
        UnsupportedDatabaseError,
    ):
        assert issubclass(error, OrmError)
