"""Patient matching, validation rules and helpers for final reports.

Pure functions where possible so they are easy to test. Nothing here logs
patient-identifying data.
"""
from __future__ import annotations

import datetime as dt
import re
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from database import FinalReport, Patient

CLINIC_TZ = ZoneInfo("Asia/Kolkata")
AGE_LIMITS = {"years": 130, "months": 240, "days": 366}

_HONORIFICS = (
    "baby of", "b/o", "mrs", "mr", "ms", "miss", "dr", "master", "mstr", "smt", "shri", "sri", "kumari", "kum",
)
_HONORIFIC_RE = re.compile(r"^(?:(?:" + "|".join(re.escape(h) for h in _HONORIFICS) + r")\.?\s+)+", re.IGNORECASE)


def normalize_name(name: str) -> str:
    """Lowercase, honorific-free, single-spaced. 'Mrs. Rama  S' -> 'rama s'."""
    value = re.sub(r"\s+", " ", (name or "").strip().lower())
    value = _HONORIFIC_RE.sub("", value)
    value = re.sub(r"[.,]", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def normalize_identifier(identifier: str | None) -> str | None:
    value = re.sub(r"\s+", "", (identifier or "")).upper()
    return value or None


def clinic_today() -> dt.date:
    return dt.datetime.now(CLINIC_TZ).date()


def validate_age(value: int, unit: str) -> str | None:
    if unit not in AGE_LIMITS:
        return "Age unit must be years, months or days"
    if value < 0 or value > AGE_LIMITS[unit]:
        return f"Age must be between 0 and {AGE_LIMITS[unit]} {unit}"
    return None


def validate_study_date(value: dt.date) -> str | None:
    if value > clinic_today():
        return "Study date cannot be in the future"
    if value.year < 1900:
        return "Study date is not valid"
    return None


def _months_between(a: dt.date, b: dt.date) -> int:
    months = (b.year - a.year) * 12 + (b.month - a.month)
    if b.day < a.day:
        months -= 1
    return months


def suggest_age(last_age: int, unit: str, last_study: dt.date, new_study: dt.date) -> int:
    """Last recorded age plus elapsed time, rounded down, in the same unit."""
    if new_study <= last_study:
        return last_age
    if unit == "days":
        return last_age + (new_study - last_study).days
    months = _months_between(last_study, new_study)
    if unit == "months":
        return last_age + months
    return last_age + months // 12


def scoped_patients(db: Session, doctor_id: int):
    return db.query(Patient).filter(Patient.owner_doctor_id == doctor_id)


def get_patient_for_doctor(db: Session, doctor_id: int, patient_id: int) -> Patient | None:
    return scoped_patients(db, doctor_id).filter(Patient.id == patient_id).first()


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search_patients(db: Session, doctor_id: int, q: str, limit: int = 20) -> list[Patient]:
    """Partial normalized-name match or identifier prefix. An exact identifier wins outright."""
    q = (q or "").strip()
    if not q:
        return []
    ident = normalize_identifier(q)
    base = scoped_patients(db, doctor_id)
    if ident:
        exact = base.filter(Patient.patient_identifier_normalized == ident).all()
        if exact:
            return exact
    name = normalize_name(q)
    clauses = []
    if name:
        clauses.append(Patient.full_name_normalized.like(f"%{_escape_like(name)}%", escape="\\"))
    if ident:
        clauses.append(Patient.patient_identifier_normalized.like(f"{_escape_like(ident)}%", escape="\\"))
    if not clauses:
        return []
    return base.filter(or_(*clauses)).order_by(Patient.full_name_normalized).limit(limit).all()


def find_possible_duplicates(db: Session, doctor_id: int, full_name: str, identifier: str | None) -> list[Patient]:
    name = normalize_name(full_name)
    ident = normalize_identifier(identifier)
    clauses = [Patient.full_name_normalized == name] if name else []
    if ident:
        clauses.append(Patient.patient_identifier_normalized == ident)
    if not clauses:
        return []
    return scoped_patients(db, doctor_id).filter(or_(*clauses)).all()


def patient_report_stats(db: Session, patient_ids: list[int]) -> dict[int, dict]:
    """Count of current (non-superseded) final reports and latest study date per patient."""
    if not patient_ids:
        return {}
    rows = (
        db.query(FinalReport.patient_id, func.count(FinalReport.id), func.max(FinalReport.study_date))
        .filter(FinalReport.patient_id.in_(patient_ids), current_version_filter())
        .group_by(FinalReport.patient_id)
        .all()
    )
    return {pid: {"report_count": count, "latest_study_date": latest} for pid, count, latest in rows}


def current_version_filter():
    """Rows not superseded by an amendment."""
    newer = FinalReport.__table__.alias("newer")
    amended_ids = select(newer.c.amends_report_id).where(newer.c.amends_report_id.is_not(None))
    return FinalReport.id.not_in(amended_ids)


def last_age_record(db: Session, patient_id: int) -> FinalReport | None:
    return (
        db.query(FinalReport)
        .filter(FinalReport.patient_id == patient_id)
        .order_by(FinalReport.study_date.desc(), FinalReport.id.desc())
        .first()
    )
