"""
Interior font axis (Interior Catch-Up Part B, W2 1.13.0) — the body
face catches up to the covers' Cover Font axis.

Three curated voices, each a complete fontspec setup block the
template-fill step substitutes for {{FONT_SETUP}}:

- EB Garamond (DEFAULT) — the shipped classic old-style. Its block is
  BYTE-IDENTICAL to the setup the 14 templates carried before the
  placeholder existed: default orders assemble the exact same .tex.
- Lora — warm contemporary transitional; the same voice offered on
  covers (a book can speak one voice inside and out). Vendored static
  instances (fonts/lora/, Dockerfile COPY), real italics.
- Libertine — Linux Libertine, the scholarly workhorse; darker color,
  larger x-height. Already installed in the production image
  (fonts-linuxlibertine), zero Docker change.

All OFL-licensed (Libertine dual GPL/OFL), all carry REAL italics, all
comfortably readable at the Interior Standard's 11pt body size.

House pattern (covers.resolve): read by name, trimmed +
case-insensitive, dict-or-string tolerated; empty/unknown -> default +
a logged warning (silent defaults earn a warning).

Author: Pronto Publishing
"""

from dataclasses import dataclass
from typing import Any, Optional, Tuple

DEFAULT_FONT = "EB Garamond"

# The default block must stay byte-identical to the pre-1.13 template
# text — it is what every existing order re-assembles to. Do not
# reformat it, even trailing spaces.
_EB_GARAMOND_SETUP = (
    "% Main font: EB Garamond, pinned to explicit OTF paths to bypass fontconfig.\n"
    "\\setmainfont{EB Garamond}[\n"
    "  Path = /usr/share/fonts/opentype/ebgaramond/ ,\n"
    "  Extension = .otf ,\n"
    "  UprightFont = EBGaramond12-Regular ,\n"
    "  ItalicFont = EBGaramond12-Italic ,\n"
    "  BoldFont = EBGaramond12-Bold ,\n"
    "  BoldItalicFont = EBGaramond12-Bold ,\n"
    "  BoldItalicFeatures = {FakeSlant=0.2} ,\n"
    "  Ligatures = TeX ,\n"
    "]"
)

_LORA_SETUP = (
    "% Main font: Lora, vendored static instances (fonts/lora, OFL).\n"
    "\\setmainfont{Lora}[\n"
    "  Path = /usr/share/fonts/truetype/lora/ ,\n"
    "  Extension = .ttf ,\n"
    "  UprightFont = Lora-Regular ,\n"
    "  ItalicFont = Lora-Italic ,\n"
    "  BoldFont = Lora-Bold ,\n"
    "  BoldItalicFont = Lora-BoldItalic ,\n"
    "  Ligatures = TeX ,\n"
    "]"
)

_LIBERTINE_SETUP = (
    "% Main font: Linux Libertine (fonts-linuxlibertine, in the image).\n"
    "\\setmainfont{Linux Libertine}[\n"
    "  Path = /usr/share/fonts/opentype/linux-libertine/ ,\n"
    "  Extension = .otf ,\n"
    "  UprightFont = LinLibertine_R ,\n"
    "  ItalicFont = LinLibertine_RI ,\n"
    "  BoldFont = LinLibertine_RB ,\n"
    "  BoldItalicFont = LinLibertine_RBI ,\n"
    "  Ligatures = TeX ,\n"
    "]"
)


@dataclass(frozen=True)
class InteriorFont:
    name: str            # the literal Airtable choice string
    setup_latex: str     # complete fontspec block for {{FONT_SETUP}}


FONTS = {
    "EB Garamond": InteriorFont("EB Garamond", _EB_GARAMOND_SETUP),
    "Lora": InteriorFont("Lora", _LORA_SETUP),
    "Libertine": InteriorFont("Libertine", _LIBERTINE_SETUP),
}

_BY_KEY = {name.strip().casefold(): f for name, f in FONTS.items()}


def resolve_interior_font(field: Any) -> Tuple[InteriorFont, Optional[str]]:
    """Book Metadata `Interior Font` -> (InteriorFont, warning|None).
    Empty -> default silently is NOT the posture: empty is fine (the
    field simply isn't set — no warning), unknown earns the warning."""
    raw = field
    if isinstance(raw, dict):                 # singleSelect object shape
        raw = raw.get("name", "")
    literal = (str(raw).strip() if raw is not None else "")
    if not literal:
        return FONTS[DEFAULT_FONT], None
    hit = _BY_KEY.get(literal.casefold())
    if hit:
        return hit, None
    return FONTS[DEFAULT_FONT], (
        f"interior-font-default: Book Metadata Interior Font is "
        f"{literal!r} (expected {', '.join(FONTS)}) — defaulting to "
        f"{DEFAULT_FONT}")
