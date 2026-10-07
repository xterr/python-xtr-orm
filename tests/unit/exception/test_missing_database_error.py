"""Unit tests for :class:`xtr_orm.exception.MissingDatabaseError`."""

from __future__ import annotations

from xtr_orm.exception import MissingDatabaseError, OrmError


def test_missing_database_error_names_the_database_and_the_operation() -> None:
    error = MissingDatabaseError("/srv/app.sqlite", "drop")

    assert (error.database, error.operation) == ("/srv/app.sqlite", "drop")
    assert str(error) == 'Cannot drop the database "/srv/app.sqlite": it does not exist.'


def test_it_is_caught_as_the_package_s_error_and_as_a_missing_file() -> None:
    error = MissingDatabaseError("/srv/app.sqlite", "drop")

    assert isinstance(error, OrmError)
    assert isinstance(error, FileNotFoundError)
