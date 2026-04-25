"""
Blocks to LaTeX Converter v3.0.0 (v1.3 / consume-manuscript-v2)
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
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# Canonical Layer 2 role enum from Doc 22 v1.0.2.
ROLES = frozenset({
    "title_page",
    "front_matter",
    "part_divider",
    "chapter_heading",
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
        """Convert v2.0 blocks to LaTeX. Legacy single-string return.

        Concatenates front-matter and body LaTeX into one string, in
        document order. Retained for back-compat; new callers should
        prefer `convert_split()` so the front matter and body land in
        the right LaTeX page-numbering regions (per Doc 23 R-2.x and
        R-6.1).
        """
        front, body = self.convert_split(blocks, params, degraded_mode)
        if front and body:
            return front.rstrip() + "\n" + body
        return front or body

    def convert_split(
        self,
        blocks: List[Dict[str, Any]],
        params: Dict[str, Any],
        degraded_mode: bool = False,
    ) -> tuple[str, str]:
        """Convert v2.0 blocks to LaTeX, returning (front_matter, body).

        front_matter LaTeX is suitable for the `{{FRONT_MATTER_CONTENT}}`
        template placeholder (inside `\\frontmatter`). Body LaTeX is
        suitable for `{{CONTENT}}` (inside `\\mainmatter`). This
        separation enforces Doc 23 R-2.x layout and R-6.1 page-
        numbering (lowercase Roman in front, Arabic from body).

        For B.1 substrate scope, the partition is simple: blocks with
        role == "front_matter" route to front matter; everything else
        (including title_page, which is still tightly coupled with the
        SYSTEM_TITLE_PAGE / H-001 placeholder) routes to body.
        Subsequent Bucket B commits widen the partition and add
        Doc 23 R-2.x semantics (subtype-ordered rendering, recto
        starts, half-title page, system copyright page).
        """
        logger.info(
            f"Converting {len(blocks)} v2 blocks to LaTeX "
            f"(degraded={degraded_mode})"
        )

        # Doc 23 R-3.4 — single-rendering invariant. Collapse adjacent
        # duplicate chapter_heading blocks BEFORE partition. Per W1
        # contract I-4 this should never occur on a clean artifact;
        # the collapse is a defensive measure against producer drift,
        # and each collapse emits a warning so the operator can chase
        # the upstream cause.
        blocks = _collapse_adjacent_duplicate_chapter_headings(blocks)

        # Doc 23 §Front Matter — partition by role into the LaTeX
        # \frontmatter region vs. the \mainmatter region.
        front_blocks, body_blocks = _partition_front_matter(blocks)

        ctx_base = {"degraded": degraded_mode, "params": params}
        front_latex = self._render_block_sequence(front_blocks, ctx_base)
        body_latex = self._render_block_sequence(body_blocks, ctx_base)
        return front_latex, body_latex

    # -- Block-sequence rendering ------------------------------------------

    def _render_block_sequence(
        self,
        blocks: List[Dict[str, Any]],
        ctx_base: Dict[str, Any],
    ) -> str:
        """Render a sequence of blocks to LaTeX. Shared by the
        front-matter and body halves of convert_split().

        State (list grouping, R-3.5/R-4.4 next-paragraph-no-indent
        flag) is local to one call — the front-matter and body
        sequences are independent.
        """
        if not blocks:
            return ""

        out: List[str] = []
        list_state = _ListState()

        # Doc 23 R-3.5 + R-4.4 — first-paragraph-no-indent. The first
        # body_paragraph after a chapter_heading or scene_break renders
        # with `\noindent ` prefix. Any other intervening block clears
        # the flag (R-3.5 / R-4.4 say "first paragraph immediately
        # following"; a list_item or blockquote between consumes the
        # adjacency). The flag clears after one body_paragraph.
        next_paragraph_no_indent = False

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
                # Doc 23 R-7.1 — unrecognized role. Two cases:
                #   1. Schema-drift-forward: a future Doc 22 version
                #      added a role this W2 doesn't know yet. Render
                #      as body_paragraph so the content survives;
                #      don't fail the Service.
                #   2. A typo / corruption / producer bug: same
                #      remediation, but the warning makes it visible.
                # __init__'s deployment guard catches the *coding*
                # variant (HANDLER_MAP missing a known canonical role).
                logger.warning(
                    "R-7.1: unrecognized role %r on block %r — rendering "
                    "as body_paragraph fallback. Either Doc 22 grew a "
                    "new role since this W2 was deployed, or the "
                    "producer drifted.",
                    role, block.get("id"),
                )
                handler_name = "_render_body_paragraph"
            handler = getattr(self, handler_name)
            latex = handler(block, ctx_base)

            # R-3.5 / R-4.4: prepend \noindent to the first body_paragraph
            # after a chapter_heading or scene_break.
            if (role == "body_paragraph"
                    and next_paragraph_no_indent
                    and latex):
                latex = "\\noindent " + latex

            # Update the no-indent flag for the NEXT iteration. Set on
            # chapter_heading / scene_break; clear on every other role
            # (the body_paragraph that consumed it, or any intervening
            # structure that broke adjacency).
            if role in ("chapter_heading", "scene_break"):
                next_paragraph_no_indent = True
            else:
                next_paragraph_no_indent = False

            if latex:
                out.append(latex)
                out.append("")

        # Close any list still open at end-of-sequence.
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

        Doc 23 R-4.2 — `underline` and `strikethrough` marks are stripped
        in v1 (the underlying span text is preserved, the mark is
        not rendered). Underline in print fiction is dated; strikethrough
        is rare and usually accidental from track-changes leakage. Both
        are no-ops here.
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
                # R-4.2: stripped in v1 — text passes through unmarked.
                pass
            elif mark == "strikethrough":
                # R-4.2: stripped in v1 — text passes through unmarked.
                pass
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
        """
        spans = block.get("spans")
        if isinstance(spans, list) and spans:
            text = "".join(s.get("text", "") for s in spans if isinstance(s, dict))
        else:
            text = block.get("text", "") or ""
        return self._escape(text)

    # -- Role handlers ------------------------------------------------------

    def _render_title_page(self, block: Dict[str, Any], ctx: Dict[str, Any]) -> str:
        """No-op handler — title_page blocks are consumed upstream.

        Per Doc 23 R-2.2 (Bucket B.2), title_page-role blocks don't
        render here; their text was extracted into manuscript_meta
        during W1's classify phase (C-003), and the template-fill
        layer reads from manuscript_meta to build the system title
        page (lib.title_page.render_title_page_latex). Re-rendering
        the raw blocks would produce a duplicate title page.

        The handler is retained because BlocksToLatexConverter's
        __init__ requires HANDLER_MAP coverage for every role in
        ROLES (the deployment guard). _partition_front_matter drops
        title_page blocks before convert() iterates, so this handler
        is unreachable in practice. If a producer ever bypasses the
        partition (e.g. a future schema variant), the no-op fallback
        preserves the contract that title_page blocks don't double
        the rendered title page.
        """
        return ""

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
        return (
            f"\\chapter*{{{text_body}}}\n"
            f"\\addcontentsline{{toc}}{{chapter}}{{{text_body}}}"
        )

    def _render_part_divider(self, block: Dict[str, Any], ctx: Dict[str, Any]) -> str:
        """Part divider. Per I-5 always carries force_page_break: true.
        We honor that explicitly here so the page break is visible at
        the rendered-source level, not buried inside titlesec config.
        """
        title = self._escape(block.get("part_title") or "")
        force_break = block.get("force_page_break", True)
        prefix = "\\clearpage\n" if force_break else ""
        return f"{prefix}\\part*{{{title}}}\n\\addcontentsline{{toc}}{{part}}{{{title}}}"

    def _render_chapter_heading(self, block: Dict[str, Any], ctx: Dict[str, Any]) -> str:
        """v2 chapter heading: chapter_number + chapter_title are
        separate fields. Numbered chapters get \\chapter (LaTeX auto-
        prefixes "CHAPTER N" via the template's titlesec config);
        unnumbered chapters get \\chapter* + a TOC line.

        This is where the doubled-chapter bug dies: chapter_title is
        the title alone, never "Chapter N\\nTitle".
        """
        title = self._escape(block.get("chapter_title") or "")
        chapter_number = block.get("chapter_number")
        if chapter_number is None:
            return (
                f"\\chapter*{{{title}}}\n"
                f"\\addcontentsline{{toc}}{{chapter}}{{{title}}}"
            )
        return f"\\chapter{{{title}}}"

    def _render_body_paragraph(self, block: Dict[str, Any], ctx: Dict[str, Any]) -> str:
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
        """v1.3 placeholder. Doc 22 v1.0.2 defers table-internal
        structure to the schema; once schema firms up rows/cells, this
        handler renders to tabular. For now, emit a visible placeholder
        so operators see where tables would land.
        """
        return (
            "\\begin{center}\n"
            "[Table placeholder — see Doc 22 v1.0.2 §CIR Block Structure]\n"
            "\\end{center}"
        )

    def _render_image(self, block: Dict[str, Any], ctx: Dict[str, Any]) -> str:
        """v1.3 placeholder. Image extraction is a Layer 5 concern in
        Doc 22; for now, emit a visible placeholder.
        """
        return (
            "\\begin{center}\n"
            "[Image placeholder]\n"
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
# Doc 23 §Front Matter — block partition
# ---------------------------------------------------------------------------

# Roles that route to LaTeX \frontmatter rather than \mainmatter.
# Doc 23 R-2.4 / R-2.6 — dedication, foreword, preface, prologue,
# generic front matter all carry role == "front_matter" with a
# subtype.
_FRONT_MATTER_ROLES = frozenset({"front_matter"})

# Roles that are CONSUMED upstream of rendering — they don't emit
# LaTeX in either the \frontmatter or \mainmatter region.
# Doc 23 R-2.2 — title_page blocks: C-003 already extracted their
# text into artifact.manuscript_meta during W1's classify phase. The
# template-fill layer reads from manuscript_meta to build the system
# title page. Re-rendering the raw blocks here would double the title
# page (one from the system generator + one from the converter). So
# title_page blocks are silently dropped from rendering.
_CONSUMED_ROLES = frozenset({"title_page"})


def _partition_front_matter(
    blocks: List[Dict[str, Any]],
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Split blocks into (front_matter, body) by role.

    Preserves document order within each partition. Pure function;
    does not mutate input. Roles in `_CONSUMED_ROLES` (currently only
    title_page) are dropped — they're handled by the template-fill
    layer reading artifact.manuscript_meta directly.
    """
    front: List[Dict[str, Any]] = []
    body: List[Dict[str, Any]] = []
    for block in blocks:
        role = block.get("role")
        if role in _CONSUMED_ROLES:
            continue
        if role in _FRONT_MATTER_ROLES:
            front.append(block)
        else:
            body.append(block)
    return front, body


# ---------------------------------------------------------------------------
# Doc 23 R-3.4 — single-rendering invariant
# ---------------------------------------------------------------------------

def _collapse_adjacent_duplicate_chapter_headings(
    blocks: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Drop adjacent chapter_heading blocks whose (chapter_number,
    chapter_title) is identical to the immediately preceding
    chapter_heading.

    Per Doc 23 R-3.4: if two consecutive chapter_heading blocks share
    identical chapter_number AND identical chapter_title, collapse to
    a single rendering. Each collapse emits a `logger.warning` carrying
    the dropped block's id so an operator can trace the upstream cause
    (per W1 I-4 this should not occur on a clean artifact).

    "Consecutive" is interpreted strictly — only two chapter_heading
    blocks with NO intervening blocks of any role collapse. A chapter
    heading followed by a body paragraph followed by an identical
    chapter heading is left untouched (the second is more likely a
    legitimate repeat than a producer bug; treating it as a collapse
    target would silently drop content).

    Returns a new list; does not mutate input. Non-chapter_heading
    blocks pass through unchanged.
    """
    if not blocks:
        return blocks

    out: List[Dict[str, Any]] = []
    prev_chapter_key: Optional[tuple] = None

    for block in blocks:
        if block.get("role") == "chapter_heading":
            key = (
                block.get("chapter_number"),
                block.get("chapter_title"),
            )
            if prev_chapter_key is not None and key == prev_chapter_key:
                logger.warning(
                    "R-3.4: collapsing adjacent duplicate chapter_heading "
                    "block %r (chapter_number=%r, chapter_title=%r). "
                    "Per W1 I-4 this should not occur — investigate the "
                    "upstream producer.",
                    block.get("id"),
                    block.get("chapter_number"),
                    block.get("chapter_title"),
                )
                continue  # drop the duplicate
            prev_chapter_key = key
            out.append(block)
        else:
            # Any non-chapter_heading block resets the adjacency window.
            prev_chapter_key = None
            out.append(block)

    return out


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
