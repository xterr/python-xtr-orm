<div align="center">

# xtr-orm

**Databases for async applications: engines, sessions and versioned schema migrations, configured once per connection.**

<img alt="python 3.11+" src="https://img.shields.io/badge/python-%E2%89%A5%203.11-3776AB?logo=python&logoColor=white">
<img alt="typed" src="https://img.shields.io/badge/typed-ty%20%2B%20basedpyright-1f6feb">
<img alt="license MIT" src="https://img.shields.io/badge/license-MIT-blue">

</div>

---

## Why?

An application with a database needs the same things every time: an engine per database, a
session per request or message, a way to change the schema one reviewed step at a time, and
commands to run those steps from a deploy script. Each is a few dozen lines of glue, written
again in every project.

This package is that glue, done once. You describe each connection — a URL, its replicas,
its engine and session options, where its revisions live — and get:

- 🔌 **Engines and sessions** built from one configuration, on
  [SQLAlchemy](https://www.sqlalchemy.org/)'s async API and
  [advanced-alchemy](https://advanced-alchemy.litestar.dev/)'s models, repositories and
  services.
- 📖 **Read replicas** — reads go to a replica, writes and everything after them to the
  primary.
- 🧬 **Versioned migrations** on [Alembic](https://alembic.sqlalchemy.org/): diffed from your
  models, run up or down to any revision, one at a time or all at once — with no `env.py` and
  no `alembic.ini` to maintain.
- 📜 **A full history**: every revision applied, when, and how long it took.
- 🧾 **One transaction per message** — with [xtr-messenger](../xtr-messenger), every handler of
  a message shares one session, committed once they all succeeded and rolled back otherwise.
- 🛠️ **Fifteen console commands**, from `orm:database:create` to `orm:migrations:up-to-date`.

## Install

```sh
uv add "xtr-orm[postgres]"                        # asyncpg
uv add "xtr-orm[di,console,messenger,sqlite]"     # everything, on SQLite
```

| Extra | Brings | For |
|---|---|---|
| `postgres` / `mysql` / `sqlite` | `asyncpg` / `asyncmy` / `aiosqlite` | The async driver of your database |
| `di` | `xtr-dependency-injection` | The `OrmBundle`: engines, sessions, migrators from one configuration |
| `console` | `xtr-console` | The `orm:*` commands |
| `messenger` | `xtr-messenger` | The [message bus middleware](#message-bus-middleware) |

## Quick start

Without a container, a `Migrator` runs one database's revisions:

```python
from sqlalchemy.ext.asyncio import create_async_engine
from xtr_orm import Migrator, MigrationsConfig

from app.models import Base

engine = create_async_engine("postgresql+asyncpg://app:secret@db/shop")
migrator = Migrator(engine, MigrationsConfig(directory="migrations"), Base.metadata)

await migrator.diff("add the catalogue")  # writes migrations/<date>_<rev>_add_the_catalogue.py
await migrator.migrate()  # runs every revision not applied yet
status = await migrator.status()
```

## Migrations

Revisions are ordinary migration files, one per change, in the connection's migrations
directory. The package writes them from its own template and runs them itself, handing the
migration runner the live connection and your table definitions directly — there is no
start-up script to keep in step with your models.

The database keeps two tables, in the same schema:

- the **version table** (`alembic_version`) holds the revisions the database is *at*. It
  decides what a migration runs.
- the **history table** (`alembic_version_history`) holds a row per revision ever applied —
  `version`, `executed_at`, `execution_time` in milliseconds. Each row is written by the step
  that applies its revision, in the same transaction, so the two agree. It is what lets a
  report name every applied revision, including one whose file is gone.

A **target** — for `migrate` and `plan` — is a revision (a full or partial id), a relative
one (`+1`, `-2`, `ae10+1`), or `latest`, `first` (before every revision), `next`, `prev` or
`current`. A revision already applied is migrated *down* to; one that is not, *up* to.

| `Migrator` method | Does |
|---|---|
| `status()` | Where the database stands: current, latest, previous, next, available, executed, new, and executed but without a file |
| `plan(target)` / `migrate(target)` / `migrate_sql(target)` | What reaching a target runs / run it / the SQL it would run, recording included |
| `plan_for_versions(versions, direction)` / `execute(...)` / `execute_sql(...)` | What running exactly those revisions, each up or down, runs — every id resolved and checked / run them, nothing before or after / the SQL it would run |
| `generate(message)` | Write an empty revision after the latest |
| `diff(message, allow_empty=, from_empty_schema=)` | Write what differs between the database and the table definitions |
| `dump_schema(message, table_filters=)` | Write a first revision creating every table an existing database has |
| `add_versions(versions)` / `add_all_versions()` | Record revisions as applied, running nothing |
| `delete_versions(versions)` / `delete_all_versions()` | Record revisions as not applied, running nothing |
| `rollup()` | Forget every applied revision, then record the single remaining one |

**Running one revision alone.** The version table holds only where the database *is*, so a
revision can be run — or recorded — on its own only where that stays true: going up, it must
not be applied and must follow only applied revisions; going down, it must be applied and
followed by none that is. Several versions are checked in turn, so a revision and the one
after it can go together. Anything else is refused before the database is touched.

**Up to date** means every revision with a file is applied — the database's versions against
the files, not its schema against your models; `diff` compares those.

`MigrationsConfig`:

| Field | Default | Meaning |
|---|---|---|
| `directory` | `"migrations"` | Where revision files are read and written |
| `version_table` / `history_table` | `"alembic_version"` / `"alembic_version_history"` | The two tables |
| `version_table_schema` | `None` | Their schema; the connection's default when `None` |
| `file_template` | `"{year}{month}{day}{hour}{minute}{second}_{rev}_{slug}"` | How a file is named; also `{epoch}` |
| `truncate_slug_length` / `timezone` | `40` / `None` | The longest message part of a name / the zone of a revision's date |
| `template_directory` | `None` | A directory with a `script.py.mako` to render new revisions from |
| `recursive_version_locations` | `False` | Read subdirectories of `directory` too |
| `post_write_hooks` | `()` | Programs run on each file written, such as a formatter |
| `transaction_per_migration` / `transactional_ddl` | `False` / `None` | Commit after each revision / run schema changes in the transaction |
| `compare_type` / `compare_server_default` | `False` / `False` | What a diff compares besides tables, columns, indexes and constraints |
| `render_as_batch` | `False` | Write table changes as batches, which SQLite needs |
| `include_schemas` / `include_name` / `include_object` | `False` / `None` / `None` | What a diff reads |
| `render_item` / `process_revision_directives` / `user_module_prefix` | `None` | How a diff is written |
| `context_options` | `{}` | Any other migration context option, passed as it is |

A custom column type is written under its own module's name, and the revision imports that
module — `advanced_alchemy.types.guid.GUID(length=16)` with `import advanced_alchemy.types.guid`;
set `user_module_prefix` or `render_item` to write it otherwise. `compare_type` is off by
default because a type the database stores as another — a UUID kept as bytes on SQLite — would
otherwise differ in every diff.

### Your own revision template

New revisions are rendered from `script.py.mako` — the package's own, or the one in
`template_directory`. It receives what Alembic's own templates do: `message`, `up_revision`,
`down_revision`, `branch_labels`, `depends_on`, `create_date`, `imports`, `upgrades`,
`downgrades`, and the `comma` filter (`${down_revision | comma,n}`). A template written for an
Alembic project works as it is; nothing but that file is read from the directory.

```python
MigrationsConfig(
    template_directory="%kernel.project_dir%/resources/migrations",
    user_module_prefix="sa.",  # a template aliasing sa.GUID = GUID, as advanced-alchemy's does
)
```

A template calling `op.get_context().autocommit_block()` commits a revision's schema changes
before the version and history tables are written, and gives up the transaction a failing
revision would roll back; set `transaction_per_migration=True` with it, and keep it for the
revisions that need it (`CREATE INDEX CONCURRENTLY`).

## Use in an application

Everything adding this package to an application on
[xtr-dependency-injection](../xtr-dependency-injection) takes — and, read backwards, what
removing it undoes.

- **Install** — `uv add "xtr-orm[di,console,postgres]"`; `mysql` or `sqlite` instead of
  `postgres` for those databases; drop `console` to go without the commands; add `messenger`
  for the [message bus middleware](#message-bus-middleware).
- **Activate** — `OrmBundle: {"all": True}` in `BUNDLES` in `<app>/bundles.py`, imported from
  `xtr_orm.bundle`.
- **Brings along** — the logging and console bundles, when those packages are installed.
  With the messenger bundle active too, the [middleware](#message-bus-middleware) are
  registered for a bus to list.
- **Configure** — optional: with no configuration there is one connection, `default`, reading
  `DATABASE_URL`, with its revisions in `migrations` in the project directory and diffs
  against the models advanced-alchemy registers. Connections, replicas and table definitions go
  in `<app>/config/orm.py`, a `@configure` function returning `OrmConfig` — see
  [Kernel / bundle](#kernel--bundle).
- **Environment** — `DATABASE_URL`, read when a connection is first used — engine, session,
  migrator or command — not when the application boots. Its query may carry options; see
  [Options in the URL](#options-in-the-url).
- **Ignore** — nothing: commit `migrations/`.
- **Remove** — take the `orm_*` entries out of every bus's `middleware`, drop the `BUNDLES`
  entry, delete `<app>/config/orm.py`, then `uv remove xtr-orm`.
- **Check** — `debug:bundles` shows `orm` as `listed` and `active`, and
  `orm:migrations:status` reaches the database.

## Kernel / bundle

```python
# app/bundles.py
from xtr_orm.bundle import OrmBundle

BUNDLES = {OrmBundle: {"all": True}}
```

```python
# app/config/orm.py
from xtr_dependency_injection import configure, env
from xtr_orm.bundle import ConnectionConfig, OrmConfig

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
            ),
            "reports": ConnectionConfig(url=env("REPORTS_URL"), bind_key="reports"),
        },
    )
```

For every connection, qualified by its name — and the default connection's without a
qualifier too:

| Service | What it is |
|---|---|
| `SQLAlchemyAsyncConfig` | advanced-alchemy's configuration, for its repositories and services |
| `AsyncEngine` | The engine on the primary database |
| `async_sessionmaker[AsyncSession]` | The session maker — `RoutingAsyncSessionMaker` instead for a connection with replicas |
| `AsyncSession` | One per unit of work — a request, a message, a command — closed, and rolled back if not committed, when the unit ends |
| `Migrator` / `DatabaseManager` | The connection's migrations / its database, both on the primary |
| `ConnectionRegistry` | Every connection by name, unqualified — what the commands use |

```python
from typing import Annotated

from sqlalchemy.ext.asyncio import AsyncSession
from xtr_dependency_injection import Injected, Target, as_service


@as_service
class InvoiceRepository:
    def __init__(self, session: Injected[AsyncSession]) -> None: ...


async def report(session: Annotated[AsyncSession, Target("reports")]) -> None: ...
```

Every engine is disposed when the container closes. With the logging bundle active, an `orm`
channel is added and every migrator logs each revision it runs there. With the messenger
bundle active, the [message bus middleware](#message-bus-middleware) are registered by name, and
every message is a unit of work: its handlers share one `AsyncSession` per connection.

| `OrmConfig` field | Default | Meaning |
|---|---|---|
| `default_connection` | `"default"` | The connection provided without a qualifier, and used by every command not given `--connection` |
| `connections` | `{"default": ConnectionConfig()}` | Every connection, by name |

| `ConnectionConfig` field | Default | Meaning |
|---|---|---|
| `url` | `"%env(DATABASE_URL)%"` | The database URL, with an async driver; its query may carry options — see below |
| `replicas` | `{}` | Read replicas, each a URL by name |
| `keep_replica` | `False` | Go back to the replicas once a session commits |
| `engine_options` | `{}` | `echo`, `pool_size`, `max_overflow`, `pool_pre_ping`, `pool_recycle`, `isolation_level`, `connect_args`, … |
| `session_options` | `{}` | `expire_on_commit`, `autoflush`, `info`, … |
| `alchemy_options` | `{}` | Any other option of advanced-alchemy's configuration, such as `enable_touch_updated_timestamp_listener` |
| `bind_key` | `None` | Which models belong to this database, when they declare several |
| `metadata` | `None` | The table definitions a diff compares with; advanced-alchemy's for `bind_key` when `None` |
| `migrations` | `None` | `MigrationsConfig`; `migrations` in the project directory for the default connection, `migrations/<name>` for any other, when `None` |

### Options in the URL

One environment variable can configure a whole connection. An engine or session option, or
`keep_replica`, is taken out of the URL's query and merged over the one configured — the URL
wins; every other option stays on the URL for the driver:

```sh
DATABASE_URL="postgresql+asyncpg://app:secret@db/shop?pool_size=20&expire_on_commit=false&ssl=require"
```

| Read from the URL | Options |
|---|---|
| Engine | `echo`, `echo_pool`, `enable_from_linting`, `hide_parameters`, `insertmanyvalues_page_size`, `isolation_level`, `label_length`, `logging_name`, `max_identifier_length`, `max_overflow`, `paramstyle`, `pool_logging_name`, `pool_pre_ping`, `pool_recycle`, `pool_size`, `pool_timeout`, `pool_use_lifo`, `query_cache_size`, `use_insertmanyvalues` |
| Session | `autobegin`, `autoflush`, `expire_on_commit`, `join_transaction_mode`, `twophase` |
| Connection | `keep_replica` |

Flags read `1`/`true`/`yes`/`on` and `0`/`false`/`no`/`off`; numbers are numbers; `echo` also
takes `debug`. A value that does not read fails the service that needed the URL, naming the
option. Only the connection's own URL is read this way, not its replicas'.

### Read replicas

With `replicas`, a session reads from a replica picked at random, and goes to the primary —
`url` — for a write, for a transaction's statements, and for every read after them, so it
sees what it wrote. It stays there for the rest of its unit of work, unless `keep_replica`
sends it back to the replicas once it commits. Each unit of work starts on the replicas,
whatever the one before wrote. Migrations and the database commands always use the primary.

A block can be sent elsewhere with advanced-alchemy's `primary_context()` and
`replica_context()`, from `advanced_alchemy.routing`.

## Console commands

Every command takes `--connection NAME`; the default connection's is used without it. The
commands that change the database ask first; `-n` answers yes.

| Command | Does |
|---|---|
| `orm:database:create [--if-not-exists]` | Creates the database, through the server's maintenance database |
| `orm:database:drop --force [--if-exists]` | Drops it; refused without `--force` |
| `orm:run-sql SQL [--force-fetch]` | Runs a statement, committed; shows its rows or how many it changed — when the driver can tell |
| `orm:migrations:current` | The revisions the database is at — `base` for none |
| `orm:migrations:latest` | The revisions no other follows |
| `orm:migrations:list` | Every revision with its status, when it ran and how long it took |
| `orm:migrations:status` | The tables, the database, previous / current / next / latest, and the counts |
| `orm:migrations:up-to-date [-u] [-l]` | Exits 1 with revisions not applied; 2 with `--fail-on-unregistered` and applied revisions without a file |
| `orm:migrations:migrate [TARGET] [--dry-run] [--write-sql PATH] [--allow-no-migration]` | Runs every revision to `TARGET`, `latest` by default |
| `orm:migrations:execute VERSION... [--up \| --down] [--dry-run] [--write-sql PATH]` | Runs exactly those revisions |
| `orm:migrations:generate [--message M]` | Writes an empty revision |
| `orm:migrations:diff [--message M] [--allow-empty-diff] [--from-empty-schema]` | Writes what the models add; the database must be up to date |
| `orm:migrations:dump-schema [--message M] [--filter-tables RE]...` | Writes a first revision from an existing database; `rollup` then records it |
| `orm:migrations:version [VERSION] (--add \| --delete) [--all]` | Records revisions as applied or not, running nothing |
| `orm:migrations:rollup` | Records the single remaining revision as all there is |

`--write-sql` writes to the file named, or to a dated file in the directory named.

Without a container, give the commands their connections once:

```python
from xtr_orm import ConnectionRegistry, DatabaseManager
from xtr_orm.command import use_connections

registry = ConnectionRegistry()
registry.register("default", engine=engine, migrator=migrator, database=DatabaseManager(url))
use_connections(registry)
```

## Message bus middleware

With the `messenger` extra and a kernel running both bundles, a message handler asks for a
session the way any service does, and three middleware — registered by name — decide what
happens to it. Nothing is added to a bus by itself: the bus lists the ones it wants.

```python
# app/billing/handlers.py
@as_message_handler(IssueInvoice)
async def issue(message: IssueInvoice, session: Injected[AsyncSession]) -> None:
    session.add(Invoice(order_id=message.order_id))  # no commit: orm_transaction does it


@as_message_handler(IssueInvoice)
class NotifyAccounting:
    # A scoped repository on the same session: one transaction for both handlers.
    async def __call__(
        self, message: IssueInvoice, invoices: Injected[InvoiceRepository]
    ) -> None: ...
```

```python
# app/config/messenger.py
MessageBusConfig(
    middleware=[
        "orm_close_connection",
        "orm_transaction",
        {"orm_transaction": {"connection_name": "reports"}},  # another connection too
        "orm_open_transaction_logger",
    ],
)
```

| Name | Class | Does | Arguments |
|---|---|---|---|
| `orm_transaction` | `TransactionMiddleware` | Runs every handler of a message in one transaction, committed once they all succeeded and rolled back otherwise; a failure drops the other handlers' handled stamps, so a retry runs them all again | `connection_name`, the default connection when left out |
| `orm_close_connection` | `CloseConnectionMiddleware` | Closes the connections once a worker handled a message it consumed, so an idle worker holds none — once the last, when it handles several at once | `connection_names`, every connection when left out |
| `orm_open_transaction_logger` | `OpenTransactionLoggerMiddleware` | Logs an error — to the application's logger when the logging bundle is active — when a handler began a transaction — `begin()`, `begin_nested()` — and left it open | `connection_names`, every connection when left out |

- **One session per message.** The messenger bundle makes every message a unit of work, and a
  scoped service — the session, a repository built on it — is the unit's: every handler of
  the message gets the same one, released once the message is done with. A message
  dispatched while another is handled joins its unit, and its transaction — in a savepoint of
  its own, so when it fails only its handlers' work is rolled back, and the handler that
  dispatched it decides whether the rest goes on.
- **Handlers do not commit** under `orm_transaction`; a handler that does ends the
  transaction early, and one using `async with session.begin()` is refused, the transaction
  being open already.
- **Order matters.** `orm_close_connection` outermost, so it closes after the transaction
  ended; `orm_open_transaction_logger` inside `orm_transaction`, so it looks before the
  commit closes everything.
- **Only messages a worker consumed are closed after** — one carrying a `ReceivedStamp` on
  arrival. A message handled during its dispatch, `sync://` included, closes nothing. A worker
  handling several at once closes once the last of them is done, keeping its pool meanwhile.
- **Follow-ups wait for the commit when stamped.** A message a handler dispatches to a
  transport is sent at once — before the commit, and whether or not it comes. Dispatch it
  with `DispatchAfterCurrentBusStamp` and it goes out only once the message being handled
  was committed, and never if it was rolled back:

  ```python
  await bus.dispatch(SendReceipt(order.id), DispatchAfterCurrentBusStamp())
  ```
- **A dropped connection** is found by the engine option `pool_pre_ping` as a connection is
  taken from the pool — `?pool_pre_ping=true` on a worker's URL — so there is no middleware
  for that.

Without a container, build them with a `ConnectionRegistry` whose connections are registered
with a `session` — what returns the session the handlers use — and put the instances in the
configuration.

## Creating and dropping databases

`DatabaseManager(url)` creates and drops the database a URL names. A database cannot be
created from a connection to itself, so the server is reached through its maintenance
database — `postgres` on PostgreSQL, `master` on SQL Server, none on MySQL and MariaDB — with
every statement committed as it runs, and with every connection parameter of the URL but its
database: the credentials, the host and the driver's query options, such as `ssl`. A SQLite
database is its file. Any other server is refused with `UnsupportedDatabaseError`.

## Errors

Every error derives from `OrmError`.

| Error | Raised when |
|---|---|
| `InvalidArgumentError` | A configuration cannot be used — an empty name, an unknown option, a URL option that does not read (also a `ValueError`) |
| `MigrationError` | A migration is refused or its revisions cannot be read — an unknown or ambiguous version, a revision out of order, a diff of a database behind its revisions |
| `UnknownConnectionError` | A connection is asked for by a name nothing registered (also a `LookupError`) |
| `UnsupportedDatabaseError` | A database is created or dropped on a server whose statements are not known |
| `SessionUnavailableError` | A connection's session is asked for outside a unit of work, or of a connection registered without one |

## Known limitations

- **advanced-alchemy's model registry is process-wide.** Its `metadata_registry` maps a
  `bind_key` to table definitions for the whole process, so two kernels in one process share
  it. Give a connection its `metadata` explicitly to keep a kernel's diff to its own models.
- **The version table holds only the current revisions**, so a revision is run or recorded
  alone only where the database stays consistent — see [Migrations](#migrations). The history
  table records every one.
- **Async only**: engines and sessions are async; there is no sync counterpart.

## Development

Developed in the [python-xtr](https://github.com/xterr/python-xtr) monorepo, under
`packages/xtr-orm`; run the commands below from there. Every test runs on SQLite files in the
test's own directory; no server is needed.

```sh
uv sync
uv run ruff check && uv run ruff format --check && uv run basedpyright && uv run ty check && uv run pytest
```

## License

MIT — see [LICENSE](LICENSE).
