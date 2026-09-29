"""Unit tests for :class:`xtr_orm.exception.UnknownConnectionError`."""

from __future__ import annotations

from xtr_orm.exception import UnknownConnectionError


def test_unknown_connection_error_lists_the_known_names() -> None:
    error = UnknownConnectionError("nope", ("default", "reports"))

    assert isinstance(error, LookupError)
    assert (error.name, error.known) == ("nope", ("default", "reports"))
    assert str(error) == 'Unknown connection "nope"; the connections are: "default", "reports".'


def test_unknown_connection_error_says_when_there_is_none() -> None:
    assert str(UnknownConnectionError("x", ())).endswith("the connections are: none.")
