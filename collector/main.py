"""Reading-interest collector - Windows background daemon (main entry).

Run on Windows:

    python -m collector.main

Installs global hotkeys (config.ratings). Pressing one while located in any app
captures the current selection + source and writes a labelled row to SQLite.
A daemon sampler thread writes periodic control samples.

Useful quick checks (Hermes or manual):
    python -m collector.main --check        # print config + db path, no hotkeys
"""

import argparse
import logging
import os
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


def main():
    args = _parse_args()
    cfg = cfg_mod.load_config(args.config)
    db_path = args.db or cfg["db_path"]

    if args.check:
        print("Reading-interest collector config:")
        print("  db          : %s" % os.path.abspath(os.path.expanduser(db_path)))
        for label, hk in cfg["ratings"].items():
            print("  %-18s -> %s" % (label, hk))
        print("  adapters    : %s" % ", ".join(cfg["app_adapters"]))
        print("  sampler     : %s (%s min)" % (
            "on" if cfg["sampler"]["enabled"] else "off",
            cfg["sampler"]["interval_minutes"]))
        return 0

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(message)s")
    log = logging.getLogger("ric").info

    conn = datastore.connect(db_path)
    lock = threading.Lock()

    def write_highlight(rating):
        try:
            from collector import capture
            ctx = capture.build_context(cfg)
            with lock:
                datastore.record_highlight(
                    conn, rating=rating,
                    app=ctx.get("app"),
                    source=ctx.get("source"),
                    url=ctx.get("url"),
                    title=ctx.get("title"),
                    page=ctx.get("page"),
                    location=ctx.get("location"),
                    selected_text=ctx.get("selected_text"),
                )
            log("logged [%s] %s",
                rating,
                (ctx.get("selected_text") or "")[:60].replace("\n", " "))
        except Exception as exc:
            log("capture error: %s", exc)

    # Import the Windows-only pieces here so --check works anywhere.
    from collector import capture  # noqa: F401  (validates imports early)
    capture_fn = lambda: capture.build_context(cfg)

    # Global hotkeys -> rating.
    from pynput import keyboard
    rating_by_key = cfg_mod.ratings_for_keys(cfg)
    log("Hotkeys armed:")
    hotkeys = {}
    for hk, rating in rating_by_key.items():
        hotkeys[hk] = lambda r=rating: write_highlight(r)
        log("  %-18s -> %s", rating, hk)

    listener = keyboard.GlobalHotKeys(hotkeys)

    # Sampler thread for control samples.
    from collector.sampler import Sampler
    stop_event = threading.Event()
    sampler = Sampler(cfg, conn, capture_fn, log=log, stop_event=stop_event)

    log("Starting. Reading now - select text, press a hotkey.")
    stop_event.clear()
    sampler.start()
    listener.start()

    def shutdown(*_):
        stop_event.set()
        listener.stop()
        conn.close()

    import signal
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
