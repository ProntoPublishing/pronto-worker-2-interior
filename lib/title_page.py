"""
Title-page rendering — Doc 23 R-2.1 (half-title) + R-2.2 (title page).

Per Doc 23 R-2.2:

    If the artifact contains a `title_page` block (per C-003), W2 uses
    the extracted title, subtitle, and author fields. Otherwise W2
    falls back to Book Metadata fields from Airtable.

    If neither is present, W2 fails the Service.

The "extracted title, subtitle, and author fields" live in
artifact.manuscript_meta — C-003 populates them from the title_page
blocks during W1's classify phase. This module reads from there
first, falls back to params (which the production caller derives
from Airtable Book Metadata; the --local caller derives from
RenderParams.{book_title, author_name}), and raises
TitlePageMissingError if neither source supplies a title.

Why title_page-role blocks themselves don't render:
  C-003 already extracted the title-page text into manuscript_meta.
  Re-rendering the raw blocks would double-up the title page (one
  from the system generator + one from the converter). The blocks
  are informational; consumed-by-metadata.

LaTeX produced
  Half-title (R-2.1):
    \cleardoublepage  (lands on recto)
    \thispagestyle{empty}
    \vspace*{\fill}
    \begin{center} {\Huge\textbf{TITLE}} \end{center}
    \vspace*{\fill}
    \cleardoublepage  (next page is recto = title page)

  Title page (R-2.2):
    \thispagestyle{empty}
    \vspace*{2in}
    \begin{center}
      {\Huge\textbf{TITLE}}\\[1em]
      [\Large\textit{SUBTITLE}\\[2em]   -- if present
      {\large AUTHOR}                    -- if present
    \end{center}
    \vfill
    \clearpage  (copyright lands on the verso of title)
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, Optional


class TitlePageMissingError(Exception):
    """R-2.2 — neither artifact.manuscript_meta nor params/Airtable
    Book Metadata supplied a title. W2 cannot render a title page;
    the production caller fails the Service.

    Carries `field` so the caller can write a precise error log.
    """

    def __init__(self, field: str = "title") -> None:
        super().__init__(
            f"Title-page rendering requires a non-empty `{field}` from "
            f"artifact.manuscript_meta or fallback params; got neither. "
            f"Doc 23 R-2.2 — fail the Service."
        )
        self.field = field


@dataclass(frozen=True)
class ResolvedTitleFields:
    """Resolved title-page values, ready for template substitution.

    Frozen so a caller can't accidentally mutate after the resolution
    decision (which is logged for auditability).
    """
    title: str
    subtitle: Optional[str]
    author: Optional[str]
    title_source: str
    """Where `title` came from. One of:
        "manuscript_meta"  — artifact.manuscript_meta.title (C-003)
        "params"           — params.book_title (Airtable / local)
    The caller logs this so an operator can trace which fallback fired.
    """


def resolve_title_fields(
    artifact: Dict[str, Any],
    params: Dict[str, Any] | Any,
) -> ResolvedTitleFields:
    """Apply Doc 23 R-2.2 fallback chain.

    Args
        artifact: the manuscript.v2 artifact (full top-level dict).
        params: either a dict (legacy production path) or a RenderParams
            instance (--local path). Both expose `book_title` /
            `subtitle` / `author_name` keys / attrs for fallback.

    Raises
        TitlePageMissingError: if `title` is unresolvable from both
            sources. Subtitle and author are optional — absent is fine.
    """
    meta = artifact.get("manuscript_meta") or {}

    # Helper to read either a dict or a RenderParams attribute.
    def _from_params(attr: str) -> Optional[str]:
        if isinstance(params, dict):
            v = params.get(attr)
        else:
            v = getattr(params, attr, None)
        if isinstance(v, str) and v.strip():
            return v.strip()
        return None

    # Title — required.
    meta_title = (meta.get("title") or "").strip() if isinstance(meta.get("title"), str) else ""
    fallback_title = _from_params("book_title")
    if meta_title:
        title, source = meta_title, "manuscript_meta"
    elif fallback_title:
        title, source = fallback_title, "params"
    else:
        raise TitlePageMissingError("title")

    # Subtitle — optional. Prefer artifact, then params (rare to have
    # subtitle in fallback Airtable fields, but allowed).
    meta_subtitle = meta.get("subtitle")
    if isinstance(meta_subtitle, str) and meta_subtitle.strip():
        subtitle: Optional[str] = meta_subtitle.strip()
    else:
        subtitle = _from_params("subtitle")

    # Author — optional. Prefer artifact, then params.
    meta_author = meta.get("author")
    if isinstance(meta_author, str) and meta_author.strip():
        author: Optional[str] = meta_author.strip()
    else:
        author = _from_params("author_name")

    return ResolvedTitleFields(
        title=title,
        subtitle=subtitle,
        author=author,
        title_source=source,
    )


def render_half_title_page_latex(fields: ResolvedTitleFields) -> str:
    """R-2.1 — recto page, book title only, vertically centered.

    Wraps with \\cleardoublepage on both sides: the leading one
    forces a recto landing for the half-title itself; the trailing
    one ensures the title page lands on the next recto.
    """
    title = _latex_escape(fields.title)
    return (
        "\\cleardoublepage\n"
        "\\thispagestyle{empty}\n"
        "\\vspace*{\\fill}\n"
        "\\begin{center}\n"
        f"{{\\Huge\\textbf{{{title}}}}}\n"
        "\\end{center}\n"
        "\\vspace*{\\fill}\n"
        "\\cleardoublepage"
    )


def render_title_page_latex(fields: ResolvedTitleFields) -> str:
    """R-2.2 — recto title page. Title (Huge bold), subtitle (Large
    italic, if present), author byline (large, if present).

    The trailing \\clearpage (NOT \\cleardoublepage) so the copyright
    page lands on the verso per R-2.3.
    """
    title = _latex_escape(fields.title)
    out = [
        "\\thispagestyle{empty}",
        "\\vspace*{2in}",
        "\\begin{center}",
        f"{{\\Huge\\textbf{{{title}}}}}\\\\[1em]",
    ]
    if fields.subtitle:
        out.append(
            f"{{\\Large\\textit{{{_latex_escape(fields.subtitle)}}}}}\\\\[2em]"
        )
    if fields.author:
        out.append(f"{{\\large {_latex_escape(fields.author)}}}")
    out.extend([
        "\\end{center}",
        "\\vfill",
        "\\clearpage",
    ])
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Internal — LaTeX escape for the title-page substitutions.
#
# Duplicates the converter's _ESCAPES table because importing the
# converter for a 6-line helper bloats this module's deps. Kept in
# sync by convention (both list the LaTeX special set verbatim).
# ---------------------------------------------------------------------------
_ESCAPES = (
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
)


def _latex_escape(text: str) -> str:
    if not text:
        return ""
    out = text
    for ch, repl in _ESCAPES:
        out = out.replace(ch, repl)
    return out
