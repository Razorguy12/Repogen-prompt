"""Saved custom report format per doctor. Additive only.

Revision ID: 0005_custom_format
Revises: 0004_report_flags
Create Date: 2026-11-10
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_custom_format"
down_revision = "0004_report_flags"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("custom_report_format", sa.Text, nullable=True))


def downgrade():
    op.drop_column("users", "custom_report_format")
