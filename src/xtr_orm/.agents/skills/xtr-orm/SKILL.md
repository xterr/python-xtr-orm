---
name: xtr-orm
description: How to configure database connections, inject async sessions and run versioned schema migrations with xtr-orm. Use when application code needs an AsyncEngine, an AsyncSession, a session per request or per message, read replicas, a DATABASE_URL, a new migration revision, a schema diff against models, the orm:migrations:* or orm:database:* console commands, one transaction per message on a bus, when a library bundle must add tables it builds in code to a connection's definitions, or when adding OrmBundle to an application on xtr-dependency-injection.
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
- In an application, with xtr-dependency-injection installed beside the package (it is not a
  dependency): activate `OrmBundle` and inject what it registers. Only `xtr_orm.bundle` needs the
  container.
- A library bringing its own tables registers an `OrmMappingsPass` from its bundle's `build`; its
  driver's `load_metadata` must be idempotent.
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

## Map tables from a bundle

For a library whose own tables an application configures — their prefix, which of them it keeps,
which column type an id gets — so they exist only once that configuration is read. Its bundle
keeps an `OrmMappingsPass`, registers it in `build`, and hands it the driver it builds in
`load_extension`; the pass loads the tables into the definitions the named connection's
migrations use, so `orm:migrations:diff` writes them like the application's own models.

```python
from typing import final

from sqlalchemy import Column, Integer, MetaData, Table
from typing_extensions import override
from xtr_dependency_injection import (
    Bundle,
    ContainerBuilder,
    ServiceConfigurator,
    as_bundle,
    required_bundle,
)
from xtr_orm import MappingDriverInterface
from xtr_orm.bundle import OrmBundle, OrmMappingsPass


@final
@required_bundle(OrmBundle)
@as_bundle("invoicing", config=InvoicingConfig)
class InvoicingBundle(Bundle[InvoicingConfig]):
    def __init__(self) -> None:
        self._mappings = OrmMappingsPass("invoicing.connection", "invoicing.persist")

    @override
    def build(self, builder: ContainerBuilder) -> None:
        builder.add_compiler_pass(self._mappings)

    @override
    def load_extension(
        self, config: InvoicingConfig, services: ServiceConfigurator, builder: ContainerBuilder
    ) -> None:
        builder.set_parameter("invoicing.connection", config.connection)
        builder.set_parameter("invoicing.persist", config.persist)
        if config.persist:
            self._mappings.set_driver(InvoicingDriver(config.table_prefix))


@final
class InvoicingDriver(MappingDriverInterface):
    def __init__(self, prefix: str) -> None:
        self._prefix = prefix

    def load_metadata(self, metadata: MetaData) -> tuple[str, ...]:
        name = f"{self._prefix}invoice"
        if name in metadata.tables:
            return ()
        _ = Table(name, metadata, Column("id", Integer, primary_key=True))
        return (name,)
```

A driver is anything satisfying `MappingDriverInterface`: `load_metadata(metadata)` adds its
tables and returns the names it added. Subclassing it has the type checker hold you to that call.

| Rule | What it means |
|---|---|
| Idempotent | Skip every name already in `metadata.tables` and leave it out of the return. The registered definitions are process-wide — one `MetaData` per bind key for the whole process — so a second kernel loads the same driver into the same one. It outlives the flag: a kernel built with persistence off maps nothing itself, yet still sees and diffs every table a persisting kernel of the same process put in that bind key, or in a module-level `MetaData` both reach. Give such a kernel a `bind_key`, or a freshly built `MetaData`, no persisting kernel used |
| Which definitions | The connection's `metadata` when it has one, else advanced-alchemy's for its `bind_key`. A connection keeping several sets is refused, naming it |
| On or off | The flag parameter is read for truth; unset means off. On with no driver, or a connection name nothing configured, fails the build with `InvalidArgumentError` |
| Plain values | Both parameters are read while compiling, before `%name%` is resolved and long before `env(...)` is — set them from the bundle's own resolved config. One still holding a `%name%` reference fails the build naming the parameter, as does a connection parameter holding something that is not a name at all: a name is never coerced out of it, a connection being allowed to be called `7` |
| Required peer | The bundle must declare `@required_bundle(OrmBundle)`; without it the pass cannot read the orm's configuration and the build fails with `UnknownConfigTypeError` |

## Console commands

Needs xtr-console installed beside the package. Every command takes `--connection NAME`,
defaulting to `OrmConfig.default_connection`. The ones that change the database ask first; `-n`
answers yes.

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

Every command takes the `ConnectionRegistry` it acts on as its one constructor argument. Nothing
stands in for it: a console with no container to supply it raises `MissingContainerError` naming
`connections`.

```python
from xtr_orm import ConnectionRegistry, DatabaseManager
from xtr_orm.command import MigrationsMigrateCommand

registry = ConnectionRegistry()
registry.register("default", engine=engine, migrator=migrator, database=DatabaseManager(url))

migrate = MigrationsMigrateCommand(registry)
```

## Use in an application

`uv run xtr-recipes recipes:sync` applies the recipe shipped with this package: it lists `OrmBundle`,
writes a starting `config/orm.py` with the `default` connection, and `DATABASE_URL` in `.env`. That
is the steps below a recipe can do; the middleware it prints for you to add.

1. **Install** — `uv add "xtr-orm[postgres]" xtr-dependency-injection`: the bundle needs the
   container installed beside it, never as an extra; `mysql` or `sqlite` instead of `postgres`.
   Install xtr-console beside it for the `orm:*` commands, and xtr-messenger for the bus
   middleware.
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

With xtr-messenger installed beside it and both bundles active, three middleware are registered
by name. Nothing is added to a bus by itself — the bus lists what it wants, and order matters.

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
is its file. Without `if_exists`, dropping a SQLite file that is not there raises
`MissingDatabaseError`. Any other server raises `UnsupportedDatabaseError`.

## Testing

Test against a SQLite file in the test's own directory: it is a real database, needs no server,
and goes away with `tmp_path`. Give a `Migrator` the engine, a `MigrationsConfig` pointing at a
directory of its own, and your table definitions.

```python
# tests/test_invoices.py
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from xtr_orm import DatabaseManager, MigrationsConfig, Migrator

from app.models import Base


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_the_schema_the_models_describe_is_migrated(tmp_path: Path) -> None:
    url = f"sqlite+aiosqlite:///{tmp_path / 'app.sqlite'}"
    assert await DatabaseManager(url).create()
    engine = create_async_engine(url)
    migrator = Migrator(
        engine,
        # render_as_batch: SQLite cannot alter a table any other way.
        MigrationsConfig(directory=str(tmp_path / "migrations"), render_as_batch=True),
        Base.metadata,
    )
    try:
        assert await migrator.diff("the catalogue") is not None
        _ = await migrator.migrate()

        assert (await migrator.status()).is_up_to_date
        async with engine.connect() as connection:
            _ = await connection.execute(text("select count(*) from invoice"))
    finally:
        await engine.dispose()
```

- **A command** takes a `ConnectionRegistry`, so build one for the test and hand it over:
  `MigrationsStatusCommand(registry)`. Register the connection with the engine, migrator and
  `DatabaseManager` the test made.
- **A unit of work** — the scope an `AsyncSession` lives in — is opened by
  `bind_callable(container, work, per_call_scope=True)` under a kernel; outside one, ask the
  registry for a session only where you registered one, or `SessionUnavailableError` says so.
- **Two kernels in one process** share advanced-alchemy's model registry, so give each
  connection its `metadata` rather than let a diff pick up another test's tables.
- **A mapping driver** needs no container: `driver.load_metadata(MetaData())` returns the names
  it added, and a second call on the same `MetaData` must return `()`. A kernel test asserting
  a library mapped nothing needs a bind key of its own, or an earlier kernel's tables are still
  in the one it diffs.
- **Dispose every engine you build**, in a fixture's teardown: an engine left open holds the
  SQLite file and warns when the loop closes.

## Errors

Every error derives from `OrmError`.

| Error | Raised when |
|---|---|
| `InvalidArgumentError` | A configuration cannot be used: an empty name, an unknown engine/session option, a URL option that does not read. Also a `ValueError` |
| `MigrationError` | A migration is refused or revisions cannot be read: an unknown or ambiguous version, a revision out of order, a diff of a database behind its revisions |
| `MissingDatabaseError` | A database dropped without `if_exists` is not there — a SQLite file that does not exist. Also a `FileNotFoundError` |
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
- Do not write a mapping driver that defines a table unconditionally: a `load_metadata` that
  does not skip what is already there fails the second kernel of the process.
- Do not read turning a library's persistence off as a clean slate: that kernel maps nothing of
  its own, but still sees and diffs the tables a persisting kernel of the same process left in
  the bind key — give it a `bind_key`, or a freshly built `MetaData`, no persisting kernel used.
- Do not expect a timezone on `executed_at` outside PostgreSQL; it is naive elsewhere.
