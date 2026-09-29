"""Unit tests for :class:`xtr_orm.migrations.AvailableMigration`."""

from __future__ import annotations

from xtr_orm.migrations import AvailableMigration


def test_two_readings_of_one_file_are_the_same_revision() -> None:
    first = AvailableMigration("a1", "first", (), "migrations/a1.py", is_head=True)
    again = AvailableMigration("a1", "first", (), "migrations/a1.py", is_head=True)

    assert first == again
    assert len({first, again}) == 1
