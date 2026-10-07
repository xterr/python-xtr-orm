"""The ``orm:*`` console commands.

Importing this module declares them. With a container, the orm bundle loads
it when the console bundle is active, and every command acts on the
connections the bundle registered.

Every command takes that :class:`~xtr_orm.ConnectionRegistry` as its one
constructor argument, so a console application registering them itself builds
each with a registry of its own:

```python
from xtr_orm import ConnectionRegistry
from xtr_orm.command import MigrationsMigrateCommand

registry = ConnectionRegistry()
registry.register("default", engine=engine, migrator=migrator, database=database)
command = MigrationsMigrateCommand(registry)
```

Needs the ``console`` extra: ``xtr-orm[console]``.
"""

from __future__ import annotations

from .database_create_command import DatabaseCreateCommand
from .database_drop_command import DatabaseDropCommand
from .migrations_current_command import MigrationsCurrentCommand
from .migrations_diff_command import MigrationsDiffCommand
from .migrations_dump_schema_command import MigrationsDumpSchemaCommand
from .migrations_execute_command import MigrationsExecuteCommand
from .migrations_generate_command import MigrationsGenerateCommand
from .migrations_latest_command import MigrationsLatestCommand
from .migrations_list_command import MigrationsListCommand
from .migrations_migrate_command import MigrationsMigrateCommand
from .migrations_rollup_command import MigrationsRollupCommand
from .migrations_status_command import MigrationsStatusCommand
from .migrations_up_to_date_command import MigrationsUpToDateCommand
from .migrations_version_command import MigrationsVersionCommand
from .run_sql_command import RunSqlCommand

__all__ = [
    "DatabaseCreateCommand",
    "DatabaseDropCommand",
    "MigrationsCurrentCommand",
    "MigrationsDiffCommand",
    "MigrationsDumpSchemaCommand",
    "MigrationsExecuteCommand",
    "MigrationsGenerateCommand",
    "MigrationsLatestCommand",
    "MigrationsListCommand",
    "MigrationsMigrateCommand",
    "MigrationsRollupCommand",
    "MigrationsStatusCommand",
    "MigrationsUpToDateCommand",
    "MigrationsVersionCommand",
    "RunSqlCommand",
]
