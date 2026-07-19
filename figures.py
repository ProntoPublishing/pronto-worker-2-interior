"""
E3 2a — Figure validation + grayscale-v1 (W2 1.8.0-a1)
=======================================================

The W8-§4 battery subset for interior figures (shared-framework port,
Manus Q1 confirmed): decode, effective-DPI-at-placed-size >= 300
(below-floor -> hold naming the figure + its max printable width),
the provenance triple (class + sha256 + rights basis — W1 stamps
class/rights at extraction, sha at upload; any missing -> hold), and
the attribution check (Manus Edit 1).

Grayscale conversion (Manus Q5 RULED: fidelity operation,
conditional-allow — Edit 4):
- ONE named deterministic method, versioned `grayscale-v1` =
  Pillow mode-"L" conversion (ITU-R 601-2 luma: L = 299R/1000 +
  587G/1000 + 114B/1000), PNG-encoded.
- The manifest records source hash + converted hash + the derivation
  link; the checklist carries the disclosure (W4 renders it).
- Contrast-collapse tripwire: a near-uniform luminance histogram
  after conversion (dynamic range or spread collapse — the
  red-on-green chart case) -> Review hold with the converted image
  attached (uploaded beside the manifest).

Author: Pronto Publishing
"""

import hashlib
import io
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from PIL import Image

GRAYSCALE_METHOD = "grayscale-v1"
MIN_FIGURE_DPI = 300.0
# Contrast collapse: converted image whose 5th-95th percentile
# luminance band is narrower than this (0-255) reads as mud in print.
CONTRAST_MIN_P5_P95_RANGE = 40

DOC14_AI_FIELDS = ("model", "prompt_hash", "seed")
HOLD_CLASSES = ("licensed_stock",)
ACQUISITION_CLASSES = ("customer_supplied", "house_ai")


@dataclass
class FigureVerdict:
    block_id: str
    image_key: Optional[str] = None
    ok: bool = True
    holds: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    px: Optional[Tuple[int, int]] = None
    placed_w_in: Optional[float] = None
    effective_dpi: Optional[float] = None
    source_sha256: Optional[str] = None
    converted_sha256: Optional[str] = None
    grayscale_converted: bool = False
    render_bytes: Optional[bytes] = None
    figure: Optional[Dict] = None

    def hold(self, msg: str) -> None:
        self.ok = False
        self.holds.append(f"figure {self.block_id}: {msg}")


def _histogram_p5_p95_range(gray: Image.Image) -> int:
    hist = gray.histogram()
    total = sum(hist)
    if total == 0:
        return 0
    lo_target = total * 0.05
    hi_target = total * 0.95
    acc = 0
    p5 = p95 = 0
    for i, n in enumerate(hist):
        acc += n
        if acc >= lo_target and p5 == 0:
            p5 = i
        if acc >= hi_target:
            p95 = i
            break
    return p95 - p5


def validate_figure(block_id: str, figure: Dict, data: bytes,
                    text_measure_in: float) -> FigureVerdict:
    """The full per-figure battery. `text_measure_in` is the placed
    width (figures fill the text measure; height capped by the render
    rule, aspect preserved)."""
    v = FigureVerdict(block_id=block_id, figure=figure,
                      image_key=figure.get("image_key"))
    v.source_sha256 = hashlib.sha256(data).hexdigest()

    # --- Provenance triple ---
    cls = figure.get("acquisition_class")
    rights = figure.get("rights_basis")
    if not cls:
        v.hold("acquisition_class missing (Manus triple)")
    elif cls in HOLD_CLASSES:
        v.hold("licensed-stock images are not accepted (Amendment 2)")
    elif cls not in ACQUISITION_CLASSES:
        v.hold(f"acquisition_class {cls!r} unrecognized")
    if rights in (None, "", {}):
        v.hold("rights_basis missing (Manus triple)")
    elif cls == "house_ai" and isinstance(rights, dict):
        missing = [f for f in DOC14_AI_FIELDS if not rights.get(f)]
        if missing:
            v.hold(f"house_ai rights_basis missing Doc 14 field(s): "
                   f"{', '.join(missing)}")
    stamped = figure.get("sha256")
    if stamped and stamped != v.source_sha256:
        v.hold(f"sha mismatch: manuscript stamps {stamped[:12]}…, R2 "
               f"object is {v.source_sha256[:12]}… — chain of custody")
    # Attribution check (Manus Edit 1)
    if figure.get("attribution_required") and not (figure.get("credit")
                                                   or "").strip():
        v.hold("rights basis requires attribution but no credit line is "
               "present (Manus Edit 1)")

    # --- Decode + DPI at placed size ---
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception as e:
        v.hold(f"does not decode cleanly ({e.__class__.__name__}: {e})")
        return v
    v.px = img.size
    v.placed_w_in = text_measure_in
    dpi = img.size[0] / text_measure_in
    v.effective_dpi = dpi
    if dpi < MIN_FIGURE_DPI:
        max_w = img.size[0] / MIN_FIGURE_DPI
        v.hold(f"effective resolution {dpi:.0f} DPI at the "
               f"{text_measure_in:.2f}\" text measure is below "
               f"{MIN_FIGURE_DPI:.0f} — max printable width for this "
               f"image is {max_w:.2f}\"")
        return v

    # --- Grayscale-v1 (fidelity operation, conditional-allow) ---
    if img.mode in ("L", "1"):
        out = io.BytesIO()
        img.convert("L").save(out, format="PNG")
        v.render_bytes = out.getvalue()
        v.converted_sha256 = hashlib.sha256(v.render_bytes).hexdigest()
        return v

    if img.mode in ("RGBA", "LA", "PA"):
        base = Image.new("RGB", img.size, (255, 255, 255))
        rgba = img.convert("RGBA")
        base.paste(rgba, mask=rgba.getchannel("A"))
        img = base
        v.warnings.append(f"figure {block_id}: alpha flattened onto "
                          f"paper-white for print")
    gray = img.convert("L")
    v.grayscale_converted = True
    spread = _histogram_p5_p95_range(gray)
    out = io.BytesIO()
    gray.save(out, format="PNG")
    v.render_bytes = out.getvalue()
    v.converted_sha256 = hashlib.sha256(v.render_bytes).hexdigest()
    if spread < CONTRAST_MIN_P5_P95_RANGE:
        v.hold(f"contrast collapse after {GRAYSCALE_METHOD}: the "
               f"converted luminance band spans only {spread}/255 — "
               f"colors that distinguished this figure vanish in "
               f"black-ink print (converted image uploaded for review)")
    return v
