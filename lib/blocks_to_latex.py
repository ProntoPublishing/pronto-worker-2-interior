"""
Blocks to LaTeX Converter v3.1.0 (v1.3.1 chapter-heading fixes)
================================================================

Consumes manuscript.v2.0-shaped blocks and emits LaTeX body markup.
v1.0 artifacts are upgraded to v2.0 shape upstream by
`lib.artifact_readers.read_artifact()` before reaching this converter,
so this module sees a single representation: blocks with a non-null
`role`, plus role-specific fields (chapter_number / chapter_title for
chapter_heading, force_page_break for part_divider, subtype for
front/back_matter, etc.).

Why this is a rewrite vs. v2.0.0
  v2.0.0 (still in W2 main pre-this-branch) dispatched on the v1
  block `type` field — paragraph, chapter_heading, list, etc. The
  dispatch axis was the v1 vocabulary. v2.0 artifacts use semantic
  roles instead, so the dispatch axis flips. As a side effect, the
  doubled-chapter bug ("CHAPTER 1\\nWhat Depression Actually Is" sent
  whole into \\chapter{...}) is structurally impossible: chapter_title
  carries the title alone; chapter_number is a separate field.

Design

  - HANDLER_MAP keys are v2 roles (15 from Doc 22 v1.0.2 §Layer 2).
  - __init__ verifies coverage; refuses to start if any role is
    missing a handler.
  - LaTeX special characters are escaped at span boundaries
    (preserves the v2.0.0 C3 fix from REVIEW_NOTES).
  - List grouping wraps consecutive list_item-role blocks in a single
    itemize/enumerate based on the optional `list_ordered` field
    (defaults to itemize when absent).
  - Public API stays signature-compatible:
      `BlocksToLatexConverter().convert(blocks, params, degraded_mode) -> str`
"""
from __future__ import annotations
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# Canonical Layer 2 role enum from Doc 22 v1.0.2, plus the v2.1 schema
# addition (chapter_subtitle, amendment spec §2.3 — a title paired to the
# landmark above it: Carol's stave names, Hatch's italic chapter subtitles).
ROLES = frozenset({
    "title_page",
    "front_matter",
    "part_divider",
    "chapter_heading",
    "chapter_subtitle",
    "body_paragraph",
    "scene_break",
    "back_matter",
    "heading",
    "list_item",
    "blockquote",
    "table",
    "image",
    "code_block",
    "footnote",
    "structural",
})

# Canonical span marks vocabulary (Doc 22 v1.0.1 §CIR).
SPAN_MARKS = frozenset({
    "italic", "bold", "small_caps", "code",
    "underline", "strikethrough", "superscript", "subscript",
})


class BlocksToLatexConverter:
    """v3.0.0: v2.0-native, role-based dispatch."""

    HANDLER_MAP: Dict[str, str] = {
        "title_page":      "_render_title_page",
        "front_matter":    "_render_front_matter",
        "part_divider":    "_render_part_divider",
        "chapter_heading": "_render_chapter_heading",
        "chapter_subtitle": "_render_chapter_subtitle",
        "body_paragraph":  "_render_body_paragraph",
        "scene_break":     "_render_scene_break",
        "back_matter":     "_render_back_matter",
        "heading":         "_render_heading",
        "list_item":       "_render_list_item",
        "blockquote":      "_render_blockquote",
        "table":           "_render_table",
        "image":           "_render_image",
        "code_block":      "_render_code_block",
        "footnote":        "_render_footnote",
        "structural":      "_render_structural",
    }

    # LaTeX special-char escapes. Order matters: backslash first.
    _ESCAPES = [
        ("\\", "\\textbackslash{}"),
        ("&",  r"\&"),
        ("%",  r"\%"),
        ("$",  r"\$"),
        ("#",  r"\#"),
        ("_",  r"\_"),
        ("{",  r"\{"),
        ("}",  r"\}"),
        ("~",  r"\textasciitilde{}"),
        ("^",  r"\textasciicircum{}"),
    ]

    def __init__(self):
        """Verify exhaustive role coverage."""
        missing = ROLES - set(self.HANDLER_MAP.keys())
        if missing:
            raise RuntimeError(
                f"BlocksToLatexConverter is missing handlers for roles: "
                f"{sorted(missing)}. The Layer 2 enum was updated but the "
                f"converter was not. This is a deployment-blocking error."
            )
        extra = set(self.HANDLER_MAP.keys()) - ROLES
        if extra:
            logger.warning(
                f"Converter has handlers for non-canonical roles: "
                f"{sorted(extra)}. These will never be called."
            )

    # -- Public API ----------------------------------------------------------

    def convert(
        self,
        blocks: List[Dict[str, Any]],
        params: Dict[str, Any],
        degraded_mode: bool = False,
    ) -> str:
        """Convert v2.0 blocks to LaTeX body content.

        Returns a string suitable for substituting into the {{CONTENT}}
        placeholder in fiction_6x9.tex / nonfiction_6x9.tex.

        Title-page invariant (§6 review, 2026-07-16): title_page-role
        blocks NEVER render here — the body is the wrong position for a
        title page. They render (when H-001 chose them) in the template's
        front-matter §3 slot via render_title_page_cluster(); this
        method emits traceability comments in their place.
        """
        logger.info(
            f"Converting {len(blocks)} v2 blocks to LaTeX "
            f"(degraded={degraded_mode})"
        )

        out: List[str] = []
        list_state = _ListState()

        for block in blocks:
            role = block.get("role")
            if role is None:
                # Producer should have applied terminal default. The v2
                # reader catches missing role; if we're here, something's
                # off — emit a comment and continue rather than crash.
                logger.error(f"Block {block.get('id')} has no role")
                out.append(f"% ERROR: block {block.get('id')} has no role")
                continue

            # List-grouping: wrap consecutive list_item blocks.
            new_env = list_state.transition(block, role)
            if new_env.close_prev:
                out.append(f"\\end{{{new_env.close_prev}}}")
                out.append("")
            if new_env.open_new:
                out.append(f"\\begin{{{new_env.open_new}}}")

            handler_name = self.HANDLER_MAP.get(role)
            if handler_name is None:
                # FAIL-SAFE DEFAULT (amendment spec §5.3). A role this
                # converter doesn't know — a future schema addition —
                # must never cost the reader content. Render the block's
                # text as a plain body paragraph and log loudly. The
                # worst case becomes a formatting deficiency, not silent
                # content loss.
                logger.error(
                    f"UNKNOWN ROLE {role!r} on block {block.get('id')} — "
                    f"no handler; rendering as plain body text (fail-safe "
                    f"default). A W2 update for this role is overdue."
                )
                fallback = self._render_spans(block)
                out.append(f"% WARNING: unknown role {role} rendered as body text")
                if fallback:
                    out.append(fallback)
                    out.append("")
                continue
            handler = getattr(self, handler_name)
            ctx = {"degraded": degraded_mode, "params": params}
            latex = handler(block, ctx)
            if latex:
                out.append(latex)
                out.append("")

        # Close any list still open at end-of-document.
        if list_state.open_env:
            out.append(f"\\end{{{list_state.open_env}}}")
            out.append("")

        return "\n".join(out).rstrip() + "\n"

    # -- Span / text rendering ----------------------------------------------

    def _render_spans(self, block: Dict[str, Any]) -> str:
        """Render a block's spans (or text) to escaped LaTeX, applying
        per-span marks. v2 always uses spans (with at least one span).
        For defensiveness against malformed input, falls back to
        block.text.
        """
        spans = block.get("spans")
        if isinstance(spans, list) and spans:
            parts: List[str] = []
            for span in spans:
                text = span.get("text", "") if isinstance(span, dict) else str(span)
                marks = span.get("marks", []) if isinstance(span, dict) else []
                # Escape THEN wrap, so escapes don't mangle LaTeX commands.
                escaped = self._escape(text)
                parts.append(self._wrap_with_marks(escaped, marks))
            return "".join(parts)
        return self._escape(block.get("text", "") or "")

    def _wrap_with_marks(self, escaped_text: str, marks: List[str]) -> str:
        """Wrap escaped text with the per-span marks. Marks not in the
        canonical vocabulary are dropped silently (the v1 reader already
        normalizes what it carries through; W1 v5.0 producer emits only
        canonical marks).
        """
        if not marks:
            return escaped_text
        wrapped = escaped_text
        for mark in marks:
            if mark == "italic":
                wrapped = f"\\textit{{{wrapped}}}"
            elif mark == "bold":
                wrapped = f"\\textbf{{{wrapped}}}"
            elif mark == "small_caps":
                wrapped = f"\\textsc{{{wrapped}}}"
            elif mark == "code":
                wrapped = f"\\texttt{{{wrapped}}}"
            elif mark == "underline":
                wrapped = f"\\underline{{{wrapped}}}"
            elif mark == "strikethrough":
                wrapped = f"\\sout{{{wrapped}}}"
            elif mark == "superscript":
                wrapped = f"\\textsuperscript{{{wrapped}}}"
            elif mark == "subscript":
                wrapped = f"\\textsubscript{{{wrapped}}}"
            # else: unknown mark, drop silently.
        return wrapped

    def _escape(self, text: str) -> str:
        """Escape every LaTeX special character. Applied at span
        boundaries before wrapping with marks (the v2.0.0 C3 fix).
        """
        if not text:
            return ""
        out = text
        for ch, replacement in self._ESCAPES:
            out = out.replace(ch, replacement)
        return out

    # -- Plain text helper (titles, headings without inline marks) ---------

    def _plain(self, block: Dict[str, Any]) -> str:
        """Get a block's text as a single escaped string, ignoring marks.
        Used for chapter titles, headings, and similar where running the
        full mark-rendering would put `\\textbf{}` etc. inside `\\chapter{}`
        — legal LaTeX but unusual.

        Whitespace runs (including newlines) collapse to single spaces:
        every caller passes the result into a sectioning-command argument,
        where an embedded blank line is a LaTeX error that nonstopmode
        "recovers" from by spilling the argument as unstyled body text
        (Book 02 corpus finding, 2026-07-14).
        """
        spans = block.get("spans")
        if isinstance(spans, list) and spans:
            text = "".join(s.get("text", "") for s in spans if isinstance(s, dict))
        else:
            text = block.get("text", "") or ""
        return self._escape(" ".join(text.split()))

    # -- Role handlers ------------------------------------------------------

    def _render_title_page(self, block: Dict[str, Any], ctx: Dict[str, Any]) -> str:
        """title_page-role blocks NEVER render in the body (§6 review
        invariant, 2026-07-16): exactly one title page per book, in the
        front-matter §3 position. H-001 arbitration decides what fills
        the template's title-page slot — fired → this cluster, rendered
        there via render_title_page_cluster(); not fired → the system
        page. Either way the body copy is suppressed; this comment is
        the traceability marker.
        """
        return (
            f"% title_page block {block.get('id')} suppressed in body "
            f"(renders in the front-matter slot iff H-001 chose it)"
        )

    @staticmethod
    def _positional_of(block: Dict[str, Any]) -> str:
        """Positional sub-role ("title" / "subtitle" / "author_or_byline")
        from C-003's classification_notes; "" when absent (v1
        synthesized title_page blocks)."""
        for n in (block.get("classification_notes") or []):
            if "positional role:" in n:
                return n.split(":", 1)[-1].strip().lower()
        return ""

    def render_title_page_cluster(self, blocks: List[Dict[str, Any]]) -> str:
        """LaTeX for the front-matter §3 title-page SLOT, built from the
        author's classified title_page cluster (call only when H-001
        fired). One folio-free recto: title \\Huge, subtitle \\Large,
        byline/anything-else \\large, in document order; ends with
        \\clearpage so the copyright page lands on the verso behind it,
        exactly like the system title page it replaces.
        """
        lines: List[str] = []
        for block in blocks:
            if block.get("role") != "title_page":
                continue
            text = self._render_spans(block)
            if not text:
                continue
            positional = self._positional_of(block)
            if positional == "title" or not positional:
                lines.append(f"{{\\Huge\\textbf{{{text}}}}}\\par\\vspace{{1.5em}}")
            elif positional == "subtitle":
                lines.append(f"{{\\Large {text}}}\\par\\vspace{{1em}}")
            else:  # author_or_byline / unknown positional
                lines.append(f"{{\\large {text}}}\\par\\vspace{{1em}}")
        if not lines:
            # Defensive: slot caller checked H-001, but the cluster is
            # empty — emit nothing rather than a blank styled page.
            return "% H-001 fired but title_page cluster is empty"
        return (
            "\\thispagestyle{empty}\n"
            "\\begin{center}\n"
            "\\vspace*{1in}\n"
            + "\n".join(lines) + "\n"
            "\\vfill\n"
            "\\end{center}\n"
            "\\clearpage"
        )

    def _render_front_matter(self, block: Dict[str, Any], ctx: Dict[str, Any]) -> str:
        """Front-matter heading + (optional) body. Subtype steers the
        layout: dedication → centered italic; copyright → small flushleft;
        anything else → unnumbered chapter-style.
        """
        subtype = (block.get("subtype") or "generic").lower()
        title = self._plain(block)
        text_body = title  # v1.3: front_matter blocks are heading-shaped.

        if subtype == "dedication":
            return (
                "\\vspace*{\\fill}\n"
                "\\begin{center}\n"
                f"\\textit{{{text_body}}}\n"
                "\\end{center}\n"
                "\\vspace*{\\fill}\n"
                "\\clearpage"
            )
        if subtype == "copyright":
            return (
                "\\thispagestyle{empty}\n"
                "\\vspace*{\\fill}\n"
                "\\begin{flushleft}\n"
                "\\small\n"
                f"{text_body}\n"
                "\\end{flushleft}\n"
                "\\clearpage"
            )
        # generic / preface / foreword / introduction / note_to_reader / etc.
        # Interior Standard v1 §3.5 [BOUND]: front-matter items are NOT
        # listed in the TOC — no \addcontentsline here (back matter
        # keeps its entries).
        return f"\\chapter*{{{text_body}}}"

    def _render_part_divider(self, block: Dict[str, Any], ctx: Dict[str, Any]) -> str:
        """Part divider. Per I-5 always carries force_page_break: true.
        We honor that explicitly here so the page break is visible at
        the rendered-source level, not buried inside titlesec config.
        """
        title = self._escape(block.get("part_title") or "")
        force_break = block.get("force_page_break", True)
        prefix = "\\clearpage\n" if force_break else ""
        # Clear the running-header chapter mark: pages between a part
        # divider and its first chapter must not show the previous
        # chapter's title.
        return (
            f"{prefix}\\part*{{{title}}}\n"
            f"\\addcontentsline{{toc}}{{part}}{{{title}}}\n"
            f"\\markright{{}}"
        )

    # Matches the line inside a multi-line chapter_title that carries the
    # chapter designation. Deliberately a bare prefix (no \b): corpus
    # sources produce fused headings like "CHAPTERXXVII." (Book 02).
    _CHAPTER_LINE_RE = re.compile(r"^chapter", re.IGNORECASE)

    # Label-shaped title detection (schema 2.1 / rules 1.1 coordination):
    # W1 v1.1 emits chapter_number as an INTEGER ("the integer is
    # metadata") and synthesizes titles like "Letter IV" / "Stave ONE" /
    # "Chapter XXVII" from the source's section word + display ordinal.
    # A title that is nothing but such a label must render ONCE (the
    # \chapter* path), preserving the source's word and ordinal style —
    # otherwise the template prints its own "CHAPTER n" above it and
    # every heading doubles (Frankenstein letters rendered "CHAPTER 1 /
    # LETTER I"). Lexicon mirrors W1's landmarks.py — shared-library
    # consolidation punchlist item, same as the roman parser.
    _LABEL_RE = re.compile(
        r"^(?:chapter|chap\.?|stave|letter|canto|section|act|scene|lesson"
        r"|part|book|volume|vol\.?)\s*(?P<ordinal>[\w\-]+?)[.:]?$",
        re.IGNORECASE,
    )

    _WORD_ORDINALS = {
        **{w: i for i, w in enumerate(
            ("ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX", "SEVEN",
             "EIGHT", "NINE"), 1)},
        **{w: i for i, w in enumerate(
            ("TEN", "ELEVEN", "TWELVE", "THIRTEEN", "FOURTEEN", "FIFTEEN",
             "SIXTEEN", "SEVENTEEN", "EIGHTEEN", "NINETEEN"), 10)},
        "TWENTY": 20, "THIRTY": 30, "FORTY": 40, "FIFTY": 50,
        "SIXTY": 60, "SEVENTY": 70, "EIGHTY": 80, "NINETY": 90,
    }

    def _title_is_label(self, head: str, number_int: Optional[int]) -> bool:
        """True when the chapter_title is just the heading label itself
        (section word + the same ordinal chapter_number carries)."""
        if number_int is None:
            return False
        m = self._LABEL_RE.match(head.strip())
        if not m:
            return False
        tok = m.group("ordinal")
        value = self._chapter_number_as_int(tok)
        if value is None:
            value = self._word_ordinal_to_int(tok)
        return value == number_int

    def _word_ordinal_to_int(self, token: str) -> Optional[int]:
        s = re.sub(r"[\s\-]+", " ", token.strip().upper())
        if s in self._WORD_ORDINALS:
            return self._WORD_ORDINALS[s]
        parts = s.split(" ")
        if (len(parts) == 2 and parts[0] in self._WORD_ORDINALS
                and parts[1] in self._WORD_ORDINALS
                and self._WORD_ORDINALS[parts[0]] % 10 == 0
                and self._WORD_ORDINALS[parts[1]] < 10):
            return self._WORD_ORDINALS[parts[0]] + self._WORD_ORDINALS[parts[1]]
        return None

    def _render_chapter_heading(self, block: Dict[str, Any], ctx: Dict[str, Any]) -> str:
        """v2 chapter heading: chapter_number + chapter_title are
        separate fields.

        Two hardening rules from the Book 02 (P&P) corpus run, 2026-07-14:

        1. The printed ordinal comes from the artifact's chapter_number,
           never from LaTeX's own chapter counter. \\chapter{} auto-numbers
           sequentially over *numbered* chapters only, so any unnumbered
           chapter in between desynchronizes the label (Chapter IV rendered
           "CHAPTER 2"). We \\setcounter{chapter}{N-1} from the artifact
           before every numbered \\chapter.

        2. chapter_title may span multiple lines: DOCX conversions can merge
           adjacent text (e.g. an illustration caption) into the heading
           block. A blank line inside a sectioning-command argument is a
           LaTeX error, and nonstopmode "recovers" by spilling the argument
           into the body as unstyled text — dropping content and doubling
           the heading. Titles are therefore split into lines: the
           chapter-pattern line becomes the styled heading; every other
           line renders as a centered italic line directly beneath it.
           Nothing is dropped. Single-line titles take the exact same path
           they always did.

        When the source heading was number-only (C-001 synthesizes
        chapter_title as "Chapter <n>"), printing the template's label
        AND the synthesized title would show the ordinal twice — so those
        render once, via \\chapter*, preserving the source's numbering
        style (e.g. roman "CHAPTER IV" rather than arabic "CHAPTER 4").
        """
        raw_title = block.get("chapter_title") or ""
        chapter_number = block.get("chapter_number")

        lines = [ln.strip() for ln in raw_title.splitlines() if ln.strip()]
        if not lines:
            lines = [raw_title.strip()]

        if len(lines) == 1:
            head, extras = lines[0], []
        else:
            matches = [
                i for i, ln in enumerate(lines) if self._CHAPTER_LINE_RE.match(ln)
            ]
            pick = matches[0] if len(matches) == 1 else 0
            head = lines[pick]
            extras = [ln for i, ln in enumerate(lines) if i != pick]

        title = self._escape(head)
        extra_latex = ""
        if extras:
            extra_lines = " \\\\\n".join(self._escape(e) for e in extras)
            extra_latex = (
                "\n\\begin{center}\n"
                f"\\itshape {extra_lines}\n"
                "\\end{center}"
            )

        number_int = self._chapter_number_as_int(chapter_number)
        synthesized = (
            chapter_number is not None
            and head.rstrip(".").strip().lower()
            == f"chapter {chapter_number}".lower()
        ) or self._title_is_label(head, number_int)

        if chapter_number is not None and not synthesized and number_int is not None:
            heading = (
                f"\\setcounter{{chapter}}{{{number_int - 1}}}\n"
                f"\\chapter{{{title}}}"
            )
        else:
            if chapter_number is not None and not synthesized and number_int is None:
                # e.g. chapter_number "Five": no counter representation.
                # The title still renders; the ordinal is only in the text.
                logger.warning(
                    f"Block {block.get('id')}: chapter_number "
                    f"{chapter_number!r} not representable as an integer; "
                    f"rendering unnumbered"
                )
            # Interior Standard v1 §4 [BOUND]: label lines in spaced
            # small caps. Only label-shaped/synthesized titles get the
            # \prontolabel wrap (real titles are display text); the TOC
            # entry and header mark stay plain.
            display = f"\\prontolabel{{{title}}}" if synthesized else title
            heading = (
                f"\\chapter*{{{display}}}\n"
                f"\\addcontentsline{{toc}}{{chapter}}{{{title}}}"
            )
        # Running-header mark (recto = chapter title). Emitted explicitly
        # for BOTH paths: \chapter* never sets a mark, and for numbered
        # chapters an explicit \markright with the truncated title wins
        # over the \chaptermark default — headers get a bounded string
        # even when the source title is a DQ-length sentence.
        mark = self._escape(self._truncate_for_header(head))
        return heading + f"\n\\markright{{{mark}}}" + extra_latex

    _HEADER_MARK_MAX = 58

    @classmethod
    def _truncate_for_header(cls, text: str) -> str:
        t = " ".join(text.split())
        if len(t) <= cls._HEADER_MARK_MAX:
            return t
        cut = t[:cls._HEADER_MARK_MAX].rsplit(" ", 1)[0].rstrip(",;:")
        return cut + "…"

    @staticmethod
    def _chapter_number_as_int(number: Any) -> Optional[int]:
        """Coerce the artifact's chapter_number (int, arabic string, or
        roman-numeral string per schema) to a positive int, or None when
        it has no integer representation (e.g. "Five").
        """
        if isinstance(number, bool) or number is None:
            return None
        if isinstance(number, int):
            return number if number > 0 else None
        if not isinstance(number, str):
            return None
        s = number.strip()
        if s.isdigit():
            value = int(s)
            return value if value > 0 else None
        if s and re.fullmatch(r"[IVXLCDM]+", s.upper()):
            values = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
            total = 0
            upper = s.upper()
            for i, ch in enumerate(upper):
                v = values[ch]
                if i + 1 < len(upper) and values[upper[i + 1]] > v:
                    total -= v
                else:
                    total += v
            return total if total > 0 else None
        return None

    def _render_chapter_subtitle(self, block: Dict[str, Any], ctx: Dict[str, Any]) -> str:
        """v2.1 role: a title paired to the landmark above it (stave
        names, chapter subtitles). Italic centered line beneath the
        heading — full styling deferred per amendment spec §5.2.
        """
        text = self._plain(block)
        if not text:
            return ""
        return (
            "\\begin{center}\n"
            f"\\itshape {text}\n"
            "\\end{center}"
        )

    # Ornament-only paragraphs are scene breaks in the wild: authors
    # (and Gutenberg conversions) type "* * *", "***", "~", "• • •" or
    # a short dash run instead of a styled break. W1 carries them
    # faithfully as body_paragraph; the presentation layer normalizes
    # them to the template's \scenebreak asterism. (Interior Standard
    # v1 draft; when W1 grows a scene_break classifier this detector
    # becomes redundant but harmless.)
    _ASTERISM_RE = re.compile(r"^[\s*·•~–—#_-]{1,16}$")

    def _render_body_paragraph(self, block: Dict[str, Any], ctx: Dict[str, Any]) -> str:
        raw = "".join(
            s.get("text", "") for s in (block.get("spans") or [])
        )
        stripped = raw.strip()
        if stripped and self._ASTERISM_RE.match(stripped) and any(
            ch in "*·•~–—#_-" for ch in stripped
        ):
            return "\\scenebreak"
        return self._render_spans(block)

    def _render_scene_break(self, block: Dict[str, Any], ctx: Dict[str, Any]) -> str:
        return "\\scenebreak"

    def _render_back_matter(self, block: Dict[str, Any], ctx: Dict[str, Any]) -> str:
        """Unnumbered chapter-style heading + TOC line. Same shape as a
        front_matter generic heading; subtype is informational only.
        """
        title = self._plain(block)
        return (
            f"\\chapter*{{{title}}}\n"
            f"\\addcontentsline{{toc}}{{chapter}}{{{title}}}"
        )

    def _render_heading(self, block: Dict[str, Any], ctx: Dict[str, Any]) -> str:
        """Generic sub-section heading. Maps heading_level → LaTeX
        sectioning command:
          1 → \\chapter*  (rare for role=heading; L1 usually classifies)
          2 → \\section*  (rare for role=heading; L2 = chapter usually)
          3 → \\subsection*
          4+ → \\subsubsection*
        """
        title = self._plain(block)
        level = int(block.get("heading_level") or 3)
        cmd = {1: "\\chapter*", 2: "\\section*", 3: "\\subsection*"}.get(
            level, "\\subsubsection*"
        )
        return f"{cmd}{{{title}}}"

    def _render_list_item(self, block: Dict[str, Any], ctx: Dict[str, Any]) -> str:
        """Single \\item. Wrapping is handled by _ListState in convert()."""
        body = self._render_spans(block)
        return f"  \\item {body}"

    def _render_blockquote(self, block: Dict[str, Any], ctx: Dict[str, Any]) -> str:
        body = self._render_spans(block)
        if ctx.get("degraded"):
            return f"\\begin{{quote}}\n{body}\n\\end{{quote}}"
        return f"\\begin{{quotation}}\n{body}\n\\end{{quotation}}"

    def _render_table(self, block: Dict[str, Any], ctx: Dict[str, Any]) -> str:
        """Table-internal structure is deferred to a future schema rev;
        once rows/cells firm up, this handler renders to tabular. Until
        then, emit a visible stand-in marking where the table lands.
        CUSTOMER-FACING TEXT (§6 review, 2026-07-16): must stay neutral —
        no internal doc/spec references, and never the word
        "placeholder" (harness row 14 scans rendered output for all
        three).
        """
        return (
            "\\begin{center}\n"
            "\\textit{[Table omitted from this edition]}\n"
            "\\end{center}"
        )

    def _render_image(self, block: Dict[str, Any], ctx: Dict[str, Any]) -> str:
        """Image extraction is deferred (v1.2 punchlist); emit a visible
        stand-in. Same customer-neutral wording rule as _render_table.
        """
        return (
            "\\begin{center}\n"
            "\\textit{[Illustration omitted from this edition]}\n"
            "\\end{center}"
        )

    def _render_code_block(self, block: Dict[str, Any], ctx: Dict[str, Any]) -> str:
        """Verbatim code rendering. Spans are flattened to plain text
        because verbatim doesn't process inline marks.
        """
        text = ""
        spans = block.get("spans")
        if isinstance(spans, list) and spans:
            text = "".join(s.get("text", "") for s in spans if isinstance(s, dict))
        else:
            text = block.get("text", "") or ""
        return f"\\begin{{verbatim}}\n{text}\n\\end{{verbatim}}"

    def _render_footnote(self, block: Dict[str, Any], ctx: Dict[str, Any]) -> str:
        """v1.3 emits footnote content as a flush-left small block.
        Proper \\footnote{} wiring requires the footnote_ref linkage
        from the producer, which v1 readers don't synthesize. Tracked
        on the v1.1 punchlist.
        """
        body = self._render_spans(block)
        return f"\\begin{{flushleft}}\n\\small\n{body}\n\\end{{flushleft}}"

    def _render_structural(self, block: Dict[str, Any], ctx: Dict[str, Any]) -> str:
        """role=structural is the catch-all for layout-only blocks
        (page_break, horizontal_rule, toc_marker upgraded from v1).
        Dispatch on the underlying CIR type.
        """
        cir_type = block.get("type")
        if cir_type == "page_break":
            return "\\clearpage"
        if cir_type == "horizontal_rule":
            return (
                "\\par\\vspace{\\baselineskip}\n"
                "\\noindent\\rule{\\textwidth}{0.4pt}\n"
                "\\par\\vspace{\\baselineskip}"
            )
        # toc_marker (v1 upgrade) — let the template's TOC handle this.
        # Emit a comment for traceability.
        return f"% structural block {block.get('id')} (CIR type={cir_type!r})"


# ---------------------------------------------------------------------------
# List grouping state machine
# ---------------------------------------------------------------------------

class _ListEnvTransition:
    __slots__ = ("close_prev", "open_new")
    def __init__(self, close_prev: Optional[str] = None, open_new: Optional[str] = None):
        self.close_prev = close_prev
        self.open_new = open_new


class _ListState:
    """Tracks the open list environment across consecutive list_item
    blocks. Wraps runs of list_item-role blocks in itemize / enumerate;
    closes the wrap when a non-list_item block (or a block with a
    different list_ordered value) shows up.
    """

    def __init__(self):
        self.open_env: Optional[str] = None  # "itemize" | "enumerate" | None

    def transition(self, block: Dict[str, Any], role: str) -> _ListEnvTransition:
        if role != "list_item":
            if self.open_env is not None:
                close = self.open_env
                self.open_env = None
                return _ListEnvTransition(close_prev=close)
            return _ListEnvTransition()

        # list_item block.
        wanted_env = "enumerate" if block.get("list_ordered") else "itemize"
        if self.open_env == wanted_env:
            return _ListEnvTransition()  # already open in the right kind
        if self.open_env is not None:
            # Switching kind — close the prior, open the new.
            close = self.open_env
            self.open_env = wanted_env
            return _ListEnvTransition(close_prev=close, open_new=wanted_env)
        # Not in a list — open one.
        self.open_env = wanted_env
        return _ListEnvTransition(open_new=wanted_env)
