"""
W2 1.7.1 — Interior Page Count structured field (W3 spec R1 / §9.4).

The INTFMT Service gets the counted page total as a number field at
completion. Cross-check only: W3 recounts from the artifact and the
counted value stays canonical. Completion must NEVER depend on the
field existing — if Airtable rejects the write (field not created
yet), the service still completes via the fallback retry.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _make_processor():
    # Path is patched because the constructor mkdirs /tmp/worker_2 —
    # fine on the Railway Linux image, absent on a Windows dev box.
    with patch("pronto_worker_2.ProntoR2Client"), \
         patch("pronto_worker_2.AirtableClient"), \
         patch("pronto_worker_2.PDFGenerator"), \
         patch("pronto_worker_2.PDFValidator"), \
         patch("pronto_worker_2.Path", MagicMock()):
        from pronto_worker_2 import InteriorProcessor
        p = InteriorProcessor()
    p.airtable_client = MagicMock()
    return p


class TestInteriorPageCountField(unittest.TestCase):
    def test_complete_writes_structured_page_count(self):
        p = _make_processor()
        p.airtable_client.update_service.return_value = True
        p._complete_service(
            service_id="svc1", pdf_url="u", pdf_key="k",
            page_count=74, duration=1.0, degradations=None,
        )
        p.airtable_client.update_service.assert_called_once()
        fields = p.airtable_client.update_service.call_args.args[1]
        self.assertEqual(fields["Interior Page Count"], 74)
        self.assertEqual(fields["Status"], "Complete")
        # Operator Notes blob keeps carrying it too (unchanged behavior)
        self.assertIn('"page_count": 74', fields["Operator Notes"])

    def test_completion_survives_missing_airtable_field(self):
        p = _make_processor()
        # First write rejected (field doesn't exist), retry succeeds.
        p.airtable_client.update_service.side_effect = [False, True]
        p._complete_service(
            service_id="svc1", pdf_url="u", pdf_key="k",
            page_count=74, duration=1.0, degradations=None,
        )
        self.assertEqual(p.airtable_client.update_service.call_count, 2)
        retry_fields = p.airtable_client.update_service.call_args_list[1].args[1]
        self.assertNotIn("Interior Page Count", retry_fields)
        self.assertEqual(retry_fields["Status"], "Complete")

    def test_review_path_carries_field_and_typecast(self):
        p = _make_processor()
        p.airtable_client.update_service.return_value = True
        p._complete_service(
            service_id="svc1", pdf_url="u", pdf_key="k",
            page_count=28, duration=1.0, degradations=None,
            review_reason="V-007: title cluster crosses a manual page break",
        )
        call = p.airtable_client.update_service.call_args
        self.assertEqual(call.args[1]["Status"], "Review")
        self.assertEqual(call.args[1]["Interior Page Count"], 28)
        self.assertTrue(call.kwargs["typecast"])


if __name__ == "__main__":
    unittest.main()
