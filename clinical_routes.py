"""Patients, finalization, final reports and amendments.

Every route is scoped server-side to the signed-in doctor: patients and
final reports are only ever looked up through owner/doctor filters.
Responses may contain patient details (the doctor's own); logs and audit
events never do — they carry record IDs only.
"""
from __future__ import annotations

import datetime as dt
import json
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

import auth
import clinical
import model.model as model
from audit_service import log_audit_event
from database import Comparison, FinalReport, Patient, Report, User, get_db, iso_utc, utcnow
from rate_limit import enforce_rate_limit

router = APIRouter(prefix="/api")

Gender = Literal["Male", "Female", "Other", "Not stated"]
AgeUnit = Literal["years", "months", "days"]
Variant = Literal["concise", "standard", "detailed"]


# --------------------------------------------------------------------------- schemas

class PatientInput(BaseModel):
    full_name: str = Field(min_length=2, max_length=100)
    patient_identifier: Optional[str] = Field(default=None, max_length=64)
    gender: Gender

    @field_validator("full_name")
    @classmethod
    def _trim_name(cls, v: str) -> str:
        v = " ".join(v.split())
        if len(v) < 2:
            raise ValueError("Full name must be 2–100 characters")
        return v

    @field_validator("patient_identifier")
    @classmethod
    def _trim_identifier(cls, v):
        v = (v or "").strip()
        return v or None


class DuplicateCheck(BaseModel):
    full_name: str = Field(default="", max_length=100)
    patient_identifier: Optional[str] = Field(default=None, max_length=64)


class FlagAck(BaseModel):
    index: int = Field(ge=0)
    acknowledged_at: dt.datetime


class ExamInput(BaseModel):
    modality: model.Modality
    region: str = Field(min_length=1, max_length=120)
    laterality: model.Laterality


class FinalizeRequest(BaseModel):
    selected_variant: Variant
    patient_id: Optional[int] = None
    new_patient: Optional[PatientInput] = None
    create_new_anyway: bool = False
    age_value: int
    age_unit: AgeUnit
    study_date: dt.date
    exam: ExamInput
    flag_acknowledgements: list[FlagAck] = []
    approved: bool


class AmendRequest(BaseModel):
    final_text: str = Field(min_length=1, max_length=50_000)


# --------------------------------------------------------------------------- serializers

def patient_payload(p: Patient, stats: dict | None = None) -> dict:
    stats = stats or {}
    latest = stats.get("latest_study_date")
    return {
        "id": p.id,
        "full_name": p.full_name,
        "patient_identifier": p.patient_identifier,
        "gender": p.gender,
        "report_count": stats.get("report_count", 0),
        "latest_study_date": latest.isoformat() if latest else None,
        "created_at": iso_utc(p.created_at),
        "updated_at": iso_utc(p.updated_at),
    }


def final_report_payload(fr: FinalReport, db: Session, detail: bool = True) -> dict:
    newer = db.query(FinalReport.id).filter(FinalReport.amends_report_id == fr.id).first()
    data = {
        "id": fr.id,
        "draft_id": fr.draft_id,
        "status": fr.status,
        "amends_report_id": fr.amends_report_id,
        "superseded_by_id": newer[0] if newer else None,
        "patient": patient_payload(fr.patient),
        "doctor_name": fr.doctor.name if fr.doctor else None,
        "selected_variant": fr.selected_variant,
        "exam": {"modality": fr.exam_modality, "region": fr.exam_region, "laterality": fr.exam_laterality},
        "exam_title": fr.exam_title,
        "age": {"value": fr.patient_age_at_study, "unit": fr.age_unit},
        "study_date": fr.study_date.isoformat(),
        "finalized_at": iso_utc(fr.finalized_at),
        "created_at": iso_utc(fr.created_at),
        "updated_at": iso_utc(fr.updated_at),
    }
    if detail:
        data.update({
            "final_text": fr.final_text,
            "final_sections": fr.final_sections,
            "flags": fr.flags or [],
            "flag_acknowledgements": fr.flag_acknowledgements or [],
            "flags_acknowledged_at": iso_utc(fr.flags_acknowledged_at),
            "prompt_version": fr.prompt_version,
            "model_id": fr.model_id,
        })
    return data


# --------------------------------------------------------------------------- helpers

def _draft_params(draft: Report) -> dict:
    try:
        return json.loads(draft.input_params or "{}") or {}
    except json.JSONDecodeError:
        return {}


def _own_final_report(db: Session, user: User, report_id: int) -> FinalReport:
    fr = db.query(FinalReport).filter(FinalReport.id == report_id, FinalReport.doctor_id == user.id).first()
    if not fr:
        raise HTTPException(status_code=404, detail="Final report not found")
    return fr


def _bad(detail: str, code: int = 422):
    raise HTTPException(status_code=code, detail=detail)


# --------------------------------------------------------------------------- patients

@router.get("/patients")
def list_patients(q: str = Query(default="", max_length=100), db: Session = Depends(get_db),
                  user: User = Depends(auth.get_current_user)):
    patients = clinical.search_patients(db, user.id, q)
    stats = clinical.patient_report_stats(db, [p.id for p in patients])
    return [patient_payload(p, stats.get(p.id)) for p in patients]


@router.post("/patients/duplicates")
def check_duplicates(body: DuplicateCheck, db: Session = Depends(get_db),
                     user: User = Depends(auth.get_current_user)):
    matches = clinical.find_possible_duplicates(db, user.id, body.full_name, body.patient_identifier)
    stats = clinical.patient_report_stats(db, [p.id for p in matches])
    return [patient_payload(p, stats.get(p.id)) for p in matches]


@router.get("/patients/{patient_id}")
def get_patient(patient_id: int, db: Session = Depends(get_db), user: User = Depends(auth.get_current_user)):
    patient = clinical.get_patient_for_doctor(db, user.id, patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    stats = clinical.patient_report_stats(db, [patient.id])
    last = clinical.last_age_record(db, patient.id)
    payload = patient_payload(patient, stats.get(patient.id))
    payload["last_age"] = (
        {"value": last.patient_age_at_study, "unit": last.age_unit, "study_date": last.study_date.isoformat()}
        if last else None
    )
    return payload


@router.get("/patients/{patient_id}/age-suggestion")
def age_suggestion(patient_id: int, study_date: dt.date, db: Session = Depends(get_db),
                   user: User = Depends(auth.get_current_user)):
    if not clinical.get_patient_for_doctor(db, user.id, patient_id):
        raise HTTPException(status_code=404, detail="Patient not found")
    last = clinical.last_age_record(db, patient_id)
    if not last:
        return None
    return {
        "value": clinical.suggest_age(last.patient_age_at_study, last.age_unit, last.study_date, study_date),
        "unit": last.age_unit,
    }


@router.patch("/patients/{patient_id}")
def update_patient(patient_id: int, body: PatientInput, request: Request, db: Session = Depends(get_db),
                   user: User = Depends(auth.get_current_user)):
    patient = clinical.get_patient_for_doctor(db, user.id, patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    ident = clinical.normalize_identifier(body.patient_identifier)
    if ident and clinical.scoped_patients(db, user.id).filter(
            Patient.patient_identifier_normalized == ident, Patient.id != patient.id).first():
        _bad("Another patient already has this ID", 409)
    patient.full_name = body.full_name
    patient.full_name_normalized = clinical.normalize_name(body.full_name)
    patient.patient_identifier = body.patient_identifier
    patient.patient_identifier_normalized = ident
    patient.gender = body.gender
    db.commit()
    db.refresh(patient)
    log_audit_event(db, "PATIENT_UPDATED", user_id=user.id, request=request, resource_type="patient",
                    resource_id=patient.id)
    return patient_payload(patient, clinical.patient_report_stats(db, [patient.id]).get(patient.id))


@router.get("/patients/{patient_id}/final-reports")
def patient_final_reports(patient_id: int, include_superseded: bool = False, db: Session = Depends(get_db),
                          user: User = Depends(auth.get_current_user)):
    if not clinical.get_patient_for_doctor(db, user.id, patient_id):
        raise HTTPException(status_code=404, detail="Patient not found")
    query = db.query(FinalReport).filter(FinalReport.patient_id == patient_id, FinalReport.doctor_id == user.id)
    if not include_superseded:
        query = query.filter(clinical.current_version_filter())
    rows = query.order_by(FinalReport.study_date.desc(), FinalReport.id.desc()).all()
    return [final_report_payload(fr, db, detail=False) for fr in rows]


# --------------------------------------------------------------------------- finalize

@router.post("/reports/{draft_id}/finalize")
def finalize_draft(draft_id: int, body: FinalizeRequest, request: Request, db: Session = Depends(get_db),
                   user: User = Depends(auth.get_current_user)):
    enforce_rate_limit(user.id, "finalize", limit=30)
    draft = db.query(Report).filter(Report.id == draft_id).first()
    if not draft or draft.user_id != user.id:
        raise HTTPException(status_code=404, detail="Draft not found")
    if db.query(FinalReport.id).filter(FinalReport.draft_id == draft.id, FinalReport.status == "final").first():
        _bad("This draft has already been finalized. Add an amendment to the final report instead.", 409)
    if not body.approved:
        _bad("Confirm that you have reviewed and approved the report")

    params = _draft_params(draft)
    alternatives = params.get("alternatives") or []
    selected = params.get("selected") or "standard"
    if not alternatives:
        _bad("Only prompt drafts can be finalized with patient details")
    if body.selected_variant != selected:
        _bad("The selected variant changed. Reload the draft and try again.", 409)
    variant = next((a for a in alternatives if a.get("type") == selected), None)
    if not variant or not (variant.get("full_report") or "").strip():
        _bad("The selected report is empty")

    # Flags: every flag stored with the draft must be acknowledged.
    flags = params.get("flags") or []
    now = utcnow()
    acks = {a.index: a.acknowledged_at for a in body.flag_acknowledgements}
    if any(i not in acks for i in range(len(flags))):
        _bad("Acknowledge every flag before finalizing")
    ack_records = []
    for i, flag in enumerate(flags):
        at = acks[i] if acks[i].tzinfo else acks[i].replace(tzinfo=dt.timezone.utc)
        ack_records.append({"flag": flag, "acknowledged_at": iso_utc(min(at, now))})

    for err in (clinical.validate_age(body.age_value, body.age_unit), clinical.validate_study_date(body.study_date)):
        if err:
            _bad(err)
    if body.exam.modality == "UNSPECIFIED":
        _bad("Choose the modality before finalizing")

    # Patient: existing (scoped) or new with duplicate guard.
    created_patient = None
    if body.patient_id is not None:
        patient = clinical.get_patient_for_doctor(db, user.id, body.patient_id)
        if not patient:
            raise HTTPException(status_code=404, detail="Patient not found")
    elif body.new_patient is not None:
        np_ = body.new_patient
        ident = clinical.normalize_identifier(np_.patient_identifier)
        matches = clinical.find_possible_duplicates(db, user.id, np_.full_name, np_.patient_identifier)
        id_clash = [m for m in matches if ident and m.patient_identifier_normalized == ident]
        if id_clash or (matches and not body.create_new_anyway):
            stats = clinical.patient_report_stats(db, [m.id for m in matches])
            raise HTTPException(status_code=409, detail={
                "code": "identifier_in_use" if id_clash else "possible_duplicate",
                "message": "A patient with this ID already exists" if id_clash else "Possible existing patient",
                "matches": [patient_payload(m, stats.get(m.id)) for m in matches],
            })
        patient = Patient(owner_doctor_id=user.id, full_name=np_.full_name,
                          full_name_normalized=clinical.normalize_name(np_.full_name),
                          patient_identifier=np_.patient_identifier, patient_identifier_normalized=ident,
                          gender=np_.gender)
        db.add(patient)
        db.flush()
        created_patient = patient
    else:
        _bad("Choose an existing patient or enter new patient details")

    fr = FinalReport(
        draft_id=draft.id, patient_id=patient.id, doctor_id=user.id, status="final",
        selected_variant=selected, final_text=variant["full_report"], final_sections=None,
        exam_modality=body.exam.modality, exam_region=body.exam.region.strip(),
        exam_laterality=body.exam.laterality, exam_title=(variant.get("title") or "Radiology report")[:200],
        patient_age_at_study=body.age_value, age_unit=body.age_unit, study_date=body.study_date,
        source_input=params.get("prompt"), flags=flags, flag_acknowledgements=ack_records,
        flags_acknowledged_at=now if flags else None,
        prompt_version=params.get("prompt_version"), model_id=params.get("model_id"), finalized_at=now,
    )
    db.add(fr)
    draft.status = "final"           # locks the draft through the existing edit guards
    draft.updated_at = now.replace(tzinfo=None)
    db.commit()
    db.refresh(fr)
    if created_patient is not None:
        log_audit_event(db, "PATIENT_CREATED", user_id=user.id, request=request, resource_type="patient",
                        resource_id=created_patient.id)
    log_audit_event(db, "REPORT_FINALIZED", user_id=user.id, request=request, resource_type="final_report",
                    resource_id=fr.id)
    return final_report_payload(fr, db)


# --------------------------------------------------------------------------- final reports

@router.get("/final-reports")
def recent_final_reports(limit: int = Query(default=10, ge=1, le=50), db: Session = Depends(get_db),
                         user: User = Depends(auth.get_current_user)):
    rows = (db.query(FinalReport).filter(FinalReport.doctor_id == user.id, clinical.current_version_filter())
            .order_by(FinalReport.finalized_at.desc()).limit(limit).all())
    return [final_report_payload(fr, db, detail=False) for fr in rows]


@router.get("/final-reports/by-draft/{draft_id}")
def final_report_for_draft(draft_id: int, db: Session = Depends(get_db), user: User = Depends(auth.get_current_user)):
    fr = (db.query(FinalReport).filter(FinalReport.draft_id == draft_id, FinalReport.doctor_id == user.id,
                                       FinalReport.status == "final").first())
    if not fr:
        raise HTTPException(status_code=404, detail="Final report not found")
    return {"id": fr.id}


@router.get("/final-reports/{report_id}")
def get_final_report(report_id: int, db: Session = Depends(get_db), user: User = Depends(auth.get_current_user)):
    fr = _own_final_report(db, user, report_id)
    data = final_report_payload(fr, db)
    # Version chain (oldest first) so the view can show every version.
    chain, cursor = [], fr
    while cursor.amends_report_id:
        cursor = _own_final_report(db, user, cursor.amends_report_id)
        chain.insert(0, {"id": cursor.id, "status": cursor.status, "finalized_at": iso_utc(cursor.finalized_at)})
    data["previous_versions"] = chain
    data["comparisons"] = [
        {"id": c.id, "status": c.status, "created_at": iso_utc(c.created_at), "interval_days": c.interval_days,
         "baseline_report_id": c.baseline_report_id, "followup_report_id": c.followup_report_id}
        for c in db.query(Comparison).filter(
            Comparison.created_by == user.id, Comparison.status == "saved",
            (Comparison.baseline_report_id == fr.id) | (Comparison.followup_report_id == fr.id),
        ).order_by(Comparison.created_at.desc())
    ]
    return data


@router.post("/final-reports/{report_id}/amend")
def amend_final_report(report_id: int, body: AmendRequest, request: Request, db: Session = Depends(get_db),
                       user: User = Depends(auth.get_current_user)):
    original = _own_final_report(db, user, report_id)
    if db.query(FinalReport.id).filter(FinalReport.amends_report_id == original.id).first():
        _bad("This version has already been amended. Amend the latest version instead.", 409)
    text = body.final_text.strip()
    if text == original.final_text.strip():
        _bad("The amendment is identical to the current version")
    now = utcnow()
    amended = FinalReport(
        draft_id=original.draft_id, patient_id=original.patient_id, doctor_id=user.id, status="amended",
        amends_report_id=original.id, selected_variant=original.selected_variant, final_text=text,
        final_sections=None, exam_modality=original.exam_modality, exam_region=original.exam_region,
        exam_laterality=original.exam_laterality, exam_title=original.exam_title,
        patient_age_at_study=original.patient_age_at_study, age_unit=original.age_unit,
        study_date=original.study_date, source_input=original.source_input, flags=original.flags,
        flag_acknowledgements=original.flag_acknowledgements, flags_acknowledged_at=original.flags_acknowledged_at,
        prompt_version=original.prompt_version, model_id=original.model_id, finalized_at=now,
    )
    db.add(amended)
    db.commit()
    db.refresh(amended)
    log_audit_event(db, "REPORT_AMENDED", user_id=user.id, request=request, resource_type="final_report",
                    resource_id=amended.id)
    return final_report_payload(amended, db)


@router.post("/final-reports/{report_id}/export-event", status_code=204)
def record_export(report_id: int, request: Request, format: Literal["print", "copy"] = "print",
                  db: Session = Depends(get_db), user: User = Depends(auth.get_current_user)):
    fr = _own_final_report(db, user, report_id)
    log_audit_event(db, "FINAL_REPORT_EXPORTED", user_id=user.id, request=request, resource_type="final_report",
                    resource_id=fr.id, details={"format": format})
    return None
