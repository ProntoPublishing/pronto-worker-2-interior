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

## Pending Interior Standard v1 binding
- Header font/size/case, folio placement, TOC typography (tocloft), chapter
  opener drop, half-title styling, scene-break glyph, `\raggedbottom` vs
  flush, per-genre differences (nonfiction footer is outside-corner).
- Re-render + re-verify the six with `tools/render_local.py`, checker:
  scratchpad `verify_presentation.py` pattern (TOC page, folios, header
  spread sampling, doubling guard).
