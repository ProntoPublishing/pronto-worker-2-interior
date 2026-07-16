"""Label-shaped chapter titles (rules-1.1 coordination): titles that
are just the heading label ("Letter IV", "Stave ONE", "Chapter XXVII")
with an integer chapter_number must render ONCE via \\chapter*,
preserving the source's section word and ordinal style."""
from __future__ import annotations
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.blocks_to_latex import BlocksToLatexConverter


def render(block):
    conv = BlocksToLatexConverter()
    return conv._render_chapter_heading(block, {})


class TestLabelShapedTitles(unittest.TestCase):
    def test_letter_roman_int_number(self):
        out = render({"id": "b1", "role": "chapter_heading",
                      "chapter_number": 4, "chapter_title": "Letter IV"})
        self.assertIn("\\chapter*{\\prontolabel{Letter IV}}", out)
        self.assertNotIn("\\setcounter", out)

    def test_stave_word_ordinal(self):
        out = render({"id": "b1", "role": "chapter_heading",
                      "chapter_number": 1, "chapter_title": "Stave ONE"})
        self.assertIn("\\chapter*{\\prontolabel{Stave ONE}}", out)

    def test_chapter_roman_from_fused_source(self):
        out = render({"id": "b1", "role": "chapter_heading",
                      "chapter_number": 27, "chapter_title": "Chapter XXVII"})
        self.assertIn("\\chapter*{\\prontolabel{Chapter XXVII}}", out)

    def test_mismatched_ordinal_is_not_label(self):
        # Title says IV but the artifact number is 5 — not label-shaped;
        # render numbered so the artifact's ordinal wins visibly.
        out = render({"id": "b1", "role": "chapter_heading",
                      "chapter_number": 5, "chapter_title": "Letter IV"})
        self.assertIn("\\setcounter{chapter}{4}", out)
        self.assertIn("\\chapter{Letter IV}", out)

    def test_real_title_still_numbered(self):
        # DQ shape: a genuine trailing title renders on the numbered path.
        out = render({"id": "b1", "role": "chapter_heading",
                      "chapter_number": 1,
                      "chapter_title": "WHICH TREATS OF THE CHARACTER"})
        self.assertIn("\\setcounter{chapter}{0}", out)
        self.assertIn("\\chapter{WHICH TREATS OF THE CHARACTER}", out)

    def test_legacy_string_number_path_unchanged(self):
        # rules-1.0.2 artifacts: chapter_number "IV" + synthesized
        # "Chapter IV" — the original equality check still fires.
        out = render({"id": "b1", "role": "chapter_heading",
                      "chapter_number": "IV", "chapter_title": "Chapter IV"})
        self.assertIn("\\chapter*{\\prontolabel{Chapter IV}}", out)

    def test_caption_lines_still_render_beneath(self):
        out = render({"id": "b1", "role": "chapter_heading",
                      "chapter_number": 2,
                      "chapter_title": "Chapter II\nThe efforts of his aunt"})
        self.assertIn("\\chapter*{\\prontolabel{Chapter II}}", out)
        self.assertIn("The efforts of his aunt", out)
        self.assertIn("\\itshape", out)


if __name__ == "__main__":
    unittest.main()
