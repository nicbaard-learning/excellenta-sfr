"""Add frameworks.fdi and controls.legacy_scf_ids for SCF release upgrades.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-19

"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    # app.schema_upgrade may already have added these at startup.
    if "fdi" not in {c["name"] for c in inspector.get_columns("frameworks")}:
        op.add_column("frameworks", sa.Column("fdi", sa.String(255), nullable=True))
    if "legacy_scf_ids" not in {c["name"] for c in inspector.get_columns("controls")}:
        op.add_column("controls", sa.Column("legacy_scf_ids", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("controls", "legacy_scf_ids")
    op.drop_column("frameworks", "fdi")
