"""
W2 1.7.2 — vendored Bold glyph coverage (Perennial-publish blocker).

Debian's EBGaramond12-Bold.otf v0.016 has 127 glyphs and no
typographic punctuation; every bold heading/TOC context rendered
U+2019 / U+2014 (etc.) as tofu (first surfaced on Book 18, run
e5N05Gk). The repo now vendors the complete v1.002 Bold and the
Dockerfile overwrites the package file. This test pins the vendored
file's coverage so a regression to a stub bold can never ship quietly.
"""

import os
import unittest

try:
    from fontTools.ttLib import TTFont
    HAVE_FONTTOOLS = True
except ImportError:  # dev-only dependency; prod image never runs tests
    HAVE_FONTTOOLS = False

FONT_PATH = os.path.join(os.path.dirname(__file__), "..", "fonts",
                         "EBGaramond12-Bold.otf")

# The punctuation that tofu'd in e5N05Gk plus the rest of the
# typographic set W1 normalization emits.
REQUIRED_CODEPOINTS = {
    0x2014: "EM DASH",
    0x2013: "EN DASH",
    0x2018: "LEFT SINGLE QUOTATION MARK",
    0x2019: "RIGHT SINGLE QUOTATION MARK",
    0x201C: "LEFT DOUBLE QUOTATION MARK",
    0x201D: "RIGHT DOUBLE QUOTATION MARK",
    0x2026: "HORIZONTAL ELLIPSIS",
    0x00A9: "COPYRIGHT SIGN",
}


@unittest.skipUnless(HAVE_FONTTOOLS, "fontTools not installed (dev-only check)")
class TestVendoredBoldCoverage(unittest.TestCase):
    def test_bold_covers_typographic_punctuation(self):
        font = TTFont(FONT_PATH)
        cmap = font.getBestCmap()
        missing = [f"U+{cp:04X} {name}"
                   for cp, name in REQUIRED_CODEPOINTS.items()
                   if cp not in cmap]
        self.assertEqual(missing, [],
                         f"vendored Bold is missing glyphs: {missing}")

    def test_bold_is_not_the_debian_stub(self):
        font = TTFont(FONT_PATH)
        cmap = font.getBestCmap()
        # The Debian stub has 127 mapped codepoints; the complete
        # continuation Bold has ~2,091. Anything under 1,000 means the
        # stub crept back in.
        self.assertGreater(len(cmap), 1000,
                           f"Bold has only {len(cmap)} glyphs — stub bold?")


if __name__ == "__main__":
    unittest.main()
