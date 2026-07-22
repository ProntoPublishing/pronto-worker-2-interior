"""QA Reviewer v0 — W2 contract: _complete_service merges QA fields
into the canonical write. (The full render path is XeLaTeX-bound and
exercised in acceptance, not unit tests; the QA module itself is
covered by tests/test_qa.py.)"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _processor():
    # __init__ mkdirs /tmp/worker_2 (POSIX-only) and builds real
    # clients — _complete_service needs neither, so skip it.
    from pronto_worker_2 import InteriorProcessor
    p = InteriorProcessor.__new__(InteriorProcessor)
    p.airtable_client = MagicMock()
    p.airtable_client.update_service.return_value = True
    return p


class TestCompleteServiceQAFields(unittest.TestCase):
    def test_pass_fields_merged_on_complete(self):
        p = _processor()
        p._complete_service(
            service_id="svc1", pdf_url="https://r2/i", pdf_key="k",
            page_count=124, duration=1.0, degradations=[],
            review_reason=None,
            qa_fields={"QA Status": "Pass", "QA Report": "qa 0.1.0 ..."})
        fields = p.airtable_client.update_service.call_args.args[1]
        self.assertEqual(fields["Status"], "Complete")
        self.assertEqual(fields["QA Status"], "Pass")
        self.assertIn("QA Report", fields)

    def test_blocked_fields_merged_on_review(self):
        p = _processor()
        p._complete_service(
            service_id="svc1", pdf_url="https://r2/i", pdf_key="k",
            page_count=124, duration=1.0, degradations=[],
            review_reason="QA: r2_object: uploaded object missing",
            qa_fields={"QA Status": "Fail", "QA Report": "...",
                       "Blocked": True,
                       "Blocked Reason": "r2_object: uploaded object missing"})
        fields = p.airtable_client.update_service.call_args.args[1]
        self.assertEqual(fields["Status"], "Review")
        self.assertEqual(fields["QA Status"], "Fail")
        self.assertIs(fields["Blocked"], True)
        self.assertIn("r2_object", fields["Blocked Reason"])
        # artifact fields still written — ship-reviewable-output posture
        self.assertEqual(fields["Artifact Type"], "Interior PDF")

    def test_no_qa_fields_is_backward_compatible(self):
        p = _processor()
        p._complete_service(
            service_id="svc1", pdf_url="https://r2/i", pdf_key="k",
            page_count=124, duration=1.0, degradations=[],
            review_reason=None)
        fields = p.airtable_client.update_service.call_args.args[1]
        self.assertNotIn("QA Status", fields)
        self.assertNotIn("Blocked", fields)


if __name__ == "__main__":
    unittest.main()
