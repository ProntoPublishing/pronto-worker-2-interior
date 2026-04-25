"""
Doc 23 v1 (Pronto Standard Edition) rule tests.

Each rule in Doc 23 R-1 / R-3 / R-4 / R-7 that lands in Bucket A gets
unit tests here. Per-rule classes; tests inside name the specific
behavior they're asserting.

Distinct from tests/test_local_fixtures.py: those are corpus-level
golden-diff tests that catch unintended drift across the whole 5-book
set. These tests pin specific rule behaviors at unit grain.
"""
from __future__ import annotations
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib.render_params import RenderParams  # noqa: E402
from lib.blocks_to_latex import (  # noqa: E402
    BlocksToLatexConverter,
    _collapse_adjacent_duplicate_chapter_headings,
)


class Test_R1_TypographyParameters(unittest.TestCase):
    """R-1.1 / R-1.2 / R-1.3 — Pronto Standard Edition v1 typography
    defaults. The RenderParams module-default values must match Doc 23
    verbatim so a fresh `RenderParams()` produces a Doc-23-compliant
    layout without any caller configuration.
    """

    def setUp(self) -> None:
        self.p = RenderParams()

    # -- R-1.1 trim size ------------------------------------------------
    def test_R0101_trim_is_6x9_inches(self) -> None:
        self.assertEqual(self.p.paper_width_in,  6.0)
        self.assertEqual(self.p.paper_height_in, 9.0)

    # -- R-1.2 margins --------------------------------------------------
    def test_R0102_inside_margin_0p875in(self) -> None:
        self.assertEqual(self.p.inside_margin_in, 0.875)

    def test_R0102_outside_margin_0p625in(self) -> None:
        self.assertEqual(self.p.outside_margin_in, 0.625)

    def test_R0102_top_and_bottom_margin_0p75in(self) -> None:
        self.assertEqual(self.p.top_margin_in,    0.75)
        self.assertEqual(self.p.bottom_margin_in, 0.75)

    # -- R-1.3 body typography -----------------------------------------
    def test_R0103_body_font_family_eb_garamond(self) -> None:
        self.assertEqual(self.p.body_font_family, "EB Garamond")

    def test_R0103_body_font_size_10p5pt(self) -> None:
        self.assertEqual(self.p.body_font_size_pt, 10.5)

    def test_R0103_body_leading_14pt(self) -> None:
        self.assertEqual(self.p.body_leading_pt, 14.0)

    def test_R0103_parindent_1em(self) -> None:
        self.assertEqual(self.p.parindent_em, 1.0)


class Test_R3_2_OpenRight(unittest.TestCase):
    """R-3.2 — every chapter starts on a recto. Bucket A enforces this
    via the `openright` documentclass option (the LaTeX-canonical
    mechanism); future commits may layer per-chapter `\\cleardoublepage`
    in the converter for belt-and-suspenders coverage.
    """

    def test_R0302_default_openright_is_true(self) -> None:
        self.assertTrue(RenderParams().openright)

    def test_R0302_template_fill_emits_openright(self) -> None:
        fills = RenderParams().to_template_fills()
        self.assertEqual(fills["{{PARAM_DOCCLASS_OPENING}}"], "openright")

    def test_R0302_openright_false_resolves_to_openany(self) -> None:
        # Future "Custom Layout" tier may override; verify the bool→str
        # mapping in both directions.
        from dataclasses import replace
        p = replace(RenderParams(), openright=False)
        fills = p.to_template_fills()
        self.assertEqual(fills["{{PARAM_DOCCLASS_OPENING}}"], "openany")


class Test_TemplateFillSurface(unittest.TestCase):
    """Contract tests for the template ↔ RenderParams seam.

    The templates and `to_template_fills()` are coupled: every key the
    template references must be in the fills map, and every fill the
    map emits should land in at least one template (the latter is a
    soft check; we tolerate fills that no template currently uses, in
    case a template is added later).

    The hard requirement: after substitution, no `{{PARAM_*}}` literal
    survives anywhere in the rendered .tex. A surviving placeholder
    means the template references a key the fills map doesn't define.
    """

    def setUp(self) -> None:
        self.fills = RenderParams().to_template_fills()
        self.fiction_path = ROOT / "fiction_6x9.tex"
        self.nonfiction_path = ROOT / "nonfiction_6x9.tex"
        self.fiction = self.fiction_path.read_text(encoding="utf-8")
        self.nonfiction = self.nonfiction_path.read_text(encoding="utf-8")

    def _apply_fills(self, template: str) -> str:
        out = template
        for k, v in self.fills.items():
            out = out.replace(k, v)
        # Also apply the book-specific fills the local runner performs,
        # so this test reflects the real post-fill surface. Use stub
        # values; the surviving-{{PARAM_}} check is what matters.
        for k, v in (
            ("{{CONTENT}}", ""),
            ("{{SYSTEM_TITLE_PAGE}}", ""),
            ("{{BOOK_TITLE}}", "Stub"),
            ("{{AUTHOR_NAME}}", "Stub"),
            ("{{FONT_NAME}}", "EB Garamond"),
            ("{{YEAR}}", "1970"),
            ("{{ISBN}}", ""),
        ):
            out = out.replace(k, v)
        return out

    def test_fiction_template_consumes_all_referenced_param_keys(self) -> None:
        rendered = self._apply_fills(self.fiction)
        survivors = re.findall(r"\{\{PARAM_[A-Z_0-9]+\}\}", rendered)
        self.assertEqual(
            survivors, [],
            f"fiction_6x9.tex references {survivors!r} but RenderParams "
            f"doesn't emit them. Either add the key to "
            f"to_template_fills() or remove it from the template."
        )

    def test_nonfiction_template_consumes_all_referenced_param_keys(self) -> None:
        rendered = self._apply_fills(self.nonfiction)
        survivors = re.findall(r"\{\{PARAM_[A-Z_0-9]+\}\}", rendered)
        self.assertEqual(
            survivors, [],
            f"nonfiction_6x9.tex references {survivors!r} but RenderParams "
            f"doesn't emit them."
        )

    def test_no_book_specific_placeholders_survive(self) -> None:
        """Defense-in-depth: after the full template-fill pass, no
        `{{...}}` literal of any kind survives. Keeps a bare `{{FOO}}`
        typo from sneaking past the param-keyed check above.
        """
        rendered = self._apply_fills(self.fiction)
        survivors = re.findall(r"\{\{[A-Z_0-9]+\}\}", rendered)
        self.assertEqual(survivors, [])

    def test_documentclass_line_carries_doc23_values(self) -> None:
        rendered = self._apply_fills(self.fiction)
        # The full-line check is brittle to LaTeX-comment additions
        # above the documentclass; just look for the salient pattern.
        self.assertIn(r"\documentclass[12pt,openright]{book}", rendered)

    def test_geometry_block_carries_doc23_margins(self) -> None:
        rendered = self._apply_fills(self.fiction)
        self.assertIn("inner=0.875in,",  rendered)
        self.assertIn("outer=0.625in,",  rendered)
        self.assertIn("paperwidth=6in,", rendered)
        self.assertIn("paperheight=9in,", rendered)

    def test_body_typography_carries_doc23_values(self) -> None:
        rendered = self._apply_fills(self.fiction)
        self.assertIn(r"\fontsize{10.5pt}{14pt}\selectfont", rendered)
        self.assertIn(r"\setlength{\parindent}{1em}", rendered)


def _make_chapter(block_id: str, number, title: str, *, role: str = "chapter_heading") -> dict:
    """Build a synthetic v2 chapter_heading block for unit tests."""
    return {
        "id": block_id,
        "type": "heading",
        "role": role,
        "heading_level": 2,
        "chapter_number": number,
        "chapter_title": title,
        "spans": [{"text": title, "marks": []}],
    }


def _make_body(block_id: str, text: str) -> dict:
    return {
        "id": block_id,
        "type": "paragraph",
        "role": "body_paragraph",
        "spans": [{"text": text, "marks": []}],
    }


class Test_R3_4_SingleRenderingInvariant(unittest.TestCase):
    """R-3.4 — single rendering per chapter_heading block + collapse
    of adjacent duplicates (with warning)."""

    # -- Defensive collapse pre-pass -----------------------------------
    def test_R0304_adjacent_duplicate_blocks_collapse_to_one(self) -> None:
        a = _make_chapter("b1", 1, "The Beginning")
        b = _make_chapter("b2", 1, "The Beginning")  # exact duplicate
        with self.assertLogs("lib.blocks_to_latex", level="WARNING") as caught:
            out = _collapse_adjacent_duplicate_chapter_headings([a, b])
        self.assertEqual(len(out), 1, "duplicate should collapse")
        self.assertEqual(out[0]["id"], "b1", "first occurrence wins")
        self.assertTrue(
            any("R-3.4" in r and "b2" in r for r in caught.output),
            f"expected R-3.4 warning naming b2; got {caught.output!r}",
        )

    def test_R0304_three_adjacent_duplicates_collapse_to_one_with_two_warnings(
        self,
    ) -> None:
        a = _make_chapter("b1", 1, "Same")
        b = _make_chapter("b2", 1, "Same")
        c = _make_chapter("b3", 1, "Same")
        with self.assertLogs("lib.blocks_to_latex", level="WARNING") as caught:
            out = _collapse_adjacent_duplicate_chapter_headings([a, b, c])
        self.assertEqual(len(out), 1)
        warning_msgs = [r for r in caught.output if "R-3.4" in r]
        self.assertEqual(len(warning_msgs), 2,
                         f"expected 2 warnings; got {warning_msgs!r}")

    def test_R0304_different_titles_both_kept(self) -> None:
        a = _make_chapter("b1", 1, "First")
        b = _make_chapter("b2", 2, "Second")
        # No warning expected. assertLogs(...) requires at least one log
        # at the level, so use assertNoLogs (3.10+).
        out = _collapse_adjacent_duplicate_chapter_headings([a, b])
        self.assertEqual([x["id"] for x in out], ["b1", "b2"])

    def test_R0304_intervening_body_block_preserves_both(self) -> None:
        """Strict adjacency: identical chapter heads with a body
        paragraph between them are NOT collapsed. They're more likely
        a legitimate repeat than producer drift; conservatively
        preserve content."""
        a = _make_chapter("b1", 1, "Same")
        body = _make_body("b2", "Some intervening content.")
        c = _make_chapter("b3", 1, "Same")
        out = _collapse_adjacent_duplicate_chapter_headings([a, body, c])
        self.assertEqual([x["id"] for x in out], ["b1", "b2", "b3"])

    def test_R0304_same_number_different_title_both_kept(self) -> None:
        a = _make_chapter("b1", 1, "Title One")
        b = _make_chapter("b2", 1, "Title Two")  # same number, different title
        out = _collapse_adjacent_duplicate_chapter_headings([a, b])
        self.assertEqual([x["id"] for x in out], ["b1", "b2"])

    def test_R0304_same_title_different_number_both_kept(self) -> None:
        a = _make_chapter("b1", 1, "Title")
        b = _make_chapter("b2", 2, "Title")
        out = _collapse_adjacent_duplicate_chapter_headings([a, b])
        self.assertEqual([x["id"] for x in out], ["b1", "b2"])

    def test_R0304_empty_input_returns_empty(self) -> None:
        self.assertEqual(_collapse_adjacent_duplicate_chapter_headings([]), [])

    def test_R0304_no_chapter_headings_passes_through(self) -> None:
        body1 = _make_body("b1", "First.")
        body2 = _make_body("b2", "Second.")
        out = _collapse_adjacent_duplicate_chapter_headings([body1, body2])
        self.assertEqual(out, [body1, body2])

    # -- The first sentence of R-3.4 (single rendering per block) ------
    def test_R0304_one_chapter_heading_block_renders_one_chapter_command(
        self,
    ) -> None:
        """A single chapter_heading block carrying both chapter_number
        and chapter_title produces exactly ONE \\chapter command, not
        two (the bug R-3.4 codifies the absence of)."""
        block = _make_chapter("b1", 1, "The Beginning")
        latex = BlocksToLatexConverter().convert(
            [block], params={}, degraded_mode=False,
        )
        # Numbered chapters use \chapter (no asterisk); count the
        # exact command name without matching \chapter*.
        chapter_count = len(re.findall(r"\\chapter\{", latex))
        chapter_star_count = len(re.findall(r"\\chapter\*\{", latex))
        self.assertEqual(chapter_count, 1,
                         f"expected exactly 1 \\chapter; got {chapter_count}\n{latex}")
        self.assertEqual(chapter_star_count, 0)

    def test_R0304_unnumbered_chapter_renders_one_chapter_star(self) -> None:
        block = _make_chapter("b1", None, "Prologue")
        latex = BlocksToLatexConverter().convert(
            [block], params={}, degraded_mode=False,
        )
        self.assertEqual(latex.count(r"\chapter*{Prologue}"), 1)


class Test_R3_5_R4_4_FirstParagraphNoIndent(unittest.TestCase):
    """R-3.5 + R-4.4 — first paragraph after chapter heading or scene
    break renders without first-line indent. Shared mechanism: a
    next_paragraph_no_indent flag in convert() set on chapter_heading
    or scene_break, consumed by the next body_paragraph (which gets a
    `\\noindent ` prefix), cleared by any other intervening role.
    """

    def setUp(self) -> None:
        self.converter = BlocksToLatexConverter()

    def _convert(self, blocks):
        return self.converter.convert(blocks, params={}, degraded_mode=False)

    # -- R-3.5 (after chapter_heading) ---------------------------------
    def test_R0305_first_para_after_chapter_has_noindent(self) -> None:
        ch = _make_chapter("b1", 1, "Beginning")
        body = _make_body("b2", "It was a quiet morning.")
        out = self._convert([ch, body])
        # \noindent must appear immediately before the body paragraph
        # text — i.e. the body paragraph line starts with \noindent.
        self.assertIn(r"\noindent It was a quiet morning.", out)

    def test_R0305_only_FIRST_para_after_chapter_gets_noindent(self) -> None:
        ch = _make_chapter("b1", 1, "Beginning")
        body1 = _make_body("b2", "First paragraph.")
        body2 = _make_body("b3", "Second paragraph.")
        out = self._convert([ch, body1, body2])
        self.assertIn(r"\noindent First paragraph.", out)
        # The second paragraph indents normally — no \noindent prefix.
        self.assertNotIn(r"\noindent Second paragraph.", out)

    def test_R0305_intervening_block_clears_noindent_flag(self) -> None:
        """A list_item between chapter_heading and body_paragraph
        clears the flag — the body paragraph indents normally."""
        ch = _make_chapter("b1", 1, "Beginning")
        list_block = {
            "id": "b2", "type": "paragraph", "role": "list_item",
            "spans": [{"text": "An interrupting list item.", "marks": []}],
        }
        body = _make_body("b3", "Body text follows.")
        out = self._convert([ch, list_block, body])
        self.assertNotIn(r"\noindent Body text follows.", out)

    # -- R-4.4 (after scene_break) -------------------------------------
    def test_R0404_first_para_after_scene_break_has_noindent(self) -> None:
        body0 = _make_body("b1", "Closing of the prior scene.")
        sb = {"id": "b2", "type": "paragraph", "role": "scene_break"}
        body1 = _make_body("b3", "A new scene begins.")
        out = self._convert([body0, sb, body1])
        self.assertIn(r"\noindent A new scene begins.", out)

    def test_R0404_only_FIRST_para_after_scene_break_gets_noindent(
        self,
    ) -> None:
        sb = {"id": "b1", "type": "paragraph", "role": "scene_break"}
        body1 = _make_body("b2", "First scene paragraph.")
        body2 = _make_body("b3", "Second scene paragraph.")
        out = self._convert([sb, body1, body2])
        self.assertIn(r"\noindent First scene paragraph.", out)
        self.assertNotIn(r"\noindent Second scene paragraph.", out)

    # -- Shared mechanism ----------------------------------------------
    def test_chapter_then_sceneBreak_then_body_keeps_noindent(self) -> None:
        """Chapter sets the flag; scene_break re-sets the same flag;
        body paragraph still gets \\noindent. Tests that the flag
        composes across both triggers without a gap."""
        ch = _make_chapter("b1", 1, "Beginning")
        sb = {"id": "b2", "type": "paragraph", "role": "scene_break"}
        body = _make_body("b3", "Resumed content.")
        out = self._convert([ch, sb, body])
        self.assertIn(r"\noindent Resumed content.", out)

    def test_body_with_no_chapter_or_scene_break_indents_normally(
        self,
    ) -> None:
        body = _make_body("b1", "An ordinary paragraph.")
        out = self._convert([body])
        self.assertNotIn(r"\noindent An ordinary paragraph.", out)
        self.assertIn("An ordinary paragraph.", out)


class Test_R4_2_StripUnderlineStrikethrough(unittest.TestCase):
    """R-4.2 — `underline` and `strikethrough` span marks are stripped
    in v1. The underlying span text passes through to LaTeX unmarked.
    Other canonical span marks (italic, bold, small_caps, code,
    superscript, subscript) are unaffected.
    """

    def setUp(self) -> None:
        self.converter = BlocksToLatexConverter()

    def _convert_with_marks(self, text: str, marks: list[str]) -> str:
        block = {
            "id": "b1", "type": "paragraph", "role": "body_paragraph",
            "spans": [{"text": text, "marks": marks}],
        }
        return self.converter.convert([block], params={}, degraded_mode=False)

    def test_R0402_underline_mark_stripped(self) -> None:
        out = self._convert_with_marks("emphasized phrase", ["underline"])
        self.assertNotIn(r"\underline", out)
        self.assertIn("emphasized phrase", out)

    def test_R0402_strikethrough_mark_stripped(self) -> None:
        out = self._convert_with_marks("crossed out", ["strikethrough"])
        self.assertNotIn(r"\sout", out)
        self.assertIn("crossed out", out)

    def test_R0402_italic_still_rendered(self) -> None:
        """Sanity: only underline + strikethrough strip; italic stays."""
        out = self._convert_with_marks("emphatic", ["italic"])
        self.assertIn(r"\textit{emphatic}", out)

    def test_R0402_bold_still_rendered(self) -> None:
        out = self._convert_with_marks("loud", ["bold"])
        self.assertIn(r"\textbf{loud}", out)

    def test_R0402_underline_combined_with_italic_keeps_italic(self) -> None:
        """A span carrying both underline and italic marks: underline
        strips, italic renders. Order matters in _wrap_with_marks since
        marks layer; verify the italic survives regardless."""
        out_under_first = self._convert_with_marks(
            "complex", ["underline", "italic"]
        )
        out_italic_first = self._convert_with_marks(
            "complex", ["italic", "underline"]
        )
        self.assertIn(r"\textit{complex}", out_under_first)
        self.assertIn(r"\textit{complex}", out_italic_first)
        self.assertNotIn(r"\underline", out_under_first)
        self.assertNotIn(r"\underline", out_italic_first)

    def test_R0402_strikethrough_combined_with_bold_keeps_bold(self) -> None:
        out = self._convert_with_marks("bold-and-struck", ["bold", "strikethrough"])
        self.assertIn(r"\textbf{bold-and-struck}", out)
        self.assertNotIn(r"\sout", out)

    def test_R0402_super_and_subscript_still_render(self) -> None:
        super_out = self._convert_with_marks("st", ["superscript"])
        sub_out = self._convert_with_marks("2", ["subscript"])
        self.assertIn(r"\textsuperscript{st}", super_out)
        self.assertIn(r"\textsubscript{2}", sub_out)

    def test_R0402_small_caps_and_code_still_render(self) -> None:
        sc_out = self._convert_with_marks("LITERAL", ["small_caps"])
        code_out = self._convert_with_marks("verb", ["code"])
        self.assertIn(r"\textsc{LITERAL}", sc_out)
        self.assertIn(r"\texttt{verb}", code_out)


if __name__ == "__main__":
    unittest.main()
