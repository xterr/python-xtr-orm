"""Unit tests for :class:`xtr_orm.migrations.MigrationPlan`."""

from __future__ import annotations

from xtr_orm.migrations import Direction, MigrationPlan


def test_plans_are_equal_when_the_same_revision_would_run_the_same_way() -> None:
    assert MigrationPlan("a1", Direction.UP, "first") == MigrationPlan("a1", Direction.UP, "first")
    assert MigrationPlan("a1", Direction.UP, "first") != MigrationPlan(
        "a1", Direction.DOWN, "first"
    )
