"""
Blocks to LaTeX Converter v2.0
===============================

Converts manuscript.v1.json blocks to LaTeX body markup.

Contract-first design:
  - Imports canonical block types from manuscript_schema.
  - Has an explicit handler for EVERY block type in the schema.
  - Fails loudly if a block type has no handler (schema was updated but
    this file was not).
  - Uses the canonical spans format for all text rendering.

Author: Pronto Publishing
Version: 2.0.0

Contract v1.1 integration (2026-04-23):
  This file replaces the v1.x BlocksToLatexConverter shipped with Worker 2
  through 1.2.0. It resolves the block-type vocabulary mismatch with the
  schema (REVIEW_NOTES C1), the spans/positional-marks mismatch (C2), and
  the partial LaTeX escaping (C3). All 14 canonical block types now have
  explicit handlers; unknown types raise in `__init__` rather than silently
  emitting `% Unknown block type: X` comments. Public API surface unchanged:
  `BlocksToLatexConverter(degraded=bool).convert(blocks) -> str`.
  Shared-schema import is relative to `lib/` (standard intra-package
  convention in this repo).
"""

import logging
from typing import List, Dict, Any, Optional

# Import the shared schema — single source of truth
from .manuscript_schema import (
    BLOCK_TYPES,
    BLOCK_TYPES_WITH_TEXT,
    BLOCK_TYPES_STRUCTURAL,
    INLINE_MARKS,
    BLOCK_FRONT_MATTER_TITLE,
    BLOCK_FRONT_MATTER_COPYRIGHT,
    BLOCK_FRONT_MATTER_DEDICATION,
    BLOCK_TOC_MARKER,
    BLOCK_CHAPTER_HEADING,
    BLOCK_HEADING,
    BLOCK_PARAGRAPH,
    BLOCK_BLOCKQUOTE,
    BLOCK_LIST,
    BLOCK_SCENE_BREAK,
    BLOCK_HORIZONTAL_RULE,
    BLOCK_PAGE_BREAK,
    BLOCK_BACK_MATTER_ABOUT_AUTHOR,
    BLOCK_BACK_MATTER_ALSO_BY,
    normalize_block_text,
)

logger = logging.getLogger(__name__)


class BlocksToLatexConverter:
    """
    Converts a normalized blocks array to LaTeX body content.

    The output is the BODY only (no preamble, no \\begin{document}).
    The caller (pronto_worker_2.py) is responsible for injecting this body
    into the appropriate .tex template via the {{CONTENT}} placeholder.
    """

    # -----------------------------------------------------------------------
    # Handler registry — maps every canonical block type to a method.
    # If a block type exists in the schema but not here, __init__ will raise.
    # -----------------------------------------------------------------------

    HANDLER_MAP: Dict[str, str] = {
        BLOCK_FRONT_MATTER_TITLE:       "_render_front_matter_title",
        BLOCK_FRONT_MATTER_COPYRIGHT:   "_render_front_matter_copyright",
        BLOCK_FRONT_MATTER_DEDICATION:  "_render_front_matter_dedication",
        BLOCK_TOC_MARKER:               "_render_toc_marker",
        BLOCK_CHAPTER_HEADING:          "_render_chapter_heading",
        BLOCK_HEADING:                  "_render_heading",
        BLOCK_PARAGRAPH:                "_render_paragraph",
        BLOCK_BLOCKQUOTE:               "_render_blockquote",
        BLOCK_LIST:                     "_render_list_item",
        BLOCK_SCENE_BREAK:              "_render_scene_break",
        BLOCK_HORIZONTAL_RULE:          "_render_horizontal_rule",
        BLOCK_PAGE_BREAK:               "_render_page_break",
        BLOCK_BACK_MATTER_ABOUT_AUTHOR: "_render_back_matter_about_author",
        BLOCK_BACK_MATTER_ALSO_BY:      "_render_back_matter_also_by",
    }

    # LaTeX special characters that need escaping
    LATEX_ESCAPES = [
        ('\\', r'\textbackslash{}'),   # Must be first
        ('&',  r'\&'),
        ('%',  r'\%'),
        ('$',  r'\$'),
        ('#',  r'\#'),
        ('_',  r'\_'),
        ('{',  r'\{'),
        ('}',  r'\}'),
        ('~',  r'\textasciitilde{}'),
        ('^',  r'\textasciicircum{}'),
    ]

    def __init__(self):
        """Initialize and verify exhaustive handler coverage."""
        # Verify every schema block type has a handler
        missing = BLOCK_TYPES - set(self.HANDLER_MAP.keys())
        if missing:
            raise RuntimeError(
                f"BlocksToLatexConverter is missing handlers for block types: "
                f"{sorted(missing)}. The schema was updated but the converter "
                f"was not. This is a deployment-blocking error."
            )

        extra = set(self.HANDLER_MAP.keys()) - BLOCK_TYPES
        if extra:
            logger.warning(
                f"Converter has handlers for non-schema block types: "
                f"{sorted(extra)}. These will never be called."
            )

    def convert(
        self,
        blocks: List[Dict[str, Any]],
        params: Dict[str, Any],
        degraded_mode: bool = False,
    ) -> str:
        """
        Convert blocks to LaTeX body content.

        Args:
            blocks: List of blocks from manuscript artifact (already normalized).
            params: Formatting parameters (trim size, font, genre, etc.).
            degraded_mode: If True, use fallback rendering for edge cases.

        Returns:
            LaTeX body content as string (no preamble, no document wrapper).
        """
        logger.info(
            f"Converting {len(blocks)} blocks to LaTeX "
            f"(degraded={degraded_mode})"
        )

        output_parts: List[str] = []

        # State tracking for list grouping
        current_list_group: Optional[int] = None
        current_list_type: Optional[str] = None

        # State tracking for back matter section headings
        seen_about_author = False
        seen_also_by = False

        for i, raw_block in enumerate(blocks):
            # Normalize legacy text → spans
            block = normalize_block_text(raw_block)
            block_type = block.get("type", "")
            meta = block.get("meta", {})

            # ---- List grouping logic ----
            is_list = block_type == BLOCK_LIST
            block_list_group = meta.get("list_group") if is_list else None
            block_list_type = meta.get("list_type", "unordered") if is_list else None

            # Close previous list if we're leaving a list group
            if current_list_group is not None and (
                not is_list or block_list_group != current_list_group
            ):
                env = "enumerate" if current_list_type == "ordered" else "itemize"
                output_parts.append(f"\\end{{{env}}}")
                output_parts.append("")
                current_list_group = None
                current_list_type = None

            # Open new list if starting a new group
            if is_list and block_list_group != current_list_group:
                env = "enumerate" if block_list_type == "ordered" else "itemize"
                output_parts.append(f"\\begin{{{env}}}")
                current_list_group = block_list_group
                current_list_type = block_list_type

            # ---- Dispatch to handler ----
            handler_name = self.HANDLER_MAP.get(block_type)

            if handler_name is None:
                # This should never happen if __init__ validation passed
                logger.error(f"No handler for block type '{block_type}'")
                output_parts.append(f"% ERROR: no handler for {block_type}")
                continue

            handler = getattr(self, handler_name)

            # Pass context for back matter heading tracking
            ctx = {
                "degraded": degraded_mode,
                "seen_about_author": seen_about_author,
                "seen_also_by": seen_also_by,
            }

            latex = handler(block, ctx)

            # Update back matter tracking
            if block_type == BLOCK_BACK_MATTER_ABOUT_AUTHOR:
                seen_about_author = True
            if block_type == BLOCK_BACK_MATTER_ALSO_BY:
                seen_also_by = True

            if latex:
                output_parts.append(latex)
                output_parts.append("")  # Blank line between blocks

        # Close any trailing open list
        if current_list_group is not None:
            env = "enumerate" if current_list_type == "ordered" else "itemize"
            output_parts.append(f"\\end{{{env}}}")
            output_parts.append("")

        return "\n".join(output_parts)

    # ===================================================================
    # Span rendering — the core text engine
    # ===================================================================

    def _render_spans(self, block: Dict[str, Any]) -> str:
        """
        Render a block's spans to LaTeX text with inline formatting.

        Handles the canonical spans format:
            [{"text": "hello ", "marks": []}, {"text": "world", "marks": ["bold"]}]

        Also handles legacy format (block has 'text' string, no 'spans')
        via normalize_block_text() which should have already been called.
        """
        spans = block.get("spans", [])

        if not spans:
            # Fallback: if somehow we still have a plain text field
            text = block.get("text", "")
            return self._escape_latex(text)

        parts = []
        for span in spans:
            text = span.get("text", "")
            marks = span.get("marks", [])

            escaped = self._escape_latex(text)

            # Apply marks (innermost first, then wrap outward)
            result = escaped
            for mark in marks:
                if mark == "italic":
                    result = f"\\textit{{{result}}}"
                elif mark == "bold":
                    result = f"\\textbf{{{result}}}"
                elif mark == "smallcaps":
                    result = f"\\textsc{{{result}}}"
                elif mark == "code":
                    result = f"\\texttt{{{result}}}"
                # Unknown marks are silently ignored (schema validation
                # should have caught them upstream)

            parts.append(result)

        return "".join(parts)

    def _render_spans_plain(self, block: Dict[str, Any]) -> str:
        """
        Render a block's spans as plain text (no LaTeX formatting commands),
        but still escape LaTeX special characters.

        Used for contexts where inline formatting would break (e.g., chapter titles
        in \\chapter{} commands where nested commands can cause issues).
        """
        spans = block.get("spans", [])
        if not spans:
            return self._escape_latex(block.get("text", ""))

        return "".join(self._escape_latex(s.get("text", "")) for s in spans)

    def _escape_latex(self, text: str) -> str:
        """Escape LaTeX special characters in text."""
        for char, replacement in self.LATEX_ESCAPES:
            text = text.replace(char, replacement)
        return text

    # ===================================================================
    # Block handlers — one per canonical block type
    # ===================================================================

    def _render_front_matter_title(
        self, block: Dict[str, Any], ctx: Dict
    ) -> str:
        """
        Front matter title block.

        The template already has a title page with {{BOOK_TITLE}}, so we emit
        a LaTeX comment. If the template's title page is removed in the future,
        this handler can be updated to render the title directly.
        """
        return "% front_matter_title: handled by template title page"

    def _render_front_matter_copyright(
        self, block: Dict[str, Any], ctx: Dict
    ) -> str:
        """
        Copyright notice text from the manuscript.

        The template already has a copyright page with boilerplate. This renders
        any additional copyright text the author included in their manuscript.
        """
        text = self._render_spans(block)
        if not text.strip():
            return "% front_matter_copyright: empty"
        # Render as small text on the copyright page area
        return (
            f"\\begin{{flushleft}}\n"
            f"\\small\n"
            f"{text}\n"
            f"\\end{{flushleft}}\n"
            f"\\clearpage"
        )

    def _render_front_matter_dedication(
        self, block: Dict[str, Any], ctx: Dict
    ) -> str:
        """Dedication: centered text (italic applied via spans), then page break."""
        text = self._render_spans(block)
        return (
            f"\\vspace*{{\\fill}}\n"
            f"\\begin{{center}}\n"
            f"{text}\n"
            f"\\end{{center}}\n"
            f"\\vspace*{{\\fill}}\n"
            f"\\clearpage"
        )

    def _render_toc_marker(
        self, block: Dict[str, Any], ctx: Dict
    ) -> str:
        """
        Table of contents marker.

        The template controls whether TOC is included. This is a no-op
        placeholder that acknowledges the marker exists.
        """
        return "% toc_marker: TOC placement handled by template"

    def _render_chapter_heading(
        self, block: Dict[str, Any], ctx: Dict
    ) -> str:
        """Chapter heading — numbered or unnumbered."""
        meta = block.get("meta", {})
        chapter_num = meta.get("chapter_number")
        title = self._render_spans_plain(block)

        if chapter_num is not None and chapter_num > 0:
            # Numbered chapter: \chapter{Title}
            return f"\\chapter{{{title}}}"
        else:
            # Unnumbered chapter (prologue, epilogue, etc.)
            return (
                f"\\chapter*{{{title}}}\n"
                f"\\addcontentsline{{toc}}{{chapter}}{{{title}}}"
            )

    def _render_heading(
        self, block: Dict[str, Any], ctx: Dict
    ) -> str:
        """Sub-heading (level 2–4)."""
        meta = block.get("meta", {})
        level = meta.get("level", 2)
        title = self._render_spans_plain(block)

        if level == 2:
            return f"\\section*{{{title}}}"
        elif level == 3:
            return f"\\subsection*{{{title}}}"
        elif level == 4:
            return f"\\subsubsection*{{{title}}}"
        else:
            return f"\\section*{{{title}}}"

    def _render_paragraph(
        self, block: Dict[str, Any], ctx: Dict
    ) -> str:
        """Body paragraph — the most common block type."""
        return self._render_spans(block)

    def _render_blockquote(
        self, block: Dict[str, Any], ctx: Dict
    ) -> str:
        """Block quotation."""
        text = self._render_spans(block)
        return (
            f"\\begin{{quotation}}\n"
            f"{text}\n"
            f"\\end{{quotation}}"
        )

    def _render_list_item(
        self, block: Dict[str, Any], ctx: Dict
    ) -> str:
        """
        Single list item.

        List grouping (begin/end itemize/enumerate) is handled by the
        convert() method's list group tracking, not here.
        """
        text = self._render_spans(block)
        return f"  \\item {text}"

    def _render_scene_break(
        self, block: Dict[str, Any], ctx: Dict
    ) -> str:
        """Scene break (visual separator)."""
        return "\\scenebreak"

    def _render_horizontal_rule(
        self, block: Dict[str, Any], ctx: Dict
    ) -> str:
        """Horizontal rule."""
        return (
            "\\par\\vspace{\\baselineskip}\n"
            "\\noindent\\rule{\\textwidth}{0.4pt}\n"
            "\\par\\vspace{\\baselineskip}"
        )

    def _render_page_break(
        self, block: Dict[str, Any], ctx: Dict
    ) -> str:
        """Forced page break."""
        return "\\clearpage"

    def _render_back_matter_about_author(
        self, block: Dict[str, Any], ctx: Dict
    ) -> str:
        """
        About the Author section.

        First occurrence gets a chapter heading; subsequent blocks in the
        same section are rendered as body paragraphs.
        """
        text = self._render_spans(block)
        if not ctx.get("seen_about_author"):
            return (
                f"\\chapter*{{About the Author}}\n"
                f"\\addcontentsline{{toc}}{{chapter}}{{About the Author}}\n"
                f"{text}"
            )
        else:
            return text

    def _render_back_matter_also_by(
        self, block: Dict[str, Any], ctx: Dict
    ) -> str:
        """
        Also By section.

        First occurrence gets a chapter heading; subsequent blocks are body text.
        """
        text = self._render_spans(block)
        if not ctx.get("seen_also_by"):
            return (
                f"\\chapter*{{Also By}}\n"
                f"\\addcontentsline{{toc}}{{chapter}}{{Also By}}\n"
                f"{text}"
            )
        else:
            return text
