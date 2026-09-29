"""A connection registry whose session is one real session per test, on the test's SQLite file."""

from __future__ import annotations

from typing import TYPE_CHECKING, final

from sqlalchemy.ext.asyncio import AsyncSession

from xtr_orm import ConnectionRegistry, DatabaseManager

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from sqlalchemy.ext.asyncio import AsyncEngine

    from xtr_orm import Migrator


@final
class Sessions:
    """The session each connection hands out, the connections in use, and those closed.

    Every connection starts in use; a session asked of one that is not fails,
    as building an engine nothing configured would.
    """

    def __init__(self, engine: AsyncEngine, migrator: Migrator, *names: str) -> None:
        self.by_name = {name: AsyncSession(engine) for name in names}
        self.in_use = set(names)
        self.closed: list[str] = []
        self.registry = ConnectionRegistry(names[0])
        for name in names:
            self.registry.register(
                name,
                engine=engine,
                migrator=migrator,
                database=DatabaseManager("sqlite+aiosqlite://"),
                session=self._session(name),
                close=self._close(name),
                in_use=lambda name=name: name in self.in_use,
            )

    def _session(self, name: str) -> Callable[[], Awaitable[AsyncSession]]:
        async def session() -> AsyncSession:
            if name not in self.in_use:
                raise LookupError(name)
            return self.by_name[name]

        return session

    def _close(self, name: str) -> Callable[[], Awaitable[None]]:
        async def close() -> None:
            self.closed.append(name)

        return close

    async def aclose(self) -> None:
        for session in self.by_name.values():
            await session.close()
