"""What the fixture app dispatches: handled in process, queued for a worker, or nested."""

from __future__ import annotations

from dataclasses import dataclass

from xtr_messenger import as_message


@as_message(name="tests.orm.write_note.v1")
@dataclass(frozen=True, slots=True)
class WriteNote:
    """Handled in process by three handlers; ``fail`` makes the last one raise.

    With ``nested``, the second dispatches a :class:`NestedNote` — failing instead
    when ``fail`` — held back until this one was handled when ``after``, and
    carries on when it fails if ``catch_nested``. ``refuse`` makes the last
    handler raise whatever else is asked.
    """

    text: str
    fail: bool = False
    nested: bool = False
    leave_open: bool = False
    catch_nested: bool = False
    after: bool = False
    refuse: bool = False


@as_message(name="tests.orm.nested_note.v1")
@dataclass(frozen=True, slots=True)
class NestedNote:
    """Dispatched while a :class:`WriteNote` is handled; ``fail`` makes its handler raise."""

    text: str
    fail: bool = False


@as_message(name="tests.orm.queued_note.v1")
@dataclass(frozen=True, slots=True)
class QueuedNote:
    """Routed to the ``jobs`` transport: written only once a worker handles it."""

    text: str
    fail: bool = False
