"""Revision files written by hand, for histories a single chain of generated ones cannot make."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def write_revision(
    directory: Path,
    version: str,
    down: str | tuple[str, ...] | None = None,
    *,
    table: str | None = None,
    message: str | None = None,
    depends_on: str | None = None,
) -> Path:
    """Write revision ``version`` following ``down``, creating ``table`` — and dropping it again.

    Without a table the revision changes nothing, which is all a test of the
    version bookkeeping needs.
    """
    directory.mkdir(parents=True, exist_ok=True)
    upgrade = (
        f"op.create_table({table!r}, sa.Column('id', sa.Integer(), primary_key=True))"
        if table
        else "pass"
    )
    downgrade = f"op.drop_table({table!r})" if table else "pass"
    path = directory / f"{version}.py"
    _ = path.write_text(
        f'''"""{message or f"revision {version}"}"""

import sqlalchemy as sa
from alembic import op

revision = {version!r}
down_revision = {down!r}
branch_labels = None
depends_on = {depends_on!r}


def upgrade():
    {upgrade}


def downgrade():
    {downgrade}
''',
        encoding="utf-8",
    )
    return path
