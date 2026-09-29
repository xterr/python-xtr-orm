"""``orm:run-sql``: run a statement and show what it returned."""

from __future__ import annotations

from typing import Any, cast, final

from sqlalchemy import Row, text
from sqlalchemy.exc import SQLAlchemyError
from xtr_console import ConsoleStyle, ExitCode, as_command, escape

from .connection_command import ConnectionCommand

__all__ = ["RunSqlCommand"]


@as_command("orm:run-sql")
@final
class RunSqlCommand(ConnectionCommand):
    """Executes arbitrary SQL directly from the command line."""

    __slots__ = ()

    async def __call__(
        self,
        io: ConsoleStyle,
        sql: str,
        *,
        force_fetch: bool = False,
        connection: str | None = None,
    ) -> int:
        """Run the statement, committed, and show its rows or how many it changed.

        Args:
            io: Where the command writes.
            sql: The statement to run.
            force_fetch: Show the result as rows even when the statement
                does not look like it returns any.
            connection: The connection to run it on; the default one when
                left out.
        """
        engine = await self._engine(io, connection)
        if engine is None:
            return ExitCode.FAILURE
        columns: list[str] = []
        rows: list[list[str]] = []
        affected = 0
        try:
            async with engine.begin() as opened:
                result = await opened.execute(text(sql))
                if result.returns_rows:
                    columns = [str(column) for column in result.keys()]  # noqa: SIM118 — a result's keys are its columns, not a dict's
                    rows = [[_cell(value) for value in _values(row)] for row in result.all()]
                else:
                    affected = result.rowcount
        except SQLAlchemyError as error:
            io.error(escape(str(error)))
            return ExitCode.FAILURE
        if not columns and not force_fetch:
            # A driver that cannot tell — after a schema change, say — reports -1.
            if affected < 0:
                io.success("The statement was executed.")
            else:
                io.success(f"{affected} row{'' if affected == 1 else 's'} affected.")
            return ExitCode.SUCCESS
        if not rows:
            io.success("The query yielded an empty result set.")
            return ExitCode.SUCCESS
        io.table([escape(column) for column in columns], rows)
        return ExitCode.SUCCESS


def _values(row: Row[Any]) -> tuple[object, ...]:  # pyright: ignore[reportExplicitAny] -- a row of a text statement has no known column types
    return tuple(cast("tuple[object, ...]", row))


def _cell(value: object) -> str:
    return "NULL" if value is None else escape(str(value))
