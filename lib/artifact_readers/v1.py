"""
v1 reader — in-memory upgrader from manuscript.v1.0 to v2.0 shape.

v1.0 carried role-as-type (a single `type` field that conflated
structural CIR type and semantic role) and stored chapter-heading
content as a single string ("Chapter 1\\nWhat Depression Actually Is")
that the renderer split badly. v2.0 separates structural type from
semantic role and carries chapter_number / chapter_title / etc. as
their own fields.

This reader does the minimum necessary upgrade to feed the v2-aware
converter:

  - Maps v1 `type` to v2 (`type`, `role`) per the table below.
  - Splits chapter_heading text into chapter_number + chapter_title
    using the C-001 v1.0.1 regex (the one in W1 v2). chapter_title is
    never null/empty (I-4); chapter_number may be null when the heading
    text doesn't contain an extractable number.
  - Synthesizes manuscript_meta from any front_matter_title block
    present (extracted text becomes title; subtitle and author left
    None — v1 doesn't separate them).
  - Always emits spans (v1 may have carried plain `text`; that becomes
    a single empty-marks span).

The v1 reader does NOT re-classify generic blocks. It trusts the v1
producer's typing — those blocks were already classified, just into
the v1 schema's vocabulary. The mapping below is type-for-type.
"""
from __future__ import annotations
import re
from typing import Any, Dict, List, Optional, Tuple


# v1 type → (v2 CIR type, v2 role, optional subtype, optional notes).
# When subtype is None, the role does not require subtype (only
# front_matter and back_matter need it per I-6).
_V1_TYPE_MAP: Dict[str, Tuple[str, str, Optional[str], Optional[str]]] = {
    "front_matter_title":     ("paragraph",       "title_page",        None,                  None),
    "front_matter_copyright": ("paragraph",       "front_matter",      "copyright",           None),
    "front_matter_dedication":("paragraph",       "front_matter",      "dedication",          None),
    "toc_marker":             ("page_break",      "structural",        None,                  "v1 toc_marker (no v2 type)"),
    "chapter_heading":        ("heading",         "chapter_heading",   None,                  None),
    "heading":                ("heading",         "heading",           None,                  None),
    "paragraph":              ("paragraph",       "body_paragraph",    None,                  None),
    "blockquote":             ("blockquote",      "blockquote",        None,                  None),
    "list":                   ("list_item",       "list_item",         None,                  None),
    "scene_break":            ("paragraph",       "scene_break",       None,                  None),
    "horizontal_rule":        ("horizontal_rule", "structural",        None,                  None),
    "page_break":             ("page_break",      "structural",        None,                  None),
    "back_matter_about_author":("heading",        "back_matter",       "about_the_author",    None),
    "back_matter_also_by":    ("heading",         "back_matter",       "also_by",             None),
}

# C-001 chapter pattern (Doc 22 v1.0.1 Patch 3). Used to split
# "Chapter 1\nTitle" into chapter_number + chapter_title.
_CHAPTER_PATTERN = re.compile(
    r"^(Chapter|Ch\.?|CHAPTER)\s+([\w\d]+)(?:[\s\n:.]+(.+))?",
    re.IGNORECASE | re.DOTALL,
)


def read(artifact: Dict[str, Any]) -> Dict[str, Any]:
    """Upgrade a v1.0/v1.1 artifact to v2.0 shape.

    Returns a new dict; does not mutate the input. The result has
    schema_version="2.0" — the producer's version is preserved on
    `processing.upgraded_from_schema_version` so downstream operators
    can see the original source shape.
    """
    sv = artifact.get("schema_version")
    if sv not in ("1.0", "1.1"):
        raise ValueError(f"v1 reader called on schema_version={sv!r}")

    in_blocks = artifact.get("content", {}).get("blocks", []) or []
    out_blocks: List[Dict[str, Any]] = []
    manuscript_meta: Dict[str, Any] = {"title": None, "subtitle": None, "author": None}

    for blk in in_blocks:
        upgraded = _upgrade_block(blk)
        out_blocks.append(upgraded)
        # Synthesize manuscript_meta from front_matter_title text.
        if blk.get("type") == "front_matter_title" and not manuscript_meta["title"]:
            text = _block_text(blk)
            if text:
                manuscript_meta["title"] = text.strip()

    # Carry forward source / processing / analysis where possible.
    source = artifact.get("source") or {}
    processing = dict(artifact.get("processing") or {})
    processing["upgraded_from_schema_version"] = sv

    # v1 carried analysis.warnings; v2 carries warnings at top level.
    v1_warnings = artifact.get("analysis", {}).get("warnings", []) or []

    out: Dict[str, Any] = {
        "schema_version": "2.0",
        "worker_version": artifact.get("worker_version") or processing.get("worker_version") or "unknown",
        "rules_version":  artifact.get("rules_version") or "n/a (upgraded from v1)",
        "artifact_type":  artifact.get("artifact_type", "manuscript"),
        "artifact_id":    artifact.get("artifact_id") or "",
        "service_id":     artifact.get("service_id") or processing.get("service_id") or "",
        "source":         source,
        "processing":     processing,
        "content":        {"blocks": out_blocks},
        "applied_rules":  [],     # v1 didn't track these.
        "warnings":       _upgrade_warnings(v1_warnings),
        "rule_faults":    [],     # v1 didn't track these either.
    }
    # Only emit manuscript_meta when at least one field is populated.
    if any(manuscript_meta.values()):
        out["manuscript_meta"] = manuscript_meta
    return out


# ---------------------------------------------------------------------------
# Per-block upgrade
# ---------------------------------------------------------------------------

def _upgrade_block(blk: Dict[str, Any]) -> Dict[str, Any]:
    v1_type = blk.get("type")
    mapping = _V1_TYPE_MAP.get(v1_type)
    if mapping is None:
        # Unknown v1 type — preserve the content under a safe v2 shape
        # and tag it for operator review. Do NOT silently drop.
        return _wrap_unknown_v1_type(blk, v1_type)

    cir_type, role, subtype, mapping_note = mapping

    out: Dict[str, Any] = {
        "id": blk.get("id") or _synthesize_id(blk),
        "type": cir_type,
        "role": role,
    }

    # Source pointer: v1 had source_loc; v2 calls it source.
    src = blk.get("source") or blk.get("source_loc")
    if src:
        out["source"] = src

    # heading_level: v2 requires it on type=heading. v1 chapter_heading
    # implicitly was level 2; v1 heading might carry meta.level.
    if cir_type == "heading":
        meta = blk.get("meta") or {}
        if v1_type == "chapter_heading":
            out["heading_level"] = 2
        elif v1_type == "heading":
            out["heading_level"] = int(meta.get("level") or 3)
        elif v1_type.startswith("back_matter_"):
            out["heading_level"] = 1
        else:
            out["heading_level"] = 2

    # Text/spans: v2 always uses spans.
    spans = _normalize_spans(blk)
    # Structural CIR types (page_break, horizontal_rule) have neither.
    if cir_type not in ("page_break", "horizontal_rule"):
        out["spans"] = spans

    # style_tags: pass through any v1 style_tags (none in current v1
    # producers, but defensive).
    if blk.get("style_tags"):
        out["style_tags"] = list(blk["style_tags"])

    # Role-specific fields.
    notes: List[str] = []
    if mapping_note:
        notes.append(mapping_note)

    if role == "chapter_heading":
        text = _block_text(blk)
        chapter_number, chapter_title, chap_note = _split_chapter(text)
        out["chapter_number"] = chapter_number
        out["chapter_title"] = chapter_title or text or "Untitled"
        if chap_note:
            notes.append(chap_note)
    elif role == "front_matter":
        out["subtype"] = subtype or "generic"
        out["title"] = _block_text(blk)
    elif role == "back_matter":
        out["subtype"] = subtype or "generic"
        out["title"] = _block_text(blk)
    elif role == "part_divider":
        out["force_page_break"] = True  # I-5 (no v1 type maps here, but defensive)
    elif role == "list_item":
        # v1 list blocks may carry meta.list_type ∈ {"ordered","unordered"}.
        # Preserve as a top-level boolean so the v2 converter can pick
        # itemize vs enumerate. v2 native producers (W1 v5.0) currently
        # default this to False; the field formalizes when list ordering
        # becomes a v2 producer concern.
        v1_meta = blk.get("meta") or {}
        if v1_meta.get("list_type") == "ordered":
            out["list_ordered"] = True

    if notes:
        out["classification_notes"] = notes
    return out


def _wrap_unknown_v1_type(blk: Dict[str, Any], v1_type: Any) -> Dict[str, Any]:
    """A v1 block with a type the mapping doesn't know about. Emit as
    a body_paragraph with a clear classification note so downstream
    operators see the gap rather than a silent drop.
    """
    return {
        "id": blk.get("id") or _synthesize_id(blk),
        "type": "paragraph",
        "role": "body_paragraph",
        "spans": _normalize_spans(blk),
        "classification_notes": [
            f"unknown v1 block type {v1_type!r}; upgraded as body_paragraph"
        ],
    }


def _normalize_spans(blk: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return spans list, converting v1's `text` field to a single
    empty-marks span when needed.
    """
    spans = blk.get("spans")
    if isinstance(spans, list) and spans:
        out = []
        for s in spans:
            text = s.get("text", "") if isinstance(s, dict) else str(s)
            # v1.0 (positional marks) is closed per the prior R2-artifact
            # verification. v1.1 spans use {marks: [str]} per-span. Pass
            # marks through if present and well-formed; coerce to list[str]
            # otherwise.
            marks_in = s.get("marks") if isinstance(s, dict) else None
            marks_out: List[str] = []
            if isinstance(marks_in, list):
                for m in marks_in:
                    if isinstance(m, str):
                        marks_out.append(m)
                    elif isinstance(m, dict) and isinstance(m.get("type"), str):
                        # Defensive: positional marks would be {type, start, end}.
                        # Drop start/end (they're invalid in v2) but keep type.
                        marks_out.append(m["type"])
            out.append({"text": text, "marks": marks_out})
        return out
    text = blk.get("text", "")
    return [{"text": text, "marks": []}]


def _block_text(blk: Dict[str, Any]) -> str:
    """Concatenate a v1 block's text content."""
    spans = blk.get("spans")
    if isinstance(spans, list):
        return "".join(s.get("text", "") for s in spans if isinstance(s, dict))
    return blk.get("text", "") or ""


def _split_chapter(text: str) -> Tuple[Any, str, Optional[str]]:
    """Apply the C-001 v1.0.1 regex to split a chapter heading.

    Returns (chapter_number, chapter_title, classification_note).
    chapter_number is int when extractable, string for non-arabic
    numerals, None when unextractable. chapter_title is the trimmed
    title fragment, or the full text when no pattern match.
    """
    text = (text or "").strip()
    if not text:
        return None, "", "chapter heading was empty"

    m = _CHAPTER_PATTERN.match(text)
    if m:
        num_raw = m.group(2)
        title_raw = m.group(3)
        try:
            number: Any = int(num_raw)
        except (TypeError, ValueError):
            number = num_raw
        if title_raw:
            return number, title_raw.strip(), None
        # Number-only heading (e.g., "Chapter 5") — synthesize.
        return number, f"Chapter {num_raw}", "chapter_title synthesized from number-only heading"
    return None, text, "chapter_number not extractable"


def _synthesize_id(blk: Dict[str, Any]) -> str:
    """Some malformed v1 blocks may lack an id. Synthesize one from the
    block's hash so the upgrade still satisfies I-1 unique-ids — and
    log the synthesis as a classification note via a sentinel id
    pattern operators can grep for.
    """
    import hashlib
    h = hashlib.sha256(repr(blk).encode("utf-8")).hexdigest()[:6]
    return f"b_synth_{h}"


def _upgrade_warnings(v1_warnings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """v1 warnings may use codes that don't match v2's V-### / H-###
    schema. Wrap each as a generic V-000 entry so the v2 schema accepts
    it; preserve the original code in detail.
    """
    out = []
    for w in v1_warnings:
        if not isinstance(w, dict):
            continue
        code = w.get("code") or w.get("rule") or "UNKNOWN"
        sev = w.get("severity") or "medium"
        msg = w.get("detail") or w.get("message") or str(w)
        rule_id = w.get("rule") or "V-000"
        if not re.match(r"^[VH]-\d{3}$", str(rule_id)):
            rule_id = "V-000"
        out.append({
            "rule": rule_id,
            "severity": sev if sev in ("low", "medium", "high") else "medium",
            "detail": f"[upgraded from v1 warning code {code!r}] {msg}",
        })
    return out
