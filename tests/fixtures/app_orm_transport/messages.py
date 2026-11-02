"""What the fixture app queues."""

from __future__ import annotations

from dataclasses import dataclass

from xtr_messenger import as_message


@as_message(name="tests.orm.transport.queued_order.v1")
@dataclass(frozen=True, slots=True)
class QueuedOrder:
    """Routed to the ``orders`` table on the default database."""

    order: str


@as_message(name="tests.orm.transport.queued_report.v1")
@dataclass(frozen=True, slots=True)
class QueuedReport:
    """Routed to the ``report_messages`` table on the reports database."""

    report: str
