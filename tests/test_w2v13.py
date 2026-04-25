"""
W2 v1.3 — feature/consume-manuscript-v2 test suite.

Iter 1 lays the foundation: regression tests for the {{CONTENT}}
template trap and the count=1 substitution defense. Subsequent
iterations add tests for the artifact dispatcher, v1 reader, v2 reader,
and the v2-native converter.

Run with:
    python -m unittest tests.test_w2v13
or
    python -m unittest discover tests
"""
from __future__ import annotations
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


# ---------------------------------------------------------------------------
# Iter 1 — {{CONTENT}} template trap regression
# ---------------------------------------------------------------------------

class Test_TemplateContentPlaceholder(unittest.TestCase):
    """Each template carries exactly ONE {{CONTENT}} literal — the
    real placeholder. The duplication bug returns the moment a second
    literal sneaks back in (e.g., inside a LaTeX % comment) because
    str.replace() substitutes every occurrence and the multi-line body
    breaks out of the '%' comment at its first newline.
    """

    TEMPLATES = ("fiction_6x9.tex", "nonfiction_6x9.tex")

    def test_each_template_has_exactly_one_content_placeholder(self):
        for name in self.TEMPLATES:
            path = REPO_ROOT / name
            self.assertTrue(path.exists(), f"missing template: {name}")
            text = path.read_text(encoding="utf-8")
            count = text.count("{{CONTENT}}")
            self.assertEqual(
                count, 1,
                f"{name} has {count} occurrences of {{{{CONTENT}}}}; "
                f"expected exactly 1. The duplication bug returns "
                f"whenever a second literal is added (especially in a "
                f"% comment, where the '%' only protects up to the "
                f"first newline of the substituted body).",
            )

    def test_each_template_substitution_inserts_body_once(self):
        """End-to-end check: the count=1 path in pronto_worker_2.py
        substitutes the body in exactly one place. We simulate the
        substitution against a multi-line body and assert the
        resulting .tex contains the body exactly once.
        """
        body = (
            "\\textbf{The Long Quiet}\n\n"
            "\\textit{A Gentle Guide to Moving Through Depression}\n\n"
            "\\chapter{Opening}\n\n"
            "Body of chapter one.\n"
        )
        for name in self.TEMPLATES:
            tpl = (REPO_ROOT / name).read_text(encoding="utf-8")
            # Mirror the production substitution.
            filled = (
                tpl
                .replace("{{CONTENT}}", body, 1)
                .replace("{{BOOK_TITLE}}", "The Long Quiet")
                .replace("{{AUTHOR_NAME}}", "Test Author")
                .replace("{{FONT_NAME}}", "EB Garamond")
                .replace("{{YEAR}}", "2026")
                .replace("{{ISBN}}", "")
            )
            occurrences = filled.count(body)
            self.assertEqual(
                occurrences, 1,
                f"{name}: body appears {occurrences} time(s) after "
                f"substitution; expected exactly 1."
            )


class Test_PythonReplaceCount(unittest.TestCase):
    """Defense-in-depth check on the worker code itself. Even if a
    template regression slipped through, the Python substitution must
    hard-cap to one substitution.
    """

    def test_pronto_worker_2_uses_count_1_for_content(self):
        path = REPO_ROOT / "pronto_worker_2.py"
        src = path.read_text(encoding="utf-8")
        # The CONTENT replacement line must specify count=1 (positional
        # third arg to str.replace). We grep for the line and assert
        # the count.
        marker = '.replace("{{CONTENT}}"'
        self.assertIn(marker, src, "CONTENT placeholder substitution missing")
        # Find the line that does the CONTENT substitution and check it
        # carries the count argument.
        for line in src.splitlines():
            if marker in line:
                # Three string literals in this line are illegal: the
                # placeholder, the body var, and a count=N integer. We
                # just check that "1)" appears at the end (with the
                # body identifier between the placeholder and the count).
                self.assertTrue(
                    ", 1)" in line,
                    f"CONTENT replace line missing count=1: {line!r}"
                )
                break
        else:
            self.fail("could not find the CONTENT substitution line")


# ---------------------------------------------------------------------------
# Iter 2 — artifact reader dispatcher + v1 upgrader + v2 identity
# ---------------------------------------------------------------------------

from lib.artifact_readers import (
    read_artifact,
    UnsupportedSchemaVersionError,
)


def _minimal_v1_artifact(blocks):
    """Build a minimal v1.0 artifact wrapper around a blocks list."""
    return {
        "schema_version": "1.0",
        "artifact_type": "manuscript",
        "artifact_version": "1",
        "source": {"original_filename": "x.docx", "original_format": "docx"},
        "processing": {
            "worker_name": "worker_1_manuscript_processor",
            "worker_version": "4.1.0",
            "service_id": "recSVC123",
            "processed_at": "2026-04-24T00:00:00Z",
        },
        "content": {"blocks": blocks},
        "analysis": {"warnings": []},
    }


def _minimal_v2_artifact(blocks):
    """Build a minimal v2.0 artifact wrapper around a blocks list."""
    return {
        "schema_version": "2.0",
        "worker_version": "5.0.0-a1",
        "rules_version": "1.0.2",
        "artifact_type": "manuscript",
        "artifact_id": "art_test",
        "service_id": "recSVC123",
        "source": {
            "original_filename": "x.docx",
            "original_format": "docx",
            "source_hash_sha256": "a" * 64,
            "ingested_at": "2026-04-24T00:00:00Z",
        },
        "processing": {
            "worker_name": "worker_1_manuscript_processor",
            "run_id": "run_test",
            "project_id": "recPROJ",
            "processed_at": "2026-04-24T00:00:01Z",
        },
        "content": {"blocks": blocks},
        "applied_rules": [],
        "warnings": [],
        "rule_faults": [],
    }


class Test_Dispatcher(unittest.TestCase):

    def test_dispatches_v1_to_upgrader(self):
        art = _minimal_v1_artifact([
            {"id": "b_000001", "type": "paragraph", "text": "Hello."},
        ])
        out = read_artifact(art)
        self.assertEqual(out["schema_version"], "2.0")
        self.assertEqual(out["content"]["blocks"][0]["role"], "body_paragraph")
        # The caller's object must not have been mutated.
        self.assertEqual(art["schema_version"], "1.0")

    def test_dispatches_v11_to_upgrader(self):
        art = _minimal_v1_artifact([
            {"id": "b_000001", "type": "paragraph",
             "spans": [{"text": "Hello.", "marks": []}]}
        ])
        art["schema_version"] = "1.1"
        out = read_artifact(art)
        self.assertEqual(out["schema_version"], "2.0")

    def test_dispatches_v2_to_identity_reader(self):
        art = _minimal_v2_artifact([
            {"id": "b_000001", "type": "paragraph", "role": "body_paragraph",
             "spans": [{"text": "Hi.", "marks": []}]}
        ])
        out = read_artifact(art)
        self.assertEqual(out["schema_version"], "2.0")
        self.assertEqual(out["content"]["blocks"][0]["role"], "body_paragraph")

    def test_unknown_version_raises(self):
        art = {"schema_version": "9.9", "content": {"blocks": []}}
        with self.assertRaises(UnsupportedSchemaVersionError) as cm:
            read_artifact(art)
        self.assertIn("9.9", str(cm.exception))
        self.assertIn("1.0", str(cm.exception))
        self.assertIn("2.0", str(cm.exception))

    def test_non_dict_raises(self):
        with self.assertRaises(TypeError):
            read_artifact("not a dict")  # type: ignore[arg-type]


class Test_V1Reader_TypeMapping(unittest.TestCase):
    """Each v1 type maps to a defined v2 (CIR type, role) pair plus
    role-specific fields. One test per mapping line.
    """

    def _read_one(self, v1_block):
        art = _minimal_v1_artifact([v1_block])
        return read_artifact(art)["content"]["blocks"][0]

    def test_paragraph(self):
        out = self._read_one({"id": "b_000001", "type": "paragraph",
                              "text": "Hello world."})
        self.assertEqual(out["type"], "paragraph")
        self.assertEqual(out["role"], "body_paragraph")
        self.assertEqual(out["spans"], [{"text": "Hello world.", "marks": []}])

    def test_heading(self):
        out = self._read_one({"id": "b_000001", "type": "heading",
                              "text": "A Sub-Section",
                              "meta": {"level": 3}})
        self.assertEqual(out["type"], "heading")
        self.assertEqual(out["role"], "heading")
        self.assertEqual(out["heading_level"], 3)

    def test_chapter_heading_with_number_and_title(self):
        out = self._read_one({"id": "b_000013", "type": "chapter_heading",
                              "text": "Chapter 1\nWhat Depression Actually Is",
                              "meta": {"chapter_number": 1}})
        self.assertEqual(out["role"], "chapter_heading")
        self.assertEqual(out["chapter_number"], 1)
        self.assertEqual(out["chapter_title"], "What Depression Actually Is")

    def test_chapter_heading_number_only_synthesizes_title(self):
        out = self._read_one({"id": "b_000013", "type": "chapter_heading",
                              "text": "Chapter 5"})
        self.assertEqual(out["chapter_number"], 5)
        self.assertEqual(out["chapter_title"], "Chapter 5")
        self.assertIn("synthesized", " ".join(out.get("classification_notes", [])))

    def test_chapter_heading_unparseable_text_keeps_full_title(self):
        out = self._read_one({"id": "b_000013", "type": "chapter_heading",
                              "text": "Prologue"})
        self.assertIsNone(out["chapter_number"])
        self.assertEqual(out["chapter_title"], "Prologue")
        self.assertIn("not extractable", " ".join(out.get("classification_notes", [])))

    def test_front_matter_dedication(self):
        out = self._read_one({"id": "b_000001", "type": "front_matter_dedication",
                              "text": "For everyone."})
        self.assertEqual(out["role"], "front_matter")
        self.assertEqual(out["subtype"], "dedication")

    def test_front_matter_copyright_preserves_subtype(self):
        out = self._read_one({"id": "b_000001", "type": "front_matter_copyright",
                              "text": "Copyright 2026."})
        self.assertEqual(out["role"], "front_matter")
        self.assertEqual(out["subtype"], "copyright")

    def test_back_matter_about_author(self):
        out = self._read_one({"id": "b_000001", "type": "back_matter_about_author",
                              "text": "About the Author"})
        self.assertEqual(out["role"], "back_matter")
        self.assertEqual(out["subtype"], "about_the_author")

    def test_back_matter_also_by_preserves_subtype(self):
        out = self._read_one({"id": "b_000001", "type": "back_matter_also_by",
                              "text": "Also By"})
        self.assertEqual(out["subtype"], "also_by")

    def test_scene_break_role(self):
        out = self._read_one({"id": "b_000001", "type": "scene_break"})
        self.assertEqual(out["role"], "scene_break")

    def test_horizontal_rule_maps_to_structural(self):
        out = self._read_one({"id": "b_000001", "type": "horizontal_rule"})
        self.assertEqual(out["type"], "horizontal_rule")
        self.assertEqual(out["role"], "structural")
        self.assertNotIn("spans", out)  # structural blocks carry no text

    def test_page_break_maps_to_structural(self):
        out = self._read_one({"id": "b_000001", "type": "page_break"})
        self.assertEqual(out["type"], "page_break")
        self.assertEqual(out["role"], "structural")

    def test_toc_marker_carries_a_classification_note(self):
        out = self._read_one({"id": "b_000001", "type": "toc_marker"})
        self.assertEqual(out["role"], "structural")
        self.assertTrue(any("toc_marker" in n for n in out.get("classification_notes", [])))

    def test_unknown_v1_type_does_not_silently_drop(self):
        out = self._read_one({"id": "b_000001", "type": "totally_made_up",
                              "text": "Mystery content."})
        self.assertEqual(out["role"], "body_paragraph")
        self.assertEqual(out["spans"][0]["text"], "Mystery content.")
        self.assertTrue(any("unknown v1 block type" in n for n in out["classification_notes"]))


class Test_V1Reader_ManuscriptMeta(unittest.TestCase):

    def test_front_matter_title_populates_manuscript_meta(self):
        art = _minimal_v1_artifact([
            {"id": "b_000001", "type": "front_matter_title",
             "text": "The Long Quiet"},
            {"id": "b_000002", "type": "paragraph", "text": "Body."},
        ])
        out = read_artifact(art)
        self.assertIn("manuscript_meta", out)
        self.assertEqual(out["manuscript_meta"]["title"], "The Long Quiet")
        self.assertIsNone(out["manuscript_meta"]["subtitle"])
        self.assertIsNone(out["manuscript_meta"]["author"])

    def test_no_title_no_meta_section(self):
        art = _minimal_v1_artifact([
            {"id": "b_000001", "type": "paragraph", "text": "Body."},
        ])
        out = read_artifact(art)
        self.assertNotIn("manuscript_meta", out)


class Test_V1Reader_TextSpansHandling(unittest.TestCase):

    def test_text_only_block_becomes_single_span(self):
        out = read_artifact(_minimal_v1_artifact([
            {"id": "b_000001", "type": "paragraph", "text": "Plain."}
        ]))
        block = out["content"]["blocks"][0]
        self.assertEqual(block["spans"], [{"text": "Plain.", "marks": []}])

    def test_spans_block_passes_through_with_marks(self):
        out = read_artifact(_minimal_v1_artifact([
            {"id": "b_000001", "type": "paragraph",
             "spans": [{"text": "italic ", "marks": ["italic"]},
                       {"text": "plain", "marks": []}]}
        ]))
        block = out["content"]["blocks"][0]
        self.assertEqual(block["spans"][0]["text"], "italic ")
        self.assertEqual(block["spans"][0]["marks"], ["italic"])

    def test_v1_warnings_promoted_to_top_level(self):
        art = _minimal_v1_artifact([
            {"id": "b_000001", "type": "paragraph", "text": "Body."},
        ])
        art["analysis"]["warnings"] = [
            {"code": "OCR_QUALITY_ISSUES", "severity": "medium",
             "detail": "possible OCR artifacts"},
        ]
        out = read_artifact(art)
        self.assertEqual(len(out["warnings"]), 1)
        # v1 codes get wrapped under V-000 since they don't match V-###/H-###.
        self.assertEqual(out["warnings"][0]["rule"], "V-000")
        self.assertIn("OCR_QUALITY_ISSUES", out["warnings"][0]["detail"])


class Test_V2Reader(unittest.TestCase):

    def test_pass_through(self):
        art = _minimal_v2_artifact([
            {"id": "b_000001", "type": "paragraph", "role": "body_paragraph",
             "spans": [{"text": "Hi.", "marks": []}]}
        ])
        out = read_artifact(art)
        self.assertEqual(out["content"]["blocks"][0]["role"], "body_paragraph")

    def test_block_without_role_raises(self):
        """I-2 enforcement: producer must have applied terminal default."""
        art = _minimal_v2_artifact([
            {"id": "b_000001", "type": "paragraph",
             "spans": [{"text": "no role here", "marks": []}]}
        ])
        with self.assertRaises(ValueError) as cm:
            read_artifact(art)
        self.assertIn("I-2", str(cm.exception))

    def test_empty_blocks_raises(self):
        art = _minimal_v2_artifact([])
        # _minimal_v2_artifact already gave us an empty blocks list.
        with self.assertRaises(ValueError):
            read_artifact(art)

    def test_missing_required_field_raises(self):
        art = _minimal_v2_artifact([
            {"id": "b_000001", "type": "paragraph", "role": "body_paragraph",
             "spans": [{"text": "Hi.", "marks": []}]}
        ])
        del art["source"]
        with self.assertRaises(ValueError):
            read_artifact(art)


if __name__ == "__main__":
    unittest.main(verbosity=2)
