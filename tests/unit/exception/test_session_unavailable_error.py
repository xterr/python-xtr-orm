"""Unit tests for :class:`xtr_orm.exception.SessionUnavailableError`."""

from __future__ import annotations

from xtr_orm.exception import OrmError, SessionUnavailableError


def test_it_names_the_connection_and_why_it_has_no_session() -> None:
    error = SessionUnavailableError("reports", "no unit of work is under way")

    assert isinstance(error, OrmError)
    assert (error.connection, error.reason) == ("reports", "no unit of work is under way")
    assert (
        str(error) == 'The "reports" connection has no session here: no unit of work is under way.'
    )
