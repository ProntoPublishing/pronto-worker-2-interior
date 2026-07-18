# Vendored font overrides

## EBGaramond12-Bold.otf — EB Garamond Bold v1.002 (octaviopardo continuation)

**Why this file exists (W2 1.7.2, 2026-07-18):** Debian bookworm's
`fonts-ebgaramond` package ships `EBGaramond12-Bold.otf` **v0.016 with
only 127 glyphs** — Georg Duffner's famously unfinished bold. It lacks
U+2014 em-dash, U+2013 en-dash, U+2018/U+2019/U+201C/U+201D curly
quotes, and U+2026 ellipsis. Every bold context in the interior
(subsection heads, `\part*` titles, TOC rows — tocloft/book-class
defaults are bold) rendered those characters as tofu. First surfaced
by Book 18 *Perennial* (run e5N05Gk): "Gardener□s Log □ Day 6",
"□ THE PLANTING" in TOC/part pages. Regular/Italic (1,949/1,540
glyphs) were never affected — body text always rendered clean.

This file is the **complete** Bold (2,091 glyphs, v1.002) from the
maintained continuation of the EB Garamond project
(github.com/octaviopardo/EBGaramond12, the same lineage Google Fonts
ships). It is byte-identical to the `.localfonts` copy the local
corpus render loop has used all along — which is why local renders
never showed the defect.

The Dockerfile COPYs it over the package file at
`/usr/share/fonts/opentype/ebgaramond/EBGaramond12-Bold.otf` (the
templates pin explicit font paths, so same-name replacement fixes
both templates with zero template diff). BoldItalic continues to be
synthesized from this Bold via `FakeSlant=0.2`, unchanged.

License: SIL OFL 1.1 (`fonts/OFL.txt`). Verified locally on the live
e5N05Gk artifact: broken fonts → 54 unmapped glyphs; this file → 0,
page count identical (74pp) both ways.
