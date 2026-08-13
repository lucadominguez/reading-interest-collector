import os
import tempfile
import unittest
from threading import Event

from collector import datastore
from collector.sampler import Sampler


class SamplerTest(unittest.TestCase):
    def setUp(self):
        self.fd, self.db = tempfile.mkstemp(suffix=".db")
        os.close(self.fd)
        self.conn = datastore.connect(self.db)

    def tearDown(self):
        self.conn.close()
        os.unlink(self.db)

    def _sampler(self, cfg_extra=None, captured=None, reading=True):
        cfg = {
            "sampler": {"enabled": True, "interval_minutes": 5,
                        "only_reading_apps": True},
            "reading_apps": ["chrome", "sumatrapdf"],
        }
        if cfg_extra:
            cfg.update(cfg_extra)
        if captured is None:
            captured = {"app": "chrome", "source": "https://x.com/a",
                        "url": "https://x.com/a", "title": "T"}
            if not reading:
                captured = {"app": "notepad.exe", "source": "untitled"}
        calls = {"n": 0}

        def capture_fn():
            calls["n"] += 1
            return captured
        return Sampler(cfg, self.conn, capture_fn, log=lambda *a, **k: None,
                       stop_event=Event()), calls

    def test_is_reading_app(self):
        s, _ = self._sampler(reading=True)
        self.assertTrue(s._is_reading_app("Chrome"))
        self.assertTrue(s._is_reading_app("SumatraPDF"))
        self.assertFalse(s._is_reading_app("notepad.exe"))

    def test_maybe_sample_records_control_sample(self):
        s, _ = self._sampler(reading=True)
        s._maybe_sample()
        self.assertEqual(datastore.count(self.conn, kind="control_sample"), 1)
        rows = datastore.all_rows(self.conn)
        self.assertEqual(rows[0]["source"], "https://x.com/a")

    def test_maybe_sample_skips_non_reading_app(self):
        s, _ = self._sampler(reading=False)
        s._maybe_sample()
        self.assertEqual(datastore.count(self.conn), 0)


if __name__ == "__main__":
    unittest.main()
