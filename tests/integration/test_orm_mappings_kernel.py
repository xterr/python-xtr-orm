"""The tables a library bundle maps are the ones the connection's next revision creates."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Final

import pytest
from advanced_alchemy.base import metadata_registry
from xtr_dependency_injection import Kernel

from tests.fixtures.app_orm_mappings.config import BIND_KEY
from tests.fixtures.app_orm_mappings_off.config import BIND_KEY as OFF_BIND_KEY
from tests.fixtures.orm_mappings_bundle import TABLES
from xtr_orm import Migrator

if TYPE_CHECKING:
    from xtr_orm import AvailableMigration

pytestmark = pytest.mark.anyio

_PERSISTING: Final = "tests.fixtures.app_orm_mappings"
_OFF: Final = "tests.fixtures.app_orm_mappings_off"


def _kernel(package: str, root: Path) -> Kernel:
    root.mkdir(parents=True, exist_ok=True)
    return Kernel(
        package,
        env="test",
        environ={
            "ORM_TEST_URL": f"sqlite+aiosqlite:///{root / 'app.sqlite'}",
            "ORM_TEST_MIGRATIONS": str(root / "migrations"),
        },
    )


async def _diff(package: str, root: Path) -> AvailableMigration | None:
    """Return the revision a kernel of ``package`` rooted at ``root`` writes, if any."""
    async with await _kernel(package, root).boot() as booted:
        return await (await booted.container.get(Migrator)).diff("the toy tables")


async def _body(root: Path) -> str:
    """Return the revision the persisting kernel writes for its library's tables."""
    written = await _diff(_PERSISTING, root)
    assert written is not None
    return Path(written.path).read_text(encoding="utf-8")


async def test_a_diff_creates_every_table_the_library_mapped(tmp_path: Path) -> None:
    body = await _body(tmp_path)

    for table in TABLES:
        assert f"op.create_table({table!r}" in body


async def test_a_second_kernel_in_the_same_process_maps_the_tables_once(tmp_path: Path) -> None:
    async with await _kernel(_PERSISTING, tmp_path / "first").boot():
        pass

    body = await _body(tmp_path / "second")

    assert body.count("op.create_table(") == len(TABLES)
    assert sorted(metadata_registry.get(BIND_KEY).tables) == sorted(TABLES)


async def test_persistence_off_on_a_bind_key_of_its_own_writes_no_tables(tmp_path: Path) -> None:
    async with await _kernel(_PERSISTING, tmp_path / "persisting").boot():
        pass
    assert sorted(metadata_registry.get(BIND_KEY).tables) == sorted(TABLES)

    written = await _diff(_OFF, tmp_path / "off")

    assert written is None
    assert not metadata_registry.get(OFF_BIND_KEY).tables
