"""SQLite storage for the reading-interest dataset.

Cross-platform, stdlib-only. The schema keeps raw observations (never reduces
them into an interest profile) so the data can be exported later for fine-tuning,
preference/reward training, few-shot prompts, embeddings, or evaluation.

A row is one of:
  - a labelled highlight (the raw signal the user reacted to), or
  - a control_sample (a passage encountered but not highlighted, for negative/
    neutral examples).
"""

import json
import os
import sqlite3
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS observations (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            TEXT    NOT NULL,          -- ISO8601 UTC
    kind          TEXT    NOT NULL DEFAULT 'highlight',  -- highlight | control_sample
    rating        TEXT,                      -- very_interesting|interesting|already_knew|uninteresting|research
    app           TEXT,                      -- active application / adapter name
    source        TEXT,                      -- document path or URL (canonical identifier)
    url           TEXT,                      -- URL when reading on the web
    title         TEXT,                      -- window title / page title
    page          INTEGER,                   -- page / location where available
    location      TEXT,                      -- epub/chapter/element id when available
    selected_text TEXT                       -- the passage text
);

CREATE INDEX IF NOT EXISTS idx_obs_rating ON observations(rating);
CREATE INDEX IF NOT EXISTS idx_obs_source ON observations(source);
CREATE INDEX IF NOT EXISTS idx_obs_ts     ON observations(ts);
"""


def _now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(db_path):
    if db_path.startswith("~"):
        db_path = os.path.expanduser(db_path)
    parent = os.path.dirname(os.path.abspath(db_path))
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def insert_observation(conn, **fields):
    """Insert one observation. Unknown fields are ignored (schema is fixed)."""
    allowed = {"kind", "rating", "app", "source", "url", "title",
               "page", "location", "selected_text"}
    data = {k: v for k, v in fields.items() if k in allowed}
    data.setdefault("kind", "highlight")
    if "ts" not in data:
        data["ts"] = _now_iso()
    cols = list(data.keys())
    qs = ",".join("?" * len(cols))
    cur = conn.execute(
        "INSERT INTO observations (%s) VALUES (%s)" % (",".join(cols), qs),
        [data[c] for c in cols],
    )
    conn.commit()
    return cur.lastrowid


def record_highlight(conn, rating, app=None, source=None, url=None,
                     title=None, page=None, location=None, selected_text=None):
    return insert_observation(
        conn,
        kind="highlight",
        rating=rating,
        app=app,
        source=source,
        url=url,
        title=title,
        page=page,
        location=location,
        selected_text=_clean_text(selected_text),
    )


def record_control_sample(conn, app=None, source=None, url=None, title=None,
                          page=None, location=None, selected_text=None):
    return insert_observation(
        conn,
        kind="control_sample",
        app=app,
        source=source,
        url=url,
        title=title,
        page=page,
        location=location,
        selected_text=_clean_text(selected_text),
    )


def _clean_text(text):
    if text is None:
        return None
    text = text.strip()
    # Collapse stray whitespace/newlines inside the passage to keep it clean.
    return " ".join(text.split()) if text else None


def all_rows(conn):
    return [dict(r) for r in conn.execute(
        "SELECT * FROM observations ORDER BY ts, id")]


def count(conn, kind=None, rating=None):
    sql = "SELECT COUNT(*) AS n FROM observations"
    args = []
    conds = []
    if kind is not None:
        conds.append("kind = ?")
        args.append(kind)
    if rating is not None:
        conds.append("rating = ?")
        args.append(rating)
    if conds:
        sql += " WHERE " + " AND ".join(conds)
    return conn.execute(sql, args).fetchone()["n"]


def stats(conn):
    """Small summary: totals + counts per rating, for quick inspection."""
    out = {"total": count(conn)}
    out["highlights"] = count(conn, kind="highlight")
    out["control_samples"] = count(conn, kind="control_sample")
    out["by_rating"] = {
        r["rating"]: r["n"]
        for r in conn.execute(
            "SELECT rating, COUNT(*) AS n FROM observations "
            "WHERE kind='highlight' GROUP BY rating ORDER BY n DESC")
    }
    return out


def to_json(conn):
    return json.dumps(all_rows(conn), indent=2, ensure_ascii=False)
