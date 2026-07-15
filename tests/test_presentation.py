"""Presentation-layer tests (Interior Standard v1 arc): running-header
marks, asterism scene breaks, header-mark truncation."""
from __future__ import annotations
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.blocks_to_latex import BlocksToLatexConverter


def conv():
    return BlocksToLatexConverter()


def para(text):
    return {"id": "b1", "role": "body_paragraph", "type": "paragraph",
            "spans": [{"text": text, "marks": []}]}


class TestHeaderMarks(unittest.TestCase):
    def test_starred_chapter_sets_mark(self):
        out = conv()._render_chapter_heading(
            {"id": "b1", "role": "chapter_heading",
             "chapter_number": 4, "chapter_title": "Letter IV"}, {})
        self.assertIn("\\markright{Letter IV}", out)

    def test_numbered_chapter_sets_truncated_mark(self):
        long_title = ("WHICH TREATS OF THE CHARACTER AND PURSUITS OF THE "
                      "FAMOUS GENTLEMAN DON QUIXOTE OF LA MANCHA")
        out = conv()._render_chapter_heading(
            {"id": "b1", "role": "chapter_heading",
             "chapter_number": 1, "chapter_title": long_title}, {})
        self.assertIn("\\markright{", out)
        mark = out.split("\\markright{", 1)[1].split("}", 1)[0]
        self.assertLessEqual(len(mark), 60)
        self.assertTrue(mark.endswith("…"))

    def test_part_divider_clears_mark(self):
        out = conv()._render_part_divider(
            {"id": "b1", "role": "part_divider", "part_number": 2,
             "part_title": "Volume II", "force_page_break": True}, {})
        self.assertIn("\\markright{}", out)

    def test_caption_lines_not_in_mark(self):
        out = conv()._render_chapter_heading(
            {"id": "b1", "role": "chapter_heading", "chapter_number": 2,
             "chapter_title": "Chapter II\nThe caption line"}, {})
        mark = out.split("\\markright{", 1)[1].split("}", 1)[0]
        self.assertEqual(mark, "Chapter II")


class TestAsterismSceneBreaks(unittest.TestCase):
    POSITIVES = ["* * *", "***", "~", "• • •", "—", "* * * * *", "###"]
    NEGATIVES = [
        "It was a dark night.",
        "*emphatic* start of a paragraph",
        "",
        "3 - 2 - 1",   # digits — not ornament-only
    ]

    def test_ornament_paragraphs_become_scenebreak(self):
        for s in self.POSITIVES:
            with self.subTest(s=s):
                self.assertEqual(
                    conv()._render_body_paragraph(para(s), {}),
                    "\\scenebreak", f"{s!r} should be a scene break")

    def test_prose_untouched(self):
        for s in self.NEGATIVES:
            with self.subTest(s=s):
                self.assertNotEqual(
                    conv()._render_body_paragraph(para(s), {}),
                    "\\scenebreak", f"{s!r} must not be a scene break")

    def test_scene_break_role_still_renders(self):
        out = conv()._render_scene_break(
            {"id": "b1", "role": "scene_break"}, {})
        self.assertEqual(out, "\\scenebreak")


if __name__ == "__main__":
    unittest.main()
