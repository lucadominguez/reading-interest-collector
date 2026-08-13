#!/usr/bin/env python3
"""Inspect and maintain the reading-interest dataset. Cross-platform.

Ran by Hermes (or anyone) against the SQLite db without touching Windows APIs:

    python scripts/manage.py stats
    python scripts/manage.py recent [--limit 20]
    python scripts/manage.py search "keyword" [--kind all]
    python scripts/manage.py context <obs_id>        # recover surrounding text
    python scripts/manage.py ratings                 # show hotkey/rating map
"""

import argparse
import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from collector import config, context, datastore  # noqa: E402


def cmd_stats(conn, _args):
    st = datastore.stats(conn)
    print("total observations : %d" % st["total"])
    print("highlights         : %d" % st["highlights"])
    print("control samples    : %d" % st["control_samples"])
    print("dwells             : %d" % st["dwells"])
    print("total dwell time   : %ds  (%.1f min)" % (st["dwell_s"], st["dwell_s"] / 60.0))
    print("total scroll-backs : %d" % st["scroll_backs"])
    print("by rating:")
    for r, n in st["by_rating"].items() or [("(none)", 0)]:
        print("  %-18s %d" % (r, n))


def cmd_recent(conn, args):
    rows = conn.execute(
        "SELECT id, ts, kind, rating, source, title, dwell_s, scroll_backs, "
        "substr(selected_text,1,50) AS snip "
        "FROM observations ORDER BY id DESC LIMIT ?",
        (args.limit,)).fetchall()
    if not rows:
        print("(no observations yet)")
        return
    for r in rows:
        tag = (r["rating"] or "control") if r["kind"] == "highlight" else (
            "dwell" if r["kind"] == "dwell" else "CONTROL")
        sig = ""
        if r["dwell_s"] or r["scroll_backs"]:
            sig = " dwell=%ss sb=%d" % (r["dwell_s"] or 0, r["scroll_backs"] or 0)
        print("[%s]%s %s | %s | %s | %s" % (
            tag, sig, r["ts"], r["source"] or r["title"] or "?",
            r["id"], r["snip"] or ""))


def cmd_search(conn, args):
    like = "%" + args.query + "%"
    sql = ("SELECT id, ts, kind, rating, source, page, dwell_s, scroll_backs, "
           "substr(selected_text,1,70) AS snip "
           "FROM observations WHERE selected_text LIKE ?")
    qargs = [like]
    if args.kind != "all":
        sql += " AND kind = ?"
        qargs.append(args.kind)
    sql += " ORDER BY id"
    rows = conn.execute(sql, qargs).fetchall()
    print("%d match(es):" % len(rows))
    for r in rows:
        sig = ""
        if r["dwell_s"] or r["scroll_backs"]:
            sig = " dwell=%ss sb=%d" % (r["dwell_s"] or 0, r["scroll_backs"] or 0)
        print("  #%s%s [%s %s] p.%s %s\n     %s" % (
            r["id"], sig, r["kind"], r["rating"] or "-",
            r["page"] if r["page"] else "?",
            r["source"] or "", r["snip"] or ""))


def cmd_context(conn, args):
    row = conn.execute("SELECT * FROM observations WHERE id = ?",
                       (args.obs_id,)).fetchone()
    if not row:
        print("no observation #%d" % args.obs_id)
        return
    print(context.recover_context(dict(row)))


def cmd_ratings(_conn, args):
    cfg = config.load_config(args.config)
    for label, hk in cfg["ratings"].items():
        print("  %-18s -> %s" % (label, hk))


def main():
    ap = argparse.ArgumentParser(description="Reading-interest dataset management")
    ap.add_argument("--db", default=config.default_db_path())
    ap.add_argument("--config", default=None)
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("stats")
    p.set_defaults(fn=cmd_stats)

    p = sub.add_parser("recent")
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(fn=cmd_recent)

    p = sub.add_parser("search")
    p.add_argument("query")
    p.add_argument("--kind", choices=["all", "highlight", "control_sample"], default="all")
    p.set_defaults(fn=cmd_search)

    p = sub.add_parser("context")
    p.add_argument("obs_id", type=int)
    p.set_defaults(fn=cmd_context)

    p = sub.add_parser("ratings")
    p.set_defaults(fn=cmd_ratings)

    args = ap.parse_args()
    if not getattr(args, "cmd", None):
        ap.print_help()
        return 2
    need_db = args.cmd not in ("ratings",)
    conn = datastore.connect(args.db) if need_db else None
    try:
        args.fn(conn, args)
    finally:
        if conn:
            conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
