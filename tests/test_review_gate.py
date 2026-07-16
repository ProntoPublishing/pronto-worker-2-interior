"""Review gate tests — Gate 2 ruling Q4 (2026-07-16).

A gating warning (V-005 zero-structure; V-006 pre-wired for rules 1.2)
at severity >= medium builds the book fully but completes the service
as Status=Review instead of Complete. H-001 stays warn-only.
"""
from __future__ import annotations
import sys
import unittest
from unittest.mock import MagicMock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.warning_handler import WarningHandler


def w(rule, severity="medium", detail="d"):
    return {"rule": rule, "severity": severity, "detail": detail}


class TestRequiresReview(unittest.TestCase):
    def setUp(self):
        self.h = WarningHandler()

    def test_v005_medium_gates(self):
        reason = self.h.requires_review([w("V-005", "medium",
                                           "zero structural roles across 798 blocks")])
        self.assertIsNotNone(reason)
        self.assertIn("V-005", reason)
        self.assertIn("zero structural roles", reason)

    def test_v006_medium_gates_prewired(self):
        # Training wheels: rules 1.2's pattern-only promotion warning
        # routes through the same gate until downgraded to info.
        self.assertIsNotNone(self.h.requires_review([w("V-006")]))

    def test_h001_medium_does_not_gate(self):
        # Warn-only per ruling: test intakes always mismatch.
        self.assertIsNone(self.h.requires_review(
            [w("H-001", "medium", "title differs")]))

    def test_low_severity_does_not_gate(self):
        self.assertIsNone(self.h.requires_review([w("V-005", "low")]))

    def test_high_severity_gates(self):
        self.assertIsNotNone(self.h.requires_review([w("V-005", "high")]))

    def test_empty_and_none_do_not_gate(self):
        self.assertIsNone(self.h.requires_review([]))
        self.assertIsNone(self.h.requires_review(None))

    def test_mixed_reports_only_gating_rules(self):
        reason = self.h.requires_review([
            w("C-001", "low", "fused heading"),
            w("H-001", "medium", "title differs"),
            w("V-005", "medium", "zero structure"),
        ])
        self.assertIn("V-005", reason)
        self.assertNotIn("H-001", reason)
        self.assertNotIn("C-001", reason)

    def test_gate_does_not_change_build_decision(self):
        # The review gate is a separate axis: the same warnings still
        # evaluate to PROCEED for the build itself.
        warnings = [w("V-005", "medium")]
        decision = self.h.evaluate(warnings)
        self.assertEqual(decision.action, "PROCEED")
        self.assertIsNotNone(self.h.requires_review(warnings))


class TestCompleteServiceStatus(unittest.TestCase):
    """_complete_service writes Review + typecast iff a review reason
    is present; plain Complete (no typecast) otherwise."""

    def _processor(self):
        from pronto_worker_2 import InteriorProcessor
        p = InteriorProcessor.__new__(InteriorProcessor)  # skip env-dependent __init__
        p.airtable_client = MagicMock()
        return p

    def test_review_reason_sets_review_status_with_typecast(self):
        p = self._processor()
        p._complete_service(
            service_id="recX", pdf_url="u", pdf_key="k",
            page_count=162, duration=4.2, degradations=None,
            review_reason="V-005: zero structural roles",
        )
        (sid, fields), kwargs = p.airtable_client.update_service.call_args
        self.assertEqual(fields["Status"], "Review")
        self.assertTrue(kwargs.get("typecast"))
        self.assertIn("V-005", fields["Operator Notes"])

    def test_no_reason_sets_complete_without_typecast(self):
        p = self._processor()
        p._complete_service(
            service_id="recX", pdf_url="u", pdf_key="k",
            page_count=342, duration=5.9, degradations=None,
        )
        (sid, fields), kwargs = p.airtable_client.update_service.call_args
        self.assertEqual(fields["Status"], "Complete")
        self.assertFalse(kwargs.get("typecast"))
        self.assertNotIn("review_gate", fields["Operator Notes"])


if __name__ == "__main__":
    unittest.main()
