"""Unit tests for :class:`xtr_orm.migrations.MigrationStatus`."""

from __future__ import annotations

from xtr_orm.migrations import AvailableMigration, MigrationStatus

A1 = AvailableMigration("a1", "first", (), "a1.py", is_head=True)


def _status(*new: AvailableMigration) -> MigrationStatus:
    return MigrationStatus(
        current=(),
        latest=("a1",),
        previous=(),
        next=(),
        available=(A1,),
        executed=(),
        new=new,
        executed_unavailable=(),
    )


def test_it_is_up_to_date_with_nothing_new() -> None:
    assert _status().is_up_to_date


def test_it_is_out_of_date_with_a_new_revision() -> None:
    assert not _status(A1).is_up_to_date
