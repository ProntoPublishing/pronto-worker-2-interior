"""
Interior Standard v1 §6 acceptance harness.

Checks every mechanically-checkable §6 row against a rendered corpus
book (artifact JSON + output dir from tools/render_local.py). Row 7
(widow/orphan sampling) is [TUNE: automate later] and reported as
SKIP; row 9's threshold is [TUNE] so the row reports counts and only
fails on gross breakage.

Usage:
    python tests/interior_standard_check.py \
        --artifact <manuscript.json> --render-dir <dir> \
        --title "Book Title" --author "Author" [--isbn ISBN]

Exit 0 = all checked rows pass. Designed to run per book; the corpus
driver loops it.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path

from pypdf import PdfReader

OK, FAIL, SKIP = "PASS", "FAIL", "SKIP"


def norm(s: str) -> str:
    return "".join(s.split()).lower()


# Row-10 normalization also neutralizes extraction artifacts that are
# not content changes: line-end hyphenation and ligature glyphs.
_LIGATURES = {"ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl", "ﬀ": "ff"}


def norm_content(s: str) -> str:
    for k, v in _LIGATURES.items():
        s = s.replace(k, v)
    s = s.replace("-", "").replace("­", "")
    return norm(s)


def block_text(b) -> str:
    return "".join(s.get("text", "") for s in (b.get("spans") or []))


_ASTERISM_RE = re.compile(r"^[\s*·•~–—#_-]{1,16}$")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifact", type=Path, required=True)
    ap.add_argument("--render-dir", type=Path, required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--author", required=True)
    ap.add_argument("--isbn", default="")
    ap.add_argument("--run-id", default="local")
    args = ap.parse_args()

    artifact = json.loads(args.artifact.read_text(encoding="utf-8"))
    blocks = artifact["content"]["blocks"]
    pdf = PdfReader(args.render_dir / f"{args.run_id}.pdf")
    pages = [(p.extract_text() or "") for p in pdf.pages]
    tex = (args.render_dir / f"{args.run_id}.tex").read_text(encoding="utf-8")
    log_path = args.render_dir / f"{args.run_id}.log"
    log = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""

    rows = []

    def row(n, name, status, detail=""):
        rows.append((n, name, status, str(detail)))

    def lines_of(i):
        return [l.strip() for l in pages[i].splitlines() if l.strip()]

    # Row 1 — half title page 1, no folio/header; blank verso follows.
    p1 = lines_of(0)
    half_ok = (
        len(p1) >= 1
        and norm(args.title) in norm(" ".join(p1))
        and not any(re.fullmatch(r"[ivxl]+|\d+", l) for l in p1)
    )
    p2_blank = len(lines_of(1)) == 0
    row(1, "half title p1 / blank verso", OK if half_ok and p2_blank else FAIL,
        f"p1={p1[:3]}, p2 lines={len(lines_of(1))}")

    # Row 2 — title page strings + imprint (H-001 output == the
    # title/author the driver was given).
    h001_fired = any(r.get("rule") == "H-001"
                     for r in (artifact.get("applied_rules") or []))
    tp = None
    for i in range(2, 6):
        joined = norm(" ".join(lines_of(i)))
        if norm(args.title) in joined and norm(args.author) in joined:
            tp = i
            break
    if h001_fired or blocks and any(b.get("role") == "title_page" for b in blocks):
        # author-supplied title page renders from blocks; strings may
        # legitimately differ from intake — check presence of title only.
        tp_ok = any(norm(args.title) in norm(" ".join(lines_of(i)))
                    for i in range(2, 6))
        row(2, "title page strings (author-supplied page)", OK if tp_ok else FAIL,
            "title found" if tp_ok else "title missing pages 3-6")
    else:
        imprint = tp is not None and "prontopublishing" in norm(" ".join(lines_of(tp)))
        row(2, "title page strings + imprint",
            OK if tp is not None and imprint else FAIL,
            f"title-page pdf-page {tp and tp+1}, imprint={imprint}")

    # Row 3 — copyright page; ISBN IFF isbn exists.
    cp = next((i for i in range(2, 8)
               if norm("all rights reserved") in norm(" ".join(lines_of(i)))), None)
    isbn_present = cp is not None and "isbn" in norm(" ".join(lines_of(cp)))
    isbn_ok = isbn_present == bool(args.isbn)
    row(3, "copyright page + ISBN iff exists",
        OK if cp is not None and isbn_ok else FAIL,
        f"copyright pdf-page {cp and cp+1}, isbn_present={isbn_present}, "
        f"isbn_given={bool(args.isbn)}")

    # Row 4 — TOC condition + entry count + dot leaders.
    expected_entries = sum(1 for b in blocks if b.get("role") in
                           ("chapter_heading", "part_divider", "back_matter"))
    toc_idx = next((i for i, t in enumerate(pages[:14])
                    if re.search(r"^\s*Contents\s*$", t, re.MULTILINE)), None)
    if expected_entries >= 2:
        if toc_idx is None:
            row(4, "TOC present + entries + leaders", FAIL, "no Contents page")
        else:
            # TOC spans until the page whose LAST line is arabic folio 1
            # (first body page). DQ's TOC runs ~14 pages.
            toc_text = ""
            for j in range(toc_idx, min(toc_idx + 20, len(pages))):
                ls = lines_of(j)
                if ls and re.fullmatch(r"1", ls[-1]):
                    break
                toc_text += pages[j]
            folio_rows = len(re.findall(r"\S\s*\.?\s*\d+\s*$", toc_text, re.MULTILINE))
            dots = toc_text.count(". . .") + toc_text.count("....") \
                + len(re.findall(r"\.\s\.\s\.", toc_text))
            # Dot leaders apply to CHAPTER rows only — a parts-only TOC
            # (Leaves) is correctly leaderless per Standard §3.5.
            chapter_rows_expected = sum(
                1 for b in blocks
                if b.get("role") in ("chapter_heading", "back_matter"))
            dots_ok = dots > 0 or chapter_rows_expected == 0
            count_ok = abs(folio_rows - expected_entries) <= max(2, expected_entries // 10)
            row(4, "TOC present + entries + leaders",
                OK if count_ok and dots_ok else FAIL,
                f"expected {expected_entries}, folio rows ~{folio_rows}, "
                f"dot-leader evidence {dots} "
                f"(chapter rows {chapter_rows_expected})")
    else:
        row(4, "TOC omitted (<2 entries)",
            OK if toc_idx is None else FAIL,
            f"entries={expected_entries}")

    # Row 5 — roman → arabic folio switch; arabic starts at 1.
    roman_pages, first_arabic = [], None
    for i in range(min(len(pages), 30)):
        ls = lines_of(i)
        if not ls:
            continue
        last = ls[-1]
        if re.fullmatch(r"[ivxl]+", last):
            roman_pages.append(i + 1)
        if first_arabic is None and re.fullmatch(r"1", last):
            first_arabic = i + 1
    row(5, "roman front folios -> arabic 1 at body",
        OK if roman_pages and first_arabic and first_arabic > max(roman_pages)
        else FAIL,
        f"roman pdf-pages {roman_pages[:6]}, arabic-1 at {first_arabic}")

    # Row 6 — headers: verso/recto content, absent on openers, bounded.
    #   Small caps extract case-variably: compare case-insensitively.
    marks = re.findall(r"\\markright\{([^}]*)\}", tex)
    overlong = [m for m in marks if len(m) > 60]
    mid = len(pages) // 2
    verso = recto = openers_bad = 0
    sampled = 0
    for i in range(mid, min(mid + 14, len(pages))):
        ls = lines_of(i)
        if not ls:
            continue
        first = ls[0]
        pdf_page_is_even = (i + 1) % 2 == 0
        folio = ls[-1] if re.fullmatch(r"\d+", ls[-1]) else None
        if folio is None:
            continue
        book_side = int(folio) % 2  # 0 = verso (even folio)
        sampled += 1
        if book_side == 0 and norm(args.title)[:16] in norm(first):
            verso += 1
        elif book_side == 1 and len(first) < 70 and not first[:1].isdigit():
            recto += 1
    row(6, "headers verso/recto + bounded marks",
        OK if verso > 0 and recto > 0 and not overlong else FAIL,
        f"sampled {sampled}: verso-title {verso}, recto-mark {recto}, "
        f"overlong marks {len(overlong)}")

    # Row 7 — widow/orphan sampling [TUNE: automate].
    row(7, "widow/orphan sampling", SKIP, "TUNE: automate via extraction heuristic")

    # Row 8 — scene breaks: ornament source paragraphs == asterisms
    # rendered; no raw ornament body paragraph survives un-normalized.
    src_ornaments = sum(
        1 for b in blocks
        if b.get("role") == "body_paragraph"
        and (t := block_text(b).strip())
        and _ASTERISM_RE.match(t)
        and any(ch in "*·•~–—#_-" for ch in t)
    )
    tex_breaks = tex.count("\\scenebreak") - 1  # minus the \newcommand def
    row(8, "scene-break normalization",
        OK if tex_breaks == src_ornaments else FAIL,
        f"source ornaments {src_ornaments}, \\scenebreak uses {tex_breaks}")

    # Row 9 — box-warning counts [TUNE threshold: report, fail only gross].
    under = len(re.findall(r"Underfull \\[vh]box", log))
    over = len(re.findall(r"Overfull \\[vh]box", log))
    row(9, "box warnings (threshold TUNE)",
        OK if over < 50 else FAIL, f"underfull={under}, overfull={over}")

    # Row 10 — content preservation: sampled body paragraphs all present.
    body = [b for b in blocks
            if b.get("role") == "body_paragraph" and len(block_text(b)) > 80]
    rng = random.Random(20260715)
    sample = rng.sample(body, min(40, len(body))) if body else []
    full = norm_content("\n".join(pages))
    missing = [b.get("id") for b in sample
               if norm_content(block_text(b))[:120] not in full]
    row(10, "content preservation (40-paragraph sample)",
        OK if not missing else FAIL,
        f"{len(sample) - len(missing)}/{len(sample)} found; missing {missing[:5]}")

    width = max(len(r[1]) for r in rows)
    failed = 0
    for n, name, status, detail in rows:
        if status == FAIL:
            failed += 1
        print(f"  row {n:>2} {name:<{width}}  {status}  {detail[:110]}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
