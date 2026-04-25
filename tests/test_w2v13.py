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


# ---------------------------------------------------------------------------
# Iter 3 — v2-native blocks-to-LaTeX converter
# ---------------------------------------------------------------------------

from lib.blocks_to_latex import BlocksToLatexConverter, ROLES


class Test_ConverterCoverage(unittest.TestCase):

    def test_every_role_has_a_handler(self):
        c = BlocksToLatexConverter()
        self.assertEqual(set(c.HANDLER_MAP.keys()), set(ROLES))

    def test_init_refuses_partial_coverage(self):
        """If someone removes a handler from HANDLER_MAP, __init__ must
        fail loudly per the contract-first design.
        """
        class Broken(BlocksToLatexConverter):
            HANDLER_MAP = {k: v for k, v in BlocksToLatexConverter.HANDLER_MAP.items()
                           if k != "chapter_heading"}
        with self.assertRaises(RuntimeError) as cm:
            Broken()
        self.assertIn("chapter_heading", str(cm.exception))


class Test_ConverterChapterHeading(unittest.TestCase):
    """The doubled-chapter bug from The Long Quiet dies here. With
    chapter_number and chapter_title separated, \\chapter{title} carries
    only the title; the template's titlesec config provides "CHAPTER N".
    No prefix-in-title duplication.
    """

    def setUp(self):
        self.c = BlocksToLatexConverter()

    def test_numbered_chapter_uses_chapter_command(self):
        block = {
            "id": "b_000001", "type": "heading", "heading_level": 2,
            "role": "chapter_heading",
            "chapter_number": 1,
            "chapter_title": "What Depression Actually Is",
        }
        out = self.c.convert([block], params={})
        self.assertIn("\\chapter{What Depression Actually Is}", out)
        # Critical: the title alone, not "Chapter 1\nWhat Depression..."
        self.assertNotIn("Chapter 1\\nWhat", out)
        self.assertNotIn("Chapter 1 What", out)

    def test_null_chapter_number_uses_chapter_star(self):
        block = {
            "id": "b_000001", "type": "heading", "heading_level": 2,
            "role": "chapter_heading",
            "chapter_number": None,
            "chapter_title": "Prologue",
        }
        out = self.c.convert([block], params={})
        self.assertIn("\\chapter*{Prologue}", out)
        self.assertIn("\\addcontentsline{toc}{chapter}{Prologue}", out)


class Test_ConverterPartDivider(unittest.TestCase):

    def test_part_divider_clears_page_then_emits_part(self):
        """I-5: part_divider always carries force_page_break: true.
        The converter honors it explicitly with \\clearpage so the
        rendered .tex shows the break in source.
        """
        block = {
            "id": "b_000001", "type": "heading", "heading_level": 1,
            "role": "part_divider",
            "part_number": 1, "part_title": "Understanding",
            "force_page_break": True,
        }
        out = BlocksToLatexConverter().convert([block], params={})
        # \clearpage precedes \part*
        cp_idx = out.index("\\clearpage")
        part_idx = out.index("\\part*{Understanding}")
        self.assertLess(cp_idx, part_idx)
        self.assertIn("\\addcontentsline{toc}{part}{Understanding}", out)


class Test_ConverterFrontBackMatter(unittest.TestCase):

    def setUp(self):
        self.c = BlocksToLatexConverter()

    def test_dedication_renders_centered_italic_with_clearpage(self):
        block = {
            "id": "b_000001", "type": "paragraph",
            "role": "front_matter", "subtype": "dedication",
            "title": "For everyone.",
            "spans": [{"text": "For everyone.", "marks": []}],
        }
        out = self.c.convert([block], params={})
        self.assertIn("\\begin{center}", out)
        self.assertIn("\\textit{For everyone.}", out)
        self.assertIn("\\clearpage", out)

    def test_copyright_renders_flushleft_small(self):
        block = {
            "id": "b_000001", "type": "paragraph",
            "role": "front_matter", "subtype": "copyright",
            "title": "Copyright 2026 by Author.",
            "spans": [{"text": "Copyright 2026 by Author.", "marks": []}],
        }
        out = self.c.convert([block], params={})
        self.assertIn("\\begin{flushleft}", out)
        self.assertIn("\\small", out)

    def test_generic_front_matter_uses_chapter_star(self):
        block = {
            "id": "b_000001", "type": "heading", "heading_level": 1,
            "role": "front_matter", "subtype": "note_to_reader",
            "title": "A Note Before You Begin",
            "spans": [{"text": "A Note Before You Begin", "marks": []}],
        }
        out = self.c.convert([block], params={})
        self.assertIn("\\chapter*{A Note Before You Begin}", out)
        self.assertIn("\\addcontentsline{toc}{chapter}{A Note Before You Begin}", out)

    def test_back_matter_renders_chapter_star_with_toc(self):
        block = {
            "id": "b_000001", "type": "heading", "heading_level": 1,
            "role": "back_matter", "subtype": "about_the_author",
            "title": "About the Author",
            "spans": [{"text": "About the Author", "marks": []}],
        }
        out = self.c.convert([block], params={})
        self.assertIn("\\chapter*{About the Author}", out)


class Test_ConverterListGrouping(unittest.TestCase):

    def setUp(self):
        self.c = BlocksToLatexConverter()

    def test_consecutive_unordered_list_items_wrap_in_itemize(self):
        blocks = [
            {"id": "b_001", "type": "list_item", "role": "list_item",
             "spans": [{"text": "First", "marks": []}]},
            {"id": "b_002", "type": "list_item", "role": "list_item",
             "spans": [{"text": "Second", "marks": []}]},
            {"id": "b_003", "type": "paragraph", "role": "body_paragraph",
             "spans": [{"text": "After.", "marks": []}]},
        ]
        out = self.c.convert(blocks, params={})
        self.assertIn("\\begin{itemize}", out)
        self.assertIn("\\end{itemize}", out)
        # Wrap closes BEFORE the body paragraph.
        self.assertLess(out.index("\\end{itemize}"), out.index("After."))
        self.assertIn("\\item First", out)
        self.assertIn("\\item Second", out)

    def test_ordered_list_items_use_enumerate(self):
        blocks = [
            {"id": "b_001", "type": "list_item", "role": "list_item",
             "list_ordered": True,
             "spans": [{"text": "Step 1", "marks": []}]},
            {"id": "b_002", "type": "list_item", "role": "list_item",
             "list_ordered": True,
             "spans": [{"text": "Step 2", "marks": []}]},
        ]
        out = self.c.convert(blocks, params={})
        self.assertIn("\\begin{enumerate}", out)
        self.assertIn("\\end{enumerate}", out)
        self.assertNotIn("\\begin{itemize}", out)

    def test_switching_ordering_closes_and_reopens(self):
        blocks = [
            {"id": "b_001", "type": "list_item", "role": "list_item",
             "spans": [{"text": "Bullet", "marks": []}]},
            {"id": "b_002", "type": "list_item", "role": "list_item",
             "list_ordered": True,
             "spans": [{"text": "Number", "marks": []}]},
        ]
        out = self.c.convert(blocks, params={})
        self.assertIn("\\begin{itemize}", out)
        self.assertIn("\\end{itemize}", out)
        self.assertIn("\\begin{enumerate}", out)
        self.assertIn("\\end{enumerate}", out)
        # itemize ends before enumerate begins.
        self.assertLess(out.index("\\end{itemize}"), out.index("\\begin{enumerate}"))

    def test_list_at_end_of_document_is_closed(self):
        blocks = [
            {"id": "b_001", "type": "list_item", "role": "list_item",
             "spans": [{"text": "Last item", "marks": []}]},
        ]
        out = self.c.convert(blocks, params={})
        self.assertIn("\\end{itemize}", out)


class Test_ConverterSpansAndEscaping(unittest.TestCase):

    def setUp(self):
        self.c = BlocksToLatexConverter()

    def test_body_paragraph_renders_marks(self):
        block = {
            "id": "b_001", "type": "paragraph", "role": "body_paragraph",
            "spans": [
                {"text": "It was a ", "marks": []},
                {"text": "dark", "marks": ["italic"]},
                {"text": " and ", "marks": []},
                {"text": "stormy", "marks": ["bold"]},
                {"text": " night.", "marks": []},
            ],
        }
        out = self.c.convert([block], params={})
        self.assertIn("\\textit{dark}", out)
        self.assertIn("\\textbf{stormy}", out)

    def test_special_chars_escape_outside_marks(self):
        """C3 fix from the contract-v1.1 work: every span's text is
        escaped before mark-wrapping, so unmarked $/%/& don't slip
        through into LaTeX command position.
        """
        block = {
            "id": "b_001", "type": "paragraph", "role": "body_paragraph",
            "spans": [
                {"text": "$100 & 50% off", "marks": []},
            ],
        }
        out = self.c.convert([block], params={})
        self.assertIn(r"\$100 \& 50\% off", out)

    def test_special_chars_escape_inside_marked_span(self):
        block = {
            "id": "b_001", "type": "paragraph", "role": "body_paragraph",
            "spans": [
                {"text": "$pricey", "marks": ["italic"]},
            ],
        }
        out = self.c.convert([block], params={})
        self.assertIn(r"\textit{\$pricey}", out)


class Test_ConverterStructural(unittest.TestCase):

    def setUp(self):
        self.c = BlocksToLatexConverter()

    def test_page_break_renders_clearpage(self):
        block = {"id": "b_001", "type": "page_break", "role": "structural"}
        out = self.c.convert([block], params={})
        self.assertIn("\\clearpage", out)

    def test_horizontal_rule_renders_rule(self):
        block = {"id": "b_001", "type": "horizontal_rule", "role": "structural"}
        out = self.c.convert([block], params={})
        self.assertIn("\\rule{", out)

    def test_scene_break_uses_template_command(self):
        block = {"id": "b_001", "type": "paragraph", "role": "scene_break"}
        out = self.c.convert([block], params={})
        self.assertIn("\\scenebreak", out)


class Test_ConverterEndToEndAcrossUpgrade(unittest.TestCase):
    """Upgrade a v1.0 artifact through read_artifact() and feed the
    blocks to the converter. Verifies the dispatcher → upgrader →
    converter chain is consistent end-to-end.
    """

    def test_v1_artifact_yields_clean_chapter_no_doubling(self):
        v1_artifact = _minimal_v1_artifact([
            {"id": "b_000013", "type": "chapter_heading",
             "text": "Chapter 1\nWhat Depression Actually Is",
             "meta": {"chapter_number": 1}},
            {"id": "b_000014", "type": "paragraph",
             "text": "Before anything else, it helps to be clear..."},
        ])
        upgraded = read_artifact(v1_artifact)
        out = BlocksToLatexConverter().convert(
            upgraded["content"]["blocks"], params={}
        )
        # The upgraded artifact has chapter_title="What Depression Actually Is"
        # alone. The converter emits \chapter{What Depression Actually Is}.
        # No "Chapter 1\nWhat" anywhere — that's the doubled-chapter bug
        # being structurally impossible.
        self.assertIn("\\chapter{What Depression Actually Is}", out)
        self.assertNotIn("Chapter 1\\n", out)
        self.assertNotIn("Chapter 1 What", out)

    def test_v1_list_with_meta_list_type_renders_enumerate(self):
        v1_artifact = _minimal_v1_artifact([
            {"id": "b_001", "type": "list",
             "text": "First step",
             "meta": {"list_type": "ordered", "list_group": 1}},
            {"id": "b_002", "type": "list",
             "text": "Second step",
             "meta": {"list_type": "ordered", "list_group": 1}},
        ])
        upgraded = read_artifact(v1_artifact)
        out = BlocksToLatexConverter().convert(
            upgraded["content"]["blocks"], params={}
        )
        self.assertIn("\\begin{enumerate}", out)
        self.assertIn("\\end{enumerate}", out)


# ---------------------------------------------------------------------------
# Iter 4 — wire-up
# ---------------------------------------------------------------------------


class Test_TemplateSystemTitlePagePlaceholder(unittest.TestCase):
    """The templates carry a {{SYSTEM_TITLE_PAGE}} placeholder that
    pronto_worker_2.py fills based on H-001's decision. This test
    just confirms the placeholder is present in both templates and
    that the substitution shape is round-trippable.
    """

    def test_each_template_has_system_title_page_placeholder(self):
        for name in ("fiction_6x9.tex", "nonfiction_6x9.tex"):
            text = (REPO_ROOT / name).read_text(encoding="utf-8")
            self.assertEqual(
                text.count("{{SYSTEM_TITLE_PAGE}}"), 1,
                f"{name}: SYSTEM_TITLE_PAGE placeholder missing or duplicated"
            )


# Test_SystemTitlePageHelper removed in Bucket B.2.
# _system_title_page_latex() was the H-001-conditional title-page
# helper; it's replaced by lib.title_page.{resolve_title_fields,
# render_title_page_latex, render_half_title_page_latex}. The new
# behavior is tested in tests/test_doc23_v1.py:
#   Test_R2_1_HalfTitlePage
#   Test_R2_2_TitlePageFallbackChain


class Test_V1ReaderH001Synthesis(unittest.TestCase):

    def test_front_matter_title_synthesizes_h001(self):
        art = _minimal_v1_artifact([
            {"id": "b_000001", "type": "front_matter_title",
             "text": "The Long Quiet"},
            {"id": "b_000002", "type": "paragraph", "text": "Body."},
        ])
        out = read_artifact(art)
        h001 = [r for r in out["applied_rules"] if r.get("rule") == "H-001"]
        self.assertEqual(len(h001), 1)
        self.assertIn("suppressed system-generated", h001[0]["decision"])

    def test_no_front_matter_title_no_h001(self):
        """Long Quiet shape — no front_matter_title, just plain
        paragraphs that the v1 producer didn't classify. v1 reader
        must NOT synthesize H-001 in this case (no signal of an
        author-supplied title page from the producer's side).
        """
        art = _minimal_v1_artifact([
            {"id": "b_000001", "type": "paragraph", "text": "The Long Quiet"},
            {"id": "b_000002", "type": "paragraph", "text": "Body."},
        ])
        out = read_artifact(art)
        h001 = [r for r in out["applied_rules"] if r.get("rule") == "H-001"]
        self.assertEqual(h001, [])

    def test_v2_artifact_preserves_existing_h001(self):
        """A v2.0 artifact that came in with H-001 in applied_rules
        passes through the v2 reader unchanged. (W1 v5.0 emits H-001
        natively when the author supplied a title page.)
        """
        art = _minimal_v2_artifact([
            {"id": "b_000001", "type": "paragraph", "role": "title_page",
             "spans": [{"text": "The Long Quiet", "marks": []}]},
            {"id": "b_000002", "type": "heading", "heading_level": 2,
             "role": "chapter_heading",
             "chapter_number": 1, "chapter_title": "Opening",
             "spans": [{"text": "Chapter 1", "marks": []}]},
        ])
        art["applied_rules"] = [
            {"rule": "H-001", "version": "v1",
             "decision": "used author title page; suppressed system-generated"}
        ]
        out = read_artifact(art)
        h001 = [r for r in out["applied_rules"] if r.get("rule") == "H-001"]
        self.assertEqual(len(h001), 1)


class Test_TitlePageBlocksConsumedNotRendered(unittest.TestCase):
    """Bucket B.2 — title_page-role blocks are consumed upstream of
    rendering. C-003 already extracted their text into
    artifact.manuscript_meta during W1's classify phase. The converter's
    title_page handler is retained for HANDLER_MAP coverage but is
    unreachable: _partition_front_matter drops these blocks before
    convert_split iterates.

    The new title-page rendering is tested in tests/test_doc23_v1.py
    (Test_R2_1_HalfTitlePage, Test_R2_2_TitlePageFallbackChain).
    """

    def test_title_page_block_does_not_render_via_convert(self):
        c = BlocksToLatexConverter()
        block = {
            "id": "b_000001", "type": "paragraph", "role": "title_page",
            "spans": [{"text": "The Long Quiet", "marks": []}],
            "classification_notes": ["title_page positional role: title"],
        }
        out = c.convert([block], params={})
        self.assertEqual(
            out.strip(), "",
            "title_page blocks must not emit any LaTeX — they're consumed "
            "by the metadata extraction path.",
        )

    def test_title_page_block_dropped_from_both_partitions(self):
        from lib.blocks_to_latex import _partition_front_matter
        block = {
            "id": "b_000001", "type": "paragraph", "role": "title_page",
            "spans": [{"text": "X", "marks": []}],
        }
        front, body = _partition_front_matter([block])
        self.assertEqual(front, [])
        self.assertEqual(body, [])

    def test_title_page_handler_kept_for_handler_map_coverage(self):
        """The handler must remain registered (for the __init__
        deployment guard) even though it's unreachable in practice."""
        c = BlocksToLatexConverter()
        self.assertIn("title_page", c.HANDLER_MAP)
        # Calling it directly returns "" (the no-op behavior).
        result = c._render_title_page(
            {"id": "x", "spans": [{"text": "y", "marks": []}]},
            ctx={},
        )
        self.assertEqual(result, "")


# ---------------------------------------------------------------------------
# Iter 5 — The Long Quiet smoke (real artifacts, both reader paths)
# ---------------------------------------------------------------------------
#
# Two fixtures live under tests/fixtures/long_quiet/:
#   manuscript.v1.json   — the production v1.0 artifact at
#                          services/recSDCG0U8KxvYMdH/manuscript.v1.json,
#                          produced by W1 v4.1.0 against
#                          the_long_quiet.docx.
#   manuscript.v2.json   — the v2.0 artifact produced by running
#                          the same DOCX through W1 v2 dry-run
#                          (per MIGRATION_NOTES.md).
#
# These tests assert that the 5 bugs observed in the original buggy
# PDF are absent at the LaTeX-source level after dispatch + convert.
# The 5 bugs are:
#   (1) Whole-book duplication starting around page 42 — {{CONTENT}}
#       template trap. Fixed by Iter 1.
#   (2) Doubled chapter headings ("CHAPTER 1 CHAPTER 1 WHAT DEPRESSION
#       ACTUALLY IS"). Fixed by chapter_number/chapter_title separation
#       in upgrader (v1 path) and W1 v2 producer (v2 path).
#   (3) Run-boundary space loss ("theweather", "thefirst"). v2 path:
#       fixed by W1 v2 extractor's whitespace preservation. v1 path:
#       baked into the v1 artifact; can't be undone here.
#   (4) Triple/doubled title page. v2 path: H-001 fires, system block
#       suppressed, author cluster renders. v1 path: depends on
#       whether the v1 producer typed a front_matter_title block —
#       The Long Quiet's v1 producer didn't, so v1 path will not
#       suppress the system block (cluster paragraphs render as body
#       in document order).
#   (5) Part-divider page breaks missing. v2 path: C-002 classifies as
#       part_divider, force_page_break=true. v1 path: v1 producer
#       didn't classify as part_divider (the Long Quiet PDF showed
#       part dividers rendered inline), so v1 path can't recover.
#
# Per Jesse's note: bugs 3, 4, 5 are W1-upstream — expected to persist
# in v1 path and disappear in v2 path. Any persisting in v2 path
# means W2 is recreating them downstream — flag and investigate.

LONG_QUIET_DIR = REPO_ROOT / "tests" / "fixtures" / "long_quiet"


def _load_long_quiet(version: str) -> dict:
    name = "manuscript.v1.json" if version == "v1" else "manuscript.v2.json"
    path = LONG_QUIET_DIR / name
    if not path.exists():
        raise unittest.SkipTest(f"fixture missing: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


import json


def _render_through_pipeline(artifact: dict) -> tuple[dict, str]:
    """Run an artifact through the dispatcher + converter end-to-end.
    Returns (normalized_artifact, latex_body).
    """
    norm = read_artifact(artifact)
    body = BlocksToLatexConverter().convert(
        norm["content"]["blocks"], params={}
    )
    return norm, body


def _full_filled_template(template_name: str, norm: dict, latex_body: str,
                          latex_front: str = "") -> str:
    """Mirror pronto_worker_2.py's template-fill substitution to produce
    the final .tex source. Useful for asserting against the whole
    document, including the half-title and system title page.

    Bucket B.2: title-page substitution is now generated by
    lib.title_page from the manuscript_meta → params fallback chain.
    Tests pass synthetic params (book_title, author_name) so the
    chain resolves cleanly even on artifacts whose manuscript_meta
    is sparse.
    """
    from lib.title_page import (
        render_half_title_page_latex,
        render_title_page_latex,
        resolve_title_fields,
    )
    template = (REPO_ROOT / template_name).read_text(encoding="utf-8")
    fields = resolve_title_fields(
        norm,
        {"book_title": "The Long Quiet", "author_name": "Test Author"},
    )
    half_title = render_half_title_page_latex(fields)
    system_title = render_title_page_latex(fields)
    return (
        template
        .replace("{{CONTENT}}", latex_body, 1)
        .replace("{{FRONT_MATTER_CONTENT}}", latex_front, 1)
        .replace("{{HALF_TITLE_PAGE}}", half_title, 1)
        .replace("{{SYSTEM_TITLE_PAGE}}", system_title, 1)
        .replace("{{BOOK_TITLE}}", "The Long Quiet")
        .replace("{{AUTHOR_NAME}}", "Test Author")
        .replace("{{FONT_NAME}}", "EB Garamond")
        .replace("{{YEAR}}", "2026")
        .replace("{{ISBN}}", "")
    )


class Test_LongQuiet_V1Path(unittest.TestCase):
    """v1.0 artifact through the upgrader. The bugs that have v1
    upstream remediation should be gone; bugs 3/4/5 may persist.
    """

    def setUp(self):
        self.artifact = _load_long_quiet("v1")
        self.norm, self.body = _render_through_pipeline(self.artifact)
        self.tex = _full_filled_template("nonfiction_6x9.tex", self.norm, self.body)

    # Bug 1: duplication.
    def test_no_book_duplication_at_template_level(self):
        """Assert the body appears in the .tex exactly once. The
        Iter 1 fix (template wording + count=1) should keep this
        true regardless of artifact content.
        """
        self.assertEqual(self.tex.count(self.body), 1,
                         f"body appears {self.tex.count(self.body)} times in .tex")

    # Bug 2: doubled chapter headings.
    def test_no_doubled_chapter_heading_in_body(self):
        """The signature pattern was a chapter heading whose argument
        contained the literal "Chapter N" prefix as well as the title.
        After upgrade, \\chapter{...} arguments should be the title
        alone — never "Chapter N" prefix anywhere.
        """
        # Pull every \chapter{...} argument from the body.
        import re
        for m in re.finditer(r"\\chapter\*?\{([^{}]+)\}", self.body):
            arg = m.group(1)
            self.assertNotRegex(
                arg, r"^(Chapter|Ch\.?|CHAPTER)\s+\d",
                f"chapter argument still carries a Chapter prefix: {arg!r}"
            )
            # The Long Quiet had embedded newlines between number and title.
            # Those should also be gone.
            self.assertNotIn("\n", arg, f"newline in chapter arg: {arg!r}")

    # Bug 3: run-boundary space loss — surprising finding.
    def test_v1_path_space_loss_actually_fixed(self):
        """Surprising: bug 3 (theweather, Beforeanythingelse) is GONE
        in the v1 path too. The v1 artifact had proper spaces —
        "Before anything else, it helps to be clear..." is intact in
        the source artifact's spans. The bug must have lived in the
        OLD W2 converter (which we replaced in Iter 3) or the OLD
        template fill (which Iter 1 replaced). Either way, v1.3's
        v2-native converter renders the spaces correctly.

        Conclusion: bug 3 was a downstream rendering bug, not an
        upstream artifact bug. Both reader paths fix it.
        """
        self.assertNotIn(
            "Beforeanythingelse", self.body,
            "v1 path STILL produces 'Beforeanythingelse' — the v1.3 "
            "converter regressed on a fix the v2.0.0 contract-v1.1 "
            "spans-rendering work was supposed to give us."
        )
        # Positive assertion: the proper spacing is present.
        self.assertIn(
            "Before anything else", self.body,
            "v1 path missing the canonical chapter-1 opening — "
            "the v1 artifact's text isn't being rendered."
        )

    # Bug 4: triple/doubled title page.
    def test_v1_path_system_title_page_emitted(self):
        """The Long Quiet v1 producer didn't emit a front_matter_title
        block. Per Bucket B.2 (R-2.2), W2 always renders a system
        title page from the manuscript_meta → params fallback chain;
        the H-001 conditional is gone. We assert the new title-page
        markup is present.
        """
        # New R-2.2 system title page uses `\Huge\textbf{...}` inside
        # \begin{center}, NOT \begin{titlepage}.
        self.assertIn(r"\Huge\textbf{The Long Quiet}", self.tex,
                      "System title page (R-2.2) missing the title")
        self.assertIn(r"\large Test Author", self.tex,
                      "System title page (R-2.2) missing the author byline")
        # H-001 may or may not be in applied_rules; v1 path here didn't
        # see one (no front_matter_title block).
        h001 = [r for r in self.norm["applied_rules"] if r.get("rule") == "H-001"]
        self.assertEqual(h001, [],
                         "v1 reader synthesized H-001 unexpectedly on Long Quiet")

    # Bug 5: part-divider page break.
    def test_v1_path_part_divider_inline_documented(self):
        """v1 producer didn't classify part headings as part_divider.
        After upgrade they remain whatever role the v1 type mapped to
        (typically chapter_heading or paragraph). \\clearpage from
        a part_divider role won't appear. Documenting expected
        behavior — v2 path will have the fix.
        """
        # No part_divider blocks in the upgraded artifact for The Long
        # Quiet v1 input.
        roles = {b.get("role") for b in self.norm["content"]["blocks"]}
        self.assertNotIn("part_divider", roles,
                         "Long Quiet v1 unexpectedly has part_divider — "
                         "v1 producer behavior changed?")


class Test_LongQuiet_V2Path(unittest.TestCase):
    """v2.0 artifact (produced by W1 v2 dry-run on the Long Quiet
    DOCX) through the v2 reader. ALL FIVE bugs should be gone. Any
    that persist mean W2 is recreating the bug downstream — flag.
    """

    def setUp(self):
        self.artifact = _load_long_quiet("v2")
        self.norm, self.body = _render_through_pipeline(self.artifact)
        self.tex = _full_filled_template("nonfiction_6x9.tex", self.norm, self.body)

    # Bug 1.
    def test_no_book_duplication_at_template_level(self):
        self.assertEqual(self.tex.count(self.body), 1)

    # Bug 2.
    def test_no_doubled_chapter_heading_in_body(self):
        import re
        for m in re.finditer(r"\\chapter\*?\{([^{}]+)\}", self.body):
            arg = m.group(1)
            self.assertNotRegex(
                arg, r"^(Chapter|Ch\.?|CHAPTER)\s+\d",
                f"v2 chapter argument carries Chapter prefix: {arg!r}"
            )
            self.assertNotIn("\n", arg)

    # Bug 3.
    def test_v2_path_space_loss_fixed(self):
        """W1 v2 extractor preserves inter-run whitespace. The
        signature pattern from the buggy PDF should be GONE in the v2
        artifact's body text.
        """
        self.assertNotIn(
            "Beforeanythingelse", self.body,
            "Bug 3 (run-boundary space loss) recreated in W2 v2 path — "
            "this means W2 is doing something downstream that drops "
            "whitespace. Investigate the converter's _render_spans."
        )

    # Bug 4.
    def test_v2_path_h001_suppresses_system_title(self):
        """W1 v2 fired H-001 (intake metadata + author title page).
        Per Bucket B.2 (R-2.2), the system title page now ALWAYS
        renders from the manuscript_meta → params fallback chain —
        the H-001-conditional suppression is gone, and title_page-role
        blocks are consumed upstream rather than re-rendered. So the
        old "title page appears twice" bug is now structurally
        impossible: title_page blocks don't render at all (consumed
        by C-003 → manuscript_meta), and the system title page
        renders exactly once.
        """
        h001 = [r for r in self.norm["applied_rules"] if r.get("rule") == "H-001"]
        self.assertEqual(len(h001), 1, "H-001 missing from v2 applied_rules")
        # Old-style \begin{titlepage} is gone; new R-2.2 markup is
        # \Huge\textbf{...}. Verify the title appears exactly once
        # (defends against the doubled-title-page bug).
        title_huge_count = self.tex.count(r"\Huge\textbf{")
        # 2 occurrences: 1 for half-title (R-2.1), 1 for system title
        # page (R-2.2). NOT 3 (the doubled-title-page regression).
        self.assertEqual(
            title_huge_count, 2,
            f"Expected 2 \\Huge\\textbf occurrences (half-title + system title); "
            f"got {title_huge_count}. >2 = doubled-title-page regression."
        )
        # And the author cluster renders via title_page handler.
        title_page_blocks = [
            b for b in self.norm["content"]["blocks"]
            if b.get("role") == "title_page"
        ]
        self.assertGreater(len(title_page_blocks), 0,
                           "v2 artifact has no title_page blocks — C-003 "
                           "should have classified the opening cluster")

    # Bug 5.
    def test_v2_path_part_dividers_force_page_break(self):
        """C-002 classifies "Part One Understanding" etc. as
        part_divider with force_page_break=true. The converter emits
        \\clearpage before each \\part*. The Long Quiet has multiple
        parts — every one should produce a \\clearpage \\part* pair.
        """
        part_blocks = [
            b for b in self.norm["content"]["blocks"]
            if b.get("role") == "part_divider"
        ]
        self.assertGreater(
            len(part_blocks), 0,
            "v2 artifact has no part_divider blocks — C-002 should have "
            "classified Part One / Part Two etc."
        )
        # Each part_divider in the body should be preceded by \clearpage.
        import re
        clears_before_parts = re.findall(
            r"\\clearpage\s*\n\\part\*\{[^{}]+\}", self.body
        )
        self.assertEqual(
            len(clears_before_parts), len(part_blocks),
            f"Bug 5 recreated: {len(part_blocks)} part_divider blocks but "
            f"only {len(clears_before_parts)} \\clearpage+\\part* pairs in "
            f"the body."
        )

    # Bonus end-to-end shape assertions.
    def test_v2_path_all_blocks_have_role(self):
        """I-2 — every block has a non-null role after the v2 reader
        (terminal default applied upstream).
        """
        for b in self.norm["content"]["blocks"]:
            self.assertTrue(b.get("role"), f"block {b.get('id')} lacks role")

    def test_v2_path_chapter_count_matches(self):
        """The Long Quiet has 14 chapters. Verify all 14 land as
        chapter_heading role with non-null titles.
        """
        chapters = [
            b for b in self.norm["content"]["blocks"]
            if b.get("role") == "chapter_heading"
        ]
        self.assertEqual(len(chapters), 14,
                         f"expected 14 chapters, got {len(chapters)}")
        for ch in chapters:
            self.assertTrue(ch.get("chapter_title"))


# ---------------------------------------------------------------------------
# Production unblock 2026-04-25 — warning_handler v2.0 contract tolerance
# ---------------------------------------------------------------------------
#
# Production W1 v5.0.0-a1 emitted a real artifact whose 12 warnings used
# the v2.0 schema's `rule` field. W2's warning_handler.evaluate() was
# still reading `warning['code']` (v1.0 vocabulary), so it crashed with
# KeyError on the first warning of the first end-to-end success of the
# W1→W2 chain on v5. The patch makes evaluate() tolerant of both shapes
# via _warning_code(); these tests pin the contract so it doesn't
# silently regress.

from lib.warning_handler import WarningHandler


class Test_WarningHandler_V2Tolerance(unittest.TestCase):
    """v2.0 warnings (Doc 22 V-### / H-### rule IDs) must not crash
    evaluate(). They land in 'unknown' today and fall through to
    PROCEED — that's correct v5 behavior; the rules are advisory.
    """

    def setUp(self):
        self.handler = WarningHandler()

    def test_v2_warning_shape_does_not_crash(self):
        """Single V-001 warning, v2.0 shape — no 'code' field. The
        handler must read 'rule' instead and produce a decision.
        """
        warnings = [{
            "rule": "V-001",
            "severity": "medium",
            "detail": "chapter numbers [1, 2, 4, 5] — gap between 2 and 4",
            "blocks": ["b_000013", "b_000021"],
        }]
        decision = self.handler.evaluate(warnings)
        self.assertEqual(decision.action, "PROCEED")

    def test_full_v2_warning_set_proceeds(self):
        """All five v2.0 rule IDs the v1 producer + W1 v2 emit. Until a
        proper v2.0 rule-bucket mapping lands, every one falls through
        to PROCEED. This test pins that interim behavior so a future
        rule-bucket refactor doesn't quietly change it.
        """
        warnings = [
            {"rule": "V-001", "severity": "medium", "detail": "chapter gap"},
            {"rule": "V-002", "severity": "medium", "detail": "heading style mismatch"},
            {"rule": "V-003", "severity": "high", "detail": "possible missing space: 'theweather'"},
            {"rule": "V-004", "severity": "high", "detail": "tracked-changes residue"},
            {"rule": "H-001", "severity": "medium", "detail": "intake author divergence"},
        ]
        decision = self.handler.evaluate(warnings)
        self.assertEqual(decision.action, "PROCEED")

    def test_real_long_quiet_v2_warnings_proceed(self):
        """End-to-end against the real Long Quiet v2.0 artifact's
        warnings. The 2 warnings in that artifact (V-003 + H-001) must
        flow through to PROCEED without raising.
        """
        with open(LONG_QUIET_DIR / "manuscript.v2.json", "r", encoding="utf-8") as f:
            art = json.load(f)
        warnings = art.get("warnings") or []
        self.assertGreater(len(warnings), 0,
                           "Long Quiet v2 fixture has no warnings — fixture stale")
        decision = self.handler.evaluate(warnings)
        self.assertEqual(decision.action, "PROCEED")

    def test_malformed_warning_skipped_not_crashed(self):
        """A warning with neither 'rule' nor 'code' must be skipped,
        not crashed. The handler should still return a decision based
        on the rest of the warnings list.
        """
        warnings = [
            {"severity": "medium", "detail": "missing identifier"},  # malformed
            {"rule": "V-001", "severity": "medium", "detail": "chapter gap"},
        ]
        decision = self.handler.evaluate(warnings)
        self.assertEqual(decision.action, "PROCEED")

    def test_mixed_v1_v2_shapes_handled(self):
        """Backward compatibility: an artifact carrying both v1.0
        ('code'-shaped) and v2.0 ('rule'-shaped) warnings should be
        handled correctly. v1.0 codes still match the legacy bucket
        maps; v2.0 rules pass through.
        """
        warnings = [
            {"code": "DETECTED_FOOTNOTES", "severity": "medium",
             "detail": "footnote in chapter 3"},
            {"rule": "V-001", "severity": "medium", "detail": "chapter gap"},
        ]
        decision = self.handler.evaluate(warnings)
        # DETECTED_FOOTNOTES is in degrade_rules → DEGRADE outcome.
        self.assertEqual(decision.action, "DEGRADE")
        self.assertIn("Footnotes rendered inline", decision.degradations or [])


class Test_WarningHandler_V1BackCompat(unittest.TestCase):
    """The legacy v1.0 path still works. The patch must not break
    the original behavior for code-shaped warnings.
    """

    def setUp(self):
        self.handler = WarningHandler()

    def test_v1_fail_code_still_fails(self):
        warnings = [{"code": "DETECTED_IMAGES", "severity": "high",
                     "detail": "image found"}]
        decision = self.handler.evaluate(warnings)
        self.assertEqual(decision.action, "FAIL")
        self.assertIn("Images not supported", decision.reason or "")

    def test_v1_degrade_code_still_degrades(self):
        warnings = [{"code": "OCR_ARTIFACTS", "severity": "medium",
                     "detail": "OCR errors"}]
        decision = self.handler.evaluate(warnings)
        self.assertEqual(decision.action, "DEGRADE")

    def test_v1_proceed_code_still_proceeds(self):
        warnings = [{"code": "LOW_CHAPTER_CONFIDENCE", "severity": "low",
                     "detail": "chapter confidence below threshold"}]
        decision = self.handler.evaluate(warnings)
        self.assertEqual(decision.action, "PROCEED")

    def test_no_warnings_proceeds(self):
        decision = self.handler.evaluate([])
        self.assertEqual(decision.action, "PROCEED")


if __name__ == "__main__":
    unittest.main(verbosity=2)
