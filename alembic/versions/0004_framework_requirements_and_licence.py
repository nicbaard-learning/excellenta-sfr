"""Add framework_requirements table and licence/attribution fields on frameworks.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-17

"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())

    framework_columns = {c["name"] for c in inspector.get_columns("frameworks")}
    if "licence_name" not in framework_columns:
        op.add_column(
            "frameworks",
            sa.Column(
                "licence_name", sa.String(255), nullable=True,
                comment="Licence or reuse terms of the framework text",
            ),
        )
    if "licence_url" not in framework_columns:
        op.add_column("frameworks", sa.Column("licence_url", sa.String(500), nullable=True))
    if "attribution" not in framework_columns:
        op.add_column(
            "frameworks",
            sa.Column(
                "attribution", sa.Text(), nullable=True,
                comment="Credit and notices to show wherever the text is displayed",
            ),
        )

    # The app's startup create_all() may already have created the table.
    if inspector.has_table("framework_requirements"):
        return

    op.create_table(
        "framework_requirements",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("framework_id", sa.Integer(), nullable=False),
        sa.Column("ref", sa.String(50), nullable=False,
                  comment="Unique reference within the framework, e.g. s22, r4, ch3"),
        sa.Column("instrument", sa.String(100), nullable=False,
                  comment="Document the provision belongs to, e.g. Act, Regulations"),
        sa.Column("kind", sa.String(30), nullable=False,
                  comment="chapter, part, section, regulation, article, recital"),
        sa.Column("number", sa.String(30), nullable=True,
                  comment="Number as printed in the instrument, e.g. 22, 4, 3A"),
        sa.Column("parent_ref", sa.String(50), nullable=True,
                  comment="ref of the enclosing chapter or part"),
        sa.Column("title", sa.String(500), nullable=True),
        sa.Column("text", sa.Text(), nullable=True, comment="Provision text as published"),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("version_label", sa.String(100), nullable=True,
                  comment="Text version, e.g. 'as amended to 2020-07-01'"),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="in_force",
                  comment="in_force, not_in_force, pending_amendment, repealed"),
        sa.Column("status_note", sa.Text(), nullable=True),
        sa.Column("source_url", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["framework_id"], ["frameworks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("framework_id", "ref", name="uq_framework_requirement_ref"),
    )
    op.create_index(
        "ix_framework_requirements_framework_id", "framework_requirements", ["framework_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_framework_requirements_framework_id", table_name="framework_requirements")
    op.drop_table("framework_requirements")
    op.drop_column("frameworks", "attribution")
    op.drop_column("frameworks", "licence_url")
    op.drop_column("frameworks", "licence_name")
