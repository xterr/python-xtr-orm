"""What the package advertises: its version, read once, and names that all resolve."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import cast

import xtr_orm

PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"


def test_the_version_it_reports_is_the_one_pyproject_declares() -> None:
    declared = cast(
        "str", tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]["version"]
    )

    assert xtr_orm.__version__ == declared


def test_the_version_is_read_rather_than_written_down_a_second_time() -> None:
    source = Path(xtr_orm.__file__).read_text(encoding="utf-8")

    assert f'"{xtr_orm.__version__}"' not in source


def test_everything_it_advertises_can_be_reached() -> None:
    assert [name for name in xtr_orm.__all__ if not hasattr(xtr_orm, name)] == []
