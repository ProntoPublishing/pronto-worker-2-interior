"""Genre-Aware Interior v0 — W2 contract: Book Metadata `Genre`
routes the template family (Fiction/Nonfiction, purpose-built binary);
empty/unrecognized defaults to fiction WITH a logged warning; genre
never touches the trim."""

import os
import sys
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pronto_worker_2 import InteriorProcessor


def _params(book_metadata):
    p = InteriorProcessor.__new__(InteriorProcessor)
    p.airtable_client = MagicMock()
    p.airtable_client.get_project.return_value = {"Book Metadata": ["bm1"]}
    p.airtable_client.get_book_metadata.return_value = book_metadata
    # E4 mocks explicitly nulled — a bare MagicMock is truthy.
    p.airtable_client.get_default_imprint.return_value = None
    p.airtable_client.get_imprint.return_value = None
    return p._get_formatting_parameters({"Project": ["proj1"]})


def _bm(genre=None, trim='6" × 9"'):
    bm = {"Book Title": "T", "Author Name": "A", "Trim Size": trim}
    if genre is not None:
        bm["Genre"] = genre
    return bm


class TestGenreRouting(unittest.TestCase):
    def test_nonfiction_select_routes(self):
        params = _params(_bm(genre={"name": "Nonfiction"}))
        self.assertEqual(params["genre"], "nonfiction")

    def test_fiction_select_routes(self):
        params = _params(_bm(genre={"name": "Fiction"}))
        self.assertEqual(params["genre"], "fiction")

    def test_plain_string_shape_accepted(self):
        # pyairtable returns singleSelect values as plain strings.
        self.assertEqual(_params(_bm(genre="Nonfiction"))["genre"],
                         "nonfiction")
        self.assertEqual(_params(_bm(genre="fiction"))["genre"], "fiction")

    def test_empty_defaults_to_fiction_with_warning(self):
        with self.assertLogs("pronto_worker_2", level="WARNING") as cm:
            params = _params(_bm())
        self.assertEqual(params["genre"], "fiction")
        self.assertTrue(any("genre-default-fiction" in line
                            for line in cm.output))

    def test_unrecognized_defaults_to_fiction_with_warning(self):
        with self.assertLogs("pronto_worker_2", level="WARNING") as cm:
            params = _params(_bm(genre="Cookbook"))
        self.assertEqual(params["genre"], "fiction")
        self.assertTrue(any("genre-default-fiction" in line
                            and "Cookbook" in line for line in cm.output))

    def test_genre_never_touches_trim(self):
        params = _params(_bm(genre={"name": "Nonfiction"}, trim='5" × 8"'))
        self.assertEqual(params["genre"], "nonfiction")
        self.assertEqual(params["trim_name"], "5x8")
        self.assertEqual(params["trim_dims"], (5.0, 8.0))

    def test_template_name_composition(self):
        # The selection expression in process_service: genre routes the
        # family, trim routes the size — reproduce its composition for
        # every shipped pair and assert the file exists.
        root = os.path.join(os.path.dirname(__file__), "..")
        import trims
        for genre in ("fiction", "nonfiction"):
            for tn in trims.INTERIOR_TRIM_NAMES:
                path = os.path.join(root, f"{genre}_{tn}.tex")
                self.assertTrue(os.path.exists(path), path)


if __name__ == "__main__":
    unittest.main()
