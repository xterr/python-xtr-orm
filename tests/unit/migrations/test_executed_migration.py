"""Unit tests for :class:`xtr_orm.migrations.ExecutedMigration`."""

from __future__ import annotations

from xtr_orm.migrations import ExecutedMigration


def test_a_revision_the_history_does_not_record_has_no_time_or_duration() -> None:
    executed = ExecutedMigration("a1")

    assert executed.executed_at is None
    assert executed.execution_time is None
