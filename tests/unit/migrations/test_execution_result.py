"""Unit tests for :class:`xtr_orm.migrations.ExecutionResult`."""

from __future__ import annotations

from xtr_orm.migrations import Direction, ExecutionResult


def test_results_are_equal_when_the_same_revision_ran_the_same_way_as_long() -> None:
    assert ExecutionResult("a1", Direction.UP, 0.5) == ExecutionResult("a1", Direction.UP, 0.5)
    assert ExecutionResult("a1", Direction.UP, 0.5) != ExecutionResult("a1", Direction.DOWN, 0.5)
