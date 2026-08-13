import os
import sqlite3
import tempfile
import unittest

from collector import datastore


class DatastoreTest(unittest.TestCase):
    def setUp(self):
        self.fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(self.fd)
        self.conn = datastore.connect(self.path)

    def tearDown(self):
        self.conn.close()
        os.unlink(self.path)

    def test_schema_created(self):
        tables = [r[0] for r in self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")]
        self.assertIn("observations", tables)

    def test_highlight_roundtrip(self):
        rid = datastore.record_highlight(
            self.conn, rating="very_interesting", app="SumatraPDF",
            source=r"C:\Books\book.pdf", page=183,
            selected_text="  The   quick   fox.\n\n"
                          "jumps over. ")
        rows = datastore.all_rows(self.conn)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], rid)
        self.assertEqual(rows[0]["rating"], "very_interesting")
        self.assertEqual(rows[0]["page"], 183)
        # selected_text is cleaned (whitespace collapsed, stripped)
        self.assertEqual(rows[0]["selected_text"], "The quick fox. jumps over.")
        self.assertTrue(rows[0]["ts"])

    def test_control_sample(self):
        datastore.record_control_sample(
            self.conn, app="chrome", source="https://example.com/a",
            title="An Article")
        self.assertEqual(datastore.count(self.conn, kind="control_sample"), 1)
        self.assertEqual(datastore.count(self.conn, kind="highlight"), 0)

    def test_counts_and_stats(self):
        datastore.record_highlight(self.conn, rating="interesting")
        datastore.record_highlight(self.conn, rating="very_interesting")
        datastore.record_highlight(self.conn, rating="interesting")
        datastore.record_control_sample(self.conn)
        st = datastore.stats(self.conn)
        self.assertEqual(st["total"], 4)
        self.assertEqual(st["highlights"], 3)
        self.assertEqual(st["control_samples"], 1)
        self.assertEqual(st["by_rating"]["interesting"], 2)
        self.assertEqual(datastore.count(self.conn, rating="interesting"), 2)

    def test_unknown_fields_ignored(self):
        rid = datastore.insert_observation(
            self.conn, rating="research", bogus_field="nope", kind="highlight")
        rows = datastore.all_rows(self.conn)
        self.assertNotIn("bogus_field", rows[0])
        self.assertEqual(rows[0]["id"], rid)

    def test_db_path_creation(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "nested", "db.sqlite")
        conn = datastore.connect(os.path.expanduser(p))
        datastore.record_highlight(conn, rating="interesting")
        self.assertEqual(datastore.count(conn), 1)
        conn.close()


if __name__ == "__main__":
    unittest.main()
