# W2 v1.3 migration notes

**Branch:** `feature/consume-manuscript-v2`
**Status:** Deployment-ready cut. **DO NOT MERGE. DO NOT DEPLOY.**
**Date:** 2026-04-25

This file documents the state of Worker 2 on the
`feature/consume-manuscript-v2` branch after iteration 5 of the v1.3
parallel-reader build. The code here reads BOTH `manuscript.v1.0` and
`manuscript.v2.0` artifacts, dispatches on `schema_version`, and
renders through a single v2-native LaTeX converter. The
`{{CONTENT}}` template-trap duplication bug is fixed natively in
v1.3 (the now-deleted `fix/w2-duplication-v2.0.1` branch is
superseded — its work lives here).

The branch must NOT merge to `main` and must NOT deploy until the
coordinated W1 v5.0 + W2 v1.3 cutover after corpus testing.

## What lives on this branch

### New modules

| Path | Role |
|---|---|
| `lib/artifact_readers/__init__.py` | `read_artifact()` dispatcher on `schema_version` |
| `lib/artifact_readers/v1.py` | v1.0/v1.1 → v2.0 in-memory upgrader |
| `lib/artifact_readers/v2.py` | v2.0 defensive identity reader |
| `tests/test_w2v13.py` | 75 tests, all green |
| `tests/fixtures/long_quiet/manuscript.v1.json` | The Long Quiet v1.0 artifact (production) |
| `tests/fixtures/long_quiet/manuscript.v2.json` | The Long Quiet v2.0 artifact (W1 v2 dry-run) |

### Rewritten

- **`lib/blocks_to_latex.py`** — v3.0.0. Dispatch axis flipped from v1
  block-type to v2 role. 15 role handlers, exhaustive coverage check
  in `__init__`. Span-boundary LaTeX escaping preserved (the v2.0.0
  C3 fix). List grouping wraps consecutive `list_item` blocks in
  itemize/enumerate; switching ordering closes-and-reopens.
- **`fiction_6x9.tex`, `nonfiction_6x9.tex`** — hardcoded
  `\begin{titlepage}...\end{titlepage}` block replaced with a
  `{{SYSTEM_TITLE_PAGE}}` placeholder. The back-matter comment that
  caused the original duplication bug is rephrased to never carry the
  `{{CONTENT}}` literal.
- **`pronto_worker_2.py`** — Step 5 swapped from
  `validate_artifact(...schema_version="1.0")` to `read_artifact()`.
  Step 6 reads `artifact.warnings[]` (top-level v2.0) instead of the
  legacy `analysis.warnings[]` nesting (the v1 reader promotes
  legacy warnings to top level). New `_system_title_page_latex()`
  helper inspects `applied_rules[]` for an H-001 entry and substitutes
  either the suppression comment or the standard system title page
  block. Both `{{CONTENT}}` and `{{SYSTEM_TITLE_PAGE}}` substitutions
  use `count=1` as defense in depth.

### Untouched (pre-existing v1 path infrastructure)

- `lib/artifact_validator.py`, `lib/artifact_validate.py`,
  `lib/artifact_registry.py` — the old JSON-Schema validator path.
  `pronto_worker_2.py` no longer imports `validate_artifact` from
  these modules; they remain in tree until the shared-library
  consolidation lands.
- `lib/manuscript_schema.py` — v1.x shared-schema module from the
  contract-v1.1 redesign. v2.0 reading does not depend on it.
- `lib/airtable_client.py`, `lib/pronto_r2_client.py`,
  `lib/pdf_generator.py`, `lib/pdf_validator.py`,
  `lib/warning_handler.py`, `lib/artifact_downloader.py` — kept
  unchanged.

## No-deploy gates

Three gates must all be green before this branch merges to `main`
and ships to Railway. Each is the responsibility of a separate
workstream.

### Gate 1 — W1 v5.0 ready to ship coordinated

W2 v1.3 reads BOTH schemas. v1.0 is the current production producer
(W1 v4.x); v2.0 will arrive when W1 v5.0 ships. The deploy sequence
is to merge W2 v1.3 first (parallel reader handles both), then merge
W1 v5.0 (starts emitting v2.0). For W2 v1.3 to ship in isolation,
W1 v5.0 doesn't need to be ready — but a coordinated cutover is
preferred so corpus testing exercises the full pipeline.

### Gate 2 — Corpus testing

Same gate as W1 v5.0's MIGRATION_NOTES. The Long Quiet smoke (Iter 5)
is encouraging but not sufficient. A small corpus of 10–12 real
manuscripts running end-to-end through W1 v2 → W2 v1.3 establishes
that rule behavior holds outside The Long Quiet's specific shape.
Items to settle during corpus:

- C-005 pattern broadening for "A Few X" / "Some X" headings.
- Byline "by " prefix strip in C-003 title-page extraction.
- C-003 title-page positional-role assignment quality (the Long
  Quiet's manuscript_meta.author came out as "A Gentle Guide to
  Moving Through" — a misassignment of the byline position).
- V-003 false-positive rate in real manuscripts.
- The H-001 divergence warning rate.

### Gate 3 — H-001 conditional title-page UX review

Currently the system title page is suppressed when H-001 fires.
That's correct per Doc 22 v1 H-001's behavior. But the converter's
`_render_title_page` rendering is intentionally simple — centered
\Huge title, \Large subtitle, \large byline, then \clearpage. A real
manuscript may want more control (custom artwork, copyright
information embedded, etc.). The current implementation is enough to
unblock corpus testing; refinement is a v1.4 or v2.0 concern.

## The Long Quiet smoke (Iter 5 findings)

Real artifacts: `tests/fixtures/long_quiet/manuscript.v{1,2}.json`.

### v1 path (existing v1.0 artifact through dispatcher → v1 reader → converter)

- 164 blocks → 150 body_paragraph + 14 chapter_heading.
- No `applied_rules` entries (v1 producer didn't have classifiers).
- No `manuscript_meta` (v1 producer didn't emit `front_matter_title`).

| Bug from buggy PDF | Status in v1.3 v1 path |
|---|---|
| 1. Whole-book duplication | **Fixed** (Iter 1: templates + count=1) |
| 2. Doubled chapter headings ("CHAPTER 1 CHAPTER 1 ...") | **Fixed** (Iter 2 upgrader splits the heading text) |
| 3. Run-boundary space loss ("Beforeanythingelse") | **Fixed** (surprising — see below) |
| 4. Triple/doubled title page | Persists (W1-upstream — v1 producer didn't classify the cluster) |
| 5. Part-divider page break missing | Persists (W1-upstream — v1 producer didn't classify part headings) |

**Surprising finding on bug 3:** the v1 artifact actually carries the
proper spacing ("Before anything else, it helps to be clear about
what depression is..."). The "Beforeanythingelse" appearance in the
buggy PDF was a downstream rendering bug, not an artifact-content
bug. Either the old `BlocksToLatexConverter` or the old template
fill was concatenating spans without preserving inter-span
whitespace. The v3.0.0 converter renders correctly, so the bug
disappears in BOTH reader paths. Bug 3 is no longer W1-upstream-only.

### v2 path (Long Quiet DOCX → W1 v2 dry-run → v2.0 artifact → v2 reader → converter)

- 165 blocks: 138 body_paragraph + 14 chapter_heading + 5 title_page
  + 5 part_divider + 1 front_matter + 2 back_matter.
- `applied_rules`: `["N-004", "H-001"]`.
- `manuscript_meta`: `{"title": "The Long Quiet", "subtitle": null,
  "author": "A Gentle Guide to Moving Through"}` — the title is
  correct; the author misclassification is a C-003 positional-role
  quality issue worth corpus-testing-conversation.

| Bug from buggy PDF | Status in v1.3 v2 path |
|---|---|
| 1. Whole-book duplication | **Fixed** |
| 2. Doubled chapter headings | **Fixed** |
| 3. Run-boundary space loss | **Fixed** (W1 v2 extractor + v3.0 converter) |
| 4. Triple/doubled title page | **Fixed** (H-001 fires; system block suppressed; cluster renders via converter) |
| 5. Part-divider page break missing | **Fixed** (5 `\clearpage`+`\part*` pairs in body) |

**All five bugs are absent in the v2 path.** No bug recreated by W2
downstream — the converter and template-fill chain is clean.

### Quality items the Long Quiet smoke surfaced (not bugs)

These are observations for the corpus testing conversation; they
don't block W2 v1.3 shipping, they just highlight what corpus
testing should drill into.

- **V-003 false positive on "noticings,":** flagged as
  "possible missing space" but it's a real word with a comma. The
  35-word function-word list + dictionary check has corner cases.
  Not a v1.3 problem; a Doc 22 V-003 tightening item.
- **C-003 byline misclassification:** the manuscript_meta.author
  ended up as the SUBTITLE text instead of the byline text. Either
  C-003's positional logic needs tightening, or the Long Quiet's
  cluster shape exposes an edge.
- **H-001 divergence warning fires:** the test passed an intake
  author of "Jesse Pope" and the cluster extraction yielded "A
  Gentle Guide to Moving Through" for author. H-001 correctly
  emits a divergence warning. In production this would prompt
  human review.

## How to verify the branch locally

```bash
pip install -r requirements.txt
python -m unittest tests.test_w2v13
# expect: Ran 75 tests in ~1s, OK
```

End-to-end inspection of the Long Quiet artifacts:

```python
import json
from lib.artifact_readers import read_artifact
from lib.blocks_to_latex import BlocksToLatexConverter

with open("tests/fixtures/long_quiet/manuscript.v2.json") as f:
    art = json.load(f)
norm = read_artifact(art)
body = BlocksToLatexConverter().convert(norm["content"]["blocks"], params={})
print(body[:2000])
```

## When the gates clear

When W1 v5.0 is ready to merge and corpus testing has produced a
green sample of 10–12 books:

1. Merge `feature/consume-manuscript-v2` here first. W2 main has
   parallel-reader support but W1 still produces v1.0 artifacts;
   v1.3 reads them correctly via the v1 reader.
2. Verify the W2 v1.3 deployment is stable on the existing v1.0
   producer pipeline.
3. Then merge `feature/w1-v2-impl` on the W1 repo. Railway
   redeploys W1 as v5.0.0; new artifacts are v2.0; W2 v1.3 reads
   them via the v2 reader.
4. Watch the first 3–5 services process end-to-end. Verify all 5
   bugs from The Long Quiet remain absent. Watch for new bugs in
   real-corpus content.
5. After deployment is stable, plan W2 v2.0 (drop the v1 reader;
   atomic cutover).
