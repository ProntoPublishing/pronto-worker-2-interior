"""
Local W2 render loop — manuscript.v2.0.json → interior.pdf, no Railway.
=======================================================================

Mirrors the template-fill path of pronto_worker_2.py process_service()
(steps 5, 7, 8) without Airtable/R2/Flask. This is the corpus-testing
enabling tool: point it at an artifact, get a PDF.

Usage (from repo root):
    python tools/render_local.py <artifact.json> <out_dir> \
        [--title T] [--author A] [--genre fiction|nonfiction] [--isbn N] \
        [--fonts DIR]

--fonts DIR rewrites the template's hardcoded Linux font path
(/usr/share/fonts/opentype/ebgaramond/) to DIR so XeLaTeX resolves the
EB Garamond OTFs on a dev machine. Production templates are untouched —
the rewrite happens on the in-memory template string only.

Requires on PATH: python 3.10+, xelatex, pandoc (PDFGenerator probes it).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from lib.artifact_readers import read_artifact  # noqa: E402
from lib.blocks_to_latex import BlocksToLatexConverter  # noqa: E402
from lib.pdf_generator import PDFGenerator  # noqa: E402

DOCKER_FONT_PATH = "/usr/share/fonts/opentype/ebgaramond/"


def main() -> int:
    ap = argparse.ArgumentParser(description="Render a manuscript artifact locally")
    ap.add_argument("artifact", type=Path)
    ap.add_argument("out_dir", type=Path)
    ap.add_argument("--title", default="Local Render")
    ap.add_argument("--author", default="Local Render")
    ap.add_argument("--genre", default="fiction")
    ap.add_argument("--isbn", default="")
    ap.add_argument("--year", default="2026")
    ap.add_argument("--fonts", type=Path, default=None,
                    help="Directory containing EBGaramond12-{Regular,Italic,Bold}.otf")
    ap.add_argument("--run-id", default="local")
    args = ap.parse_args()

    raw = json.loads(args.artifact.read_text(encoding="utf-8"))
    artifact = read_artifact(raw)
    print(f"artifact: schema {raw.get('schema_version')!r}, "
          f"{len(artifact['content']['blocks'])} blocks")

    converter = BlocksToLatexConverter()
    body = converter.convert(
        blocks=artifact["content"]["blocks"],
        params={"genre": args.genre},
        degraded_mode=False,
    )
    body = body.replace("% PREAMBLE_PLACEHOLDER", "").lstrip()

    template_name = (
        "fiction_6x9.tex" if args.genre.lower() == "fiction" else "nonfiction_6x9.tex"
    )
    template = (REPO_ROOT / template_name).read_text(encoding="utf-8")

    if args.fonts:
        font_dir = args.fonts.resolve().as_posix()
        if not font_dir.endswith("/"):
            font_dir += "/"
        template = template.replace(DOCKER_FONT_PATH, font_dir)

    # Mirror _system_title_page_latex(): no H-001 entry → system page.
    h001_fired = any(
        r.get("rule") == "H-001" for r in (artifact.get("applied_rules") or [])
    )
    system_title_page = (
        "% System title page suppressed by H-001"
        if h001_fired
        else (
            "\\begin{titlepage}\n"
            "    \\centering\n"
            "    \\vspace*{2in}\n"
            "    {\\Huge\\textbf{{{BOOK_TITLE}}}}\\\\[1em]\n"
            "    {\\Large {{AUTHOR_NAME}}}\n"
            "    \\vfill\n"
            "    {\\small\\textls[160]{\\scshape PRONTO PUBLISHING}}\\\\[0.4in]\n"
            "\\end{titlepage}"
        )
    )

    # Interior Standard v1 §3.5 [BOUND]: TOC included when >= 2 entries.
    toc_entries = sum(
        1 for b in artifact["content"]["blocks"]
        if b.get("role") in ("chapter_heading", "part_divider", "back_matter")
    )
    toc_block = (
        "\\tableofcontents\n\\clearpage" if toc_entries >= 2
        else f"% TOC omitted: {toc_entries} entry(ies) < 2 (Standard s3.5)"
    )

    latex_content = (
        template
        .replace("{{CONTENT}}", body, 1)
        .replace("{{SYSTEM_TITLE_PAGE}}", system_title_page, 1)
        .replace("{{BOOK_TITLE}}", args.title)
        .replace("{{AUTHOR_NAME}}", args.author)
        .replace("{{FONT_NAME}}", "EB Garamond")
        .replace("{{YEAR}}", args.year)
        .replace("{{ISBN}}", args.isbn)
        .replace(
            "{{ISBN_LINE}}",
            f"\\\\[1em]\nISBN: {args.isbn}" if args.isbn else "",
        )
        .replace("{{TOC_BLOCK}}", toc_block, 1)
    )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    tex_file = args.out_dir / f"{args.run_id}.tex"
    tex_file.write_text(latex_content, encoding="utf-8")
    print(f"tex written: {tex_file}")

    pdf = PDFGenerator().generate(
        latex_file=tex_file, output_dir=args.out_dir, run_id=args.run_id
    )
    print(f"pdf: {pdf} ({pdf.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
