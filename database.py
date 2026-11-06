from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, ForeignKey, Text, text, JSON, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv
import datetime

load_dotenv()

# Use the DATABASE_URL from .env. If not set, raise an error or fallback to a default.
# The user asked for postgresql, so we expect something like:
# postgresql://user:password@localhost:5432/radiology_db
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL")

if SQLALCHEMY_DATABASE_URL and SQLALCHEMY_DATABASE_URL.startswith("postgres://"):
    SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace("postgres://", "postgresql://", 1)

if not SQLALCHEMY_DATABASE_URL:
    # We fallback to sqlite for testing purposes if they haven't set the postgres URL yet
    print("WARNING: DATABASE_URL not found in environment, falling back to sqlite")
    SQLALCHEMY_DATABASE_URL = "sqlite:///./radiology.db"
    
if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
    )
else:
    engine = create_engine(SQLALCHEMY_DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    is_admin = Column(Boolean, default=False)
    is_locked = Column(Boolean, default=False, nullable=False)
    report_quota_start = Column(Integer, default=0, nullable=False)
    
    reports = relationship("Report", back_populates="user")

class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    patient_id = Column(String, index=True)
    patient_name = Column(String)
    modality = Column(String)
    status = Column(String, default="draft")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    report_data = Column(Text)  # JSON string of the complete report
    input_params = Column(Text, nullable=True)  # JSON string of original form inputs
    scan_image = Column(Text, nullable=True)  # Base64 or URL of uploaded scan image
    scan_image_name = Column(String, nullable=True)  # Original filename

    user = relationship("User", back_populates="reports")


class AuditEvent(Base):
    """Append-only application audit record. Never store clinical content here."""
    __tablename__ = "audit_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(String(80), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status = Column(String(16), nullable=False, default="SUCCESS")
    resource_type = Column(String(80), nullable=True)
    resource_id = Column(String(128), nullable=True)
    ip_address = Column(String(64), nullable=True)
    user_agent = Column(String(512), nullable=True)
    request_id = Column(String(64), nullable=True)
    duration_ms = Column(Integer, nullable=True)
    details = Column(JSON().with_variant(JSONB, "postgresql"), nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.datetime.now(datetime.timezone.utc))

    __table_args__ = (
        Index("ix_audit_events_created_at", "created_at"),
        Index("ix_audit_events_user_id", "user_id"),
        Index("ix_audit_events_event_type", "event_type"),
        Index("ix_audit_events_status", "status"),
        Index("ix_audit_events_resource_id", "resource_id"),
    )

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


MIGRATION_LOCK_ID = 724_001  # arbitrary constant for pg_advisory_xact_lock


def upgrade_schema(db_engine=None):
    """Apply Alembic migrations up to head.

    Safe to call from every worker on startup: on Postgres an advisory lock
    serialises concurrent callers, and Alembic skips revisions already applied.
    """
    from pathlib import Path
    from alembic import command
    from alembic.config import Config

    db_engine = db_engine or engine
    cfg = Config(str(Path(__file__).with_name("alembic.ini")))
    with db_engine.begin() as conn:
        if conn.dialect.name == "postgresql":
            conn.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": MIGRATION_LOCK_ID})
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")


def run_migrations(db_engine=None):
    """Backward-compatible alias; schema changes now live in alembic/versions."""
    upgrade_schema(db_engine)
