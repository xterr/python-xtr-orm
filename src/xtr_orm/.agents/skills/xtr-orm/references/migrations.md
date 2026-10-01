# MigrationsConfig and revision templates

A frozen dataclass; every field has a default, so `MigrationsConfig()` is valid.
Import it from `xtr_orm` or from `xtr_orm.bundle`.

| Field | Default | Meaning |
|---|---|---|
| `directory` | `"migrations"` | Where revision files are read and written. A relative path is relative to the working directory — under a kernel start it with `%kernel.project_dir%` |
| `version_table` | `"alembic_version"` | Holds the revisions the database is at |
| `history_table` | `"alembic_version_history"` | A row per revision ever applied: `version`, `executed_at`, `execution_time` in milliseconds |
| `version_table_schema` | `None` | The schema of both; the connection's default when `None` |
| `file_template` | `"{year}{month}{day}{hour}{minute}{second}_{rev}_{slug}"` | How a file is named; `{epoch}` is available too |
| `truncate_slug_length` | `40` | The longest message part of a file name |
| `timezone` | `None` | The zone a revision's date is written in |
| `template_directory` | `None` | A directory holding a `script.py.mako` to render new revisions from |
| `recursive_version_locations` | `False` | Read subdirectories of `directory` too |
| `post_write_hooks` | `()` | Programs run on each file written, such as a formatter |
| `transaction_per_migration` | `False` | Commit after each revision rather than once |
| `transactional_ddl` | `None` | Run schema changes inside the transaction |
| `compare_type` | `False` | Compare column types in a diff |
| `compare_server_default` | `False` | Compare server defaults in a diff |
| `render_as_batch` | `False` | Write table changes as batches. **SQLite needs this** |
| `include_schemas` | `False` | Read other schemas in a diff |
| `include_name` / `include_object` | `None` | Callables deciding what a diff reads |
| `render_item` | `None` | Callable deciding how an item is written |
| `process_revision_directives` | `None` | Callable adjusting a diff before it is written |
| `user_module_prefix` | `None` | The prefix custom column types are written with |
| `context_options` | `{}` | Any other migration context option, passed through |

## Custom column types in a diff

A custom type is written under its own module's name, and the revision imports that module:
`advanced_alchemy.types.guid.GUID(length=16)` plus `import advanced_alchemy.types.guid`. Set
`user_module_prefix` or `render_item` to write it otherwise.

`compare_type` is off by default on purpose: a type the database stores as another — a UUID kept
as bytes on SQLite — would otherwise differ in every diff.

## Your own revision template

New revisions render from `script.py.mako`: the package's own, or the one in
`template_directory`. Nothing else is read from that directory.

The template receives `message`, `up_revision`, `down_revision`, `branch_labels`, `depends_on`,
`create_date`, `imports`, `upgrades`, `downgrades`, and the `comma` filter
(`${down_revision | comma,n}`). A template written for a plain migration-runner project works as
it is.

```python
MigrationsConfig(
    template_directory="%kernel.project_dir%/resources/migrations",
    user_module_prefix="sa.",  # for a template aliasing sa.GUID = GUID
)
```

A template calling `op.get_context().autocommit_block()` commits the revision's schema changes
before the version and history tables are written, and gives up the transaction a failing
revision would roll back. Set `transaction_per_migration=True` alongside it, and keep it to the
revisions that need it (`CREATE INDEX CONCURRENTLY`).

## Result objects

| Type | Fields |
|---|---|
| `MigrationPlan` | `version`, `direction: Direction`, `description` |
| `ExecutionResult` | `version`, `direction: Direction`, `duration` in seconds |
| `AvailableMigration` | `version`, `description`, `down_versions`, `path`, `is_head` |
| `ExecutedMigration` | the recorded row: its version and when it ran |
| `MigrationStatus` | `current`, `latest`, `previous`, `next`, `available`, `executed`, `new`, `executed_unavailable`, `is_up_to_date` |

`Direction` is an `Enum` with `Direction.UP` and `Direction.DOWN`.
