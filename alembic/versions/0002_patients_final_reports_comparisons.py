"""Patients, immutable final reports, and comparisons.

Additive only: no existing table or column is modified.

Revision ID: 0002_clinical
Revises: 0001_baseline
Create Date: 2026-11-06
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0002_clinical"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None

JSONType = sa.JSON().with_variant(JSONB, "postgresql")
GENDERS = "('Male', 'Female', 'Other', 'Not stated')"
MODALITIES = "('XR', 'CT', 'MRI', 'US', 'DOPPLER', 'MAMMO', 'FLUORO', 'OTHER', 'UNSPECIFIED')"


def _timestamps():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    ]


def upgrade():
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    op.create_table(
        "patients",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("owner_doctor_id", sa.Integer, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("patient_identifier", sa.String(64)),
        sa.Column("patient_identifier_normalized", sa.String(64)),
        sa.Column("full_name", sa.String(100), nullable=False),
        sa.Column("full_name_normalized", sa.String(100), nullable=False),
        sa.Column("gender", sa.String(16), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("owner_doctor_id", "patient_identifier_normalized", name="uq_patients_owner_identifier"),
        sa.CheckConstraint(f"gender IN {GENDERS}", name="ck_patients_gender"),
    )
    op.create_index("ix_patients_owner_doctor_id", "patients", ["owner_doctor_id"])
    op.create_index("ix_patients_full_name_normalized", "patients", ["full_name_normalized"])

    op.create_table(
        "final_reports",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("draft_id", sa.Integer, sa.ForeignKey("reports.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("patient_id", sa.Integer, sa.ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("doctor_id", sa.Integer, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="final"),
        sa.Column("amends_report_id", sa.Integer, sa.ForeignKey("final_reports.id", ondelete="RESTRICT")),
        sa.Column("selected_variant", sa.String(16), nullable=False),
        sa.Column("final_text", sa.Text, nullable=False),
        sa.Column("final_sections", JSONType),
        sa.Column("exam_modality", sa.String(16), nullable=False),
        sa.Column("exam_region", sa.String(120), nullable=False),
        sa.Column("exam_laterality", sa.String(32), nullable=False),
        sa.Column("exam_title", sa.String(200), nullable=False),
        sa.Column("patient_age_at_study", sa.Integer, nullable=False),
        sa.Column("age_unit", sa.String(8), nullable=False),
        sa.Column("study_date", sa.Date, nullable=False),
        sa.Column("source_input", sa.Text),
        sa.Column("flags", JSONType, nullable=False),
        sa.Column("flag_acknowledgements", JSONType, nullable=False),
        sa.Column("flags_acknowledged_at", sa.DateTime(timezone=True)),
        sa.Column("prompt_version", sa.String(16)),
        sa.Column("model_id", sa.String(120)),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        *_timestamps(),
        sa.CheckConstraint("status IN ('final', 'amended')", name="ck_final_reports_status"),
        sa.CheckConstraint("selected_variant IN ('concise', 'standard', 'detailed')", name="ck_final_reports_variant"),
        sa.CheckConstraint(f"exam_modality IN {MODALITIES}", name="ck_final_reports_modality"),
        sa.CheckConstraint("age_unit IN ('years', 'months', 'days')", name="ck_final_reports_age_unit"),
        sa.CheckConstraint("(status = 'amended') = (amends_report_id IS NOT NULL)", name="ck_final_reports_amend_link"),
    )
    for name, cols in (
        ("ix_final_reports_draft_id", ["draft_id"]),
        ("ix_final_reports_doctor_id", ["doctor_id"]),
        ("ix_final_reports_amends_report_id", ["amends_report_id"]),
        ("ix_final_reports_patient_study_date", ["patient_id", "study_date"]),
        ("ix_final_reports_exam_modality", ["exam_modality"]),
        ("ix_final_reports_exam_region", ["exam_region"]),
    ):
        op.create_index(name, "final_reports", cols)

    op.create_table(
        "comparisons",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("patient_id", sa.Integer, sa.ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("baseline_report_id", sa.Integer, sa.ForeignKey("final_reports.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("followup_report_id", sa.Integer, sa.ForeignKey("final_reports.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("interval_days", sa.Integer, nullable=False),
        sa.Column("result", JSONType, nullable=False),
        sa.Column("edited_summary", sa.Text),
        sa.Column("edited_impression", JSONType),
        sa.Column("status", sa.String(8), nullable=False, server_default="draft"),
        sa.Column("prompt_version", sa.String(16)),
        sa.Column("model_id", sa.String(120)),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("status IN ('draft', 'saved')", name="ck_comparisons_status"),
        sa.CheckConstraint("baseline_report_id <> followup_report_id", name="ck_comparisons_distinct"),
    )
    for col in ("patient_id", "baseline_report_id", "followup_report_id"):
        op.create_index(f"ix_comparisons_{col}", "comparisons", [col])

    # Signed text is immutable at the database level, not only in the API.
    if is_pg:
        op.execute("""
            CREATE FUNCTION final_reports_block_text_update() RETURNS trigger AS $$
            BEGIN
              IF NEW.final_text IS DISTINCT FROM OLD.final_text
                 OR NEW.final_sections::text IS DISTINCT FROM OLD.final_sections::text THEN
                RAISE EXCEPTION 'final_reports.final_text is immutable; create an amendment instead';
              END IF;
              RETURN NEW;
            END $$ LANGUAGE plpgsql;
        """)
        op.execute("""
            CREATE TRIGGER trg_final_reports_immutable BEFORE UPDATE ON final_reports
            FOR EACH ROW EXECUTE FUNCTION final_reports_block_text_update();
        """)
        # Partial-name search. pg_trgm is a trusted extension (PG13+), but the
        # role may still lack CREATE; fall back to the btree index if so.
        sp = bind.begin_nested()
        try:
            bind.execute(sa.text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
            bind.execute(sa.text(
                "CREATE INDEX ix_patients_full_name_trgm ON patients "
                "USING gin (full_name_normalized gin_trgm_ops)"))
            sp.commit()
        except Exception:
            sp.rollback()
            print("NOTE: pg_trgm unavailable; partial name search uses a sequential scan")
    else:
        op.execute("""
            CREATE TRIGGER trg_final_reports_immutable BEFORE UPDATE OF final_text, final_sections ON final_reports
            FOR EACH ROW WHEN NEW.final_text IS NOT OLD.final_text OR NEW.final_sections IS NOT OLD.final_sections
            BEGIN SELECT RAISE(ABORT, 'final_reports.final_text is immutable; create an amendment instead'); END;
        """)


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_patients_full_name_trgm")
        op.execute("DROP TRIGGER IF EXISTS trg_final_reports_immutable ON final_reports")
        op.execute("DROP FUNCTION IF EXISTS final_reports_block_text_update()")
        # pg_trgm is left installed; other objects may depend on it.
    else:
        op.execute("DROP TRIGGER IF EXISTS trg_final_reports_immutable")
    op.drop_table("comparisons")
    op.drop_table("final_reports")
    op.drop_table("patients")
