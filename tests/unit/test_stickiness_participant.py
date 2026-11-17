"""Each unit of work starts reading from the replicas, and leaves the one around it as it was."""

from __future__ import annotations

import contextvars

from advanced_alchemy.routing import stick_to_primary_var

from xtr_orm.stickiness_participant import StickinessParticipant


def test_a_write_sticks_reads_to_the_primary_until_the_unit_ends() -> None:
    participant = StickinessParticipant()

    def unit() -> list[bool]:
        token = participant.unit_began()
        seen = [stick_to_primary_var.get()]
        _ = stick_to_primary_var.set(True)  # what a write does
        seen.append(stick_to_primary_var.get())
        participant.unit_ended(token)
        seen.append(stick_to_primary_var.get())
        return seen

    assert contextvars.copy_context().run(unit) == [False, True, False]


def test_a_nested_unit_does_not_clear_the_outer_units_stickiness() -> None:
    participant = StickinessParticipant()

    def units() -> bool:
        outer = participant.unit_began()
        _ = stick_to_primary_var.set(True)
        inner = participant.unit_began()
        participant.unit_ended(inner)
        stuck = stick_to_primary_var.get()
        participant.unit_ended(outer)
        return stuck

    assert contextvars.copy_context().run(units) is True


def test_a_unit_exited_in_another_context_does_not_raise() -> None:
    participant = StickinessParticipant()
    token = contextvars.copy_context().run(participant.unit_began)

    contextvars.copy_context().run(participant.unit_ended, token)
