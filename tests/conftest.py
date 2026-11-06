"""Test configuration: isolate every run in a throwaway SQLite database.

Must run before `database` is imported, so it lives in conftest.
"""
import os
import sys
import tempfile
from pathlib import Path

_tmp = tempfile.mkdtemp(prefix="repogen-tests-")
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", f"sqlite:///{_tmp}/test.db")
os.environ.setdefault("AUDIT_LOG_DIR", _tmp)
os.environ.setdefault("GROQ_API_KEY", "test-key-not-used")
os.environ.setdefault("SECRET_KEY", "test-secret")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
