"""Add Threat, Risk tables and AuthoritativeSource FDI/STRM fields.

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-21

"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── Add new columns to authoritative_sources ──
    op.add_column(
        "authoritative_sources",
        sa.Column(
            "focal_document_identifier",
            sa.String(255),
            nullable=True,
            comment="Focal Document Identifier (FDI) / STRM slug",
        ),
    )
    op.add_column(
        "authoritative_sources",
        sa.Column(
            "strm_url",
            sa.String(500),
            nullable=True,
            comment="Set Theory Relationship Mapping PDF URL",
        ),
    )
    op.add_column(
        "authoritative_sources",
        sa.Column(
            "geography",
            sa.String(100),
            nullable=True,
            comment="Geographic region from the Authoritative Sources sheet",
        ),
    )

    # ── Threat Catalog tables ──
    op.create_table(
        "threats",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "threat_number",
            sa.String(50),
            nullable=True,
            comment="Threat # from the catalog",
        ),
        sa.Column(
            "threat_grouping",
            sa.String(255),
            nullable=True,
            comment="Threat Grouping category",
        ),
        sa.Column(
            "threat_title",
            sa.String(500),
            nullable=True,
            comment="Threat name / title",
        ),
        sa.Column(
            "threat_description",
            sa.Text(),
            nullable=True,
            comment="Threat description",
        ),
        sa.Column(
            "materiality_considerations",
            sa.Text(),
            nullable=True,
            comment="Materiality impact considerations",
        ),
        sa.Column(
            "source_sheet",
            sa.String(255),
            nullable=True,
            comment="Source workbook sheet name",
        ),
        sa.Column(
            "source_row",
            sa.Integer(),
            nullable=True,
            comment="Row number in source sheet",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_threats_threat_number"), "threats", ["threat_number"])

    op.create_table(
        "threat_control_links",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "threat_id",
            sa.Integer(),
            sa.ForeignKey("threats.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "control_id",
            sa.Integer(),
            sa.ForeignKey("controls.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_threat_control_links_threat_id"),
        "threat_control_links",
        ["threat_id"],
    )
    op.create_index(
        op.f("ix_threat_control_links_control_id"),
        "threat_control_links",
        ["control_id"],
    )

    # ── Risk Catalog tables ──
    op.create_table(
        "risks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "risk_number",
            sa.String(50),
            nullable=True,
            comment="Risk # from the catalog",
        ),
        sa.Column(
            "risk_grouping",
            sa.String(255),
            nullable=True,
            comment="Risk Grouping category",
        ),
        sa.Column(
            "risk_title",
            sa.String(500),
            nullable=True,
            comment="Risk name / title",
        ),
        sa.Column(
            "risk_description",
            sa.Text(),
            nullable=True,
            comment="Description of possible risk due to control deficiency",
        ),
        sa.Column(
            "nist_csf_function",
            sa.String(100),
            nullable=True,
            comment="NIST CSF Function mapping",
        ),
        sa.Column(
            "materiality_considerations",
            sa.Text(),
            nullable=True,
            comment="Materiality impact considerations",
        ),
        sa.Column(
            "source_sheet",
            sa.String(255),
            nullable=True,
            comment="Source workbook sheet name",
        ),
        sa.Column(
            "source_row",
            sa.Integer(),
            nullable=True,
            comment="Row number in source sheet",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_risks_risk_number"), "risks", ["risk_number"])

    op.create_table(
        "risk_control_links",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "risk_id",
            sa.Integer(),
            sa.ForeignKey("risks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "control_id",
            sa.Integer(),
            sa.ForeignKey("controls.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_risk_control_links_risk_id"),
        "risk_control_links",
        ["risk_id"],
    )
    op.create_index(
        op.f("ix_risk_control_links_control_id"),
        "risk_control_links",
        ["control_id"],
    )


def downgrade() -> None:
    # ── Drop Risk tables ──
    op.drop_index(op.f("ix_risk_control_links_control_id"), table_name="risk_control_links")
    op.drop_index(op.f("ix_risk_control_links_risk_id"), table_name="risk_control_links")
    op.drop_table("risk_control_links")
    op.drop_index(op.f("ix_risks_risk_number"), table_name="risks")
    op.drop_table("risks")

    # ── Drop Threat tables ──
    op.drop_index(op.f("ix_threat_control_links_control_id"), table_name="threat_control_links")
    op.drop_index(op.f("ix_threat_control_links_threat_id"), table_name="threat_control_links")
    op.drop_table("threat_control_links")
    op.drop_index(op.f("ix_threats_threat_number"), table_name="threats")
    op.drop_table("threats")

    # ── Drop new columns from authoritative_sources ──
    op.drop_column("authoritative_sources", "geography")
    op.drop_column("authoritative_sources", "strm_url")
    op.drop_column("authoritative_sources", "focal_document_identifier")
