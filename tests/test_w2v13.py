"""
W2 v1.3 — feature/consume-manuscript-v2 test suite.

Iter 1 lays the foundation: regression tests for the {{CONTENT}}
template trap and the count=1 substitution defense. Subsequent
iterations add tests for the artifact dispatcher, v1 reader, v2 reader,
and the v2-native converter.

Run with:
    python -m unittest tests.test_w2v13
or
    python -m unittest discover tests
"""
from __future__ import annotations
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


# ---------------------------------------------------------------------------
# Iter 1 — {{CONTENT}} template trap regression
# ---------------------------------------------------------------------------

class Test_TemplateContentPlaceholder(unittest.TestCase):
    """Each template carries exactly ONE {{CONTENT}} literal — the
    real placeholder. The duplication bug returns the moment a second
    literal sneaks back in (e.g., inside a LaTeX % comment) because
    str.replace() substitutes every occurrence and the multi-line body
    breaks out of the '%' comment at its first newline.
    """

    TEMPLATES = ("fiction_6x9.tex", "nonfiction_6x9.tex")

    def test_each_template_has_exactly_one_content_placeholder(self):
        for name in self.TEMPLATES:
            path = REPO_ROOT / name
            self.assertTrue(path.exists(), f"missing template: {name}")
            text = path.read_text(encoding="utf-8")
            count = text.count("{{CONTENT}}")
            self.assertEqual(
                count, 1,
                f"{name} has {count} occurrences of {{{{CONTENT}}}}; "
                f"expected exactly 1. The duplication bug returns "
                f"whenever a second literal is added (especially in a "
                f"% comment, where the '%' only protects up to the "
                f"first newline of the substituted body).",
            )

    def test_each_template_substitution_inserts_body_once(self):
        """End-to-end check: the count=1 path in pronto_worker_2.py
        substitutes the body in exactly one place. We simulate the
        substitution against a multi-line body and assert the
        resulting .tex contains the body exactly once.
        """
        body = (
            "\\textbf{The Long Quiet}\n\n"
            "\\textit{A Gentle Guide to Moving Through Depression}\n\n"
            "\\chapter{Opening}\n\n"
            "Body of chapter one.\n"
        )
        for name in self.TEMPLATES:
            tpl = (REPO_ROOT / name).read_text(encoding="utf-8")
            # Mirror the production substitution.
            filled = (
                tpl
                .replace("{{CONTENT}}", body, 1)
                .replace("{{BOOK_TITLE}}", "The Long Quiet")
                .replace("{{AUTHOR_NAME}}", "Test Author")
                .replace("{{FONT_NAME}}", "EB Garamond")
                .replace("{{YEAR}}", "2026")
                .replace("{{ISBN}}", "")
            )
            occurrences = filled.count(body)
            self.assertEqual(
                occurrences, 1,
                f"{name}: body appears {occurrences} time(s) after "
                f"substitution; expected exactly 1."
            )


class Test_PythonReplaceCount(unittest.TestCase):
    """Defense-in-depth check on the worker code itself. Even if a
    template regression slipped through, the Python substitution must
    hard-cap to one substitution.
    """

    def test_pronto_worker_2_uses_count_1_for_content(self):
        path = REPO_ROOT / "pronto_worker_2.py"
        src = path.read_text(encoding="utf-8")
        # The CONTENT replacement line must specify count=1 (positional
        # third arg to str.replace). We grep for the line and assert
        # the count.
        marker = '.replace("{{CONTENT}}"'
        self.assertIn(marker, src, "CONTENT placeholder substitution missing")
        # Find the line that does the CONTENT substitution and check it
        # carries the count argument.
        for line in src.splitlines():
            if marker in line:
                # Three string literals in this line are illegal: the
                # placeholder, the body var, and a count=N integer. We
                # just check that "1)" appears at the end (with the
                # body identifier between the placeholder and the count).
                self.assertTrue(
                    ", 1)" in line,
                    f"CONTENT replace line missing count=1: {line!r}"
                )
                break
        else:
            self.fail("could not find the CONTENT substitution line")


if __name__ == "__main__":
    unittest.main(verbosity=2)
