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


if __name__ == "__main__":
    unittest.main()
