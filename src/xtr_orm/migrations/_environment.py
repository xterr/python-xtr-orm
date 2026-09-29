"""The migration runner, set up in memory for one database.

No ``env.py`` and no ``alembic.ini``: the revision directory is built from a
:class:`MigrationsConfig`, and the runner is handed the connection, the
table definitions and every option directly, the way a start-up script would
hand them over.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Final, TypeAlias, cast, final

from alembic.config import Config
from alembic.runtime.environment import EnvironmentContext
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence
    from typing import IO

    from alembic.autogenerate import RevisionContext
    from alembic.autogenerate.api import AutogenContext
    from alembic.config import PostWriteHookConfig
    from alembic.runtime.migration import MigrationStep
    from sqlalchemy import MetaData
    from sqlalchemy.engine import Connection

    from .migrations_config import MigrationsConfig

    MigrationsFn: TypeAlias = Callable[[tuple[str, ...], MigrationContext], Iterable[MigrationStep]]
    """What the runner asks for the steps to apply, given the current revisions."""

__all__ = ["Environment"]

_TEMPLATE_DIRECTORY: Final = Path(__file__).parent / "template"
"""Where the package's own ``script.py.mako`` is."""


@final
class Environment:
    """One database's revision directory and runner options."""

    __slots__ = ("_config", "_metadata")

    _config: MigrationsConfig
    _metadata: MetaData | Sequence[MetaData] | None

    def __init__(
        self, config: MigrationsConfig, metadata: MetaData | Sequence[MetaData] | None
    ) -> None:
        """Set up for the revisions ``config`` describes, diffing against ``metadata``."""
        self._config = config
        self._metadata = metadata

    def directory(self) -> ScriptDirectory:
        """Read the revision directory afresh, so files written since are seen."""
        config = self._config
        hooks = cast(
            "list[PostWriteHookConfig]",
            [
                {"_hook_name": f"hook_{index}", **hook}
                for index, hook in enumerate(config.post_write_hooks)
            ],
        )
        return ScriptDirectory(
            config.template_directory or _TEMPLATE_DIRECTORY,
            file_template=config.alembic_file_template(),
            truncate_slug_length=config.truncate_slug_length,
            version_locations=[config.directory],
            timezone=config.timezone,
            hooks=hooks,
            recursive_version_locations=config.recursive_version_locations,
            messaging_opts={"quiet": True},
        )

    def context(self, connection: Connection) -> MigrationContext:
        """Return a context reading ``connection``'s version table, for reports."""
        return MigrationContext.configure(
            connection,
            opts={
                "version_table": self._config.version_table,
                "version_table_schema": self._config.version_table_schema,
            },
        )

    def run(  # noqa: PLR0913 — every runner option, each passed by keyword
        self,
        connection: Connection,
        directory: ScriptDirectory,
        steps: MigrationsFn,
        *,
        as_sql: bool = False,
        output: IO[str] | None = None,
        starting_rev: tuple[str, ...] | None = None,
        purge: bool = False,
        on_version_apply: Callable[..., None] | None = None,
        revision_context: RevisionContext | None = None,
        read_only: bool = False,
    ) -> None:
        """Run ``steps`` against ``connection``, or write their SQL to ``output``.

        ``read_only`` leaves even a missing version table uncreated, for a run
        that only reads — one writing a revision file.
        """
        config = self._config
        extra: dict[str, object] = {}
        if revision_context is not None:
            extra["revision_context"] = revision_context
            extra["template_args"] = revision_context.template_args
        with EnvironmentContext(
            Config(),
            directory,
            fn=steps,
            as_sql=as_sql,
            starting_rev=list(starting_rev) if as_sql and starting_rev else None,
            purge=purge,
            **extra,
        ) as environment:
            options: dict[str, object] = {
                "connection": connection,
                "target_metadata": self._metadata,
                "version_table": config.version_table,
                "version_table_schema": config.version_table_schema,
                "transaction_per_migration": config.transaction_per_migration,
                "compare_type": config.compare_type,
                "compare_server_default": config.compare_server_default,
                "render_as_batch": config.render_as_batch,
                "include_schemas": config.include_schemas,
                "include_name": _include_name(config.include_name, config.history_table),
                "include_object": config.include_object,
                "render_item": _render_item(config.render_item, config.user_module_prefix),
                # Not "process_revision_directives": the migrator runs it inside its own,
                # which the runner would call first, before the revision is complete.
                "user_module_prefix": config.user_module_prefix,
                "literal_binds": as_sql,
                "output_buffer": output,
                "on_version_apply": on_version_apply,
                "dont_mutate": read_only,
            }
            if config.transactional_ddl is not None:
                options["transactional_ddl"] = config.transactional_ddl
            options.update(config.context_options)
            # Forwarded by name, the application's own options included; the
            # runner checks each as it reads it.
            configure = cast("Callable[..., None]", environment.configure)
            configure(**options)
            with environment.begin_transaction():
                environment.run_migrations()


def _include_name(
    custom: Callable[..., bool] | None, history_table: str
) -> Callable[[str | None, str, dict[str, str | None]], bool]:
    """Keep the history table out of every diff, as the runner keeps its version table out.

    Any configured filter decides for every other name.
    """

    def include_name(name: str | None, kind: str, parents: dict[str, str | None]) -> bool:
        if kind == "table" and name == history_table:
            return False
        return custom is None or custom(name, kind, parents)

    return include_name


def _render_item(
    custom: Callable[..., str | bool] | None, user_module_prefix: str | None
) -> Callable[[str, object, AutogenContext], str | bool]:
    """Chain the configured renderer with one importing each custom type's module.

    A type from outside the database library is written under its own
    module's name; the revision imports that module so the name resolves.
    """

    def render_item(kind: str, value: object, context: AutogenContext) -> str | bool:
        if custom is not None:
            rendered = custom(kind, value, context)
            if rendered is not False:
                return rendered
        if kind == "type" and user_module_prefix is None:
            module = type(value).__module__
            if not module.startswith("sqlalchemy.") and module != "builtins":
                context.imports.add(f"import {module}")
        return False

    return render_item
