# Interior presentation layer — state & Standard binding notes

**Branch:** `feature/w2-interior-standard-v1` (off `feature/w2-schema-2.1-prereq`)
**Contract:** Interior Standard v1 (Claude, IN DRAFT — not yet in Master Docs).
Everything below is built as *draft convention*; exact values live in single
config blocks per template and get re-bound when the Standard lands.
Verified on the six §6 corpus renders (2026-07-15, `.localout/v12_*`).

## What the layer now does (both 6x9 templates)

1. **TOC** — enabled in front matter (plain style, roman folios). Entries come
   from numbered `\chapter`, starred label-shaped chapters
   (`\addcontentsline`), part dividers (`\part*` + contentsline), and
   front/back-matter starred chapters. Verified: 10–64 folio'd entries per
   corpus book.
2. **Running headers** — verso = book title, recto = current chapter title
   (`\markright` emitted by the converter for BOTH chapter paths, truncated
   at 58 chars on word boundary for DQ-length titles; cleared on part pages).
   Chapter openers and front matter stay plain.
3. **Front matter sequence** — half title (recto, no folio) → blank verso →
   title page (H-001-conditional system page) → copyright (ISBN line only
   when an ISBN exists — `{{ISBN_LINE}}`) → TOC → `\mainmatter`. Folios roman
   → arabic at body start. Verified on all six.
4. **Scene breaks** — ornament-only body paragraphs (`* * *`, `***`, `~`,
   `• • •`, dash runs; no digits/letters) normalize to the template's
   `\scenebreak` asterism. NOTE: the current corpus contains ZERO asterism
   paragraphs — coverage exists only at unit level. **Books 9/15 (corpus
   authorship plan §1.2) should include asterism scene breaks.**
5. **H&J config** — one block per template: widow/club 10000,
   brokenpenalty 5000, doublehyphendemerits 10000, finalhyphendemerits 5000,
   hyphen/exhyphen 1000, `\emergencystretch=1.5em`, `\raggedbottom`
   (flush-bottom + hard widow penalties caused the underfull-vbox noise).

## Two root-cause fixes worth knowing about

- **The production headerless-interior mystery, solved:** the template's
  `\fancypagestyle{plain}{\fancyhf{}…}` redefinition LEAKS in the shipped
  fancyhdr — every invocation of `plain` (front matter, every chapter opener)
  wipes the globally-configured `fancy` header settings. The header config
  was present since template v1.0 and never rendered. Fix: body pages use a
  self-contained named style (`prontobody`) whose body re-executes on every
  switch. (The addendum's "running headers missing in production" punchlist
  item is this.)
- **render_local/pdf_generator "flakiness", solved:** pdf_generator passed
  the caller's (possibly relative, backslashed) paths into xelatex with
  `cwd=output_dir` — the relative path broke, and TeX read `\v` in
  `.localout\v12_…` as a control sequence. Pass 1 failed EVERY local run;
  a stale PDF in the outdir masked it as success (PDF-existence criterion).
  Fixes: delete target PDF before compiling + resolve paths to absolute
  POSIX form.

## Interior Standard v1 — BOUND (2026-07-15)

Both templates reconciled to `Pronto_Interior_Standard_v1_2026-07-15.md`;
[TUNE] defaults adopted as-is. §6 checklist wired into
`tests/interior_standard_check.py` (per-book; rows 1–6, 8–10 mechanical,
row 7 SKIP per spec "[TUNE: automate]"). **All six corpus books pass every
checked row** — no bad-rendering deltas to flag. Highlights of the bind:

- 11pt/14.5pt body [BOUND §2] (was 12pt/1.2-stretch): page counts moved to
  hatch 33 / carol 85 / frank 193 / P&P 342 / leaves 368 / DQ 1002.
- 6×9 geometry [§1 row]: inner .85 / outer .65 / top .75 / bottom .85.
- 1em indent, flush first paragraph after openers/scene breaks (§2) —
  \scenebreak now ends with \@afterindentfalse\@afterheading.
- Spaced-small-caps labels (\prontolabel, §4): titleformat label for
  numbered chapters; converter wraps label-shaped starred titles (TOC
  entries and header marks stay plain).
- Headers small caps; folios bottom center on BOTH templates (§5 —
  nonfiction outside-corner folios reconciled away).
- Copyright page bound to §3.4 text (imprint + prontopublishing.com +
  "First edition, {year}"); title page gains the PRONTO PUBLISHING foot
  imprint (§3.3).
- Conditional TOC via {{TOC_BLOCK}} (≥2 entries, §3.5); front matter no
  longer emits \addcontentsline (TOC never lists it); chapter rows get
  tocloft dot leaders, part rows bold/leaderless.
- Row 9 note: bound H&J config yields underfull=0 / overfull=0 across the
  corpus.
- Nonfiction keeps bold display titles as a [TUNE] genre distinction.

Trim coverage: only the two 6×9 templates exist; the Standard's 5×8,
5.5×8.5, and 8.5×11 rows bind when those templates are authored (punchlist).
