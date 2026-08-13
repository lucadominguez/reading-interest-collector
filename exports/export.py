"""Export the observation dataset to JSON or CSV.

Cross-platform, stdlib-only. Run against any copy of the SQLite db, e.g.:

    python exports/export.py --format json --out highlights.json
    python exports/export.py --format csv  --out dataset.csv --kind all
    python exports/export.py --format jsonl --out dataset.jsonl

Outputs the RAW observations (selected_text intact) suitable for fine-tuning,
preference/reward training, few-shot prompting, embeddings, or ranking eval.
"""

import argparse
import csv
import io
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from collector.datastore import all_rows, connect  # noqa: E402

CSV_FIELDS = ["id", "ts", "kind", "rating", "app", "source", "url",
              "title", "page", "location", "selected_text"]


def main():
    ap = argparse.ArgumentParser(description="Export reading-interest dataset")
    ap.add_argument("--db", default=os.path.expanduser("~/reading_interest.db"))
    ap.add_argument("--format", choices=["json", "jsonl", "csv"], default="json")
    ap.add_argument("--out", default=None,
                    help="Output file. Defaults to reading_interest.<fmt>")
    ap.add_argument("--kind", choices=["highlight", "control_sample", "all"],
                    default="all", help="Rows to export")
    args = ap.parse_args()

    conn = connect(args.db)
    rows = all_rows(conn)
    if args.kind != "all":
        rows = [r for r in rows if r["kind"] == args.kind]

    if args.out:
        out_path = args.out
    else:
        out_path = os.path.join(os.getcwd(), "reading_interest.%s" % args.format)

    if args.format == "json":
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(rows, fh, indent=2, ensure_ascii=False)
    elif args.format == "jsonl":
        with open(out_path, "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    elif args.format == "csv":
        with io.open(out_path, "w", newline="", encoding="utf-8-sig") as fh:
            writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS,
                                    extrasaction="ignore")
            writer.writeheader()
            for r in rows:
                writer.writerow(r)

    print("Wrote %d rows to %s" % (len(rows), out_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
