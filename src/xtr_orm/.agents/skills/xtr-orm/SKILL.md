---
name: xtr-orm
description: How to configure database connections, inject async sessions and run versioned schema migrations with xtr-orm. Use when application code needs an AsyncEngine, an AsyncSession, a session per request or per message, read replicas, a DATABASE_URL, a new migration revision, a schema diff against models, the orm:migrations:* or orm:database:* console commands, one transaction per message on a bus, or when adding OrmBundle to an application on xtr-dependency-injection.
---

# xtr-orm

A connection is configuration. You name each database once — URL, replicas, engine and session
options, where its revisions live — and the bundle hands out the engine, the session maker, the
session of the current unit of work, a `Migrator` and a `DatabaseManager`, each qualified by the
connection's name. Everything is async; there is no sync counterpart.

## Quick reference

- Inject `Injected[AsyncSession]` for the default connection;
  `Annotated[AsyncSession, Target("reports")]` for another. Never build a session yourself.
- Name databases in `<app>/config/orm.py` with a `@configure` function returning `OrmConfig`.
- Set `DATABASE_URL` with an async driver: `postgresql+asyncpg://`, `mysql+asyncmy://`,
  `sqlite+aiosqlite:///`. Engine and session options may ride on its query.
- Write a revision from your models: `orm:migrations:diff --message "add invoices"`. Apply:
  `orm:migrations:migrate`. Read it: `orm:migrations:status`.
- Without a container: `Migrator(engine, MigrationsConfig(directory="migrations"), Base.metadata)`.
- One transaction per message: list `orm_transaction` in the bus's `middleware`; handlers never
  commit.
- On SQLite, set `MigrationsConfig(render_as_batch=True)` or table alterations cannot be written.

## Inject a session

```python
from typing import Annotated

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from xtr_dependency_injection import Injected, Target, as_service


@as_service
class InvoiceRepository:
    def __init__(self, session: Injected[AsyncSession]) -> None:
        self._session = session


async def report(
    session: Annotated[AsyncSession, Target("reports")],
    engine: Annotated[AsyncEngine, Target("reports")],
) -> None: ...
```

Per connection, qualified by name — and unqualified for the default one:

| Service | What it is |
|---|---|
| `AsyncSession` | The session of the current unit of work: a request, a message, a command. Closed, and rolled back when not committed, as the unit ends |
| `AsyncEngine` | The engine on the primary database. Disposed when the container closes |
| `async_sessionmaker[AsyncSession]` | The session maker; `RoutingAsyncSessionMaker` when the connection has replicas |
| `SQLAlchemyAsyncConfig` | advanced-alchemy's configuration, for its repositories and services |
| `Migrator` / `DatabaseManager` | The connection's revisions / its database, both on the primary |
| `ConnectionRegistry` | Every connection by name, unqualified — what the commands use |

A session is scoped to the unit of work: asking for one outside any raises
`SessionUnavailableError`. Do not cache a session on a singleton.

## Migrations

`Migrator` is the whole surface. Every method opens its own connection; `generate` reads files
only.

| Call | Does |
|---|---|
| `await migrator.status()` | `current`, `latest`, `previous`, `next`, `available`, `executed`, `new`, `executed_unavailable`, `is_up_to_date` |
| `await migrator.migrate(target)` | Runs every revision to `target`; returns `ExecutionResult`s. `plan(target)` plans it, `migrate_sql(target)` writes the SQL |
| `await migrator.execute(versions, Direction.UP)` | Exactly those revisions, nothing before or after. `plan_for_versions(versions, direction)` and `execute_sql(...)` alongside |
| `migrator.generate("message")` | Writes an empty revision after the latest (not awaited) |
| `await migrator.diff("message")` | Writes what the table definitions add; takes `allow_empty=`, `from_empty_schema=` |
| `await migrator.dump_schema("message", table_filters=...)` | A first revision creating every table an existing database has |
| `await migrator.add_versions(v)` / `add_all_versions()` | Records revisions as applied, running nothing |
| `await migrator.delete_versions(v)` / `delete_all_versions()` | Records them as not applied |
| `await migrator.rollup()` | Forgets every applied revision, then records the single remaining one |

A **target** is a revision id (full or partial), a relative one (`+1`, `-2`, `ae10+1`), or
`latest`, `first`, `next`, `prev`, `current`. A revision already applied is migrated *down* to.

Two tables, in one schema: `alembic_version` holds where the database **is** and decides what a
migration runs; `alembic_version_history` holds a row per revision ever applied, with
`executed_at` and `execution_time` in milliseconds.

`execute` is refused before touching the database unless the version table stays truthful: going
up a revision must not be applied and must follow only applied ones; going down it must be applied
and followed by none that is. **Up to date** compares the database's versions with the revision
files, not its schema with your models; `diff` does the latter.

Without a container:

```python
from sqlalchemy.ext.asyncio import create_async_engine
from xtr_orm import MigrationsConfig, Migrator

from app.models import Base

engine = create_async_engine("sqlite+aiosqlite:///shop.db")
migrator = Migrator(
    engine,
    MigrationsConfig(directory="migrations", render_as_batch=True),
    Base.metadata,
)

revision = await migrator.diff("add invoices")  # AvailableMigration, or None with nothing to do
await migrator.migrate()
```

`MigrationsConfig` fields you reach for most: `directory` (relative to the working directory —
under a kernel start it with `%kernel.project_dir%`), `render_as_batch` (SQLite),
`compare_type` / `compare_server_default` (off by default), `version_table` / `history_table`,
`file_template`, `post_write_hooks` (a formatter), `transaction_per_migration`,
`template_directory`, `user_module_prefix`. See [references/migrations.md](references/migrations.md)
for every field and for writing your own `script.py.mako`.

## Console commands

Needs the `console` extra. Every command takes `--connection NAME`, defaulting to
`OrmConfig.default_connection`. The ones that change the database ask first; `-n` answers yes.

| Command | Does |
|---|---|
| `orm:migrations:diff [--message M]` | Writes what the models add; the database must be up to date first |
| `orm:migrations:migrate [VERSION]` | Runs every revision to `VERSION`, `latest` by default |
| `orm:migrations:status` / `:list` / `:current` / `:latest` | Where the database stands |
| `orm:migrations:up-to-date` | Exits non-zero when revisions are not applied — for a deploy check |
| `orm:database:create` / `:drop --force` | The database itself |
| `orm:run-sql SQL` | Runs one statement, committed |

Nine more, and every flag: [references/commands.md](references/commands.md).

Deploy order: `orm:migrations:migrate` from **one** place, before the application starts —
migrations take no lock.

Without a container, hand the commands their connections once:

```python
from xtr_orm import ConnectionRegistry, DatabaseManager
from xtr_orm.command import use_connections

registry = ConnectionRegistry()
registry.register("default", engine=engine, migrator=migrator, database=DatabaseManager(url))
use_connections(registry)
```

## Use in an application

1. **Install** — `uv add "xtr-orm[di,console,postgres]"`; `mysql` or `sqlite` instead of
   `postgres`; drop `console` to go without the commands; add `messenger` for the bus middleware.
2. **Activate** — `OrmBundle: {"all": True}` in `BUNDLES` in `<app>/bundles.py`
   (`from xtr_orm.bundle import OrmBundle`).
3. **Brings along** — the logging and console bundles when those packages are installed, each
   optional. With the logging bundle active an `orm` channel is added and every migrator logs the
   revisions it runs there.
4. **Configure** — optional. With no configuration there is one connection, `default`, reading
   `DATABASE_URL`, revisions in `migrations` in the project directory, diffing against the models
   advanced-alchemy registers.

   ```python
   # <app>/config/orm.py
   from xtr_dependency_injection import configure, env
   from xtr_orm.bundle import ConnectionConfig, MigrationsConfig, OrmConfig

   from app.models import Base


   @configure
   def orm() -> OrmConfig:
       return OrmConfig(
           connections={
               "default": ConnectionConfig(
                   url=env("DATABASE_URL"),
                   replicas={"replica1": env("DATABASE_REPLICA_URL")},
                   engine_options={"pool_size": 10, "pool_pre_ping": True},
                   session_options={"expire_on_commit": False},
                   metadata=Base.metadata,
                   migrations=MigrationsConfig(directory="%kernel.project_dir%/migrations"),
               ),
               "reports": ConnectionConfig(url=env("REPORTS_URL"), bind_key="reports"),
           },
       )
   ```

5. **Environment** — `DATABASE_URL`, read when a connection is first used (engine, session,
   migrator or command), not at boot. Its query may carry options — see
   [references/connections.md](references/connections.md).
6. **Use** — inject `AsyncSession`; run `orm:migrations:*` from the console.
7. **Ignore** — nothing: commit `migrations/`.
8. **Check** — `debug:bundles` shows `orm` as `listed` and `active`, and
   `orm:migrations:status` reaches the database.
9. **Remove** — take the `orm_*` entries out of every bus's `middleware`, drop the `BUNDLES`
   entry, delete `<app>/config/orm.py`, then `uv remove xtr-orm`.

`OrmConfig` has two fields: `default_connection` (`"default"`) and `connections`
(`{"default": ConnectionConfig()}`). Two connections may not keep their revisions in one
directory; a non-default connection defaults to `%kernel.project_dir%/migrations/<name>`. Every
`ConnectionConfig` field, replicas and URL options: [references/connections.md](references/connections.md).

## One transaction per message

With the `messenger` extra and both bundles active, three middleware are registered by name.
Nothing is added to a bus by itself — the bus lists what it wants, and order matters.

```python
# <app>/config/messenger.py
MessageBusConfig(
    middleware=[
        "orm_close_connection",  # outermost: closes after the transaction ended
        "orm_transaction",
        {"orm_transaction": {"connection_name": "reports"}},
        "orm_open_transaction_logger",  # inside orm_transaction
    ],
)
```

| Name | Class | Arguments |
|---|---|---|
| `orm_transaction` | `TransactionMiddleware` | `connection_name`, the default connection when left out |
| `orm_close_connection` | `CloseConnectionMiddleware` | `connection_names`, every connection in use when left out |
| `orm_open_transaction_logger` | `OpenTransactionLoggerMiddleware` | `connection_names`, as above |

A handler asks for `Injected[AsyncSession]` like any service and adds rows; it never commits.

- Every handler of a message shares one session per connection. A message dispatched while
  another is handled joins its unit of work, in a savepoint of its own.
- A follow-up dispatched to a transport goes out at once unless stamped:
  `await bus.dispatch(SendReceipt(order.id), DispatchAfterCurrentBusStamp())` sends it only after
  the commit, and never after a rollback.
- Only a message a worker consumed closes connections afterwards; `sync://` closes nothing.
- Find a dropped connection with the engine option `pool_pre_ping`, not a middleware.

More, including building the middleware without a container:
[references/messenger.md](references/messenger.md).

## Creating and dropping a database

```python
from xtr_orm import DatabaseManager

database = DatabaseManager("postgresql+asyncpg://app:secret@db/shop")
await database.exists()
await database.create(if_not_exists=True)  # True when it created one
await database.drop(if_exists=True)
database.backend, database.database, database.safe_url  # properties
```

The server is reached through its maintenance database — `postgres`, `master`, none on MySQL and
MariaDB — carrying every connection parameter of the URL but the database name. A SQLite database
is its file. Any other server raises `UnsupportedDatabaseError`.

## Errors

Every error derives from `OrmError`.

| Error | Raised when |
|---|---|
| `InvalidArgumentError` | A configuration cannot be used: an empty name, an unknown engine/session option, a URL option that does not read. Also a `ValueError` |
| `MigrationError` | A migration is refused or revisions cannot be read: an unknown or ambiguous version, a revision out of order, a diff of a database behind its revisions |
| `UnknownConnectionError` | A connection asked for by a name nothing registered. Also a `LookupError` |
| `UnsupportedDatabaseError` | A database created or dropped on a server whose statements are not known |
| `SessionUnavailableError` | A session asked for outside a unit of work, or of a connection registered without one |

## Do not

- Do not use a sync driver. `postgresql://` fails; write `postgresql+asyncpg://`.
- Do not commit in a handler under `orm_transaction`, and do not wrap one in
  `async with session.begin()` — the transaction is already open and it is refused.
- Do not build engines or sessions by hand in application code, and do not hold a session past its
  unit of work or store one on a singleton.
- Do not write an `env.py` or an `alembic.ini`; the package runs the revisions itself.
- Do not expect `up-to-date` to notice a model change — run `diff` — and do not run `diff` against
  a database behind its revisions; migrate first.
- Do not leave `render_as_batch` off on SQLite.
- Do not run `orm:migrations:migrate` from several processes at once; it takes no lock.
- Do not rely on advanced-alchemy's process-wide model registry when two kernels share one
  process: give each connection its `metadata`.
- Do not expect a timezone on `executed_at` outside PostgreSQL; it is naive elsewhere.
