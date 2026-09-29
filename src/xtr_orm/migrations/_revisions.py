"""Reading the revision files: what exists, what is applied, and what a target means.

Everything here works on a revision directory and a database's current
revisions, and touches no database. The runner is handed the steps these
functions return and applies them.
"""

from __future__ import annotations

import re
from contextlib import contextmanager
from typing import TYPE_CHECKING, Final

from alembic.runtime.migration import MigrationStep, RevisionStep
from alembic.script.revision import ResolutionError, RevisionError
from alembic.util import CommandError

from xtr_orm.exception import MigrationError

from .available_migration import AvailableMigration
from .direction import Direction

if TYPE_CHECKING:
    from collections.abc import Generator, Iterable, Sequence

    from alembic.script import Script, ScriptDirectory

__all__ = [
    "applied",
    "available",
    "known",
    "mark_step",
    "migration",
    "parents",
    "plan",
    "refusing",
    "resolve",
    "revision_steps",
    "step",
]

_ALIASES: Final[dict[str, tuple[str, Direction]]] = {
    "latest": ("heads", Direction.UP),
    "head": ("heads", Direction.UP),
    "heads": ("heads", Direction.UP),
    "next": ("+1", Direction.UP),
    "first": ("base", Direction.DOWN),
    "base": ("base", Direction.DOWN),
    "prev": ("-1", Direction.DOWN),
}
"""Names a target may be given by, and the revision and direction each stands for."""

_RELATIVE: Final = re.compile(r"^(?:.+?@)?\w*([+-])\d+$")
"""``+2``, ``-1``, ``ae10+1``, ``branch@head-1``: a number of steps from somewhere."""


def migration(script: Script) -> AvailableMigration:
    """Describe ``script`` as the rest of the library sees a revision file."""
    return AvailableMigration(
        version=script.revision,
        description=(script.doc or "").strip(),
        down_versions=_as_tuple(script.down_revision),
        path=script.path,
        is_head=script.is_head,
    )


def available(directory: ScriptDirectory) -> tuple[Script, ...]:
    """Return every revision in ``directory``, earliest first."""
    with refusing():
        return tuple(reversed(list(directory.walk_revisions())))


def known(directory: ScriptDirectory, versions: Iterable[str]) -> tuple[str, ...]:
    """Return the ``versions`` that have a revision file."""
    found: list[str] = []
    for version in versions:
        try:
            _ = directory.get_revision(version)
        except (CommandError, ResolutionError, RevisionError):
            continue
        found.append(version)
    return tuple(found)


def applied(directory: ScriptDirectory, heads: Sequence[str]) -> set[str]:
    """Return every revision ``heads`` stand for: themselves and all they follow.

    A head without a file stands only for itself; what it followed cannot be
    known.
    """
    present = known(directory, heads)
    if not present:
        return set()
    with refusing():
        return {each.revision for each in directory.iterate_revisions(present, "base")}


def resolve(directory: ScriptDirectory, version: str) -> Script:
    """Return the one revision ``version`` names — a full or partial id, or a label.

    Raises:
        MigrationError: When no revision, or more than one, answers to it.
    """
    try:
        found = directory.get_revision(version)
    except (CommandError, ResolutionError, RevisionError) as error:
        raise MigrationError(f'Unknown version "{version}": {error}') from error
    return found


def parents(directory: ScriptDirectory, script: Script) -> tuple[str, ...]:
    """Return the revisions ``script`` needs applied first: those it follows and depends on."""
    dependencies = (resolve(directory, each).revision for each in _as_tuple(script.dependencies))
    return (*_as_tuple(script.down_revision), *dependencies)


def plan(
    directory: ScriptDirectory, heads: tuple[str, ...], target: str
) -> tuple[Direction, list[RevisionStep]]:
    """Return which way reaching ``target`` from ``heads`` goes, and the steps it takes.

    ``target`` is a revision, a relative one (``+1``, ``-2``, ``ae10+1``), or
    one of ``latest``, ``first``, ``next``, ``prev`` and ``current``.

    Raises:
        MigrationError: When the target is unknown, or cannot be reached.
    """
    if target == "current":
        return Direction.UP, []
    destination, direction = _ALIASES.get(target, (target, Direction.UP))
    if target not in _ALIASES:
        relative = _RELATIVE.match(target)
        if relative is not None:
            direction = Direction.UP if relative.group(1) == "+" else Direction.DOWN
        elif resolve(directory, target).revision in applied(directory, heads):
            direction = Direction.DOWN
    return direction, revision_steps(directory, heads, destination, direction)


def revision_steps(
    directory: ScriptDirectory, heads: tuple[str, ...], destination: str, direction: Direction
) -> list[RevisionStep]:
    """Return the steps from ``heads`` to ``destination``, going ``direction``.

    Raises:
        MigrationError: When the destination cannot be reached that way.
    """
    revision_map = directory.revision_map
    with refusing():
        if direction is Direction.UP:
            scripts = reversed(
                list(directory.iterate_revisions(destination, heads, implicit_base=True))
            )
            return [MigrationStep.upgrade_from_script(revision_map, each) for each in scripts]
        scripts = directory.iterate_revisions(heads, destination, select_for_downgrade=True)
        return [MigrationStep.downgrade_from_script(revision_map, each) for each in scripts]


def step(directory: ScriptDirectory, script: Script, direction: Direction) -> RevisionStep:
    """Return the step running ``script``'s upgrade or downgrade alone."""
    if direction is Direction.UP:
        return MigrationStep.upgrade_from_script(directory.revision_map, script)
    return MigrationStep.downgrade_from_script(directory.revision_map, script)


def mark_step(directory: ScriptDirectory, script: Script, direction: Direction) -> RevisionStep:
    """Return a step that moves the version table over ``script`` without running it."""
    marked = step(directory, script, direction)
    marked.migration_fn = _nothing
    return marked


def _nothing(**_: object) -> None:
    """Stand in for a revision's upgrade or downgrade when it is only marked."""


def _as_tuple(value: str | Sequence[str] | None) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(value)


@contextmanager
def refusing() -> Generator[None]:
    """Turn the revision reader's own errors into :class:`MigrationError`."""
    try:
        yield
    except (CommandError, ResolutionError, RevisionError) as error:
        raise MigrationError(str(error)) from error
    except KeyError as error:
        # The reader indexes its map by the ids revisions name; one naming a
        # revision that has no file surfaces as the missing key.
        raise MigrationError(
            f"A revision follows {error.args[0]!r}, which has no revision file.",
        ) from error
