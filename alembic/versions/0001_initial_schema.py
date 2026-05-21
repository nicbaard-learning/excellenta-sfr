"""Initial schema – all SFR tables.

Revision ID: 0001
Revises:
Create Date: 2025-06-01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── frameworks ────────────────────────────────────────────────
    op.create_table(
        "frameworks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("publisher", sa.String(255), nullable=True),
        sa.Column("source_url", sa.String(500), nullable=True),
        sa.Column("is_scf", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_frameworks_code", "frameworks", ["code"], unique=True)

    # ── framework_versions ────────────────────────────────────────
    op.create_table(
        "framework_versions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("framework_id", sa.Integer(), nullable=False),
        sa.Column("version_label", sa.String(50), nullable=False),
        sa.Column("release_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(50), nullable=True, server_default=sa.text("'active'")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("source_sheet", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["framework_id"], ["frameworks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("framework_id", "version_label", name="uq_framework_version"),
    )
    op.create_index("ix_framework_versions_framework_id", "framework_versions", ["framework_id"])

    # ── domains ───────────────────────────────────────────────────
    op.create_table(
        "domains",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_domains_code", "domains", ["code"], unique=True)

    # ── principles ────────────────────────────────────────────────
    op.create_table(
        "principles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("domain_id", sa.Integer(), nullable=True),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["domain_id"], ["domains.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_principles_domain_id", "principles", ["domain_id"])

    # ── controls ──────────────────────────────────────────────────
    op.create_table(
        "controls",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("scf_id", sa.String(50), nullable=False),
        sa.Column("domain_id", sa.Integer(), nullable=True),
        sa.Column("principle_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("control_question", sa.Text(), nullable=True),
        sa.Column("conformity_cadence", sa.String(100), nullable=True),
        sa.Column("relative_weighting", sa.Numeric(5, 2), nullable=True),
        sa.Column("evidence_request_list_refs", sa.Text(), nullable=True),
        sa.Column("applicability_context", sa.Text(), nullable=True),
        sa.Column("source_sheet", sa.String(255), nullable=True),
        sa.Column("source_row", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["domain_id"], ["domains.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["principle_id"], ["principles.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_controls_scf_id", "controls", ["scf_id"], unique=True)
    op.create_index("ix_controls_domain_id", "controls", ["domain_id"])

    # ── control_mappings ──────────────────────────────────────────
    op.create_table(
        "control_mappings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("control_id", sa.Integer(), nullable=False),
        sa.Column("framework_id", sa.Integer(), nullable=False),
        sa.Column("mapped_control_id", sa.String(100), nullable=True),
        sa.Column("mapped_control_title", sa.String(500), nullable=True),
        sa.Column("mapping_type", sa.String(50), nullable=True, server_default=sa.text("'equivalent'")),
        sa.Column("source_sheet", sa.String(255), nullable=True),
        sa.Column("source_column", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["control_id"], ["controls.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["framework_id"], ["frameworks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("control_id", "framework_id", "mapped_control_id", name="uq_control_mapping"),
    )
    op.create_index("ix_control_mappings_control_id", "control_mappings", ["control_id"])
    op.create_index("ix_control_mappings_framework_id", "control_mappings", ["framework_id"])

    # ── authoritative_sources ─────────────────────────────────────
    op.create_table(
        "authoritative_sources",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("control_id", sa.Integer(), nullable=True),
        sa.Column("source_title", sa.String(500), nullable=False),
        sa.Column("source_url", sa.String(500), nullable=True),
        sa.Column("source_organization", sa.String(255), nullable=True),
        sa.Column("reference_number", sa.String(100), nullable=True),
        sa.Column("source_sheet", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["control_id"], ["controls.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_authoritative_sources_control_id", "authoritative_sources", ["control_id"])

    # ── assessment_objectives ─────────────────────────────────────
    op.create_table(
        "assessment_objectives",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("control_id", sa.Integer(), nullable=False),
        sa.Column("objective_code", sa.String(100), nullable=True),
        sa.Column("objective_text", sa.Text(), nullable=False),
        sa.Column("source_sheet", sa.String(255), nullable=True),
        sa.Column("source_row", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["control_id"], ["controls.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_assessment_objectives_control_id", "assessment_objectives", ["control_id"])

    # ── evidence_artifacts ────────────────────────────────────────
    op.create_table(
        "evidence_artifacts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("control_id", sa.Integer(), nullable=False),
        sa.Column("erl_number", sa.String(50), nullable=True),
        sa.Column("evidence_title", sa.String(500), nullable=True),
        sa.Column("evidence_description", sa.Text(), nullable=True),
        sa.Column("evidence_type", sa.String(100), nullable=True),
        sa.Column("source_sheet", sa.String(255), nullable=True),
        sa.Column("source_row", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["control_id"], ["controls.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_evidence_artifacts_control_id", "evidence_artifacts", ["control_id"])

    # ── compensating_control_links ────────────────────────────────
    op.create_table(
        "compensating_control_links",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("control_id", sa.Integer(), nullable=False),
        sa.Column("compensating_control_id", sa.String(100), nullable=True),
        sa.Column("compensating_control_title", sa.String(500), nullable=True),
        sa.Column("compensating_control_description", sa.Text(), nullable=True),
        sa.Column("compensation_type", sa.String(50), nullable=True),
        sa.Column("justification", sa.Text(), nullable=True),
        sa.Column("source_sheet", sa.String(255), nullable=True),
        sa.Column("source_row", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["control_id"], ["controls.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_compensating_control_links_control_id", "compensating_control_links", ["control_id"])

    # ── jurisdictions ─────────────────────────────────────────────
    op.create_table(
        "jurisdictions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(10), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("region", sa.String(100), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_jurisdictions_code", "jurisdictions", ["code"], unique=True)

    # ── framework_jurisdictions ───────────────────────────────────
    op.create_table(
        "framework_jurisdictions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("framework_id", sa.Integer(), nullable=False),
        sa.Column("jurisdiction_id", sa.Integer(), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["framework_id"], ["frameworks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["jurisdiction_id"], ["jurisdictions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("framework_id", "jurisdiction_id", name="uq_framework_jurisdiction"),
    )
    op.create_index("ix_framework_jurisdictions_framework_id", "framework_jurisdictions", ["framework_id"])
    op.create_index("ix_framework_jurisdictions_jurisdiction_id", "framework_jurisdictions", ["jurisdiction_id"])

    # ── business_models ───────────────────────────────────────────
    op.create_table(
        "business_models",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_business_models_code", "business_models", ["code"], unique=True)

    # ── framework_applicability_rules ─────────────────────────────
    op.create_table(
        "framework_applicability_rules",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("framework_id", sa.Integer(), nullable=False),
        sa.Column("attribute_name", sa.String(100), nullable=False),
        sa.Column("attribute_value", sa.String(255), nullable=False),
        sa.Column("is_recommended", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("source_sheet", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["framework_id"], ["frameworks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("framework_id", "attribute_name", "attribute_value", name="uq_applicability_rule"),
    )
    op.create_index(
        "ix_framework_applicability_rules_framework_id",
        "framework_applicability_rules",
        ["framework_id"],
    )

    # ── import_runs ───────────────────────────────────────────────
    op.create_table(
        "import_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("filename", sa.String(500), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default=sa.text("'running'")),
        sa.Column("sheets_processed", sa.Text(), nullable=True),
        sa.Column("rows_loaded", sa.Integer(), nullable=True),
        sa.Column("rows_skipped", sa.Integer(), nullable=True),
        sa.Column("error_log", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("import_runs")
    op.drop_table("framework_applicability_rules")
    op.drop_table("business_models")
    op.drop_table("framework_jurisdictions")
    op.drop_table("jurisdictions")
    op.drop_table("compensating_control_links")
    op.drop_table("evidence_artifacts")
    op.drop_table("assessment_objectives")
    op.drop_table("authoritative_sources")
    op.drop_table("control_mappings")
    op.drop_table("controls")
    op.drop_table("principles")
    op.drop_table("domains")
    op.drop_table("framework_versions")
    op.drop_table("frameworks")
