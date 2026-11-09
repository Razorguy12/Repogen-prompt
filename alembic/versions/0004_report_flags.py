"""Structured review flags for drafts. Additive only.

Revision ID: 0004_report_flags
Revises: 0003_prompt_version
Create Date: 2026-11-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0004_report_flags"
down_revision = "0003_prompt_version"
branch_labels = None
depends_on = None

JSONType = sa.JSON().with_variant(JSONB, "postgresql")


def upgrade():
    op.create_table(
        "report_flags",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("draft_id", sa.Integer, sa.ForeignKey("reports.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("severity", sa.String(8), nullable=False),
        sa.Column("raw_text", sa.Text, nullable=False),
        sa.Column("items", JSONType, nullable=False),
        sa.Column("source", sa.String(8), nullable=False),
        sa.Column("requires_review", sa.Boolean, nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="open"),
        sa.Column("reviewed_by", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('open', 'confirmed', 'corrected', 'not_applicable')", name="ck_report_flags_status"),
        sa.CheckConstraint("source IN ('model', 'server')", name="ck_report_flags_source"),
    )
    op.create_index("ix_report_flags_draft_id", "report_flags", ["draft_id"])


def downgrade():
    op.drop_index("ix_report_flags_draft_id", table_name="report_flags")
    op.drop_table("report_flags")
