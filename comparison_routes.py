"""Comparison of two final reports for the same patient (Phase 6).

Scoped to the signed-in doctor. Only report text, exam fields and the
interval are sent to the LLM; see model/comparison.py.
"""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import auth
import model.model as model
from audit_service import log_audit_event
from clinical_routes import final_report_payload, patient_payload
from clinical import get_patient_for_doctor
from database import Comparison, FinalReport, User, get_db, iso_utc
from model import comparison as cmp
from rate_limit import enforce_rate_limit

router = APIRouter(prefix="/api")


class CreateComparison(BaseModel):
    report_ids: list[int] = Field(min_length=2, max_length=2)


class UpdateComparison(BaseModel):
    edited_summary: Optional[str] = Field(default=None, max_length=10_000)
    edited_impression: Optional[list[str]] = Field(default=None, max_length=50)
    status: Optional[Literal["draft", "saved"]] = None


def _order(a: FinalReport, b: FinalReport) -> tuple[FinalReport, FinalReport]:
    """Baseline is the earlier study_date; on a tie the caller's order is kept."""
    return (b, a) if b.study_date < a.study_date else (a, b)


def list_item(c: Comparison, db: Session) -> dict:
    dates = dict(db.query(FinalReport.id, FinalReport.study_date)
                 .filter(FinalReport.id.in_([c.baseline_report_id, c.followup_report_id])).all())
    return {
        "id": c.id, "status": c.status, "created_at": iso_utc(c.created_at), "interval_days": c.interval_days,
        "baseline_report_id": c.baseline_report_id, "followup_report_id": c.followup_report_id,
        "baseline_study_date": dates.get(c.baseline_report_id).isoformat() if dates.get(c.baseline_report_id) else None,
        "followup_study_date": dates.get(c.followup_report_id).isoformat() if dates.get(c.followup_report_id) else None,
    }


def comparison_payload(c: Comparison, db: Session) -> dict:
    baseline = db.get(FinalReport, c.baseline_report_id)
    followup = db.get(FinalReport, c.followup_report_id)
    data = list_item(c, db)
    data.update({
        "patient": patient_payload(baseline.patient),
        "baseline": final_report_payload(baseline, db),
        "followup": final_report_payload(followup, db),
        "result": c.result,
        "edited_summary": c.edited_summary,
        "edited_impression": c.edited_impression,
        "prompt_version": c.prompt_version,
        "model_id": c.model_id,
        "updated_at": iso_utc(c.updated_at),
    })
    return data


def _own_comparison(db: Session, user: User, comparison_id: int) -> Comparison:
    c = db.query(Comparison).filter(Comparison.id == comparison_id, Comparison.created_by == user.id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Comparison not found")
    return c


def _run(db: Session, user: User, request: Request, baseline: FinalReport, followup: FinalReport) -> Comparison:
    enforce_rate_limit(user.id, "comparison", limit=10)
    interval = (followup.study_date - baseline.study_date).days
    identifiers = [baseline.patient.full_name, baseline.patient.patient_identifier or ""]

    def side(fr: FinalReport) -> cmp.ExamSide:
        return cmp.ExamSide(modality=fr.exam_modality, region=fr.exam_region, laterality=fr.exam_laterality,
                            text=cmp.scrub_identifiers(fr.final_text, identifiers))

    try:
        result, attempts, adjusted = cmp.generate_comparison(side(baseline), side(followup), interval)
    except model.GenerationError:
        log_audit_event(db, "COMPARISON_GENERATION_FAILED", user_id=user.id, request=request, status="FAILED",
                        resource_type="patient", resource_id=baseline.patient_id,
                        details={"failure_category": "invalid_model_output"})
        raise HTTPException(status_code=502, detail=model.GenerationError.user_message)
    except model.ProviderBusyError:
        log_audit_event(db, "COMPARISON_GENERATION_FAILED", user_id=user.id, request=request, status="FAILED",
                        resource_type="patient", resource_id=baseline.patient_id,
                        details={"failure_category": "provider_rate_limited"})
        raise HTTPException(status_code=503, detail=model.ProviderBusyError.user_message)
    except Exception:
        log_audit_event(db, "COMPARISON_GENERATION_FAILED", user_id=user.id, request=request, status="FAILED",
                        resource_type="patient", resource_id=baseline.patient_id,
                        details={"failure_category": "generation_error"})
        raise HTTPException(status_code=500, detail="Failed to generate comparison")

    c = Comparison(patient_id=baseline.patient_id, baseline_report_id=baseline.id, followup_report_id=followup.id,
                   interval_days=interval, result=result.model_dump(), status="draft",
                   prompt_version=cmp.COMPARISON_PROMPT_VERSION, model_id=model.GROQ_MODEL, created_by=user.id)
    db.add(c)
    db.commit()
    db.refresh(c)
    log_audit_event(db, "COMPARISON_GENERATED", user_id=user.id, request=request, resource_type="comparison",
                    resource_id=c.id, details={"attempts": attempts, "interval_adjusted": adjusted,
                                               "examinations_comparable": result.examinations_comparable})
    return c


@router.post("/comparisons")
def create_comparison(body: CreateComparison, request: Request, db: Session = Depends(get_db),
                      user: User = Depends(auth.get_current_user)):
    a_id, b_id = body.report_ids
    if a_id == b_id:
        raise HTTPException(status_code=422, detail="Choose two different reports")
    rows = {fr.id: fr for fr in db.query(FinalReport).filter(FinalReport.id.in_([a_id, b_id]),
                                                            FinalReport.doctor_id == user.id)}
    if len(rows) != 2:
        raise HTTPException(status_code=404, detail="Final report not found")
    a, b = rows[a_id], rows[b_id]
    if a.patient_id != b.patient_id or not get_patient_for_doctor(db, user.id, a.patient_id):
        raise HTTPException(status_code=422, detail="Both reports must belong to the same patient")
    baseline, followup = _order(a, b)
    return comparison_payload(_run(db, user, request, baseline, followup), db)


@router.get("/comparisons/{comparison_id}")
def get_comparison(comparison_id: int, db: Session = Depends(get_db), user: User = Depends(auth.get_current_user)):
    return comparison_payload(_own_comparison(db, user, comparison_id), db)


@router.patch("/comparisons/{comparison_id}")
def update_comparison(comparison_id: int, body: UpdateComparison, request: Request, db: Session = Depends(get_db),
                      user: User = Depends(auth.get_current_user)):
    c = _own_comparison(db, user, comparison_id)
    if body.edited_summary is not None:
        c.edited_summary = body.edited_summary
    if body.edited_impression is not None:
        c.edited_impression = [s.strip() for s in body.edited_impression if s.strip()]
    if body.status:
        c.status = body.status
    db.commit()
    db.refresh(c)
    if body.status == "saved":
        log_audit_event(db, "COMPARISON_SAVED", user_id=user.id, request=request, resource_type="comparison",
                        resource_id=c.id)
    return comparison_payload(c, db)


@router.post("/comparisons/{comparison_id}/regenerate")
def regenerate_comparison(comparison_id: int, request: Request, db: Session = Depends(get_db),
                          user: User = Depends(auth.get_current_user)):
    old = _own_comparison(db, user, comparison_id)
    baseline = db.get(FinalReport, old.baseline_report_id)
    followup = db.get(FinalReport, old.followup_report_id)
    return comparison_payload(_run(db, user, request, baseline, followup), db)


@router.get("/patients/{patient_id}/comparisons")
def patient_comparisons(patient_id: int, db: Session = Depends(get_db), user: User = Depends(auth.get_current_user)):
    if not get_patient_for_doctor(db, user.id, patient_id):
        raise HTTPException(status_code=404, detail="Patient not found")
    rows = (db.query(Comparison).filter(Comparison.patient_id == patient_id, Comparison.created_by == user.id,
                                        Comparison.status == "saved")
            .order_by(Comparison.created_at.desc()).all())
    return [list_item(c, db) for c in rows]
