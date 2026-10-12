"""The builder calls a compiler pass of this package makes, answered by the test.

The real one is the compiler's to make — it is bound to the whole build state
— so the unit tests stand in for it here and the kernel tests cover it for
real.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast, final

if TYPE_CHECKING:
    from collections.abc import Mapping

    from xtr_dependency_injection import ContainerBuilder

    from xtr_orm.bundle import OrmConfig

__all__ = ["FakeBuilder", "as_builder"]


@final
class FakeBuilder:
    """Answers the parameter and config reads of a pass, and keeps what it logged."""

    __slots__ = ("_config", "_parameters", "logged")

    def __init__(self, config: OrmConfig, parameters: Mapping[str, object]) -> None:
        """Answer with ``config`` and ``parameters``, logging into :attr:`logged`."""
        self._config = config
        self._parameters = dict(parameters)
        self.logged: list[str] = []

    def has_parameter(self, name: str, /) -> bool:
        """Tell whether ``name`` was given."""
        return name in self._parameters

    def get_parameter(self, name: str, /) -> object:
        """Return what ``name`` was given.

        Raises:
            KeyError: When it was not; the real builder raises
                ``ParameterNotFoundError``, which a pass does not catch either.
        """
        return self._parameters[name]

    def get_extension_config(self, bundle: type[OrmConfig], /) -> OrmConfig:
        """Return the orm configuration this builder was made with."""
        del bundle
        return self._config

    def log(self, compiler_pass: object, message: str, /) -> None:
        """Record ``message``, as the compiler log would."""
        del compiler_pass
        self.logged.append(message)


def as_builder(fake: FakeBuilder) -> ContainerBuilder:
    """Hand ``fake`` over where the compiler would hand a pass its builder."""
    # The two are unrelated types — the fake answers the handful of calls a
    # pass makes rather than being a view of a build — and the real builder is
    # final, so the cast goes through object, as one between types that cannot
    # overlap must.
    return cast("ContainerBuilder", cast("object", fake))
