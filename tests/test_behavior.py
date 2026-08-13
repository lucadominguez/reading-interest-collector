import os
import tempfile
import unittest
from threading import Event

from collector import datastore
from collector.behavior import BehaviorWatcher, position_key


def ctx(sel, source="s", page=1, url=None, title="T", location=None):
    return {"app": "chrome", "source": source, "url": url, "title": title,
            "page": page, "location": location, "selected_text": sel}


class PositionKeyTest(unittest.TestCase):
    def test_selection_hash(self):
        a = position_key(ctx("the quick brown fox"))
        b = position_key(ctx("the quick brown fox"))
        c = position_key(ctx("a different passage"))
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)

    def test_location_fallback(self):
        k = position_key(ctx(None, source="https://x.com/a", page=3))
        self.assertIsNotNone(k)
        # same position same hash
        self.assertEqual(k, position_key(ctx(None, source="https://x.com/a", page=3)))

    def test_empty_returns_none(self):
        self.assertIsNone(position_key({}))
        self.assertIsNone(position_key(None))


class WatcherTest(unittest.TestCase):
    def setUp(self):
        fd, self.db = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.conn = datastore.connect(self.db)

    def tearDown(self):
        self.conn.close()
        os.unlink(self.db)

    def _watcher(self, current=None):
        cfg = {"behavior": {"enabled": True, "sample_seconds": 3,
                            "dwell_seconds_min": 2}}
        state = {"current": current}

        def fn():
            return state["current"]
        return BehaviorWatcher(cfg, self.conn, fn,
                               log=lambda *a, **k: None,
                               stop_event=Event()), state

    def test_dwell_recorded_on_position_change(self):
        w, state = self._watcher()
        state["current"] = ctx("alpha passage here")
        w.tick(now=100.0)
        # hold same position, accrue 4s
        state["current"] = ctx("alpha passage here")
        w.tick(now=104.0)
        for _ in range(2):
            w.add_scroll_back()
        self.assertEqual(w.current_signal(now=104.0), (4, 2))
        # move to a new position -> flush the old one
        state["current"] = ctx("beta passage")
        w.tick(now=110.0)
        rows = datastore.all_rows(self.conn)
        dwells = [r for r in rows if r["kind"] == "dwell"]
        self.assertEqual(len(dwells), 1)
        self.assertEqual(dwells[0]["dwell_s"], 10)  # 110 - 100
        self.assertEqual(dwells[0]["scroll_backs"], 2)
        self.assertEqual(dwells[0]["selected_text"], "alpha passage here")
        self.assertTrue(dwells[0]["position_hash"])

    def test_below_threshold_not_recorded(self):
        w, state = self._watcher()
        state["current"] = ctx("brief glance")
        w.tick(now=100.0)
        state["current"] = ctx("next thing")
        w.tick(now=101.0)  # only 1s dwell < 2s threshold, no scroll backs
        self.assertEqual(datastore.count(self.conn), 0)

    def test_scroll_back_alone_triggers_record(self):
        w, state = self._watcher()
        state["current"] = ctx("re-read this")
        w.tick(now=100.0)
        w.add_scroll_back()   # even short dwell: re-read is signal
        state["current"] = ctx("moved on")
        w.tick(now=100.5)
        dwells = [r for r in datastore.all_rows(self.conn) if r["kind"] == "dwell"]
        self.assertEqual(len(dwells), 1)
        self.assertEqual(dwells[0]["scroll_backs"], 1)

    def test_run_finalizes_tail_on_stop(self):
        w, state = self._watcher()
        state["current"] = ctx("last held passage")
        w.tick(now=100.0)
        w.tick(now=105.0)
        # simulated shutdown path: run() waits on stop_event then flushes
        w.stop_event.set()
        w.run_loop_once = False
        w.run()  # will exit loop immediately and flush
        dwells = [r for r in datastore.all_rows(self.conn) if r["kind"] == "dwell"]
        self.assertGreaterEqual(len(dwells), 1)


if __name__ == "__main__":
    unittest.main()
