"""Unit tests for :class:`xtr_orm.migrations.Direction`."""

from __future__ import annotations

from xtr_orm.migrations import Direction


def test_each_direction_is_written_as_the_word_reports_show() -> None:
    assert Direction.UP.value == "up"
    assert Direction.DOWN.value == "down"


def test_a_direction_is_read_back_from_its_word() -> None:
    assert Direction("down") is Direction.DOWN
