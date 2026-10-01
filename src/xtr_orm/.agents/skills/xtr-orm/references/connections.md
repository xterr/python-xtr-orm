# ConnectionConfig, URL options and read replicas

`from xtr_orm.bundle import ConnectionConfig`. A frozen dataclass, buildable with no arguments.

| Field | Default | Meaning |
|---|---|---|
| `url` | `"%env(DATABASE_URL)%"` | The database URL, with an async driver. Its query may carry options — see below |
| `engine_options` | `{}` | `echo`, `pool_size`, `max_overflow`, `pool_pre_ping`, `pool_recycle`, `isolation_level`, `connect_args`, `execution_options`, … |
| `session_options` | `{}` | `expire_on_commit`, `autoflush`, `info`, … |
| `alchemy_options` | `{}` | Any other option of advanced-alchemy's configuration, such as `enable_touch_updated_timestamp_listener` |
| `replicas` | `{}` | Read replicas, each a URL by name |
| `keep_replica` | `False` | Go back to the replicas once a session commits |
| `bind_key` | `None` | Which table definitions belong to this database when models declare several |
| `metadata` | `None` | The table definitions a diff compares the database with; those registered for `bind_key` when `None` |
| `migrations` | `None` | A `MigrationsConfig`; `%kernel.project_dir%/migrations` for the default connection, `.../migrations/<name>` for any other, when `None` |

An unknown key in `engine_options`, `session_options` or `alchemy_options` raises
`InvalidArgumentError` at configuration time, naming the options that exist. Options the bundle
sets itself — `connection_string`, `engine_config`, `session_config`, `bind_key`, `metadata`,
`engine_instance`, `session_maker`, `alembic_config`, `create_engine_callable`,
`session_maker_class`, `routing_config` — are refused in `alchemy_options`.

An empty `url`, an empty replica name or an empty replica URL is refused too. The default
`"%env(DATABASE_URL)%"` is a placeholder resolved when the connection is first used, so a missing
variable fails that use, not the boot.

## Options in the URL

One environment variable can configure a whole connection. An engine option, a session option or
`keep_replica` is taken out of the query and merged over what the configuration set — **the URL
wins**. Every other query parameter stays on the URL for the driver.

```sh
DATABASE_URL="postgresql+asyncpg://app:secret@db/shop?pool_size=20&expire_on_commit=false&ssl=require"
```

| Read from the URL | Options |
|---|---|
| Engine | `echo`, `echo_pool`, `enable_from_linting`, `hide_parameters`, `insertmanyvalues_page_size`, `isolation_level`, `label_length`, `logging_name`, `max_identifier_length`, `max_overflow`, `paramstyle`, `pool_logging_name`, `pool_pre_ping`, `pool_recycle`, `pool_size`, `pool_timeout`, `pool_use_lifo`, `query_cache_size`, `use_insertmanyvalues` |
| Session | `autobegin`, `autoflush`, `expire_on_commit`, `join_transaction_mode`, `twophase` |
| Connection | `keep_replica` |

Flags read `1`/`true`/`yes`/`on` and `0`/`false`/`no`/`off`; numbers are numbers; `echo` and
`echo_pool` also take `debug`. A value that does not read raises `InvalidArgumentError` naming the
option, failing the service that needed the URL. Only the connection's own URL is read this way,
never a replica's.

## Read replicas

```python
ConnectionConfig(
    url=env("DATABASE_URL"),
    replicas={"replica1": env("DATABASE_REPLICA_URL"), "replica2": env("DATABASE_REPLICA2_URL")},
    keep_replica=False,
)
```

- A session reads from a replica picked at random.
- It goes to the primary for a write, for a transaction's statements, and for every read after
  them, so it sees what it wrote.
- It stays on the primary for the rest of its unit of work, unless `keep_replica=True` sends it
  back to the replicas once it commits.
- Each unit of work starts on the replicas, whatever the one before wrote.
- Migrations and the `orm:database:*` commands always use the primary.
- The injected session maker is a `RoutingAsyncSessionMaker` instead of an `async_sessionmaker`.
- Send one block elsewhere with `primary_context()` / `replica_context()` from
  `advanced_alchemy.routing`.

## Without a container

```python
from sqlalchemy.ext.asyncio import create_async_engine
from xtr_orm import ConnectionRegistry, DatabaseManager, MigrationsConfig, Migrator

url = "sqlite+aiosqlite:///shop.db"
engine = create_async_engine(url)

registry = ConnectionRegistry()  # ConnectionRegistry(default="primary") renames the default
registry.register(
    "default",
    engine=engine,
    migrator=Migrator(engine, MigrationsConfig(directory="migrations", render_as_batch=True)),
    database=DatabaseManager(url),
    session=None,  # an async callable returning the unit of work's session; the middleware need it
    close=None,  # an async callable; the engine is disposed when left out
    in_use=None,  # a callable; the connection always counts as in use when left out
)

await registry.engine()  # the default connection's
await registry.migrator("reports")
registry.names(), registry.in_use(), registry.has("reports"), registry.default
await registry.close()
```

Each of `engine`, `migrator` and `database` takes the object itself or an async function building
it, called only when that piece is first asked for. `DEFAULT_CONNECTION` (`"default"`) is exported
from `xtr_orm`.
