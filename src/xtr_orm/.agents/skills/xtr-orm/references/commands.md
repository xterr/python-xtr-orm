# The `orm:*` console commands

Needs the `console` extra: `uv add "xtr-orm[console]"`. With a container, the bundle declares them
when the console bundle is active, and each acts on the connections the bundle registered.

Every command takes `--connection NAME`; the default connection is used without it. The ones that
change the database ask first, and `-n` answers yes. `--message` names the revision and its file.

## The database

| Command | Flags |
|---|---|
| `orm:database:create` | `--if-not-exists` — do nothing, successfully, when it exists |
| `orm:database:drop` | `--force` / `-f` — required, the confirmation that everything may be lost; `--if-exists` |
| `orm:run-sql SQL` | `--force-fetch` — show rows even when the statement does not look like it returns any. The statement is committed |

## Reading where the database stands

| Command | Shows |
|---|---|
| `orm:migrations:current` | The revisions the version table holds; `base` for none |
| `orm:migrations:latest` | The revisions no other follows |
| `orm:migrations:list` | Every revision with its status, when it ran and how long it took |
| `orm:migrations:status` | The two tables, the database, previous / current / next / latest, and the counts |
| `orm:migrations:up-to-date` | Exits 1 with revisions not applied. `--fail-on-unregistered` / `-u` exits 2 for applied revisions whose file is gone; `--list-migrations` / `-l` names them |

`up-to-date` is the deploy check: it compares the database's versions with the revision files, not
its schema with your models.

## Running revisions

| Command | Flags |
|---|---|
| `orm:migrations:migrate [VERSION]` | `VERSION` defaults to `latest`; also a full or partial id, a relative one (`+1`, `-2`), `first`, `next`, `prev`, `current`. `--dry-run` reports the plan; `--write-sql PATH` writes the SQL instead of running it; `--allow-no-migration` succeeds when there is nothing to run |
| `orm:migrations:execute VERSION...` | `--up` (the default) or `--down`; `--dry-run`; `--write-sql PATH`. Runs exactly those revisions and nothing before or after. Going up each must not be applied and must follow only applied ones; going down each must be applied and be followed by none that is |

`--write-sql` writes to the file named, or to a dated file in the directory named.

## Writing revisions

| Command | Flags |
|---|---|
| `orm:migrations:generate` | `--message M`. An empty revision after the latest, to fill in by hand |
| `orm:migrations:diff` | `--message M`; `--allow-empty-diff` writes a revision even when nothing differs; `--from-empty-schema` writes every table as if the database were empty. The database must be at the latest revisions first |
| `orm:migrations:dump-schema` | `--message M`; `--filter-tables RE`, repeatable, dumps only the tables whose name the expression finds. For a database that predates its revisions, so there must be none yet. Written, not applied — follow with `orm:migrations:rollup` |

## Recording without running

| Command | Flags |
|---|---|
| `orm:migrations:version [VERSION]` | Exactly one of `--add` / `--delete`; `--all` for every revision instead of one. Adding, the revision must follow only applied ones; deleting, no applied revision may follow it. An applied revision whose file is gone can always be deleted |
| `orm:migrations:rollup` | Forgets every applied revision, then records the single remaining one as all there is |

## Without a container

```python
from xtr_orm import ConnectionRegistry, DatabaseManager
from xtr_orm.command import use_connections

registry = ConnectionRegistry()
registry.register("default", engine=engine, migrator=migrator, database=DatabaseManager(url))
use_connections(registry)
```

The command classes are exported from `xtr_orm.command` — `MigrationsMigrateCommand`,
`MigrationsDiffCommand`, `DatabaseCreateCommand` and the rest — for a console application to
register itself.
