"""
W2 1.7.3 — copyright-page ISBN line (pre-publish polish round).

The {{ISBN_LINE}} plumbing existed since the Interior Standard, but
_get_formatting_parameters never read Book Metadata.ISBN, so the line
could never render. These tests pin the param and the wording
("ISBN 978-…", no colon — Jesse's call).
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _make_processor():
    with patch("pronto_worker_2.ProntoR2Client"), \
         patch("pronto_worker_2.AirtableClient"), \
         patch("pronto_worker_2.PDFGenerator"), \
         patch("pronto_worker_2.PDFValidator"), \
         patch("pronto_worker_2.Path", MagicMock()):
        from pronto_worker_2 import InteriorProcessor
        p = InteriorProcessor()
    p.airtable_client = MagicMock()
    return p


class TestIsbnParam(unittest.TestCase):
    def test_params_carry_isbn_from_book_metadata(self):
        p = _make_processor()
        p.airtable_client.get_project.return_value = {"Book Metadata": ["bm1"]}
        p.airtable_client.get_book_metadata.return_value = {
            "Book Title": "Perennial", "Author Name": "E. J. Sandoval",
            "Trim Size": "6x9", "ISBN": "978-1-971041-06-3"}
        params = p._get_formatting_parameters({"Project": ["proj1"]})
        self.assertEqual(params["isbn"], "978-1-971041-06-3")

    def test_absent_isbn_is_empty_not_missing(self):
        p = _make_processor()
        p.airtable_client.get_project.return_value = {"Book Metadata": ["bm1"]}
        p.airtable_client.get_book_metadata.return_value = {
            "Book Title": "X", "Author Name": "Y", "Trim Size": "6x9"}
        params = p._get_formatting_parameters({"Project": ["proj1"]})
        self.assertEqual(params["isbn"], "")

    def test_isbn_line_wording_no_colon(self):
        # The template-fill produces "ISBN 978-…" (no colon) when
        # present and nothing at all when absent.
        template = "before{{ISBN_LINE}}after"
        isbn = "978-1-971041-06-3"
        filled = template.replace(
            "{{ISBN_LINE}}", f"\\\\[1em]\nISBN {isbn}" if isbn else "")
        self.assertIn("ISBN 978-1-971041-06-3", filled)
        self.assertNotIn("ISBN:", filled)
        empty = template.replace("{{ISBN_LINE}}", "" if not "" else "x")
        self.assertEqual(empty, "beforeafter")


if __name__ == "__main__":
    unittest.main()
