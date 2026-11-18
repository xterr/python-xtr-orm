"""Every statement an engine sends, recorded for the profiled request that sent it."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, cast, final

from sqlalchemy import event
from sqlalchemy.engine.default import DefaultExecutionContext
from xtr_clock import MonotonicClock
from xtr_http_kernel.data_collector import RequestTrace, clone_var

from ._masking import masked
from .recorded_query import RecordedQuery

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection, ExceptionContext
    from sqlalchemy.engine.interfaces import DBAPICursor, ExecutionContext
    from sqlalchemy.ext.asyncio import AsyncEngine
    from xtr_clock import ClockInterface, DatePoint

__all__ = ["QueryListener"]

_STARTED: Final = "xtr_orm_profiled_starts"
"""The key, on a connection's ``info``, of the start times of its statements under way."""

_MAX_DEPTH: Final = 2
_MAX_ITEMS: Final = 50
_MILLISECONDS_PER_SECOND: Final = 1000


@final
class QueryListener:
    """Records each statement an engine runs into the profiled request's trace.

    Listens to the driver-level events of an engine — before and after a
    statement goes to the cursor, and when it fails — so every statement is
    seen, whether it came from a session, a connection or a migration. The
    entries go to a :class:`~xtr_http_kernel.data_collector.RequestTrace`:
    each request served at once keeps its own, and a statement run outside a
    profiled request costs a context lookup and keeps nothing.

    ```python
    listener = QueryListener()
    listener.listen(engine, "default")
    listener.trace.begin()
    async with engine.connect() as connection:
        await connection.execute(text("select 1"))
    listener.trace.entries()  # (RecordedQuery(statement="select 1", ...),)
    ```
    """

    __slots__ = ("_clock", "_trace")

    def __init__(self, clock: ClockInterface | None = None) -> None:
        """Time statements on ``clock``, a :class:`~xtr_clock.MonotonicClock` by default.

        Args:
            clock: What a statement's start and end are read from; monotonic,
                so a wall clock correction never makes a duration negative.
        """
        self._clock: ClockInterface = clock if clock is not None else MonotonicClock()
        self._trace: RequestTrace[RecordedQuery] = RequestTrace("orm_queries")

    @property
    def trace(self) -> RequestTrace[RecordedQuery]:
        """The statements the profiled request of the calling context ran, oldest first."""
        return self._trace

    def listen(self, engine: AsyncEngine, connection: str) -> None:
        """Record the statements ``engine`` runs, under the connection name ``connection``.

        Call it once per engine: every call adds its own listeners.
        """
        recorder = _EngineRecorder(connection, self._clock, self._trace)
        sync_engine = engine.sync_engine
        event.listen(sync_engine, "before_cursor_execute", recorder.before_cursor_execute)
        event.listen(sync_engine, "after_cursor_execute", recorder.after_cursor_execute)
        event.listen(sync_engine, "handle_error", recorder.handle_error)


@final
class _EngineRecorder:
    """The listeners of one engine, knowing the connection name its statements are kept under."""

    __slots__ = ("_clock", "_connection", "_trace")

    def __init__(
        self, connection: str, clock: ClockInterface, trace: RequestTrace[RecordedQuery]
    ) -> None:
        self._connection = connection
        self._clock = clock
        self._trace = trace

    def before_cursor_execute(  # noqa: PLR0913, PLR0917 — the event's own signature
        self,
        conn: Connection,
        cursor: DBAPICursor,
        statement: str,
        parameters: object,
        context: ExecutionContext | None,
        executemany: bool,
    ) -> None:
        """Note when the statement started, only while a profiled request is recorded."""
        del cursor, statement, parameters, context, executemany
        if self._trace.is_recording():
            _starts(conn).append(self._clock.now())

    def after_cursor_execute(  # noqa: PLR0913, PLR0917 — the event's own signature
        self,
        conn: Connection,
        cursor: DBAPICursor,
        statement: str,
        parameters: object,
        context: ExecutionContext | None,
        executemany: bool,
    ) -> None:
        """Record the statement that just ran, if its start was noted."""
        started = self._started(conn)
        if started is None:
            return
        row_count = cursor.rowcount
        self._trace.record(
            RecordedQuery(
                connection=self._connection,
                statement=statement,
                parameters=_parameters(parameters, context),
                executemany=executemany,
                duration_ms=self._elapsed_ms(started),
                row_count=row_count if row_count >= 0 else None,
            )
        )

    def handle_error(self, context: ExceptionContext) -> None:
        """Record the statement that failed, with the failure."""
        statement = context.statement
        if statement is None or not self._trace.is_recording():
            return
        conn = context.connection
        started = self._started(conn) if conn is not None else None
        execution = context.execution_context
        failure = context.original_exception
        self._trace.record(
            RecordedQuery(
                connection=self._connection,
                statement=statement,
                parameters=_parameters(context.parameters, execution),
                executemany=execution.executemany if execution is not None else False,
                duration_ms=self._elapsed_ms(started) if started is not None else 0.0,
                row_count=None,
                error=f"{type(failure).__name__}: {failure}",
            )
        )

    def _started(self, conn: Connection) -> DatePoint | None:
        starts = _starts(conn)
        return starts.pop() if starts else None

    def _elapsed_ms(self, started: DatePoint) -> float:
        elapsed = self._clock.now() - started
        return elapsed.total_seconds() * _MILLISECONDS_PER_SECOND


def _starts(conn: Connection) -> list[DatePoint]:
    """Return the start times of the statements under way on ``conn``, innermost last."""
    return cast("list[DatePoint]", conn.info.setdefault(_STARTED, []))


def _parameters(parameters: object, context: ExecutionContext | None) -> dict[str, object]:
    """Return the statement's parameters as a tree, credentials masked.

    A compiled statement knows each value by its name, whatever placeholder
    style the driver takes, so those are kept — and masked by name; a string
    sent as is keeps what was given with it.
    """
    given = parameters
    if isinstance(context, DefaultExecutionContext) and context.compiled is not None:
        named = context.compiled_parameters
        given = named[0] if len(named) == 1 else list(named)
    return clone_var(masked(given), max_depth=_MAX_DEPTH, max_items=_MAX_ITEMS)
