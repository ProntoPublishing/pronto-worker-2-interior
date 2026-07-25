"""
Interior Catch-Up Part B (1.13.0) — font axis + matter toggles.

Locks: (1) the resolver's read-by-name rules (empty silent, unknown
warns, case-insensitive, dict-or-string); (2) every template carries
each seam exactly once; (3) default fill consumes the matter slots
WHOLLY (no stray blank line — the byte-identity mechanism) and
substitutes the EB Garamond block verbatim; (4) matter builders
escape LaTeX and honor paragraphs; (5) non-default voices point at
real production font paths.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from interior_fonts import DEFAULT_FONT, FONTS, resolve_interior_font
from matter_pages import back_matter_latex, dedication_latex

REPO = Path(__file__).resolve().parent.parent
TEMPLATES = sorted(REPO.glob("*.tex"))


class TestResolver(unittest.TestCase):
    def test_empty_is_default_and_silent(self):
        for empty in (None, "", "   "):
            font, warning = resolve_interior_font(empty)
            self.assertEqual(font.name, DEFAULT_FONT)
            self.assertIsNone(warning)

    def test_unknown_defaults_with_warning(self):
        font, warning = resolve_interior_font("Comic Sans")
        self.assertEqual(font.name, DEFAULT_FONT)
        self.assertIn("interior-font-default", warning)
        self.assertIn("Comic Sans", warning)

    def test_each_name_resolves_case_insensitive(self):
        for name in FONTS:
            for variant in (name, name.upper(), f"  {name.lower()} "):
                font, warning = resolve_interior_font(variant)
                self.assertEqual(font.name, name)
                self.assertIsNone(warning)

    def test_dict_shape_tolerated(self):
        font, warning = resolve_interior_font({"name": "Lora"})
        self.assertEqual(font.name, "Lora")
        self.assertIsNone(warning)

    def test_voices_point_at_production_paths(self):
        self.assertIn("/usr/share/fonts/opentype/ebgaramond/",
                      FONTS["EB Garamond"].setup_latex)
        self.assertIn("/usr/share/fonts/truetype/lora/",
                      FONTS["Lora"].setup_latex)
        self.assertIn("/usr/share/fonts/opentype/linux-libertine/",
                      FONTS["Libertine"].setup_latex)
        # Libertine file stems match the Debian package exactly.
        for stem in ("LinLibertine_R", "LinLibertine_RI",
                     "LinLibertine_RB", "LinLibertine_RBI"):
            self.assertIn(stem, FONTS["Libertine"].setup_latex)

    def test_lora_vendored_files_exist(self):
        lora = REPO / "fonts" / "lora"
        for fn in ("Lora-Regular.ttf", "Lora-Italic.ttf",
                   "Lora-Bold.ttf", "Lora-BoldItalic.ttf", "OFL.txt"):
            self.assertTrue((lora / fn).exists(), f"missing {fn}")


class TestTemplateSeams(unittest.TestCase):
    def test_fourteen_templates(self):
        self.assertEqual(len(TEMPLATES), 14)

    def test_each_seam_exactly_once(self):
        for p in TEMPLATES:
            t = p.read_text(encoding="utf-8")
            for ph in ("{{FONT_SETUP}}", "{{DEDICATION_BLOCK}}",
                       "{{BACK_MATTER_BLOCK}}"):
                self.assertEqual(t.count(ph), 1, f"{p.name}: {ph}")

    def test_default_fill_consumes_slot_lines(self):
        """The byte-identity mechanism: replacing '<PH>\\n' with ''
        removes the whole line — no stray blank line remains."""
        for p in TEMPLATES:
            t = p.read_text(encoding="utf-8")
            filled = (t
                      .replace("{{FONT_SETUP}}",
                               FONTS[DEFAULT_FONT].setup_latex, 1)
                      .replace("{{DEDICATION_BLOCK}}\n", "", 1)
                      .replace("{{BACK_MATTER_BLOCK}}\n", "", 1))
            self.assertNotIn("{{FONT_SETUP}}", filled)
            self.assertNotIn("{{DEDICATION_BLOCK}}", filled)
            self.assertNotIn("{{BACK_MATTER_BLOCK}}", filled)
            self.assertIn("\\setmainfont{EB Garamond}", filled)
            # The dedication slot sat directly above the TOC comment;
            # consuming the line must leave the original neighborhood.
            self.assertIn(
                "\\clearpage\n\n% Table of contents", filled,
                f"{p.name}: dedication slot left residue")
            self.assertIn(
                "\\backmatter\n\n%", filled,
                f"{p.name}: back-matter slot left residue")


class TestMatterBuilders(unittest.TestCase):
    def test_empty_fields_yield_none(self):
        for empty in (None, "", "  \n "):
            self.assertIsNone(dedication_latex(empty))
        self.assertIsNone(back_matter_latex(None, None))
        self.assertIsNone(back_matter_latex("", "  "))

    def test_dedication_shape(self):
        d = dedication_latex("For Maria.\n\nAnd for the road home.")
        self.assertIn("\\thispagestyle{empty}", d)
        self.assertIn("\\itshape", d)
        self.assertIn("For Maria.", d)
        self.assertIn("And for the road home.", d)
        self.assertIn("\\\\[1em]", d)          # paragraph separation
        self.assertTrue(d.endswith("\\clearpage"))

    def test_dedication_escapes_latex(self):
        d = dedication_latex("For the 100% & the #1_underdog $team$")
        self.assertNotIn(" & ", d)
        self.assertIn("\\&", d)
        self.assertIn("\\%", d)
        self.assertIn("\\#", d)
        self.assertIn("\\_", d)
        self.assertIn("\\$", d)

    def test_back_matter_order_and_shape(self):
        bm = back_matter_latex("Thanks to everyone.",
                               "J. Author lives in Maine.")
        self.assertIn("\\chapter*{Acknowledgements}", bm)
        self.assertIn("\\chapter*{About the Author}", bm)
        self.assertLess(bm.index("Acknowledgements"),
                        bm.index("About the Author"))
        # House back-matter shape: TOC lines like _render_back_matter.
        self.assertIn(
            "\\addcontentsline{toc}{chapter}{Acknowledgements}", bm)
        self.assertIn(
            "\\addcontentsline{toc}{chapter}{About the Author}", bm)

    def test_single_section_alone(self):
        bm = back_matter_latex(None, "Bio only.")
        self.assertNotIn("Acknowledgements", bm)
        self.assertIn("About the Author", bm)
        bm = back_matter_latex("Ack only.", None)
        self.assertIn("Acknowledgements", bm)
        self.assertNotIn("About the Author", bm)


if __name__ == "__main__":
    unittest.main()
