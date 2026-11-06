"""Baseline: the schema as it existed before Alembic.

Brings any database (fresh, or created by the old run_migrations()) to the
same starting point. Every step is guarded, so running it on an existing
production database only adds what is missing and never rewrites data.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-11-06
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def _columns(inspector, table):
    return {c["name"] for c in inspector.get_columns(table)}


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())

    if "users" not in tables:
        op.create_table(
            "users",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("name", sa.String, index=True),
            sa.Column("username", sa.String, unique=True, index=True),
            sa.Column("email", sa.String, unique=True, index=True),
            sa.Column("hashed_password", sa.String),
            sa.Column("is_admin", sa.Boolean, default=False),
            sa.Column("is_locked", sa.Boolean, nullable=False, server_default=sa.false()),
            sa.Column("report_quota_start", sa.Integer, nullable=False, server_default="0"),
        )
    else:
        cols = _columns(insp, "users")
        if "is_locked" not in cols:
            op.add_column("users", sa.Column("is_locked", sa.Boolean, nullable=False, server_default=sa.false()))
        if "report_quota_start" not in cols:
            op.add_column("users", sa.Column("report_quota_start", sa.Integer, nullable=False, server_default="0"))

    if "reports" not in tables:
        op.create_table(
            "reports",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id")),
            sa.Column("patient_id", sa.String, index=True),
            sa.Column("patient_name", sa.String),
            sa.Column("modality", sa.String),
            sa.Column("status", sa.String, server_default="draft"),
            sa.Column("created_at", sa.DateTime),
            sa.Column("updated_at", sa.DateTime),
            sa.Column("report_data", sa.Text),
            sa.Column("input_params", sa.Text),
            sa.Column("scan_image", sa.Text),
            sa.Column("scan_image_name", sa.String),
        )
    else:
        cols = _columns(insp, "reports")
        for name, type_ in (
            ("status", sa.String),
            ("updated_at", sa.DateTime),
            ("input_params", sa.Text),
            ("scan_image", sa.Text),
            ("scan_image_name", sa.String),
        ):
            if name not in cols:
                op.add_column("reports", sa.Column(name, type_, server_default="draft" if name == "status" else None))
        if "updated_at" not in cols:
            op.execute("UPDATE reports SET updated_at = created_at WHERE updated_at IS NULL")

    if "audit_events" not in tables:
        op.create_table(
            "audit_events",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("event_type", sa.String(80), nullable=False),
            sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL")),
            sa.Column("status", sa.String(16), nullable=False),
            sa.Column("resource_type", sa.String(80)),
            sa.Column("resource_id", sa.String(128)),
            sa.Column("ip_address", sa.String(64)),
            sa.Column("user_agent", sa.String(512)),
            sa.Column("request_id", sa.String(64)),
            sa.Column("duration_ms", sa.Integer),
            sa.Column("details", sa.JSON().with_variant(JSONB, "postgresql"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
    existing_idx = {i["name"] for i in sa.inspect(bind).get_indexes("audit_events")}
    for col in ("created_at", "user_id", "event_type", "status", "resource_id"):
        name = f"ix_audit_events_{col}"
        if name not in existing_idx:
            op.create_index(name, "audit_events", [col])


def downgrade():
    # The baseline represents data that predates Alembic; it is never dropped.
    pass
