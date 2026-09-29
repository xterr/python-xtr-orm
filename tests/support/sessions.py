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
    """The session each connection hands out, and the connections closed."""

    def __init__(self, engine: AsyncEngine, migrator: Migrator, *names: str) -> None:
        self.by_name = {name: AsyncSession(engine) for name in names}
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
            )

    def _session(self, name: str) -> Callable[[], Awaitable[AsyncSession]]:
        async def session() -> AsyncSession:
            return self.by_name[name]

        return session

    def _close(self, name: str) -> Callable[[], Awaitable[None]]:
        async def close() -> None:
            self.closed.append(name)

        return close

    async def aclose(self) -> None:
        for session in self.by_name.values():
            await session.close()
