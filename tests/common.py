"""Shared setup for the test scripts. Each test is a standalone script:

    python3 tests/test_<name>.py     # or: for t in tests/test_*.py; do python3 $t; done

Import common FIRST (it wires env vars and sys.path), then call fresh_client().
Env overrides needed by a suite must be set before calling fresh_client().
"""

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "sdk"))

os.environ.setdefault("OPENSHELF_DNS_CHECK", "off")
os.environ.setdefault("OPENSHELF_RATE_LIMIT", "off")
os.environ["OPENSHELF_DB"] = os.path.join(tempfile.mkdtemp(prefix="openshelf-test-"), "test.sqlite")


def fresh_client():
    from fastapi.testclient import TestClient
    from server import main
    return TestClient(main.app), main
