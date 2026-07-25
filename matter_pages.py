"""
Matter toggles (Interior Catch-Up Part B, W2 1.13.0) — three optional
pages driven by long-text fields on Book Metadata:

- `Dedication`        -> front matter, its own page after the copyright
                         page (before the TOC). Classic treatment: no
                         folio/header, sunk a third down, centered,
                         italic.
- `Acknowledgements`  -> back matter, unnumbered chapter (house
                         back-matter shape: \\chapter* + TOC line).
- `About the Author`  -> back matter, after Acknowledgements — the
                         book's last word.

Empty field -> the page is omitted ENTIRELY (the template placeholder
line is consumed, assembling byte-identical to a book without the
feature). One house treatment each; no styling sub-options in v1.

Text handling: fields are plain text. Blank-line-separated paragraphs
are honored; everything is LaTeX-escaped through the converter's own
_escape (single source of escaping truth).

Author: Pronto Publishing
"""

from typing import Optional

from lib.blocks_to_latex import BlocksToLatexConverter

_esc = BlocksToLatexConverter()._escape


def _paragraphs(text: str) -> list:
    """Blank-line-split, whitespace-normalized, escaped paragraphs."""
    paras = []
    for p in (text or "").split("\n\n"):
        p = " ".join(p.split())
        if p:
            paras.append(_esc(p))
    return paras


def _clean(field) -> str:
    """Airtable long-text -> stripped string ('' for None/absent)."""
    return (str(field).strip() if field is not None else "")


def dedication_latex(field) -> Optional[str]:
    """The dedication page: recto after copyright, no folio, sunk,
    centered italic. None when the field is empty (page omitted)."""
    text = _clean(field)
    if not text:
        return None
    paras = _paragraphs(text)
    body = "\\\\[1em]\n".join(paras)
    return (
        "% Dedication — Book Metadata `Dedication` (Part B matter toggle).\n"
        "\\clearpage\n"
        "\\thispagestyle{empty}\n"
        "\\vspace*{0.30\\textheight}\n"
        "\\begin{center}\n"
        "\\itshape\n"
        f"{body}\n"
        "\\end{center}\n"
        "\\clearpage"
    )


def _back_section_latex(title: str, field) -> Optional[str]:
    """House back-matter shape (mirrors _render_back_matter):
    unnumbered chapter + TOC line + escaped paragraphs."""
    text = _clean(field)
    if not text:
        return None
    paras = _paragraphs(text)
    body = "\n\n".join(paras)
    return (
        f"\\chapter*{{{title}}}\n"
        f"\\addcontentsline{{toc}}{{chapter}}{{{title}}}\n"
        f"{body}"
    )


def back_matter_latex(acknowledgements_field, about_author_field
                      ) -> Optional[str]:
    """Acknowledgements then About the Author (the book's last word).
    None when both fields are empty (placeholder line consumed)."""
    sections = []
    ack = _back_section_latex("Acknowledgements", acknowledgements_field)
    if ack:
        sections.append(ack)
    about = _back_section_latex("About the Author", about_author_field)
    if about:
        sections.append(about)
    if not sections:
        return None
    return "\n\n".join(sections)
