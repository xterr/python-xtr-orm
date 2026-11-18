"""Every statement the request sent to its databases."""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING, Final, final

if TYPE_CHECKING:
    from collections.abc import Sequence

    from xtr_http_kernel.data_collector import ProfiledRequest

    from .query_listener import QueryListener

__all__ = ["OrmDataCollector"]

_NAME: Final = "orm"


@final
class OrmDataCollector:
    """Keeps the statements a :class:`QueryListener` recorded for the request.

    Read again once the response has left, since a streamed body may still
    be querying when the response starts: each statement in the order it ran,
    and what a toolbar shows — how many, how long, how many failed, and which
    ran more than once, the usual sign of a query issued per row.
    """

    __slots__ = ("_connections", "_listener")

    def __init__(self, listener: QueryListener, connections: Sequence[str]) -> None:
        """Read what ``listener`` records, for the configured ``connections``, by name."""
        self._listener = listener
        self._connections = tuple(connections)

    @property
    def name(self) -> str:
        """``"orm"``."""
        return _NAME

    def begin_request(self) -> None:
        """Start recording the request's statements, from none."""
        self._listener.trace.begin()

    def collect(self, profiled: ProfiledRequest) -> dict[str, object]:
        """Return the statements run so far; the rest follow once the response has left."""
        del profiled
        return self._read()

    def late_collect(self, data: dict[str, object], profiled: ProfiledRequest) -> dict[str, object]:
        """Return every statement of the request."""
        del data, profiled
        return self._read()

    def _read(self) -> dict[str, object]:
        queries = self._listener.trace.entries()
        runs = Counter(query.statement for query in queries)
        return {
            "queries": [query.to_data() for query in queries],
            "count": len(queries),
            "duration_ms": sum(query.duration_ms for query in queries),
            "connections": list(self._connections),
            "repeated": [
                {"statement": statement, "count": count}
                for statement, count in runs.most_common()
                if count > 1
            ],
            "errors": sum(1 for query in queries if query.error is not None),
        }
