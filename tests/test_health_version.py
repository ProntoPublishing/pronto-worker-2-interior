"""
Regression test for /health version drift.

The /health endpoint once hardcoded its own version string ('1.2.0'),
separate from the worker's real version constant — so deploys looked
like they never landed. These tests pin /health to the single
WORKER_VERSION constant in pronto_worker_2.py.

Run with:
    python -m unittest tests.test_health_version
"""
from __future__ import annotations
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from pronto_worker_2 import WORKER_VERSION
import app as app_module


class Test_HealthVersion(unittest.TestCase):

    def test_health_reports_worker_version(self):
        client = app_module.app.test_client()
        resp = client.get('/health')
        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json()
        self.assertEqual(
            payload['version'], WORKER_VERSION,
            "/health must report the WORKER_VERSION constant from "
            "pronto_worker_2.py — a mismatch means a duplicate hardcoded "
            "version literal has crept back into app.py.",
        )
        self.assertEqual(payload['status'], 'healthy')

    def test_worker_version_matches_instance_attribute_default(self):
        """InteriorProcessor.__init__ must use the same constant; guard
        against the attribute being re-hardcoded independently. We read
        the source rather than instantiating, since __init__ builds R2
        and Airtable clients that need live credentials.
        """
        source = (REPO_ROOT / "pronto_worker_2.py").read_text(encoding="utf-8")
        self.assertIn("self.worker_version = WORKER_VERSION", source)


if __name__ == '__main__':
    unittest.main()
