import json
import os
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import audit_file_logger
from database import AuditEvent
from audit_service import log_audit_event, csv_safe_cell


class AuditServiceTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        os.environ["AUDIT_LOG_DIR"] = self.tempdir.name
        audit_file_logger._logger.handlers.clear()
        audit_file_logger._configured = False
        self.engine = create_engine("sqlite:///:memory:")
        AuditEvent.__table__.create(self.engine)
        self.session = sessionmaker(bind=self.engine)()

    def tearDown(self):
        self.session.close()
        self.engine.dispose()
        self.tempdir.cleanup()
        os.environ.pop("AUDIT_LOG_DIR", None)
        for handler in audit_file_logger._logger.handlers:
            handler.close()
        audit_file_logger._logger.handlers.clear()
        audit_file_logger._configured = False

    def test_persists_json_and_excludes_sensitive_metadata(self):
        event = log_audit_event(
            self.session, "REPORT_GENERATED", user_id=None, status="SUCCESS",
            details={"workflow": "prompt", "patient_id": "secret", "medical_record_number": "secret",
                     "password": "secret", "token": "secret", "findings": "secret", "count": 3},
            duration_ms=123,
        )
        self.assertIsNotNone(event)
        saved = self.session.query(AuditEvent).one()
        self.assertEqual(saved.event_type, "REPORT_GENERATED")
        self.assertEqual(saved.details, {"workflow": "prompt"})
        output = Path(self.tempdir.name) / "audit.log"
        record = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(record["event_type"], "REPORT_GENERATED")
        self.assertNotIn("secret", output.read_text(encoding="utf-8"))
        self.assertEqual(output.stat().st_mode & 0o777, 0o640)

    def test_rejects_unknown_event(self):
        self.assertIsNone(log_audit_event(self.session, "PATIENT_REPORT_TEXT", details={"x": "y"}))
        self.assertEqual(self.session.query(AuditEvent).count(), 0)

    def test_csv_formula_prefixes_are_neutralized(self):
        for value in ("=1+1", "+cmd", "-2+3", "@SUM(A1:A2)", "\tformula", "\rformula"):
            self.assertEqual(csv_safe_cell(value), "'" + value)
        self.assertEqual(csv_safe_cell("safe text"), "safe text")

    def test_json_file_rotation_keeps_bounded_backups(self):
        log_audit_event(self.session, "LOGIN_SUCCESS")
        handler = audit_file_logger._logger.handlers[0]
        handler.maxBytes = 220
        handler.backupCount = 2
        for _ in range(8):
            log_audit_event(self.session, "LOGIN_SUCCESS", details={"purpose": "rotation test"})
        self.assertTrue((Path(self.tempdir.name) / "audit.log.1").exists())
        self.assertLessEqual(len(list(Path(self.tempdir.name).glob("audit.log.*"))), 2)
        for path in Path(self.tempdir.name).glob("audit.log*"):
            for line in path.read_text(encoding="utf-8").splitlines():
                json.loads(line)


if __name__ == "__main__":
    unittest.main()
