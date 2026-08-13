import csv
import json
import os
import subprocess
import sys
import tempfile
import unittest

from collector import datastore

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class ExportTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.db = os.path.join(self.dir, "test.db")
        self.conn = datastore.connect(self.db)
        datastore.record_highlight(
            self.conn, rating="very_interesting", app="SumatraPDF",
            source=r"C:\Books\b.pdf", page=7, selected_text="alpha passage")
        datastore.record_highlight(
            self.conn, rating="interesting", app="chrome",
            source="https://example.com", selected_text="beta passage")
        datastore.record_control_sample(
            self.conn, app="chrome", source="https://example.com/other")
        self.conn.close()

    def _run(self, *extra):
        return subprocess.run(
            [sys.executable, os.path.join(REPO, "exports", "export.py"),
             "--db", self.db] + list(extra),
            cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True)

    def test_json_export(self):
        out = os.path.join(self.dir, "out.json")
        r = self._run("--format", "json", "--out", out)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(out) as fh:
            rows = json.load(fh)
        self.assertEqual(len(rows), 3)
        self.assertTrue(rows[0]["selected_text"])
        self.assertIn("alpha", rows[0]["selected_text"])

    def test_jsonl_and_kind_filter(self):
        out = os.path.join(self.dir, "out.jsonl")
        r = self._run("--format", "jsonl", "--out", out, "--kind", "highlight")
        self.assertEqual(r.returncode, 0, r.stderr)
        lines = [json.loads(l) for l in open(out) if l.strip()]
        self.assertEqual(len(lines), 2)
        self.assertTrue(all(x["kind"] == "highlight" for x in lines))

    def test_csv_export(self):
        out = os.path.join(self.dir, "out.csv")
        r = self._run("--format", "csv", "--out", out)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(out, encoding="utf-8-sig") as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual(len(rows), 3)
        self.assertIn("selected_text", rows[0])


if __name__ == "__main__":
    unittest.main()
