"""Sampler for neutral/control examples.

While you read, this thread periodically records a `control_sample` row: a
passage-context you *encountered* but did not highlight. This keeps the dataset
from being 100% positive reactions, so downstream models can learn "how likely
is this genuinely worth knowing" with negative/neutral supervision.

It records only what is cheap and non-intrusive (app, source/window title, page
if available, timestamp). It deliberately does NOT simulate Ctrl+C, so it never
steals your clipboard or disrupts reading. This makes V1 control samples
provenance-light; richer passive signals (rereading, dwell time, scroll-back)
are explicitly deferred out of scope for V1.
"""

import threading
import time


class Sampler(threading.Thread):
    def __init__(self, cfg, conn, capture_fn, log=None, stop_event=None):
        super().__init__(daemon=True)
        self.cfg = cfg
        self.conn = conn
        self.capture_fn = capture_fn  # callable that returns a context dict
        self.log = log or (lambda *a, **k: None)
        self.stop_event = stop_event or threading.Event()
        s = cfg.get("sampler", {})
        self.enabled = s.get("enabled", True)
        self.interval = max(1, float(s.get("interval_minutes", 5))) * 60.0
        self.only_reading = s.get("only_reading_apps", True)
        self.reading_apps = [a.lower() for a in cfg.get("reading_apps", [])]

    def _is_reading_app(self, app):
        if not app:
            return False
        app_l = app.lower()
        return any(seg in app_l for seg in self.reading_apps)

    def _maybe_sample(self):
        ctx = self.capture_fn()
        if not ctx:
            return
        app = ctx.get("app") or ""
        if self.only_reading and not self._is_reading_app(app):
            return
        try:
            from collector import datastore
            datastore.record_control_sample(
                self.conn,
                app=ctx.get("app"),
                source=ctx.get("source"),
                url=ctx.get("url"),
                title=ctx.get("title"),
                page=ctx.get("page"),
                location=ctx.get("location"),
                selected_text=None,
            )
            self.log("sampler: control_sample %s" % (ctx.get("source") or ctx.get("title") or app))
        except Exception as exc:  # never let sampling crash the process
            self.log("sampler error: %s" % exc)

    def run(self):
        while not self.stop_event.wait(self.interval):
            if not self.enabled:
                continue
            try:
                self._maybe_sample()
            except Exception as exc:
                self.log("sampler error: %s" % exc)
