import os
import tempfile
import unittest

from collector import context

PASSAGE = "the quantum eraser experiment shows"


class ContextTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.text_path = os.path.join(self.dir, "notes.txt")
        with open(self.text_path, "w", encoding="utf-8") as fh:
            fh.write("Some earlier text that is not relevant here. "
                     "But then " + PASSAGE + " appears right here in the middle "
                     "of a longer paragraph that we want to see surrounding. "
                     "Followed by more trailing words.")

    def test_recover_text_file(self):
        snip = context.recover_text_file(self.text_path, PASSAGE)
        self.assertIsNotNone(snip)
        self.assertIn(PASSAGE, snip)
        self.assertGreater(len(snip), len(PASSAGE))

    def test_recover_text_file_missing(self):
        self.assertIsNone(context.recover_text_file(
            os.path.join(self.dir, "nope.txt"), PASSAGE))

    def test_recover_pdf_missing_module_returns_none(self):
        # If pymupdf is unavailable it must degrade gracefully, not raise.
        try:
            import pymupdf  # noqa: F401
            self.skipTest("pymupdf present; real PDF path not tested here")
        except Exception:
            info = context.recover_pdf("/no/such.pdf", selected_text=PASSAGE)
            self.assertIsNone(info)

    def test_recover_context_dispatch(self):
        # text source -> recovered snippet
        snip = context.recover_context(
            {"source": self.text_path, "selected_text": PASSAGE})
        self.assertIn(PASSAGE, snip)
        # web source -> no local copy
        web = context.recover_context(
            {"source": "https://example.com/a", "selected_text": PASSAGE})
        self.assertIn("no local copy", web)
        # missing source
        none = context.recover_context({"source": "", "selected_text": PASSAGE})
        self.assertEqual(none, "no source")


if __name__ == "__main__":
    unittest.main()
