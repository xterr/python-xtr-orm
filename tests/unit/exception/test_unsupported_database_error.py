"""Unit tests for :class:`xtr_orm.exception.UnsupportedDatabaseError`."""

from __future__ import annotations

from xtr_orm.exception import UnsupportedDatabaseError


def test_unsupported_database_error_names_the_server_and_the_operation() -> None:
    error = UnsupportedDatabaseError("oracle", "create")

    assert (error.backend, error.operation) == ("oracle", "create")
    assert str(error) == 'Cannot create a database on "oracle": it is not supported.'
