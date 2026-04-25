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

    Defaults are the Pronto Standard Edition v1 values from Doc 23
    R-1.2 / R-1.3 / R-3.2. Override at construction for tests; for
    production use the defaults verbatim ("opinionated by default,
    custom by exception").

    Field categories:

    Document-class options (Doc 23 R-3.2)
      - openright=True. \\documentclass[12pt,openright]{book}.

    Page geometry (Doc 23 R-1.1, R-1.2; inches)
      - 6×9 trim, asymmetric inside/outside to accommodate the gutter.

    Body typography (Doc 23 R-1.3)
      - EB Garamond, 10.5 pt body on 14 pt leading.
      - First-line indent: 1em.

    Note on the documentclass base size
      LaTeX's `book` class accepts only {10,11,12}pt as the
      documentclass base. We pass [12pt] and override the actual body
      font size + leading via \\fontsize{10.5pt}{14pt}\\selectfont in
      the body. This is the standard idiom for non-standard body sizes.
    """
    # -- documentclass ---------------------------------------------------
    documentclass_base_size_pt: int = 12
    """LaTeX `book` documentclass base size. Must be 10, 11, or 12 —
    the only values the standard book class accepts. Doc 23's 10.5 pt
    body is achieved via a body-level \\fontsize override, not by
    changing this."""

    openright: bool = True
    """documentclass openright option. Doc 23 R-3.2 mandates
    `openright` — every chapter starts on a recto."""

    # -- page geometry (inches) -----------------------------------------
    paper_width_in: float = 6.0
    paper_height_in: float = 9.0
    inside_margin_in: float = 0.875
    """Inside (binding-side) margin. Doc 23 R-1.2: 0.875in."""
    outside_margin_in: float = 0.625
    """Outside (page-edge) margin. Doc 23 R-1.2: 0.625in."""
    top_margin_in: float = 0.75
    bottom_margin_in: float = 0.75

    # -- body typography ------------------------------------------------
    body_font_family: str = "EB Garamond"
    """Family name as XeLaTeX expects via fontspec."""

    body_font_size_pt: float = 10.5
    """Actual body font size. Per Doc 23 R-1.3 = 10.5pt."""

    body_leading_pt: float = 14.0
    """Baselineskip in points. Per Doc 23 R-1.3 = 14pt."""

    parindent_em: float = 1.0
    """First-line indent in em (relative to body font size). Per
    Doc 23 R-1.3 = 1em. Used on every paragraph except the first
    paragraph of a chapter and post-scene-break paragraphs (per
    R-3.5 / R-4.4 — applied at converter level, not template)."""

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
        """Return the {{PARAM_*}} substitution map the templates consume.

        Every key here MUST appear in fiction_6x9.tex / nonfiction_6x9.tex
        (or be reserved for a future template revision). The unit tests
        verify post-substitution that no `{{PARAM_*}}` literal survives.
        """
        # Format floats deterministically: trim trailing zeros / dots.
        def fmt(x: float) -> str:
            s = f"{x:.4f}".rstrip("0").rstrip(".")
            return s if s else "0"

        return {
            "{{PARAM_DOCCLASS_BASE_SIZE_PT}}": str(self.documentclass_base_size_pt),
            "{{PARAM_DOCCLASS_OPENING}}":      "openright" if self.openright else "openany",
            "{{PARAM_PAPER_WIDTH_IN}}":        fmt(self.paper_width_in),
            "{{PARAM_PAPER_HEIGHT_IN}}":       fmt(self.paper_height_in),
            "{{PARAM_INSIDE_MARGIN_IN}}":      fmt(self.inside_margin_in),
            "{{PARAM_OUTSIDE_MARGIN_IN}}":     fmt(self.outside_margin_in),
            "{{PARAM_TOP_MARGIN_IN}}":         fmt(self.top_margin_in),
            "{{PARAM_BOTTOM_MARGIN_IN}}":      fmt(self.bottom_margin_in),
            "{{PARAM_BODY_FONT_FAMILY}}":      self.body_font_family,
            "{{PARAM_BODY_FONT_SIZE_PT}}":     fmt(self.body_font_size_pt),
            "{{PARAM_BODY_LEADING_PT}}":       fmt(self.body_leading_pt),
            "{{PARAM_PARINDENT_EM}}":          fmt(self.parindent_em),
        }


def derive(base: RenderParams, **changes: Any) -> RenderParams:
    """Convenience wrapper around dataclasses.replace for callers that
    don't want the dataclasses import. Returns a new frozen instance.
    """
    return replace(base, **changes)
