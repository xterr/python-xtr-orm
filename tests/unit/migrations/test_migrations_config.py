"""Unit tests for :class:`xtr_orm.migrations.MigrationsConfig`."""

from __future__ import annotations

from dataclasses import replace

import pytest

from xtr_orm.exception import InvalidArgumentError
from xtr_orm.migrations import MigrationsConfig


def test_it_builds_with_no_arguments() -> None:
    config = MigrationsConfig()

    assert config.directory == "migrations"
    assert config.version_table == "alembic_version"
    assert config.history_table == "alembic_version_history"


@pytest.mark.parametrize("field", ["directory", "version_table", "history_table"])
def test_an_empty_name_is_refused(field: str) -> None:
    with pytest.raises(InvalidArgumentError, match=f'"{field}" must not be empty'):
        _ = replace(MigrationsConfig(), **{field: ""})


def test_the_two_tables_must_differ() -> None:
    with pytest.raises(InvalidArgumentError, match="must differ"):
        _ = MigrationsConfig(version_table="versions", history_table="versions")


def test_a_file_template_naming_an_unknown_field_is_refused() -> None:
    with pytest.raises(InvalidArgumentError, match=r'names "\{nope\}"'):
        _ = MigrationsConfig(file_template="{rev}_{nope}")


def test_a_file_template_must_tell_revisions_apart() -> None:
    with pytest.raises(InvalidArgumentError, match="must hold"):
        _ = MigrationsConfig(file_template="{slug}")


def test_a_slug_length_below_one_is_refused() -> None:
    with pytest.raises(InvalidArgumentError, match="at least 1"):
        _ = MigrationsConfig(truncate_slug_length=0)


def test_the_file_template_is_translated_for_the_revision_writer() -> None:
    config = MigrationsConfig(file_template="{year}{month}{day}_{rev}_100%_{slug}")

    assert config.alembic_file_template() == "%(year)d%(month).2d%(day).2d_%(rev)s_100%%_%(slug)s"


def test_the_default_file_template_sorts_by_time() -> None:
    assert MigrationsConfig().alembic_file_template() == (
        "%(year)d%(month).2d%(day).2d%(hour).2d%(minute).2d%(second).2d_%(rev)s_%(slug)s"
    )
