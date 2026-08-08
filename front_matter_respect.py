"""
Front-Matter Contract v1 — W2's RESPECT half.

Doc of record: `4 - Automation System/FrontMatter_Contract_v1.md`
(Jesse's ruling 2026-07-28; C signed with amendments A1/A2/A3).

THE RULING: **the manuscript WINS when it carries its own front matter;
the form's metadata fields FILL GAPS when it doesn't.** W1 classifies
(emitting the artifact's `front_matter` section); this module turns that
into W2's suppression decisions and the copyright cross-check.

Collision rule, per the ruling: manuscript over field, ALWAYS, with a
manifest note recording the ignored field. Never both. Never neither
when the form supplied one. Never a silent choice.

DEGRADE-SAFE: an artifact with no `front_matter` section (a W1 older
than the contract) suppresses nothing — W2 behaves exactly as it does
today. That keeps this deployable independently, though the coordinated
W1+W2 release is the intended path.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

# Contract classes W2 can generate → (W2 params key, Airtable field
# name for the note). title_page is built from Book Title/Author,
# copyright from the template, toc_authorial from block structure —
# those carry no single form field, hence None.
_FORM_FIELD_BY_CLASS = {
    "dedication": ("dedication", "Dedication"),
    "acknowledgements": ("acknowledgements", "Acknowledgements"),
    "about_the_author": ("about_the_author", "About the Author"),
    "title_page": (None, None),
    "copyright_page": (None, None),
    "toc_authorial": (None, None),
}


def carried_classes(artifact: Optional[Dict[str, Any]]) -> set:
    """The set of front-matter classes the MANUSCRIPT carries. Empty
    when the artifact predates the contract (degrade-safe)."""
    fm = (artifact or {}).get("front_matter") or {}
    return set(fm.get("carried") or [])


def element_text(artifact: Optional[Dict[str, Any]], cls: str) -> str:
    """The manuscript text of a front-matter element, joined across its
    block range — the input to the copyright cross-check. Empty string
    when the artifact carries no such element."""
    fm = (artifact or {}).get("front_matter") or {}
    ranges = [e["block_range"] for e in (fm.get("elements") or [])
              if e.get("class") == cls]
    if not ranges:
        return ""
    wanted = set()
    blocks = ((artifact or {}).get("content") or {}).get("blocks") or []
    for first, last in ranges:
        collecting = False
        for b in blocks:
            if b.get("id") == first:
                collecting = True
            if collecting:
                wanted.add(id(b))
            if b.get("id") == last and collecting:
                break
    parts: List[str] = []
    for b in blocks:
        if id(b) not in wanted:
            continue
        if "spans" in b:
            parts.append("".join(s.get("text", "") for s in b["spans"]))
        else:
            parts.append(b.get("text", "") or "")
    return "\n".join(p for p in parts if p)


def suppression_decisions(
    artifact: Optional[Dict[str, Any]],
    form_values: Dict[str, Any],
) -> Tuple[Dict[str, bool], List[str]]:
    """Decide, for each generatable element, whether W2 suppresses its
    generator because the author already made that page.

    Returns (suppress_map, notes). `notes` are the manifest collision
    notes required by the ruling — one per element where the manuscript
    won over a filled form field.
    """
    carried = carried_classes(artifact)
    suppress: Dict[str, bool] = {}
    notes: List[str] = []

    for cls, (params_key, field_name) in _FORM_FIELD_BY_CLASS.items():
        manuscript_has = cls in carried
        suppress[cls] = manuscript_has
        if not manuscript_has:
            continue
        # The collision note: the manuscript won; say so, and name the
        # form field that was ignored when one was actually supplied.
        if params_key:
            supplied = str(form_values.get(params_key) or "").strip()
            if supplied:
                notes.append(
                    f"front_matter.{cls}: manuscript (form field "
                    f"{field_name!r} ignored — the author's page ships)")
            else:
                notes.append(f"front_matter.{cls}: manuscript "
                             f"(no form value; nothing ignored)")
        else:
            notes.append(f"front_matter.{cls}: manuscript "
                         f"(the author's page ships; generator suppressed)")

    # An authorial typed TOC wins, but its page numbers are almost
    # certainly wrong after typesetting — the standing warning the
    # contract requires.
    if "toc_authorial" in carried:
        notes.append(
            "front_matter.toc_authorial: the manuscript's typed table of "
            "contents ships and the generated one is suppressed — typed "
            "page numbers are usually wrong after typesetting; the "
            "generated TOC is recommended (author's choice wins)")

    return suppress, notes


# --- A3: the copyright cross-check ---------------------------------
#
# The copyright page is the ONE element the house always ensures
# exists. When the manuscript carries its own, it SHIPS AS WRITTEN and
# the machine cross-checks it — never rewrites it.
#
#   no ISBN present          -> WARNING (ship)
#   ISBN differs from assigned -> HOLD
#   imprint mismatch         -> HOLD
#   edition strings / year   -> ignored, author voice
#
# ISBN-13: the 978/979 prefix plus exactly ten more digits, each
# optionally preceded by a separator (hyphen of any dash flavour, or a
# space). Counting DIGITS rather than characters is what makes the
# plain "9781971041070" and the hyphenated "978-1-971041-07-0" forms
# both match — an early version counted characters and silently missed
# every unhyphenated ISBN.
_ISBN_RE = re.compile(r"97[89](?:[\s\-‐‑‒–—―]?\d){10}")


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s or "")


def copyright_verdicts(
    copyright_text: Optional[str],
    *,
    assigned_isbn: Optional[str],
    imprint: Optional[str],
) -> List[Dict[str, str]]:
    """Cross-check the author's copyright page. Returns a list of
    verdicts: {"level": "hold"|"warning", "detail": str}. An empty list
    means the page checks out.

    `copyright_text` is the author's page as written. When the
    manuscript carries no copyright page this is not called — W2
    generates one as it does today (the floor).
    """
    verdicts: List[Dict[str, str]] = []
    text = copyright_text or ""

    # --- ISBN ---
    found = _ISBN_RE.search(text)
    if not found:
        verdicts.append({
            "level": "warning",
            "detail": ("copyright page carries no ISBN — the assigned "
                       "ISBN still governs the record; shipping the "
                       "author's page as written"),
        })
    elif assigned_isbn:
        if _digits(found.group(0)) != _digits(assigned_isbn):
            verdicts.append({
                "level": "hold",
                "detail": (
                    f"copyright page ISBN {found.group(0).strip()!r} does "
                    f"NOT match the ISBN assigned to this order "
                    f"({assigned_isbn}) — a wrong ISBN in print is a "
                    f"recall-class error; a human must reconcile it"),
            })

    # --- imprint ---
    if imprint:
        imp = imprint.strip()
        if imp and imp.casefold() not in text.casefold():
            verdicts.append({
                "level": "hold",
                "detail": (
                    f"copyright page does not name the order's imprint "
                    f"({imp!r}) — the flag on the book and the flag in "
                    f"the record must agree; a human must reconcile it"),
            })

    # Edition strings, copyright year, rights wording: author voice.
    # Deliberately never checked (contract A3).
    return verdicts
