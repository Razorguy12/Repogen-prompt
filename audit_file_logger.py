"""Restricted rotating JSONL sink for audit events."""
import json
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from datetime import datetime, timezone

_logger = logging.getLogger("repogen.audit")
_configured = False


class JsonFormatter(logging.Formatter):
    def format(self, record):
        payload = getattr(record, "audit_payload", {})
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


class RestrictedRotatingFileHandler(RotatingFileHandler):
    def _open(self):
        stream = super()._open()
        os.chmod(self.baseFilename, 0o640)
        return stream


def get_audit_logger():
    global _configured
    if _configured:
        return _logger
    _logger.setLevel(logging.INFO)
    _logger.propagate = False
    log_dir = Path(os.getenv("AUDIT_LOG_DIR", "/var/log/repogen"))
    try:
        log_dir.mkdir(parents=True, exist_ok=True, mode=0o750)
        os.chmod(log_dir, 0o750)
        handler = RestrictedRotatingFileHandler(log_dir / "audit.log", maxBytes=10 * 1024 * 1024,
                                                backupCount=10, encoding="utf-8")
        os.chmod(log_dir / "audit.log", 0o640)
        handler.setFormatter(JsonFormatter())
        _logger.addHandler(handler)
    except OSError:
        # Keep the logger usable; the caller also records operational sink failures.
        _logger.addHandler(logging.NullHandler())
        raise
    _configured = True
    return _logger


def write_audit_file(payload):
    logger = get_audit_logger()
    logger.info("audit", extra={"audit_payload": payload})

