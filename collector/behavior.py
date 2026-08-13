"""Behavior watcher: dwell-time tracking and scroll-back (reread) signal.

This is the passive telemetry core. It answers, per position:

  - how long did I stay looking at this word / passage?       (dwell_s)
  - did I re-read it by scrolling back up?                    (scroll_backs)
  - did I highlight it (explicit label)?                      (kind=highlight)

Design
------
A background thread samples the foreground reading context every
`behavior.sample_seconds`. It computes a stable `position_hash` for where you
are: the SHA-1 of the current selection if any, else of (source, page, url).
While the position is unchanged, dwell time accrues. When the position changes
(or on shutdown), the previous position is finalised: if it exceeded the dwell
threshold OR accrued any scroll-backs, a `dwell` row is written.

A Windows low-level mouse hook (collector/mousehook.py) feeds wheel-up events
into `add_scroll_back()`; the count is attributed to the position active then.

Sampling uses UI-Automation-only selection reads (no clipboard theft), so
dwell tracking never disrupts your reading or clipboard.

The core watcher logic here is cross-platform and unit-tested. The Windows
mouse hook and the per-tick capture are injected.
"""

import hashlib
import threading
import time


def position_key(ctx):
    """Stable hash identifying "where I am" for dwell grouping."""
    if not ctx:
        return None
    sel = (ctx.get("selected_text") or "").strip()
    if sel:
        return hashlib.sha1(("sel:" + sel).encode("utf-8", "replace")).hexdigest()
    parts = [ctx.get("source"), ctx.get("page"), ctx.get("url"),
             ctx.get("location")]
    key = "|".join(str(x) for x in parts if x is not None)
    if not key:
        return None
    return hashlib.sha1(("pos:" + key).encode("utf-8", "replace")).hexdigest()


class BehaviorWatcher(threading.Thread):
    def __init__(self, cfg, conn, context_fn, log=None, stop_event=None):
        super().__init__(daemon=True)
        self.cfg = cfg
        self.conn = conn
        self.context_fn = context_fn  # returns a context dict (no clipboard sim)
        self.log = log or (lambda *a, **k: None)
        self.stop_event = stop_event or threading.Event()
        b = cfg.get("behavior", {})
        self.sample_s = max(1.0, float(b.get("sample_seconds", 3.0)))
        self.dwell_min = float(b.get("dwell_seconds_min", 2.0))
        self.enabled = b.get("enabled", True)
        self._lock = threading.Lock()
        self._cur_key = None
        self._cur_start = None
        self._cur_ctx = None
        self._cur_scroll_backs = 0

    # -- external feed (mouse hook) -----------------------------------------
    def add_scroll_back(self):
        with self._lock:
            self._cur_scroll_backs += 1

    def current_signal(self, now=None):
        """(dwell_s, scroll_backs) for the active position - attached to a
        highlight when a hotkey fires, so explicit labels carry behavior."""
        now = now if now is not None else time.time()
        with self._lock:
            if self._cur_key is None:
                return (0, 0)
            return (int(now - self._cur_start), self._cur_scroll_backs)

    # -- internal ------------------------------------------------------------
    def _flush(self, now):
        with self._lock:
            if self._cur_key is None:
                return
            dwell = now - self._cur_start
            sb = self._cur_scroll_backs
            ctx = self._cur_ctx
            key = self._cur_key
            self._cur_key = None
            self._cur_start = None
            self._cur_ctx = None
            self._cur_scroll_backs = 0
        if dwell >= self.dwell_min or sb > 0:
            try:
                from collector import datastore
                datastore.record_dwell(
                    self.conn, dwell_s=int(dwell), scroll_backs=sb,
                    app=ctx.get("app"), source=ctx.get("source"),
                    url=ctx.get("url"), title=ctx.get("title"),
                    page=ctx.get("page"), location=ctx.get("location"),
                    selected_text=ctx.get("selected_text"),
                    position_hash=key)
                self.log("dwell: %ds sb=%d %s",
                         int(dwell), sb,
                         (ctx.get("selected_text") or ctx.get("source") or "")[:60])
            except Exception as exc:
                self.log("dwell error: %s", exc)

    def tick(self, now=None):
        if not self.enabled:
            return
        now = now if now is not None else time.time()
        try:
            ctx = self.context_fn()
        except Exception as exc:
            self.log("dwell capture error: %s", exc)
            return
        key = position_key(ctx)
        with self._lock:
            same = (key is not None and key == self._cur_key)
        if same:
            return  # staying put - dwell keeps accruing
        self._flush(now)
        if key is not None and ctx:
            with self._lock:
                self._cur_key = key
                self._cur_start = now
                self._cur_ctx = ctx

    def run(self):
        while not self.stop_event.wait(self.sample_s):
            try:
                self.tick()
            except Exception as exc:
                self.log("dwell loop error: %s", exc)
        # finalise whatever we were tracking so no tail is lost
        self._flush(time.time())
