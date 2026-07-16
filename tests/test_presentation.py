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


class TestTitlePageInvariant(unittest.TestCase):
    """§6 review invariant (2026-07-16): exactly one title page per
    book, in the front-matter §3 slot, never in the body. The converter
    ALWAYS suppresses title_page-role blocks in body output; the slot
    is filled by render_title_page_cluster() (H-001 fired) or the
    system page (not fired) at the template-fill layer."""

    CLUSTER = [
        {"id": "b1", "role": "title_page", "type": "paragraph",
         "spans": [{"text": "Pride and Prejudice", "marks": []}],
         "classification_notes": ["title_page positional role: title"]},
        {"id": "b2", "role": "title_page", "type": "paragraph",
         "spans": [{"text": "Jane Austen", "marks": []}],
         "classification_notes": ["title_page positional role: author_or_byline"]},
    ]

    def test_body_always_suppresses_title_page_blocks(self):
        out = conv().convert(self.CLUSTER, params={})
        self.assertNotIn("Pride and Prejudice", out)
        self.assertNotIn("Jane Austen", out)
        # One traceability comment per suppressed block.
        self.assertEqual(out.count("title_page block"), 2)

    def test_slot_builder_renders_cluster_in_order(self):
        out = conv().render_title_page_cluster(self.CLUSTER)
        self.assertIn("Pride and Prejudice", out)
        self.assertIn("Jane Austen", out)
        self.assertLess(out.index("Pride and Prejudice"), out.index("Jane Austen"))
        # Folio-free recto that ends the page (copyright lands verso).
        self.assertIn("\\thispagestyle{empty}", out)
        self.assertTrue(out.rstrip().endswith("\\clearpage"))
        # Title sized above the rest.
        self.assertIn("\\Huge\\textbf{Pride and Prejudice}", out)
        self.assertIn("{\\large Jane Austen}", out)

    def test_slot_builder_ignores_non_cluster_blocks(self):
        blocks = self.CLUSTER + [
            {"id": "b3", "role": "body_paragraph", "type": "paragraph",
             "spans": [{"text": "It is a truth universally acknowledged", "marks": []}]},
        ]
        out = conv().render_title_page_cluster(blocks)
        self.assertNotIn("truth universally", out)

    def test_slot_builder_empty_cluster_is_safe(self):
        out = conv().render_title_page_cluster([])
        self.assertNotIn("\\thispagestyle", out)
        self.assertTrue(out.startswith("%"))


class TestCustomerNeutralStandIns(unittest.TestCase):
    """§6 review fix (2026-07-16): no internal phrases in rendered
    output — no doc references, no version strings, never the word
    'placeholder'."""

    def test_table_stand_in_is_neutral(self):
        out = conv()._render_table({"id": "b1", "role": "table"}, {})
        for phrase in ("doc 22", "cir", "placeholder", "v1.0"):
            self.assertNotIn(phrase, out.lower())
        self.assertIn("[Table omitted from this edition]", out)

    def test_image_stand_in_is_neutral(self):
        out = conv()._render_image({"id": "b1", "role": "image"}, {})
        self.assertNotIn("placeholder", out.lower())
        self.assertIn("[Illustration omitted from this edition]", out)


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
