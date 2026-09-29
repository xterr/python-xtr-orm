"""How one database connection is built: its URL, engine, sessions and migrations."""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final

from advanced_alchemy.config import AsyncSessionConfig, EngineConfig, SQLAlchemyAsyncConfig
from sqlalchemy import MetaData, make_url

from xtr_orm.exception import InvalidArgumentError
from xtr_orm.migrations import MigrationsConfig

__all__ = ["ConnectionConfig"]

_SET_BY_THE_BUNDLE: Final = frozenset(
    {
        "connection_string",
        "engine_config",
        "session_config",
        "bind_key",
        "metadata",
        "engine_instance",
        "session_maker",
        "alembic_config",
        "create_engine_callable",
        "session_maker_class",
        "routing_config",
    },
)
"""Options of the database layer's own configuration that other fields here already set."""


_NOTHING: Final[frozenset[str]] = frozenset()


def _flag(value: str) -> bool:
    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    raise ValueError("a flag: true or false")


def _echo(value: str) -> bool | str:
    return "debug" if value.strip().lower() == "debug" else _flag(value)


def _number(value: str) -> int:
    try:
        return int(value)
    except ValueError:
        raise ValueError("a whole number") from None


def _seconds(value: str) -> float:
    try:
        return float(value)
    except ValueError:
        raise ValueError("a number") from None


def _text(value: str) -> str:
    return value


_ENGINE_URL_OPTIONS: Final[dict[str, Callable[[str], object]]] = {
    "echo": _echo,
    "echo_pool": _echo,
    "enable_from_linting": _flag,
    "hide_parameters": _flag,
    "insertmanyvalues_page_size": _number,
    "isolation_level": _text,
    "label_length": _number,
    "logging_name": _text,
    "max_identifier_length": _number,
    "max_overflow": _number,
    "paramstyle": _text,
    "pool_logging_name": _text,
    "pool_pre_ping": _flag,
    "pool_recycle": _number,
    "pool_size": _number,
    "pool_timeout": _seconds,
    "pool_use_lifo": _flag,
    "query_cache_size": _number,
    "use_insertmanyvalues": _flag,
}
"""Engine options a URL's query may carry, and how each is read."""

_SESSION_URL_OPTIONS: Final[dict[str, Callable[[str], object]]] = {
    "autobegin": _flag,
    "autoflush": _flag,
    "expire_on_commit": _flag,
    "join_transaction_mode": _text,
    "twophase": _flag,
}
"""Session options a URL's query may carry, and how each is read."""


def _no_options() -> dict[str, object]:
    return {}


def _no_replicas() -> dict[str, str]:
    return {}


@dataclass(frozen=True, slots=True)
class ConnectionConfig:
    """One database: where it is, its replicas, its engine and sessions, and its migrations.

    ```python
    ConnectionConfig(
        url=env("DATABASE_URL"),
        replicas={"replica1": env("DATABASE_REPLICA_URL")},
        engine_options={"pool_size": 10, "pool_pre_ping": True},
        session_options={"expire_on_commit": False},
        migrations=MigrationsConfig(
            directory="%kernel.project_dir%/migrations", render_as_batch=True
        ),
    )
    ```

    Options may ride on the URL too, which is how one environment variable
    configures a whole connection —
    ``postgresql+asyncpg://app@db/shop?pool_size=20&expire_on_commit=false&ssl=require``.
    An engine or session option, or ``keep_replica``, is taken out of the
    URL and merged over the one configured here: the URL wins. Every other
    option stays on the URL for the driver.

    Attributes:
        url: The database URL, with an async driver —
            ``postgresql+asyncpg://…``, ``sqlite+aiosqlite:///…``,
            ``mysql+asyncmy://…``. Read from ``DATABASE_URL`` by default, when
            the connection is first used.
        engine_options: Engine options — ``echo``, ``pool_size``,
            ``max_overflow``, ``pool_pre_ping``, ``pool_recycle``,
            ``isolation_level``, ``connect_args``, ``execution_options`` and
            every other the engine takes.
        session_options: Session options — ``expire_on_commit``,
            ``autoflush``, ``info`` and the rest.
        alchemy_options: Any other option of the database layer's own
            configuration, such as ``enable_touch_updated_timestamp_listener``.
        replicas: Read replicas of the database :attr:`url` names, each a URL
            by name. With any, a session reads from a replica picked at
            random, and goes to the primary — :attr:`url` — for a write, a
            transaction's statements, and every read after them. Migrations,
            and the create and drop commands, always use the primary.
        keep_replica: Go back to the replicas once a session commits, rather
            than read from the primary for the rest of its unit of work.
        bind_key: Which table definitions belong to this database when models
            declare several; ``None`` for the default ones.
        metadata: The table definitions a migration diff compares the
            database with; those registered for :attr:`bind_key` when
            ``None``.
        migrations: Where the revisions are and how they are recorded;
            ``migrations`` in the project directory for the default
            connection, ``migrations/<name>`` for any other, when ``None``.
    """

    url: str = "%env(DATABASE_URL)%"
    engine_options: Mapping[str, object] = field(default_factory=_no_options)
    session_options: Mapping[str, object] = field(default_factory=_no_options)
    alchemy_options: Mapping[str, object] = field(default_factory=_no_options)
    replicas: Mapping[str, str] = field(default_factory=_no_replicas)
    keep_replica: bool = False
    bind_key: str | None = None
    metadata: MetaData | Sequence[MetaData] | None = None
    migrations: MigrationsConfig | None = None

    def __post_init__(self) -> None:
        """Refuse an empty URL, or an option the engine, a session or the layer does not take.

        Raises:
            InvalidArgumentError: When the configuration cannot be used.
        """
        # Compared, not tested for truth: the URL may be an environment placeholder,
        # which refuses to decide anything before the variable is read.
        if self.url == "":
            raise InvalidArgumentError("A connection's URL must not be empty.")
        for name, url in self.replicas.items():
            if not isinstance(name, str) or not name:  # pyright: ignore[reportUnnecessaryIsInstance] -- configs are written by hand; the annotation is not enforced
                raise InvalidArgumentError(f"A replica needs a non-empty name, got {name!r}.")
            if url == "":
                raise InvalidArgumentError(f'The "{name}" replica\'s URL must not be empty.')
        _check_options("engine", EngineConfig, self.engine_options)
        _check_options("session", AsyncSessionConfig, self.session_options)
        _check_options(
            "alchemy", SQLAlchemyAsyncConfig, self.alchemy_options, exclude=_SET_BY_THE_BUNDLE
        )

    def with_url_options(self) -> ConnectionConfig:
        """Return this connection with the options its URL carries merged into it.

        Called once the URL is read — an environment variable is not until a
        service needs it — so a mistake in the URL fails that service.

        Raises:
            InvalidArgumentError: When an option's value cannot be read.
        """
        url = make_url(self.url)
        driver: dict[str, str | tuple[str, ...]] = {}
        engine = dict(self.engine_options)
        session = dict(self.session_options)
        keep_replica = self.keep_replica
        for name, given in url.query.items():
            value = given if isinstance(given, str) else given[-1]
            if name in _ENGINE_URL_OPTIONS:
                engine[name] = _read(name, value, _ENGINE_URL_OPTIONS[name])
            elif name in _SESSION_URL_OPTIONS:
                session[name] = _read(name, value, _SESSION_URL_OPTIONS[name])
            elif name == "keep_replica":
                keep_replica = bool(_read(name, value, _flag))
            else:
                driver[name] = given
        if len(driver) == len(url.query):
            return self
        return dataclasses.replace(
            self,
            url=url.set(query=driver).render_as_string(hide_password=False),
            engine_options=engine,
            session_options=session,
            keep_replica=keep_replica,
        )


def _read(name: str, value: str, reader: Callable[[str], object]) -> object:
    try:
        return reader(value)
    except ValueError as error:
        raise InvalidArgumentError(
            f'The URL option "{name}" must be {error}, got "{value}".',
        ) from error


def _check_options(
    kind: str,
    target: type[EngineConfig | AsyncSessionConfig | SQLAlchemyAsyncConfig],
    options: Mapping[str, object],
    *,
    exclude: frozenset[str] = _NOTHING,
) -> None:
    known = {each.name for each in dataclasses.fields(target) if each.init} - exclude
    for name in options:
        if name not in known:
            listed = ", ".join(sorted(known))
            raise InvalidArgumentError(
                f'Unknown {kind} option "{name}"; the {kind} options are: {listed}.',
            )
