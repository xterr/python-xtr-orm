"""A connection was asked for by a name nothing registered."""

from __future__ import annotations

from .orm_error import OrmError

__all__ = ["UnknownConnectionError"]


class UnknownConnectionError(OrmError, LookupError):
    """A connection was asked for by a name nothing registered.

    Also a :class:`LookupError`, as a missing key in any other mapping is.

    Attributes:
        name: The name asked for.
        known: Every name that is registered.
    """

    name: str
    known: tuple[str, ...]

    def __init__(self, name: str, known: tuple[str, ...]) -> None:
        """Record the name asked for and the ones that exist."""
        self.name = name
        self.known = known
        names = ", ".join(f'"{each}"' for each in known) or "none"
        super().__init__(f'Unknown connection "{name}"; the connections are: {names}.')
