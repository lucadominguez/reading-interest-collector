"""Reading-interest collector - Windows background daemon (main entry).

Run on Windows:

    python -m collector.main

Installs global hotkeys (config.ratings). Pressing one while located in any app
captures the current selection + source and writes a labelled row to SQLite,
attaching the behavior watcher's current dwell/scroll-back signal to that row.

Two passive telemetry run in the background:
  - BehaviorWatcher: samples the foreground selection every few seconds and
    records `dwell` rows when you stay on a passage (dwell_s) or re-read it
    (scroll_backs).
  - ScrollBackHook: a Windows low-level mouse hook counting wheel-up events
    that feed the watcher while a reading app is foreground.

Useful quick checks (Hermes or manual):
    python -m collector.main --check        # print config + db path, no hotkeys
"""

import argparse
import logging
import os
import signal
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collector import config as cfg_mod  # noqa: E402
from collector import datastore  # noqa: E402


def _parse_args():
    ap = argparse.ArgumentParser(description="Reading-interest collector daemon")
    ap.add_argument("--config", default=None, help="Path to config.json")
    ap.add_argument("--db", default=None, help="Override SQLite db path")
    ap.add_argument("--check", action="store_true",
                    help="Print configuration and exit without starting")
    return ap.parse_args()


def _print_config(cfg, db_path):
    print("Reading-interest collector config:")
    print("  db          : %s" % os.path.abspath(os.path.expanduser(db_path)))
    for label, hk in cfg["ratings"].items():
        print("  %-18s -> %s" % (label, hk))
    print("  adapters    : %s" % ", ".join(cfg["app_adapters"]))
    print("  sampler     : %s (%s min)" % (
        "on" if cfg["sampler"]["enabled"] else "off",
        cfg["sampler"]["interval_minutes"]))
    print("  behavior    : %s (dwell>=%ss, sample every %ss)" % (
        "on" if cfg.get("behavior", {}).get("enabled", True) else "off",
        cfg.get("behavior", {}).get("dwell_seconds_min", 2),
        cfg.get("behavior", {}).get("sample_seconds", 3)))


def main():
    args = _parse_args()
    cfg = cfg_mod.load_config(args.config)
    db_path = args.db or cfg["db_path"]

    if args.check:
        _print_config(cfg, db_path)
        return 0

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(message)s")
    log = logging.getLogger("ric").info

    conn = datastore.connect(db_path)
    lock = threading.Lock()

    from collector import capture

    # Full capture for explicit hotkeys (may use clipboard fallback).
    def capture_for_hotkey():
        return capture.build_context(cfg)

    # Clipboard-free capture for the dwell watcher (never steals your clipboard).
    def capture_for_watcher():
        return capture.build_context(cfg, allow_clipboard=False)

    # Behavior watcher + scroll-back hook.
    from collector.behavior import BehaviorWatcher
    stop_event = threading.Event()
    watcher = BehaviorWatcher(cfg, conn, capture_for_watcher, log=log,
                              stop_event=stop_event)

    scroll_hook = None
    try:
        from collector.mousehook import ScrollBackHook
        scroll_hook = ScrollBackHook(
            on_scroll_back=watcher.add_scroll_back,
            active_cb=lambda: capture.is_reading_foreground(cfg))
    except Exception as exc:
        log("mouse hook unavailable (%s); scroll-back signal disabled", exc)

    def write_highlight(rating):
        ctx = None
        try:
            ctx = capture_for_hotkey()
        except Exception as exc:
            log("capture error: %s", exc)
        dwell_s, scroll_backs = watcher.current_signal()
        from collector.behavior import position_key
        try:
            with lock:
                datastore.record_highlight(
                    conn, rating=rating,
                    app=(ctx or {}).get("app"),
                    source=(ctx or {}).get("source"),
                    url=(ctx or {}).get("url"),
                    title=(ctx or {}).get("title"),
                    page=(ctx or {}).get("page"),
                    location=(ctx or {}).get("location"),
                    selected_text=(ctx or {}).get("selected_text"),
                    dwell_s=dwell_s, scroll_backs=scroll_backs,
                    position_hash=position_key(ctx),
                )
            log("logged [%s] dwell=%ss sb=%d %s",
                rating, dwell_s, scroll_backs,
                ((ctx or {}).get("selected_text") or "")[:60].replace("\n", " "))
        except Exception as exc:
            log("write error: %s", exc)

    # Hotkeys -> rating.
    from pynput import keyboard
    rating_by_key = cfg_mod.ratings_for_keys(cfg)
    hotkeys = {}
    for hk, rating in rating_by_key.items():
        hotkeys[hk] = (lambda r=rating: write_highlight(r))
        log("  %-18s -> %s", rating, hk)
    listener = keyboard.GlobalHotKeys(hotkeys)

    # Control-sample sampler.
    from collector.sampler import Sampler
    sampler = Sampler(cfg, conn, capture_for_watcher, log=log,
                      stop_event=stop_event)

    log("Starting. Reading now - select text, press a hotkey.")
    watcher.start()
    if scroll_hook is not None:
        scroll_hook.start()
    sampler.start()
    listener.start()

    def shutdown(*_):
        stop_event.set()
        listener.stop()
        watcher.join(timeout=2)
        if scroll_hook is not None:
            # break the hook's message loop
            try:
                import ctypes
                ctypes.windll.user32.PostThreadMessageW(
                    scroll_hook.ident, 0x0012, 0, 0)  # WM_QUIT
            except Exception:
                pass
        conn.close()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    listener.join()
    log("Collector stopped.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("stopped")
        sys.exit(0)
