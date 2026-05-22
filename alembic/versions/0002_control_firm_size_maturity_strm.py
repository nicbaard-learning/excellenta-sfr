"""Add firm-size, maturity, STRM type, and GitHub tracking columns.

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-21
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── controls: new columns ─────────────────────────────────────
    with op.batch_alter_table("controls") as batch_op:
        batch_op.add_column(sa.Column("relative_weight", sa.Integer(), nullable=True, comment="Relative weight integer value"))
        batch_op.add_column(sa.Column("pptdf_applicability", sa.String(255), nullable=True, comment="PPTDF Applicability classification"))
        # Firm-size solutions
        batch_op.add_column(sa.Column("solutions_micro_small", sa.Text(), nullable=True, comment="Solutions for Micro-Small organizations"))
        batch_op.add_column(sa.Column("solutions_small", sa.Text(), nullable=True, comment="Solutions for Small organizations"))
        batch_op.add_column(sa.Column("solutions_medium", sa.Text(), nullable=True, comment="Solutions for Medium organizations"))
        batch_op.add_column(sa.Column("solutions_large", sa.Text(), nullable=True, comment="Solutions for Large organizations"))
        batch_op.add_column(sa.Column("solutions_enterprise", sa.Text(), nullable=True, comment="Solutions for Enterprise organizations"))
        # SCR-CMM Maturity levels
        batch_op.add_column(sa.Column("cmm_level_0", sa.Text(), nullable=True, comment="SCR-CMM Level 0 - Incomplete"))
        batch_op.add_column(sa.Column("cmm_level_1", sa.Text(), nullable=True, comment="SCR-CMM Level 1 - Performed"))
        batch_op.add_column(sa.Column("cmm_level_2", sa.Text(), nullable=True, comment="SCR-CMM Level 2 - Managed"))
        batch_op.add_column(sa.Column("cmm_level_3", sa.Text(), nullable=True, comment="SCR-CMM Level 3 - Defined"))
        batch_op.add_column(sa.Column("cmm_level_4", sa.Text(), nullable=True, comment="SCR-CMM Level 4 - Quantitatively Managed"))
        batch_op.add_column(sa.Column("cmm_level_5", sa.Text(), nullable=True, comment="SCR-CMM Level 5 - Optimizing"))

    # ── control_mappings: strm_type column ────────────────────────
    with op.batch_alter_table("control_mappings") as batch_op:
        batch_op.add_column(sa.Column(
            "strm_type", sa.String(50), nullable=True,
            comment="Set Theory Relationship Mapping type: EQUAL, SUBSET OF, SUPERSET OF, INTERSECTS WITH"
        ))

    # ── import_runs: GitHub tracking columns ──────────────────────
    with op.batch_alter_table("import_runs") as batch_op:
        batch_op.add_column(sa.Column("last_checked_github_commit", sa.String(255), nullable=True, comment="Last checked GitHub commit SHA"))
        batch_op.add_column(sa.Column("latest_github_tag", sa.String(100), nullable=True, comment="Latest GitHub release tag (e.g. 2026.1.1)"))


def downgrade() -> None:
    with op.batch_alter_table("controls") as batch_op:
        batch_op.drop_column("cmm_level_5")
        batch_op.drop_column("cmm_level_4")
        batch_op.drop_column("cmm_level_3")
        batch_op.drop_column("cmm_level_2")
        batch_op.drop_column("cmm_level_1")
        batch_op.drop_column("cmm_level_0")
        batch_op.drop_column("solutions_enterprise")
        batch_op.drop_column("solutions_large")
        batch_op.drop_column("solutions_medium")
        batch_op.drop_column("solutions_small")
        batch_op.drop_column("solutions_micro_small")
        batch_op.drop_column("pptdf_applicability")
        batch_op.drop_column("relative_weight")

    with op.batch_alter_table("control_mappings") as batch_op:
        batch_op.drop_column("strm_type")

    with op.batch_alter_table("import_runs") as batch_op:
        batch_op.drop_column("latest_github_tag")
        batch_op.drop_column("last_checked_github_commit")
