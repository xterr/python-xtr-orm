"""How one database's migrations are written, found and recorded."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final, cast

from xtr_orm.exception import InvalidArgumentError

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

__all__ = ["MigrationsConfig"]

_FILE_TEMPLATE_FIELDS: Final = {
    "rev": "%(rev)s",
    "slug": "%(slug)s",
    "epoch": "%(epoch)s",
    "year": "%(year)d",
    "month": "%(month).2d",
    "day": "%(day).2d",
    "hour": "%(hour).2d",
    "minute": "%(minute).2d",
    "second": "%(second).2d",
}
_FIELD: Final = re.compile(r"\{(\w+)\}")


def _no_options() -> dict[str, object]:
    return {}


@dataclass(frozen=True, slots=True)
class MigrationsConfig:
    """Where a database's revisions live, how new ones are written, and how runs are recorded.

    Revisions are ordinary migration files, one per change, in
    :attr:`directory`. The database keeps its current revisions in
    :attr:`version_table`, and a row per revision ever applied — when, and how
    long it took — in :attr:`history_table`.

    ```python
    MigrationsConfig(
        directory="%kernel.project_dir%/migrations",
        version_table_schema="meta",
        render_as_batch=True,  # SQLite cannot alter a table in place
    )
    ```

    Attributes:
        directory: Where revision files are read from and written to; created
            when the first one is written.
        version_table: The table holding the database's current revisions.
        version_table_schema: The schema of both tables; the connection's
            default when ``None``.
        history_table: The table recording every revision applied, when it
            ran and how long it took.
        file_template: How a new revision's file is named. ``{rev}``,
            ``{slug}``, ``{epoch}``, ``{year}``, ``{month}``, ``{day}``,
            ``{hour}``, ``{minute}`` and ``{second}`` are filled in; the
            default sorts files by the time they were written.
        truncate_slug_length: The longest the message part of a file name
            gets.
        timezone: The time zone a revision's creation date is written in;
            local time when ``None``.
        template_directory: A directory holding a ``script.py.mako`` that new
            revisions are rendered from; the package's own when ``None``.
        recursive_version_locations: Read revisions from subdirectories of
            :attr:`directory` too.
        post_write_hooks: Programs run on every file written, such as a
            formatter — each a mapping with a ``type`` (``"console_scripts"``,
            ``"exec"`` or ``"module"``) and that type's options.
        transaction_per_migration: Commit after each revision rather than
            once after all of them.
        transactional_ddl: Whether schema changes run inside the
            transaction; the database's own answer when ``None``.
        compare_type: Compare column types when generating a diff. Off by
            default: a type the database stores as another — a UUID kept as
            bytes on SQLite — would otherwise differ in every diff.
        compare_server_default: Compare server defaults when generating a
            diff.
        render_as_batch: Write table changes as copy-and-move batches, which
            SQLite needs for anything but adding a column.
        include_schemas: Compare every schema when generating a diff, not
            only the default one.
        include_name: Decides, by name, which schemas and tables a diff
            reads from the database.
        include_object: Decides which tables, columns, indexes and
            constraints a diff considers.
        render_item: Renders a type or a construct a diff writes, before the
            default rendering.
        process_revision_directives: Adjusts a revision about to be written.
        user_module_prefix: Written before a custom type's class name; the
            type's own module — imported by the revision — when ``None``.
        context_options: Any other migration context option, passed as it
            is.
    """

    directory: str = "migrations"
    version_table: str = "alembic_version"
    version_table_schema: str | None = None
    history_table: str = "alembic_version_history"
    file_template: str = "{year}{month}{day}{hour}{minute}{second}_{rev}_{slug}"
    truncate_slug_length: int = 40
    timezone: str | None = None
    template_directory: str | None = None
    recursive_version_locations: bool = False
    post_write_hooks: Sequence[Mapping[str, str]] = ()
    transaction_per_migration: bool = False
    transactional_ddl: bool | None = None
    compare_type: bool = False
    compare_server_default: bool = False
    render_as_batch: bool = False
    include_schemas: bool = False
    include_name: Callable[..., bool] | None = None
    include_object: Callable[..., bool] | None = None
    render_item: Callable[..., str | bool] | None = None
    process_revision_directives: Callable[..., None] | None = None
    user_module_prefix: str | None = None
    context_options: Mapping[str, object] = field(default_factory=_no_options)

    def __post_init__(self) -> None:
        """Refuse an empty directory or table name, or a file template naming nothing known.

        Raises:
            InvalidArgumentError: When the configuration cannot be used.
        """
        for name in ("directory", "version_table", "history_table"):
            # Compared, not tested for truth: a value may be an environment
            # placeholder, which refuses to decide anything before it is read.
            if cast("str", getattr(self, name)) == "":
                raise InvalidArgumentError(f'The migrations "{name}" must not be empty.')
        if self.version_table == self.history_table:
            raise InvalidArgumentError(
                "The migrations version table and history table must differ, "
                f'both are "{self.version_table}".',
            )
        unknown = [
            name
            for name in cast("list[str]", _FIELD.findall(self.file_template))
            if name not in _FILE_TEMPLATE_FIELDS
        ]
        if unknown:
            known = ", ".join(f"{{{name}}}" for name in _FILE_TEMPLATE_FIELDS)
            raise InvalidArgumentError(
                f'The migrations file template names "{{{unknown[0]}}}"; it may use {known}.',
            )
        if "{rev}" not in self.file_template and "{epoch}" not in self.file_template:
            raise InvalidArgumentError(
                "The migrations file template must hold {rev} or {epoch}, "
                "or two revisions could be written to one file.",
            )
        if self.truncate_slug_length < 1:
            raise InvalidArgumentError(
                f"The migrations slug length must be at least 1, got {self.truncate_slug_length}.",
            )

    def alembic_file_template(self) -> str:
        """Return :attr:`file_template` in the form the revision writer reads."""
        escaped = self.file_template.replace("%", "%%")
        return _FIELD.sub(lambda match: _FILE_TEMPLATE_FIELDS[match.group(1)], escaped)
