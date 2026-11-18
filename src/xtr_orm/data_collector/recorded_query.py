"""One statement a profiled request sent to a database."""

from __future__ import annotations

from dataclasses import dataclass
from typing import final

__all__ = ["RecordedQuery"]


@final
@dataclass(frozen=True, slots=True)
class RecordedQuery:
    """What the panel shows of one statement, already plain data.

    Kept as plain data from the moment it is recorded: the parameters are
    copied while the statement runs, so a value the application changes
    afterwards — or a credential it held — is never read again.

    Attributes:
        connection: The name of the connection the statement ran on.
        statement: The SQL, as sent to the driver.
        parameters: The bound values, a :func:`~xtr_http_kernel.data_collector.clone_var`
            tree; a value named like a credential is ``"******"``.
        executemany: Whether the statement ran once per row of parameters.
        duration_ms: How long the driver took, in milliseconds.
        row_count: The rows the driver reports affected, or ``None`` when it
            reports none — a read, on most drivers.
        error: The failure, as ``"<type>: <message>"``, or ``None``.
    """

    connection: str
    statement: str
    parameters: dict[str, object]
    executemany: bool
    duration_ms: float
    row_count: int | None
    error: str | None = None

    def to_data(self) -> dict[str, object]:
        """Return the statement as the mapping a profile keeps."""
        return {
            "connection": self.connection,
            "statement": self.statement,
            "parameters": self.parameters,
            "executemany": self.executemany,
            "duration_ms": self.duration_ms,
            "row_count": self.row_count,
            "error": self.error,
        }
