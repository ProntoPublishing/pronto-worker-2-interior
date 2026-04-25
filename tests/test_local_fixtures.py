"""
Local fixture diff tests — the primary corpus-level test loop for W2.

What this is
  Five real-corpus W1 golden artifacts live under tests/fixtures/local/
  as `input.json`. For each, a `golden.interior.tex` captures the
  byte-exact LaTeX W2 currently produces. This test renders each
  fixture through `lib.local_runner.render_local` and asserts the
  freshly-built .tex matches the golden.

  PDF + pdftotext content-sanity diffs are layered on top when
  xelatex / pdftotext are available (i.e. CI / Docker / Railway). On
  a Windows dev machine with no XeLaTeX install they're skipped
  cleanly with an explicit `skipTest`.

Why .tex is the canonical golden
  Per Bucket A test-plan decision Q2: PDF byte-equality is brittle
  across OSes and texlive versions. The .tex IS the deterministic
  "what we'd render" representation. pdftotext output is a content
  sanity layer — it catches semantic regressions (text dropped,
  text duplicated, content mangled) without locking us to a specific
  PDF binary layout.

Updating goldens
  When a rendering change is intentional, regenerate goldens:
    python pronto_worker_2.py --local \
      --input tests/fixtures/local/<book>/input.json \
      --output tests/fixtures/local/<book>/
    mv tests/fixtures/local/<book>/interior.tex \
       tests/fixtures/local/<book>/golden.interior.tex
  …and review the diff before committing.
"""
from __future__ import annotations
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib.local_runner import render_local  # noqa: E402


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "local"

GOLDEN_BOOKS = (
    "the_hatch_list",
    "pride_and_prejudice",
    "frankenstein",
    "jekyll_and_hyde",
    "dracula",
)


def _first_diff_line(a: str, b: str) -> Optional[str]:
    """Return a human-readable summary of the first line where a and b
    differ. None if equal. Caps the snippet length so a 100KB diff
    doesn't dump into the test output.
    """
    if a == b:
        return None
    a_lines = a.splitlines()
    b_lines = b.splitlines()
    for i, (x, y) in enumerate(zip(a_lines, b_lines)):
        if x != y:
            return (
                f"first divergence at line {i + 1}:\n"
                f"  produced: {x[:160]!r}\n"
                f"  golden:   {y[:160]!r}"
            )
    if len(a_lines) != len(b_lines):
        return (
            f"line counts differ: produced={len(a_lines)} "
            f"golden={len(b_lines)}"
        )
    return "(byte-level diff with matching lines — likely line-ending drift)"


class Test_LocalFixtures(unittest.TestCase):
    """For each fixture, render and diff the .tex against the golden."""

    def _check_tex(self, book: str) -> None:
        book_dir = FIXTURES / book
        input_json = book_dir / "input.json"
        golden_tex = book_dir / "golden.interior.tex"
        self.assertTrue(input_json.exists(), f"missing fixture: {input_json}")
        self.assertTrue(golden_tex.exists(), f"missing golden: {golden_tex}")

        with tempfile.TemporaryDirectory() as tmp:
            result = render_local(
                input_path=input_json,
                output_dir=Path(tmp),
                deterministic=True,
                skip_pdf=True,  # only .tex needed for this assertion
            )
            self.assertIsNotNone(result.tex_path, f"{book}: no .tex produced")
            produced = Path(result.tex_path).read_text(encoding="utf-8")

        golden = golden_tex.read_text(encoding="utf-8")

        if produced != golden:
            diff = _first_diff_line(produced, golden) or "(no line-level diff)"
            self.fail(
                f"{book}: produced .tex diverges from golden.\n"
                f"{diff}\n"
                f"Produced size: {len(produced)} bytes  golden: {len(golden)} bytes\n"
                f"To accept the new output as the golden, run:\n"
                f"  python pronto_worker_2.py --local "
                f"--input tests/fixtures/local/{book}/input.json "
                f"--output tests/fixtures/local/{book}/\n"
                f"  mv tests/fixtures/local/{book}/interior.tex "
                f"tests/fixtures/local/{book}/golden.interior.tex"
            )

    def test_the_hatch_list(self) -> None:
        """Hatch List — 236-block AI-generated baseline."""
        self._check_tex("the_hatch_list")

    def test_pride_and_prejudice(self) -> None:
        """P&P — 2294 blocks, full role spread (chapters + title_page + table)."""
        self._check_tex("pride_and_prejudice")

    def test_frankenstein(self) -> None:
        """Frankenstein — 798 blocks, mostly body_paragraph."""
        self._check_tex("frankenstein")

    def test_jekyll_and_hyde(self) -> None:
        """Jekyll & Hyde — 364 blocks."""
        self._check_tex("jekyll_and_hyde")

    def test_dracula(self) -> None:
        """Dracula — 2164 blocks, large epistolary."""
        self._check_tex("dracula")


@unittest.skipUnless(
    shutil.which("xelatex") and shutil.which("pdftotext"),
    "xelatex and pdftotext both required for PDF content-sanity tests",
)
class Test_LocalFixtures_PdfContent(unittest.TestCase):
    """Per Bucket A test-plan Q2: when xelatex+pdftotext are available,
    render the PDF, extract text via `pdftotext -layout`, and compare
    against a golden text snapshot. This catches semantic regressions
    (e.g. content dropped, text mangled) without locking us to a
    specific PDF binary layout.

    Goldens are generated where xelatex is installed (typically Docker
    / Railway / a developer's TeX-installed machine) by running:
        python pronto_worker_2.py --local --input <input.json> --output <dir>
        cp <dir>/interior.txt tests/fixtures/local/<book>/golden.interior.txt

    On a dev machine without xelatex, this whole test class skips.
    """

    def _check_txt(self, book: str) -> None:
        book_dir = FIXTURES / book
        input_json = book_dir / "input.json"
        golden_txt = book_dir / "golden.interior.txt"
        if not golden_txt.exists():
            self.skipTest(
                f"no golden.interior.txt for {book} yet — generate it from "
                f"a machine with xelatex installed"
            )

        with tempfile.TemporaryDirectory() as tmp:
            result = render_local(
                input_path=input_json,
                output_dir=Path(tmp),
                deterministic=True,
                skip_pdf=False,
            )
            self.assertIsNotNone(
                result.txt_path,
                f"{book}: pdftotext output missing — "
                f"pdf={result.pdf_skipped_reason!r} "
                f"txt={result.txt_skipped_reason!r}",
            )
            produced = Path(result.txt_path).read_text(encoding="utf-8")

        golden = golden_txt.read_text(encoding="utf-8")

        if produced != golden:
            diff = _first_diff_line(produced, golden) or "(no line-level diff)"
            self.fail(
                f"{book}: produced pdftotext output diverges from golden.\n"
                f"{diff}"
            )

    def test_the_hatch_list(self) -> None:
        self._check_txt("the_hatch_list")

    def test_pride_and_prejudice(self) -> None:
        self._check_txt("pride_and_prejudice")


class Test_LocalRendererDeterminism(unittest.TestCase):
    """Sanity: repeated --local runs against the same input produce
    byte-identical .tex. No timestamps, no environment leaks.
    """

    def test_repeated_runs_produce_identical_tex(self) -> None:
        input_json = FIXTURES / "the_hatch_list" / "input.json"
        if not input_json.exists():  # pragma: no cover
            self.skipTest(f"fixture missing: {input_json}")

        produced = []
        for _ in range(2):
            with tempfile.TemporaryDirectory() as tmp:
                r = render_local(
                    input_path=input_json,
                    output_dir=Path(tmp),
                    deterministic=True,
                    skip_pdf=True,
                )
                produced.append(Path(r.tex_path).read_text(encoding="utf-8"))
        self.assertEqual(
            produced[0], produced[1],
            "Two deterministic-mode renders produced different .tex. A "
            "non-deterministic field slipped past render_local — likely "
            "a wall-clock-derived placeholder substitution.",
        )


if __name__ == "__main__":
    unittest.main()
