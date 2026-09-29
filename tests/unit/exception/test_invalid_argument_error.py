"""Unit tests for :class:`xtr_orm.exception.InvalidArgumentError`."""

from __future__ import annotations

from xtr_orm.exception import InvalidArgumentError, OrmError


def test_invalid_argument_error_is_a_value_error_carrying_its_reason() -> None:
    error = InvalidArgumentError("bad")

    assert isinstance(error, OrmError)
    assert isinstance(error, ValueError)
    assert error.reason == "bad"
    assert str(error) == "bad"
