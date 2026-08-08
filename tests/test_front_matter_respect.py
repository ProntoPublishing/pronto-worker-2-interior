"""Front-Matter Contract v1 — W2 RESPECT battery (build #59).

Doc of record: 4 - Automation System/FrontMatter_Contract_v1.md.
Covers the W2-side rows of the contract battery:

  4. Copyright cross-check matrix (A3), all four verdicts.
  5. Manuscript with front matter + filled form → generators suppressed,
     manifest lists every ignored field (the collision notes).
  6. Bare manuscript + filled form → nothing suppressed (the regression
     lock that keeps today's books byte-identical).
  8. Dedication-only manuscript + dedication-filled form → author's
     dedication once, collision note recorded.
  9. Typed TOC → generated TOC suppressed + standing warning.
"""
from __future__ import annotations
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from front_matter_respect import (carried_classes, copyright_verdicts,
                                  element_text, suppression_decisions)


def artifact_with(carried, elements=None, blocks=None):
    return {
        "front_matter": {
            "carried": list(carried),
            "elements": elements or [],
        },
        "content": {"blocks": blocks or []},
    }


def blk(bid, text):
    return {"id": bid, "type": "paragraph",
            "spans": [{"text": text, "marks": []}]}


class TestDegradeSafe(unittest.TestCase):
    """Case 6 — an artifact with no front_matter section (a pre-contract
    W1) must suppress NOTHING: today's behavior, byte-identical."""

    def test_no_section_suppresses_nothing(self):
        suppress, notes = suppression_decisions(
            {"content": {"blocks": []}},
            {"dedication": "For my mother."})
        self.assertFalse(any(suppress.values()))
        self.assertEqual(notes, [])

    def test_none_artifact_safe(self):
        suppress, notes = suppression_decisions(None, {})
        self.assertFalse(any(suppress.values()))
        self.assertEqual(carried_classes(None), set())


class TestSuppressionAndCollisionNotes(unittest.TestCase):
    """Cases 5 + 8 — manuscript wins, and the ignored form field is
    named in a note (the ruling's collision rule)."""

    def test_dedication_suppressed_and_noted(self):
        suppress, notes = suppression_decisions(
            artifact_with(["dedication"]),
            {"dedication": "For my mother, who kept every letter."})
        self.assertTrue(suppress["dedication"])
        self.assertTrue(any("Dedication" in n and "ignored" in n
                            for n in notes),
                        f"no collision note naming the field: {notes}")

    def test_dedication_carried_without_form_value_notes_no_collision(self):
        suppress, notes = suppression_decisions(
            artifact_with(["dedication"]), {})
        self.assertTrue(suppress["dedication"])
        self.assertTrue(any("nothing ignored" in n for n in notes))

    def test_full_front_matter_suppresses_each(self):
        suppress, notes = suppression_decisions(
            artifact_with(["title_page", "dedication", "acknowledgements",
                           "about_the_author"]),
            {"dedication": "For M.",
             "acknowledgements": "Thanks to everyone.",
             "about_the_author": "She lives by the sea."})
        for cls in ("title_page", "dedication", "acknowledgements",
                    "about_the_author"):
            self.assertTrue(suppress[cls], cls)
        # every ignored field named
        for field in ("Dedication", "Acknowledgements", "About the Author"):
            self.assertTrue(any(field in n for n in notes), field)

    def test_uncarried_element_not_suppressed(self):
        suppress, _ = suppression_decisions(
            artifact_with(["dedication"]),
            {"acknowledgements": "Thanks."})
        self.assertTrue(suppress["dedication"])
        self.assertFalse(suppress["acknowledgements"])


class TestTypedToc(unittest.TestCase):
    """Case 9 — an authorial typed TOC wins, with the standing warning
    that its page numbers are probably wrong post-typeset."""

    def test_toc_suppressed_with_standing_warning(self):
        suppress, notes = suppression_decisions(
            artifact_with(["toc_authorial"]), {})
        self.assertTrue(suppress["toc_authorial"])
        self.assertTrue(any("page numbers" in n for n in notes), notes)


class TestCopyrightMatrix(unittest.TestCase):
    """Case 4 (A3) — the four verdicts, exactly as C ruled."""

    ASSIGNED = "978-1-971041-07-0"

    def test_absent_isbn_is_warning_not_hold(self):
        v = copyright_verdicts(
            "Copyright © 2026 Wren Calloway. All rights reserved.",
            assigned_isbn=self.ASSIGNED, imprint=None)
        self.assertEqual(len(v), 1)
        self.assertEqual(v[0]["level"], "warning")
        self.assertIn("no ISBN", v[0]["detail"])

    def test_different_isbn_holds(self):
        v = copyright_verdicts(
            "Copyright © 2026. ISBN 978-1-971041-99-9. All rights reserved.",
            assigned_isbn=self.ASSIGNED, imprint=None)
        self.assertTrue(any(x["level"] == "hold" for x in v), v)
        self.assertTrue(any("does NOT match" in x["detail"] for x in v))

    def test_matching_isbn_is_clean(self):
        v = copyright_verdicts(
            f"Copyright © 2026. ISBN {self.ASSIGNED}. All rights reserved.",
            assigned_isbn=self.ASSIGNED, imprint=None)
        self.assertEqual(v, [])

    def test_imprint_mismatch_holds(self):
        v = copyright_verdicts(
            f"Copyright © 2026. ISBN {self.ASSIGNED}. "
            f"Published by Landfall Ink.",
            assigned_isbn=self.ASSIGNED, imprint="First Blossom Books")
        self.assertTrue(any(x["level"] == "hold" for x in v), v)
        self.assertTrue(any("imprint" in x["detail"] for x in v))

    def test_imprint_present_is_clean(self):
        v = copyright_verdicts(
            f"Copyright © 2026. ISBN {self.ASSIGNED}. "
            f"Published by First Blossom Books.",
            assigned_isbn=self.ASSIGNED, imprint="First Blossom Books")
        self.assertEqual(v, [])

    def test_edition_strings_and_year_ignored(self):
        # Author voice: a different year / edition wording is never a
        # verdict, so long as ISBN + imprint agree.
        v = copyright_verdicts(
            f"Copyright © 1998 by the author. Third edition, revised. "
            f"ISBN {self.ASSIGNED}. Published by First Blossom Books. "
            f"Printed in the United States of America.",
            assigned_isbn=self.ASSIGNED, imprint="First Blossom Books")
        self.assertEqual(v, [])

    def test_hyphenation_differences_tolerated(self):
        v = copyright_verdicts(
            "Copyright © 2026. ISBN 9781971041070.",
            assigned_isbn=self.ASSIGNED, imprint=None)
        self.assertEqual(v, [])


class TestElementText(unittest.TestCase):
    """The cross-check's input: the author's page text, joined across
    its block range."""

    def test_joins_block_range(self):
        art = artifact_with(
            ["copyright_page"],
            elements=[{"class": "copyright_page",
                       "block_range": ["b2", "b3"],
                       "confidence": "high", "source": "manuscript"}],
            blocks=[blk("b1", "TITLE"), blk("b2", "Copyright © 2026."),
                    blk("b3", "ISBN 978-1-971041-07-0."),
                    blk("b4", "Body text here.")])
        text = element_text(art, "copyright_page")
        self.assertIn("Copyright", text)
        self.assertIn("ISBN", text)
        self.assertNotIn("Body text", text)
        self.assertNotIn("TITLE", text)

    def test_absent_element_returns_empty(self):
        self.assertEqual(element_text(artifact_with([]), "copyright_page"), "")


if __name__ == "__main__":
    unittest.main()
