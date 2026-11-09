"""Central audit event creation. Callers must pass operational metadata only."""
import ipaddress
import json
import logging
import os
import uuid
from datetime import datetime, timezone

from database import AuditEvent
from audit_file_logger import write_audit_file

logger = logging.getLogger("repogen.audit.pipeline")
SAFE_EVENTS = {
    "LOGIN_SUCCESS", "LOGIN_FAILED", "LOGOUT", "SESSION_EXPIRED",
    "REPORT_GENERATED", "REPORT_GENERATION_FAILED", "REPORT_VIEWED",
    "REPORT_DOWNLOADED", "REPORT_UPDATED", "REPORT_STATUS_CHANGED",
    "USER_CREATED", "USER_UPDATED", "USER_DEACTIVATED", "USER_ROLE_CHANGED",
    "PASSWORD_CHANGED", "PASSWORD_RESET", "ACCESS_DENIED", "ADMIN_ACTION",
    "AUDIT_CSV_EXPORTED", "API_ERROR",
    "PATIENT_CREATED", "PATIENT_UPDATED", "REPORT_FINALIZED", "REPORT_AMENDED",
    "FINAL_REPORT_EXPORTED", "COMPARISON_GENERATED", "COMPARISON_GENERATION_FAILED", "COMPARISON_SAVED",
    "REPORT_FLAG_REVIEWED",
}
SAFE_DETAIL_KEYS = {
    "workflow", "variants", "failure_category", "auth_method", "role", "operation",
    "status", "format", "expiration_source", "filters_applied", "resource",
    "attempts", "examinations_comparable", "interval_adjusted",
}


def csv_safe_cell(value):
    """Neutralize spreadsheet formulas in values exported to CSV."""
    value = "" if value is None else str(value)
    if value.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + value
    return value


def _client_ip(request):
    client = getattr(request, "client", None) if request is not None else None
    if client is None:
        return None
    peer = client.host
    trusted = [x.strip() for x in os.getenv("TRUSTED_PROXY_IPS", "").split(",") if x.strip()]
    try:
        if any(ipaddress.ip_address(peer) in ipaddress.ip_network(net, strict=False) for net in trusted):
            forwarded = getattr(request, "headers", {}).get("x-forwarded-for", "").split(",")[0].strip()
            return str(ipaddress.ip_address(forwarded)) if forwarded else peer
    except ValueError:
        return peer
    return peer


def log_audit_event(db, action, user_id=None, status="SUCCESS", request=None,
                    details=None, duration_ms=None, resource_type=None, resource_id=None):
    """Persist to PostgreSQL and independently append to rotating JSONL.

    Return the database event when committed. Pipeline failures are reported to
    the application error logger and never turn authentication into a bypass.
    """
    if action not in SAFE_EVENTS:
        logger.error("Rejected unknown audit event type %r", action)
        return None
    # Limit values and keys; no caller-provided clinical payloads are accepted.
    clean_details = {}
    for key, value in (details or {}).items():
        key = str(key)[:64].lower()
        if key not in SAFE_DETAIL_KEYS:
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            clean_details[key] = str(value)[:256] if isinstance(value, str) else value
    request_id = getattr(getattr(request, "state", None), "request_id", None) if request else None
    if not request_id and request:
        request_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc)
    payload = {
        "timestamp": timestamp.isoformat().replace("+00:00", "Z"),
        "event_type": action, "user_id": user_id, "status": status,
        "resource_type": resource_type[:80] if resource_type else None,
        "resource_id": str(resource_id)[:128] if resource_id is not None else None,
        "ip_address": _client_ip(request),
        "user_agent": getattr(request, "headers", {}).get("user-agent", "")[:512] if request else None,
        "request_id": str(request_id)[:64] if request_id else None,
        "duration_ms": max(0, int(duration_ms)) if duration_ms is not None else None,
        "details": clean_details,
    }
    event = None
    try:
        event = AuditEvent(event_type=action, user_id=user_id, status=status,
                           resource_type=payload["resource_type"], resource_id=payload["resource_id"],
                           ip_address=payload["ip_address"], user_agent=payload["user_agent"],
                           request_id=payload["request_id"], duration_ms=payload["duration_ms"],
                           details=clean_details, created_at=timestamp)
        db.add(event)
        db.commit()
        db.refresh(event)
    except Exception:
        db.rollback()
        logger.exception("Audit database write failed for %s", action)
    try:
        write_audit_file(payload)
    except Exception:
        logger.exception("Audit file write failed for %s", action)
    return event

