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


class TestTitlePageCoordination(unittest.TestCase):
    """§6 review fix (2026-07-16): exactly one title page per document.
    When H-001 did NOT fire the template emits the system title page and
    the converter must suppress the classified source title cluster."""

    CLUSTER = [
        {"id": "b1", "role": "title_page", "type": "paragraph",
         "spans": [{"text": "Pride and Prejudice", "marks": []}],
         "classification_notes": ["title_page positional role: title"]},
        {"id": "b2", "role": "title_page", "type": "paragraph",
         "spans": [{"text": "Jane Austen", "marks": []}],
         "classification_notes": ["title_page positional role: author_or_byline"]},
    ]

    def test_suppressed_when_system_page_selected(self):
        out = conv().convert(self.CLUSTER, params={}, suppress_title_page=True)
        self.assertNotIn("Pride and Prejudice", out)
        self.assertNotIn("Jane Austen", out)
        self.assertNotIn("\\vspace*{1in}", out)  # cluster title signature
        self.assertIn("suppressed", out)  # traceability comments remain

    def test_renders_when_h001_fired(self):
        out = conv().convert(self.CLUSTER, params={}, suppress_title_page=False)
        self.assertIn("Pride and Prejudice", out)
        self.assertIn("Jane Austen", out)

    def test_default_is_render(self):
        # Back-compat: callers not passing the flag keep old behavior.
        out = conv().convert(self.CLUSTER, params={})
        self.assertIn("Pride and Prejudice", out)


class TestCustomerNeutralStandIns(unittest.TestCase):
    """§6 review fix (2026-07-16): no internal phrases in rendered
    output — no doc references, never the word 'placeholder'."""

    def test_table_stand_in_is_neutral(self):
        out = conv()._render_table({"id": "b1", "role": "table"}, {})
        for phrase in ("Doc 22", "CIR", "placeholder"):
            self.assertNotIn(phrase.lower(), out.lower())
        self.assertIn("[Table]", out)

    def test_image_stand_in_is_neutral(self):
        out = conv()._render_image({"id": "b1", "role": "image"}, {})
        self.assertNotIn("placeholder", out.lower())
        self.assertIn("[Illustration]", out)


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
