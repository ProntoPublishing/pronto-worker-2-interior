"""
E3 2a (W2 1.8.0-a1): figure battery, grayscale-v1 determinism +
contrast-collapse tripwire, converter figure emission, reader 2.2
acceptance. No-figure books ride the byte-identical pre-E3 path
(the whole existing suite is that proof).
"""

import io
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PIL import Image

from figures import (CONTRAST_MIN_P5_P95_RANGE, GRAYSCALE_METHOD,
                     validate_figure)
from lib.artifact_readers import SUPPORTED_SCHEMA_VERSIONS, read_artifact
from lib.blocks_to_latex import BlocksToLatexConverter

GOOD_FIG = {"image_key": "projects/x/figures/a.png",
            "acquisition_class": "customer_supplied",
            "rights_basis": "author manuscript submission (docx-embedded)",
            "caption": "Fig 1", "credit": None}


def _png(mode="L", size=(2000, 1400), color=255, painter=None):
    img = Image.new(mode, size, color)
    if painter:
        painter(img)
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


class TestFigureBattery(unittest.TestCase):
    def test_clean_grayscale_passes(self):
        def paint(img):
            for x in range(0, 2000, 40):
                for y in range(0, 1400, 2):
                    img.putpixel((x, y), 0)
        fig = dict(GOOD_FIG)
        data = _png(painter=paint)
        import hashlib
        fig["sha256"] = hashlib.sha256(data).hexdigest()
        v = validate_figure("b_1", fig, data, 4.5)
        self.assertTrue(v.ok, v.holds)
        self.assertGreaterEqual(v.effective_dpi, 300)
        self.assertFalse(v.grayscale_converted)

    def test_low_dpi_holds_with_max_width(self):
        v = validate_figure("b_1", dict(GOOD_FIG), _png(size=(900, 600)), 4.5)
        self.assertFalse(v.ok)
        self.assertIn("max printable width", v.holds[0])

    def test_sha_mismatch_holds(self):
        fig = dict(GOOD_FIG, sha256="0" * 64)
        v = validate_figure("b_1", fig, _png(), 4.5)
        self.assertFalse(v.ok)
        self.assertTrue(any("chain of custody" in h for h in v.holds))

    def test_color_converts_grayscale_v1_deterministically(self):
        # A real luminance gradient — broad spread, no collapse.
        def paint(img):
            for x in range(2000):
                v = int(255 * x / 2000)
                for y in range(0, 1400, 2):
                    img.putpixel((x, y), (v, 60, 255 - v))
        data = _png(mode="RGB", color=(240, 240, 235), painter=paint)
        v1 = validate_figure("b_1", dict(GOOD_FIG), data, 4.5)
        v2 = validate_figure("b_1", dict(GOOD_FIG), data, 4.5)
        self.assertTrue(v1.ok, v1.holds)
        self.assertTrue(v1.grayscale_converted)
        self.assertEqual(v1.converted_sha256, v2.converted_sha256,
                         "grayscale-v1 must be byte-deterministic")

    def test_contrast_collapse_holds(self):
        # Red-on-green: distinct hues, nearly identical luminance.
        def paint(img):
            for x in range(2000):
                for y in range(0, 1400, 4):
                    img.putpixel((x, y), (0, 120, 0))
        data = _png(mode="RGB", color=(120, 0, 0), painter=paint)
        v = validate_figure("b_1", dict(GOOD_FIG), data, 4.5)
        self.assertFalse(v.ok)
        self.assertTrue(any("contrast collapse" in h for h in v.holds),
                        v.holds)

    def test_stock_claim_holds(self):
        fig = dict(GOOD_FIG, acquisition_class="licensed_stock",
                   rights_basis="stock 99")
        v = validate_figure("b_1", fig, _png(), 4.5)
        self.assertTrue(any("Amendment 2" in h for h in v.holds))

    def test_attribution_without_credit_holds(self):
        fig = dict(GOOD_FIG, attribution_required=True)
        v = validate_figure("b_1", fig, _png(), 4.5)
        self.assertTrue(any("Edit 1" in h for h in v.holds))


class TestReader22(unittest.TestCase):
    def test_2_2_supported_and_figure_passes_through(self):
        self.assertIn("2.2", SUPPORTED_SCHEMA_VERSIONS)
        art = {
            "schema_version": "2.2",
            "artifact_type": "manuscript",
            "source": {}, "processing": {},
            "content": {"blocks": [
                {"id": "b_1", "type": "image", "role": "image",
                 "figure": {"image_key": "k", "caption": "c",
                            "acquisition_class": "customer_supplied",
                            "rights_basis": "warranty"}},
            ]},
        }
        out = read_artifact(art)
        blk = out["content"]["blocks"][0]
        self.assertEqual(blk.get("figure", {}).get("image_key"), "k")


class TestConverterFigure(unittest.TestCase):
    def test_staged_figure_emits_includegraphics(self):
        c = BlocksToLatexConverter()
        out = c._render_image(
            {"id": "b_9", "type": "image", "role": "image",
             "figure": {"caption": "The orchard", "credit": "EJS"}},
            {"params": {"figure_files": {"b_9": "fig_b_9.png"}}})
        self.assertIn("\includegraphics", out)
        self.assertIn("fig_b_9.png", out)
        self.assertIn("The orchard", out)
        self.assertIn("keepaspectratio", out)

    def test_unstaged_figure_keeps_standin(self):
        c = BlocksToLatexConverter()
        out = c._render_image({"id": "b_9", "role": "image"},
                              {"params": {}})
        self.assertIn("Illustration omitted", out)


if __name__ == "__main__":
    unittest.main()
