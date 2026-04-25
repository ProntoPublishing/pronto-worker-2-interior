"""
Render parameters — single source of truth for layout / typography.

Why this module exists
  Before this, render parameters lived three places at once: hardcoded
  in fiction_6x9.tex / nonfiction_6x9.tex, partially overridden by a
  loose `params: dict` plumbed through `BlocksToLatexConverter.convert`,
  and partially derived from Airtable fields inside
  `pronto_worker_2.py:process_service`. Doc 23 v1 ("Pronto Standard
  Edition") wants one canonical set of typography parameters, applied
  the same way every render.

Scope of v1
  This module defines the parameter shape. The value defaults are
  CURRENT-template-equivalent — exactly the values fiction_6x9.tex /
  nonfiction_6x9.tex hardcode today. That keeps this commit a pure
  refactor (no rendered-output drift). The follow-on "typography +
  openright" commit changes the defaults to the Doc 23 R-1.2 / R-1.3
  Pronto Standard Edition values and refactors the templates to read
  them via {{PARAM_*}} placeholders.

Naming
  Field names match the LaTeX concept they map to (`parindent_em`,
  `outside_margin_in`), not the Airtable field name they used to come
  from. The Airtable layer is a *source* of `book_title` /
  `author_name` / `isbn`, never of typography.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict, replace
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class RenderParams:
    """The typography + layout parameters for one render.

    Frozen so callers can't accidentally mutate a shared instance.
    Use `replace(params, foo=…)` to derive a modified copy.

    Field categories:

    Document-class options
      - `openright`: per Doc 23 R-3.2 the canonical Pronto Standard
        Edition value is True (\\documentclass[...,openright]{book}).
        v1 substrate keeps False to match the current template.

    Page geometry (inches)
      - 6×9 trim per Doc 23 R-1.1
      - asymmetric inside/outside per R-1.2

    Body typography
      - EB Garamond / 10.5pt / 14pt leading per R-1.3 (Doc 23 target)
      - Substrate baseline keeps the current 12pt / 1.2-stretch values.
    """
    # -- documentclass ---------------------------------------------------
    base_font_size_pt: float = 12.0
    """Document-class base font size. v1 substrate matches current
    template (12pt). Doc 23 R-1.3 target is 10.5pt."""

    openright: bool = False
    """documentclass openright option. v1 substrate matches current
    `openany`. Doc 23 R-3.2 mandates `openright`."""

    # -- page geometry (inches) -----------------------------------------
    paper_width_in: float = 6.0
    paper_height_in: float = 9.0
    inside_margin_in: float = 0.75
    """Inside (binding-side) margin. Doc 23 R-1.2 target: 0.875."""
    outside_margin_in: float = 0.5
    """Outside (page-edge) margin. Doc 23 R-1.2 target: 0.625."""
    top_margin_in: float = 0.75
    bottom_margin_in: float = 0.75

    # -- body typography ------------------------------------------------
    body_font_family: str = "EB Garamond"
    """Family name as XeLaTeX expects via fontspec. The
    pronto_worker_2.process_service `font_map` translation logic moves
    here in a follow-on commit."""

    line_stretch: float = 1.2
    """setstretch value. Substrate matches current template. Doc 23
    targets 14pt leading on 10.5pt body, computed via fixed
    baselineskip rather than a stretch factor."""

    parindent_in: float = 0.25
    """First-line indent in inches. Doc 23 R-1.3 target: 1em (≈ 0.146in
    at 10.5pt). Substrate matches current 0.25in."""

    # -- book metadata (carried through, not "typography" but lives on
    # this struct so the template-fill layer has one input). -----------
    book_title: str = ""
    author_name: str = ""
    isbn: str = ""
    year: str = ""
    """Copyright-page year. In deterministic mode this is pinned to a
    fixed value rather than `datetime.now().year`."""

    genre: str = "fiction"
    """Selects fiction_6x9.tex vs nonfiction_6x9.tex. Lowercased on
    read."""

    # -- legacy bag for fields not yet promoted ------------------------
    extras: Dict[str, Any] = field(default_factory=dict)
    """Free-form pass-through for fields that haven't been promoted to
    structured attributes yet (e.g. genre-template variants). The
    converter and template-fill layers may consult specific keys."""

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------
    @classmethod
    def from_airtable_book_metadata(cls, fields: Dict[str, Any]) -> "RenderParams":
        """Build a RenderParams from an Airtable Book Metadata record's
        `fields` dict. Honors only the fields that map to Pronto
        Standard Edition v1 — typography stays at module defaults
        regardless of what the Book Metadata record says, per Doc 23's
        "opinionated by default, custom by exception" posture.
        """
        return cls(
            book_title=str(fields.get("Book Title") or fields.get("Title") or ""),
            author_name=str(
                fields.get("Author Name") or fields.get("Author") or ""
            ),
            isbn=str(fields.get("ISBN") or ""),
            genre=str(fields.get("Genre") or "fiction").lower(),
        )

    @classmethod
    def deterministic(cls, **overrides: Any) -> "RenderParams":
        """Return a fully-deterministic params instance. Used by the
        local runner so PDF metadata / template-fill text doesn't vary
        run-to-run. Caller may override book_title / author_name / etc.
        when fixture-specific values are wanted.
        """
        base: Dict[str, Any] = {
            "year": "1970",  # XeLaTeX won't see datetime.now()
            "book_title": "Local Run",
            "author_name": "Local Run",
            "isbn": "",
            "genre": "fiction",
        }
        base.update(overrides)
        return cls(**base)  # type: ignore[arg-type]

    # ------------------------------------------------------------------
    # Template / dict adapters
    # ------------------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        """Plain dict for back-compat with the existing
        BlocksToLatexConverter.convert(params=…) contract.

        Carries ALL the structured fields so a converter that learns
        about a new field tomorrow doesn't need a producer change.
        """
        d = asdict(self)
        # Flatten extras into the top level for the legacy contract.
        extras = d.pop("extras", {}) or {}
        for k, v in extras.items():
            d.setdefault(k, v)
        # Convenience aliases that the legacy code already reads.
        d.setdefault("font", self.body_font_family)
        return d

    def to_template_fills(self) -> Dict[str, str]:
        """Return the {{PARAM_*}} substitution map the template
        consumes. Substrate keeps the existing template intact and
        emits a complete map anyway — the template ignores keys it
        doesn't reference, so this is forward-compatible with the
        Doc 23 typography flip without changing today's output.
        """
        # Format floats deterministically: trim trailing zeros / dots.
        def fmt(x: float) -> str:
            s = f"{x:.4f}".rstrip("0").rstrip(".")
            return s if s else "0"

        return {
            "{{PARAM_BASE_FONT_SIZE_PT}}": fmt(self.base_font_size_pt),
            "{{PARAM_DOCCLASS_OPENING}}": "openright" if self.openright else "openany",
            "{{PARAM_PAPER_WIDTH_IN}}":   fmt(self.paper_width_in),
            "{{PARAM_PAPER_HEIGHT_IN}}":  fmt(self.paper_height_in),
            "{{PARAM_INSIDE_MARGIN_IN}}":  fmt(self.inside_margin_in),
            "{{PARAM_OUTSIDE_MARGIN_IN}}": fmt(self.outside_margin_in),
            "{{PARAM_TOP_MARGIN_IN}}":    fmt(self.top_margin_in),
            "{{PARAM_BOTTOM_MARGIN_IN}}": fmt(self.bottom_margin_in),
            "{{PARAM_BODY_FONT_FAMILY}}": self.body_font_family,
            "{{PARAM_LINE_STRETCH}}":     fmt(self.line_stretch),
            "{{PARAM_PARINDENT_IN}}":     fmt(self.parindent_in),
        }


def derive(base: RenderParams, **changes: Any) -> RenderParams:
    """Convenience wrapper around dataclasses.replace for callers that
    don't want the dataclasses import. Returns a new frozen instance.
    """
    return replace(base, **changes)
