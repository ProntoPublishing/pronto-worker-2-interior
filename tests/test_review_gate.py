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

from lib.warning_handler import (
    WarningHandler, title_cluster_page_break_warning,
)


def w(rule, severity="medium", detail="d"):
    return {"rule": rule, "severity": severity, "detail": detail}


def tp(bid, text="t", **extra):
    """A title_page-role paragraph block."""
    b = {"id": bid, "type": "paragraph", "role": "title_page",
         "spans": [{"text": text, "marks": []}]}
    b.update(extra)
    return b


def body(bid, text="body", **extra):
    b = {"id": bid, "type": "paragraph", "role": "body_paragraph",
         "spans": [{"text": text, "marks": []}]}
    b.update(extra)
    return b


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


class TestV007ClusterBreakCheck(unittest.TestCase):
    """W2-side V-007 synthesis (tripwire, 2026-07-16): the C-003 title
    cluster spanning a manual page break must produce a medium gating
    warning. Break evidence is force_page_break: true (W1 5.2.1-a1
    observation) or an explicit page_break block inside the span."""

    def setUp(self):
        self.h = WarningHandler()

    def test_book15_shape_fires_and_gates(self):
        """Title + subtitle + author, manual break, absorbed dedication."""
        blocks = [
            tp("b1", "WHAT THE TIDE LEAVES"),
            tp("b2", "a novel"),
            tp("b3", "Naomi Cartwright"),
            body("b4", ""),
            tp("b5", "For my sister, who stayed.", force_page_break=True),
            body("b6", "Chapter text."),
        ]
        warning = title_cluster_page_break_warning(blocks)
        self.assertIsNotNone(warning)
        self.assertEqual(warning["rule"], "V-007")
        self.assertEqual(warning["severity"], "medium")
        self.assertIn("b5", warning["detail"])
        self.assertIn("verify title page / subtitle", warning["detail"])
        # And it routes through the Review gate.
        self.assertIsNotNone(self.h.requires_review([warning]))

    def test_break_on_non_member_inside_span_fires(self):
        """Book 01's fleuron shape: a body_paragraph inside the cluster
        span carrying the break observation still counts."""
        blocks = [
            tp("b1"), body("b2", "orphan", force_page_break=True), tp("b3"),
        ]
        self.assertIsNotNone(title_cluster_page_break_warning(blocks))

    def test_explicit_page_break_block_inside_span_fires(self):
        blocks = [
            tp("b1"),
            {"id": "b2", "type": "page_break", "role": "structural"},
            tp("b3"),
        ]
        self.assertIsNotNone(title_cluster_page_break_warning(blocks))

    def test_break_before_cluster_does_not_fire(self):
        """A cover page before the title page is normal layout."""
        blocks = [
            body("b0", "cover"),
            tp("b1", force_page_break=True),  # break BEFORE first member
            tp("b2"),
            body("b3"),
        ]
        self.assertIsNone(title_cluster_page_break_warning(blocks))

    def test_break_after_cluster_does_not_fire(self):
        """Hatch/Book-15 chapter breaks: first content after the cluster
        (chapter heading) carries the observation — outside the span."""
        blocks = [
            tp("b1"), tp("b2"),
            {"id": "b3", "type": "heading", "heading_level": 2,
             "role": "chapter_heading", "spans": [{"text": "Chapter One",
                                                   "marks": []}],
             "force_page_break": True},
        ]
        self.assertIsNone(title_cluster_page_break_warning(blocks))

    def test_no_cluster_does_not_fire(self):
        blocks = [body("b1", force_page_break=True), body("b2")]
        self.assertIsNone(title_cluster_page_break_warning(blocks))

    def test_single_member_cluster_does_not_fire(self):
        blocks = [tp("b1"), body("b2", force_page_break=True)]
        self.assertIsNone(title_cluster_page_break_warning(blocks))

    def test_pre_521_artifact_fails_open(self):
        """Artifacts from W1 <= 5.2.0-a1 carry no break observations —
        the check returns None (pre-tripwire behavior)."""
        blocks = [tp("b1"), body("b2", ""), tp("b3"), body("b4", "text")]
        self.assertIsNone(title_cluster_page_break_warning(blocks))

    def test_v007_does_not_change_build_decision(self):
        blocks = [tp("b1"), tp("b2", force_page_break=True)]
        warning = title_cluster_page_break_warning(blocks)
        decision = self.h.evaluate([warning])
        self.assertEqual(decision.action, "PROCEED")


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
