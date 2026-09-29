"""Reading what a command printed, wherever it printed it."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from xtr_console import ApplicationTester


def output(tester: ApplicationTester) -> str:
    """Everything the last run printed, to standard output then to standard error, on one line."""
    return " ".join((tester.display + tester.error_display).split())


def table_rows(tester: ApplicationTester) -> list[list[str]]:
    """The cells of every table row the last run printed, header included."""
    return [
        [cell.strip() for cell in line.strip().strip("│").split("│")]
        for line in tester.display.splitlines()
        if line.lstrip().startswith("│")
    ]
