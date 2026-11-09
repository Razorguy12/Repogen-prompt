"""Widen prompt_version so dated prompt versions fit.

Revision ID: 0003_prompt_version
Revises: 0002_clinical
Create Date: 2026-11-10
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_prompt_version"
down_revision = "0002_clinical"
branch_labels = None
depends_on = None

TABLES = ("final_reports", "comparisons")


def _alter(from_len, to_len):
    # SQLite ignores VARCHAR length, and a batch rebuild there would drop the
    # triggers that keep final reports immutable.
    if op.get_bind().dialect.name != "postgresql":
        return
    for table in TABLES:
        op.alter_column(table, "prompt_version", existing_type=sa.String(from_len), type_=sa.String(to_len),
                        existing_nullable=True)


def upgrade():
    _alter(16, 64)


def downgrade():
    _alter(64, 16)
