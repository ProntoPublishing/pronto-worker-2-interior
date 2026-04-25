"""
Local runner — drive the W2 render pipeline directly from a JSON artifact.

Purpose
  The production path (`pronto_worker_2.InteriorProcessor.process_service`)
  threads through Airtable, R2 download, R2 upload, and the Flask HTTP
  layer. None of that is necessary when you want to:
    - Iterate on Doc-23 render rules against W1 golden artifacts
    - Diff golden interior.tex / interior.txt in CI
    - Repro a corpus-test rendering finding deterministically

  This module exposes the *pure render*: artifact JSON in,
  interior.tex (always), interior.pdf + interior.txt (when xelatex /
  pdftotext are available on PATH).

Determinism
  When `deterministic=True` (the default):
    - SOURCE_DATE_EPOCH=0 in the xelatex env so /CreationDate /
      /ModDate metadata in the PDF is zeroed.
    - RenderParams.deterministic() pins year, book_title, author_name
      to fixed sentinel values when the artifact carries no
      manuscript_meta (so PDF text doesn't vary by wall clock).
    - When the artifact carries manuscript_meta, those values are
      preferred (the artifact IS deterministic given the same DOCX).

  Cross-OS PDF byte-equality is NOT guaranteed even with
  SOURCE_DATE_EPOCH=0 — different texlive versions can produce
  different PDF binaries. Per the Bucket A test plan (Q2),
  golden-comparison happens on the .tex intermediate; .pdf+.txt are
  for content-sanity confirmation, not byte-equal regression.

CLI
    python -m pronto_worker_2 --local --input <artifact.json>
                              --output <dir> [--no-deterministic]
                              [--no-pdf]

  See pronto_worker_2.py's __main__ block.
"""
from __future__ import annotations
import json
import logging
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from .blocks_to_latex import BlocksToLatexConverter
from .render_params import RenderParams

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# System title page builder — duplicated from pronto_worker_2 so the
# local runner doesn't pull in the Airtable / R2 stack that module
# imports at top level. The two MUST stay in sync; tracked on the
# punchlist for a follow-on dedupe (the natural home is render_params,
# but it depends on artifact.applied_rules so it's not strictly a
# "params" thing).
# ---------------------------------------------------------------------------
def _system_title_page_latex(artifact: Dict[str, Any]) -> str:
    h001_fired = any(
        r.get("rule") == "H-001"
        for r in (artifact.get("applied_rules") or [])
    )
    if h001_fired:
        return (
            "% System title page suppressed by H-001\n"
            "% (author supplied a title page; converter renders it from\n"
            "% title_page-role blocks)."
        )
    return (
        "\\begin{titlepage}\n"
        "    \\centering\n"
        "    \\vspace*{2in}\n"
        "    {\\Huge\\textbf{{{BOOK_TITLE}}}}\\\\[1em]\n"
        "    {\\Large {{AUTHOR_NAME}}}\n"
        "    \\vfill\n"
        "\\end{titlepage}"
    )


class LocalRenderResult:
    """Payload from `render_local()`. Reports what was produced and
    surfaces any tooling skips (xelatex / pdftotext not installed).
    """
    __slots__ = ("tex_path", "pdf_path", "txt_path",
                 "pdf_skipped_reason", "txt_skipped_reason",
                 "blocks_count", "warnings_count")

    def __init__(self) -> None:
        self.tex_path: Optional[Path] = None
        self.pdf_path: Optional[Path] = None
        self.txt_path: Optional[Path] = None
        self.pdf_skipped_reason: Optional[str] = None
        self.txt_skipped_reason: Optional[str] = None
        self.blocks_count: int = 0
        self.warnings_count: int = 0


def render_local(
    input_path: Path | str,
    output_dir: Path | str,
    *,
    deterministic: bool = True,
    skip_pdf: bool = False,
    params: Optional[RenderParams] = None,
) -> LocalRenderResult:
    """Render a W1 manuscript.v2 artifact to a local PDF (when
    xelatex is available) plus the .tex intermediate.

    Args
        input_path: manuscript.v2 JSON (typically a W1 golden).
        output_dir: where to write `interior.tex` (and `interior.pdf`,
            `interior.txt` when tooling allows).
        deterministic: pin SOURCE_DATE_EPOCH=0 for xelatex; prefer
            artifact-derived metadata over wall-clock-derived defaults.
        skip_pdf: if True, write only interior.tex and don't invoke
            xelatex even if it's available. Useful for fast inner-loop
            iteration on the converter / template.
        params: override the auto-derived params. When None, params
            are derived from the artifact's manuscript_meta with
            deterministic-mode fallbacks for missing fields.
    """
    input_path = Path(input_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not input_path.exists():
        raise FileNotFoundError(f"input artifact not found: {input_path}")

    with open(input_path, "r", encoding="utf-8") as f:
        artifact = json.load(f)

    blocks = (artifact.get("content") or {}).get("blocks") or []
    warnings = artifact.get("warnings") or []

    # Build params. In deterministic mode, prefer artifact-derived
    # title/author over the sentinel defaults — both are deterministic
    # given the same DOCX, and the sentinel is only there to stop
    # datetime.now() from leaking in.
    if params is None:
        meta = artifact.get("manuscript_meta") or {}
        params = RenderParams.deterministic(
            book_title=meta.get("title") or "Local Run",
            author_name=meta.get("author") or "Local Run",
        ) if deterministic else RenderParams(
            book_title=str((meta.get("title") or "")),
            author_name=str((meta.get("author") or "")),
            year=str(datetime.now(timezone.utc).year),
        )

    # Step 1: blocks → LaTeX. convert_split returns (front_matter, body)
    # so the front-matter content lands in \frontmatter (lowercase
    # Roman page numbers per Doc 23 R-6.1) and the body lands in
    # \mainmatter (Arabic).
    converter = BlocksToLatexConverter()
    latex_front, latex_body = converter.convert_split(
        blocks=blocks,
        params=params.to_dict(),
        degraded_mode=False,
    )
    latex_body = latex_body.replace("% PREAMBLE_PLACEHOLDER", "").lstrip()
    latex_front = latex_front.replace("% PREAMBLE_PLACEHOLDER", "").lstrip()

    # Step 2: Pick template + fill placeholders.
    template_name = (
        "fiction_6x9.tex" if params.genre.lower() == "fiction"
        else "nonfiction_6x9.tex"
    )
    template_path = Path(__file__).resolve().parent.parent / template_name
    if not template_path.exists():
        raise FileNotFoundError(f"template not found: {template_path}")
    template = template_path.read_text(encoding="utf-8")

    # Font-name translation from the legacy production path. Kept here
    # so the substrate's behavior matches process_service exactly; the
    # follow-on render_params commit moves this onto RenderParams.
    font_map = {
        "Garamond": "EB Garamond",
        "Palatino": "Linux Libertine O",
        "Times": "Liberation Serif",
        "Times New Roman": "Liberation Serif",
    }
    actual_font = font_map.get(params.body_font_family, "EB Garamond")

    system_title_page = _system_title_page_latex(artifact)

    # Apply book-specific placeholders first, then RenderParams typography
    # placeholders. Both halves use count=1 to defend against any
    # accidental second occurrence in the template (the multi-line
    # body would otherwise break out of LaTeX comments).
    latex = (
        template
        .replace("{{CONTENT}}", latex_body, 1)
        .replace("{{FRONT_MATTER_CONTENT}}", latex_front, 1)
        .replace("{{SYSTEM_TITLE_PAGE}}", system_title_page, 1)
        .replace("{{BOOK_TITLE}}", params.book_title)
        .replace("{{AUTHOR_NAME}}", params.author_name)
        .replace("{{FONT_NAME}}", actual_font)
        .replace("{{YEAR}}", params.year or "1970")
        .replace("{{ISBN}}", params.isbn)
    )
    for needle, replacement in params.to_template_fills().items():
        latex = latex.replace(needle, replacement)

    # Step 3: Write the .tex.
    tex_path = output_dir / "interior.tex"
    with open(tex_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(latex)

    result = LocalRenderResult()
    result.tex_path = tex_path
    result.blocks_count = len(blocks)
    result.warnings_count = len(warnings)

    # Step 4 (optional): xelatex → interior.pdf.
    if skip_pdf:
        result.pdf_skipped_reason = "skip_pdf=True"
    else:
        xelatex = shutil.which("xelatex")
        if not xelatex:
            result.pdf_skipped_reason = "xelatex not on PATH"
            logger.info("local render: xelatex not found on PATH — skipping PDF")
        else:
            pdf_path = _run_xelatex(
                xelatex, tex_path, output_dir,
                deterministic=deterministic,
            )
            result.pdf_path = pdf_path

    # Step 5 (optional): pdftotext → interior.txt content sanity.
    if result.pdf_path is None:
        result.txt_skipped_reason = result.pdf_skipped_reason or "no PDF produced"
    else:
        pdftotext = shutil.which("pdftotext")
        if not pdftotext:
            result.txt_skipped_reason = "pdftotext not on PATH"
        else:
            txt_path = output_dir / "interior.txt"
            try:
                subprocess.run(
                    [pdftotext, "-layout", str(result.pdf_path), str(txt_path)],
                    check=True,
                    capture_output=True,
                )
                result.txt_path = txt_path
            except subprocess.CalledProcessError as e:
                result.txt_skipped_reason = (
                    f"pdftotext failed: {e.stderr.decode('utf-8', 'replace')[:200]}"
                )

    return result


def _run_xelatex(
    xelatex: str,
    tex_path: Path,
    output_dir: Path,
    *,
    deterministic: bool,
) -> Optional[Path]:
    """Run xelatex twice (so cross-references resolve). Returns the
    PDF path on success, None otherwise. Caller handles the None case
    by surfacing pdf_skipped_reason — we don't raise.
    """
    env = os.environ.copy()
    if deterministic:
        # Zero PDF metadata (CreationDate / ModDate). Honored by modern
        # texlive xelatex via the "Reproducible Builds" patches.
        env["SOURCE_DATE_EPOCH"] = "0"
        # Zero job-name-derived randomness. xelatex respects
        # FORCE_SOURCE_DATE for some metadata fields.
        env["FORCE_SOURCE_DATE"] = "1"

    pdf_path = output_dir / "interior.pdf"
    for run_num in (1, 2):
        try:
            subprocess.run(
                [
                    xelatex,
                    "-interaction=nonstopmode",
                    "-output-directory", str(output_dir),
                    "-jobname", "interior",
                    str(tex_path),
                ],
                cwd=str(output_dir),
                env=env,
                capture_output=True,
                check=False,
            )
        except FileNotFoundError:
            return None
    if pdf_path.exists() and pdf_path.stat().st_size > 0:
        # Cleanup auxiliaries.
        for ext in (".aux", ".log", ".out", ".toc"):
            aux = output_dir / f"interior{ext}"
            if aux.exists():
                try:
                    aux.unlink()
                except OSError:
                    pass
        return pdf_path
    return None
