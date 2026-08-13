"""SQLite storage for the reading-interest dataset.

Cross-platform, stdlib-only. The schema keeps raw observations (never reduces
them into an interest profile) so the data can be exported later for fine-tuning,
preference/reward training, few-shot prompts, embeddings, or evaluation.

A row is one of:
  - highlight      a labelled passage the user reacted to (explicit signal),
  - control_sample a passage encountered but not highlighted (negative/neutral),
  - dwell          a position the user stayed on beyond the dwell threshold
                   (implicit "this held my attention" signal).

Behavioral columns (dwell_s, scroll_backs, position_hash, words) attach to
highlight/dwell rows so a model can learn "given info, how long did I look at
it, did I re-read (scroll back), did I highlight it".
"""

import json
import os
import sqlite3
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS observations (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            TEXT    NOT NULL,          -- ISO8601 UTC
    kind          TEXT    NOT NULL DEFAULT 'highlight',  -- highlight | control_sample | dwell
    rating        TEXT,                      -- very_interesting|interesting|already_knew|uninteresting|research
    app           TEXT,                      -- active application / adapter name
    source        TEXT,                      -- document path or URL (canonical identifier)
    url           TEXT,                      -- URL when reading on the web
    title         TEXT,                      -- window title / page title
    page          INTEGER,                   -- page / location where available
    location      TEXT,                      -- epub/chapter/element id when available
    selected_text TEXT,                      -- the passage text
    dwell_s       INTEGER,                   -- seconds spent on this position
    scroll_backs  INTEGER,                   -- wheel-up (scroll-back / reread) count
    position_hash TEXT,                      -- stable id for the position/selection
    words         INTEGER                    -- word count of selected_text
);

CREATE INDEX IF NOT EXISTS idx_obs_rating ON observations(rating);
CREATE INDEX IF NOT EXISTS idx_obs_source ON observations(source);
CREATE INDEX IF NOT EXISTS idx_obs_ts     ON observations(ts);
"""

# Columns added after V1. `_migrate` ALTERs them in for existing databases.
NEW_COLUMNS = [
    ("dwell_s", "dwell_s INTEGER"),
    ("scroll_backs", "scroll_backs INTEGER"),
    ("position_hash", "position_hash TEXT"),
    ("words", "words INTEGER"),
]

_WRITABLE = {"kind", "rating", "app", "source", "url", "title", "page",
             "location", "selected_text", "dwell_s", "scroll_backs",
             "position_hash", "words"}


def _now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _migrate(conn):
    cols = {r[1] for r in conn.execute("PRAGMA table_info(observations)")}
    for name, ddl in NEW_COLUMNS:
        if name not in cols:
            conn.execute("ALTER TABLE observations ADD COLUMN %s" % ddl)
    # Index depends on position_hash, so create it only after the column exists.
    conn.execute("CREATE INDEX IF NOT EXISTS idx_obs_poshash "
                 "ON observations(position_hash)")
    conn.commit()


def connect(db_path):
    if db_path.startswith("~"):
        db_path = os.path.expanduser(db_path)
    parent = os.path.dirname(os.path.abspath(db_path))
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    _migrate(conn)
    conn.commit()
    return conn


def insert_observation(conn, **fields):
    """Insert one observation. Unknown fields are ignored (schema is fixed)."""
    data = {k: v for k, v in fields.items() if k in _WRITABLE}
    data.setdefault("kind", "highlight")
    if "ts" not in data:
        data["ts"] = _now_iso()
    cols = list(data.keys())
    qs = ",".join("?" * len(data))
    cur = conn.execute(
        "INSERT INTO observations (%s) VALUES (%s)" % (",".join(cols), qs),
        [data[c] for c in cols],
    )
    conn.commit()
    return cur.lastrowid


def _clean_text(text):
    if text is None:
        return None
    text = text.strip()
    # Collapse stray whitespace/newlines inside the passage to keep it clean.
    return " ".join(text.split()) if text else None


def _word_count(text):
    return len(text.split()) if text else 0


def record_highlight(conn, rating, app=None, source=None, url=None,
                     title=None, page=None, location=None, selected_text=None,
                     dwell_s=None, scroll_backs=None, position_hash=None):
    selected_text = _clean_text(selected_text)
    return insert_observation(
        conn, kind="highlight", rating=rating, app=app, source=source,
        url=url, title=title, page=page, location=location,
        selected_text=selected_text, dwell_s=dwell_s, scroll_backs=scroll_backs,
        position_hash=position_hash, words=_word_count(selected_text))


def record_dwell(conn, dwell_s, scroll_backs=0, app=None, source=None,
                 url=None, title=None, page=None, location=None,
                 selected_text=None, position_hash=None):
    selected_text = _clean_text(selected_text)
    return insert_observation(
        conn, kind="dwell", app=app, source=source, url=url, title=title,
        page=page, location=location, selected_text=selected_text,
        dwell_s=int(dwell_s or 0), scroll_backs=int(scroll_backs or 0),
        position_hash=position_hash, words=_word_count(selected_text))


def record_control_sample(conn, app=None, source=None, url=None, title=None,
                          page=None, location=None, selected_text=None):
    return insert_observation(
        conn, kind="control_sample", app=app, source=source, url=url,
        title=title, page=page, location=location,
        selected_text=_clean_text(selected_text))


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
    """Small summary: totals + counts per rating + behavioral totals."""
    out = {"total": count(conn)}
    out["highlights"] = count(conn, kind="highlight")
    out["control_samples"] = count(conn, kind="control_sample")
    out["dwells"] = count(conn, kind="dwell")
    out["by_rating"] = {
        r["rating"]: r["n"]
        for r in conn.execute(
            "SELECT rating, COUNT(*) AS n FROM observations "
            "WHERE kind='highlight' GROUP BY rating ORDER BY n DESC")
    }
    agg = conn.execute(
        "SELECT COALESCE(SUM(dwell_s),0) AS d, COALESCE(SUM(scroll_backs),0) AS s "
        "FROM observations").fetchone()
    out["dwell_s"] = agg["d"]
    out["scroll_backs"] = agg["s"]
    return out


def to_json(conn):
    return json.dumps(all_rows(conn), indent=2, ensure_ascii=False)
