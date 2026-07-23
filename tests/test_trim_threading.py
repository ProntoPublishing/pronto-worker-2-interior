"""Trims v0 — W2 contract: the ordered `Trim Size` is resolved against
trims.INTERIOR_TRIMS in _get_formatting_parameters; unsupported trims
set trim_hold (→ Review upstream, closing the pre-1.10 silent-6x9
gap); the system title page sink is per-trim with 6x9 byte-stable."""

import os
import sys
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import trims
from pronto_worker_2 import InteriorProcessor, _system_title_page_latex


def _processor(book_metadata):
    p = InteriorProcessor.__new__(InteriorProcessor)
    p.airtable_client = MagicMock()
    p.airtable_client.get_project.return_value = {"Book Metadata": ["bm1"]}
    p.airtable_client.get_book_metadata.return_value = book_metadata
    # E4 mocks explicitly nulled — a bare MagicMock is truthy and
    # impersonates an eligible imprint record.
    p.airtable_client.get_default_imprint.return_value = None
    p.airtable_client.get_imprint.return_value = None
    return p


SERVICE = {"Project": ["proj1"]}


class TestTrimResolution(unittest.TestCase):
    def _params(self, trim_value):
        bm = {"Book Title": "T", "Author Name": "A"}
        if trim_value is not None:
            bm["Trim Size"] = trim_value
        return _processor(bm)._get_formatting_parameters(SERVICE)

    def test_supported_trim_resolves(self):
        params = self._params('5" × 8"')
        self.assertNotIn("trim_hold", params)
        self.assertEqual(params["trim_name"], "5x8")
        self.assertEqual(params["trim_dims"], (5.0, 8.0))

    def test_all_interior_trims_resolve_via_every_spelling(self):
        for name in trims.INTERIOR_TRIM_NAMES:
            for spelling in trims.TRIMS[name].spellings():
                params = self._params(spelling)
                self.assertEqual(params.get("trim_name"), name, spelling)

    def test_select_dict_shape_unwrapped(self):
        params = self._params({"name": '6" × 9"'})
        self.assertEqual(params["trim_name"], "6x9")
        self.assertEqual(params["trim_dims"], (6.0, 9.0))

    def test_absent_defaults_to_6x9(self):
        params = self._params(None)
        self.assertEqual(params["trim_name"], "6x9")
        self.assertNotIn("trim_hold", params)

    def test_registered_but_unsupported_holds(self):
        # 8.5x11 is real (low-content lane) but not an interior trim.
        params = self._params('8.5" × 11"')
        self.assertIn("trim_hold", params)
        self.assertNotIn("trim_name", params)
        self.assertIn("8.5", params["trim_hold"])
        self.assertIn("supported", params["trim_hold"])

    def test_unregistered_literal_holds(self):
        params = self._params("4x6")
        self.assertIn("trim_hold", params)
        self.assertIn("'4x6'", params["trim_hold"])


class TestTitleSink(unittest.TestCase):
    def test_6x9_sink_byte_stable(self):
        # The shipped literal is \vspace*{2in} — 6x9 must format to
        # exactly that (no "2.0in").
        tex = _system_title_page_latex({"applied_rules": []},
                                       title_sink_in=2.0)
        self.assertIn("\\vspace*{2in}", tex)

    def test_default_matches_6x9(self):
        self.assertEqual(_system_title_page_latex({"applied_rules": []}),
                         _system_title_page_latex({"applied_rules": []},
                                                  title_sink_in=2.0))

    def test_per_trim_sinks(self):
        for name, expected in (("5x8", "1.8in"), ("5.5x8.5", "1.9in"),
                               ("6.14x9.21", "2.05in")):
            sink = trims.INTERIOR_GEOMETRY[name].title_sink_in
            tex = _system_title_page_latex({"applied_rules": []},
                                           title_sink_in=sink)
            self.assertIn(f"\\vspace*{{{expected}}}", tex, name)


class TestTemplatePresence(unittest.TestCase):
    def test_template_exists_for_every_interior_trim(self):
        root = os.path.join(os.path.dirname(__file__), "..")
        for name in trims.INTERIOR_TRIM_NAMES:
            for genre in ("fiction", "nonfiction"):
                path = os.path.join(root, f"{genre}_{name}.tex")
                self.assertTrue(os.path.exists(path), path)

    def test_new_templates_carry_uniform_margins_and_own_size(self):
        root = os.path.join(os.path.dirname(__file__), "..")
        expect_w = {"5x8": "5in", "5.25x8": "5.25in",
                    "5.5x8.5": "5.5in", "6.14x9.21": "6.14in"}
        for name, w in expect_w.items():
            src = open(os.path.join(root, f"fiction_{name}.tex"),
                       encoding="utf-8").read()
            self.assertIn(f"paperwidth={w},", src, name)
            self.assertIn("inner=0.85in,", src, name)
            self.assertIn("outer=0.65in,", src, name)
            self.assertIn("\\setstretch{1.066}", src, name)


if __name__ == "__main__":
    unittest.main()


class TestBindingResolution(unittest.TestCase):
    """Hardcover v0: Format routes the binding; the trim accept-table
    follows it; empty/unrecognized Format -> paperback + warning."""

    def _params(self, bm_extra):
        bm = {"Book Title": "T", "Author Name": "A"}
        bm.update(bm_extra)
        return _processor(bm)._get_formatting_parameters(SERVICE)

    def test_hardcover_7x10_resolves(self):
        params = self._params({"Format": {"name": "Hardcover"},
                               "Trim Size": '7" × 10"'})
        self.assertEqual(params["binding"], "hardcover")
        self.assertEqual(params["trim_name"], "7x10")
        self.assertEqual(params["trim_dims"], (7.0, 10.0))
        self.assertNotIn("trim_hold", params)

    def test_hardcover_8_25x11_resolves(self):
        params = self._params({"Format": "Hardcover",
                               "Trim Size": "8.25x11"})
        self.assertEqual(params["trim_name"], "8.25x11")

    def test_paperback_7x10_holds(self):
        params = self._params({"Trim Size": '7" × 10"'})
        self.assertEqual(params["binding"], "paperback")
        self.assertIn("trim_hold", params)
        self.assertIn("paperback", params["trim_hold"])

    def test_hardcover_5x8_holds(self):
        # 5x8 is not a KDP case-laminate size.
        params = self._params({"Format": "Hardcover", "Trim Size": "5x8"})
        self.assertIn("trim_hold", params)
        self.assertIn("hardcover", params["trim_hold"])

    def test_empty_format_defaults_paperback_with_warning(self):
        with self.assertLogs("pronto_worker_2", level="WARNING") as cm:
            params = self._params({"Trim Size": "6x9"})
        self.assertEqual(params["binding"], "paperback")
        self.assertTrue(any("format-default-paperback" in line
                            for line in cm.output))

    def test_shared_trim_same_template_both_bindings(self):
        # Interior is binding-agnostic at shared trims: same trim_name
        # -> same template file either way.
        pb = self._params({"Trim Size": '6" × 9"'})
        hc = self._params({"Format": "Hardcover", "Trim Size": '6" × 9"'})
        self.assertEqual(pb["trim_name"], hc["trim_name"])


class TestLargeFormatTemplates(unittest.TestCase):
    def test_12pt_templates_exist_and_carry_ruling(self):
        import trims as t
        root = os.path.join(os.path.dirname(__file__), "..")
        expect = {"7x10": ("7in", "1.0in", "0.8in", "1.066"),
                  "8.25x11": ("8.25in", "1.35in", "1.35in", "1.15")}
        for name, (w, inner, outer, stretch) in expect.items():
            for genre in ("fiction", "nonfiction"):
                path = os.path.join(root, f"{genre}_{name}.tex")
                self.assertTrue(os.path.exists(path), path)
                src = open(path, encoding="utf-8").read()
                self.assertIn("\documentclass[12pt,openany]{book}", src, path)
                self.assertIn(f"paperwidth={w},", src, path)
                self.assertIn(f"inner={inner},", src, path)
                self.assertIn(f"outer={outer},", src, path)
                self.assertIn(f"\setstretch{{{stretch}}}", src, path)
                self.assertIn("headheight=15pt,", src, path)
