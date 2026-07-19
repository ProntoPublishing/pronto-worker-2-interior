"""
E4 (1.7.5): publisher-line resolution + the Manus Amendment 2 gate.
The template placeholder must exist in both .tex files, the fill is
empty in legacy mode (byte-identical books), and resolve_imprint's
three postures behave.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from imprint import ImprintNotEligibleError, resolve_imprint

ROOT = os.path.join(os.path.dirname(__file__), "..")


class TestTemplates(unittest.TestCase):
    def test_placeholder_in_both_templates_exactly_once(self):
        for name in ("fiction_6x9.tex", "nonfiction_6x9.tex"):
            src = open(os.path.join(ROOT, name), encoding="utf-8").read()
            self.assertEqual(src.count("{{PUBLISHER_LINE}}"), 1, name)
            # It sits directly ahead of the machine's credit line.
            self.assertIn("{{PUBLISHER_LINE}}Interior design and "
                          "typesetting by Pronto Publishing", src)


class TestResolution(unittest.TestCase):
    def _client(self, imprint=None, default=None):
        c = MagicMock()
        c.get_imprint.return_value = imprint
        c.get_default_imprint.return_value = default
        return c

    def test_linked_without_string_raises(self):
        with self.assertRaises(ImprintNotEligibleError) as ctx:
            resolve_imprint({"Imprint": ["x"]},
                            self._client(imprint={"Flag": "Landfall Ink"}))
        self.assertIn("not E4-eligible", str(ctx.exception))

    def test_linked_with_string_resolves(self):
        r = resolve_imprint(
            {"Imprint": ["x"]},
            self._client(imprint={"Flag": "Landfall Ink",
                                  "Bowker Canonical String": "Landfall Ink"}))
        self.assertEqual(r["canonical"], "Landfall Ink")

    def test_no_link_default_eligible(self):
        r = resolve_imprint(
            {}, self._client(default={"Flag": "Landfall Ink",
                                      "Bowker Canonical String": "Landfall Ink",
                                      "E4 Default": True}))
        self.assertEqual(r["canonical"], "Landfall Ink")
        self.assertIn("default", r["source"])

    def test_no_link_no_eligible_default_is_legacy(self):
        r = resolve_imprint({}, self._client(default={"Flag": "Landfall Ink"}))
        self.assertEqual(r["canonical"], "Pronto Publishing")
        self.assertIn("legacy", r["source"])


if __name__ == "__main__":
    unittest.main()
