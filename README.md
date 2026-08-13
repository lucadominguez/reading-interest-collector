# Reading-Interest Collector

A tiny Windows background daemon (managed by a Hermes skill) that quietly logs
what you react to while you read - in any app. **select text → press one hotkey
→ keep reading.**

The output is a clean, inspectable SQLite dataset of labelled passages plus
their provenance (app, document/URL, page, timestamp). The raw signal is
preserved so it can later be exported for model fine-tuning, preference/reward
training, few-shot prompting, embedding/retrieval work, or evaluating
personalized ranking.

**This is not a recommendation engine, knowledge graph, or research system.**
It is a logger. The dataset is the point.

## Why it exists

The long-term goal is data to answer: *"given some information, how likely am I
to think it is genuinely worth knowing?"* That needs **positive and negative
examples**, so the collector stores explicit ratings and also periodically
samples passages you *encountered but didn't highlight* as control samples.

## Core interaction

Works across SumatraPDF, browsers, EPUB readers, text files - anything with
selectable text. No need to open Hermes or paste anything.

```
select text → press one key → continue reading
```

Default hotkeys (edit in config):

| Hotkey       | Rating            |
|--------------|-------------------|
| Ctrl+Alt+1   | very_interesting  |
| Ctrl+Alt+2   | interesting       |
| Ctrl+Alt+3   | already_knew      |
| Ctrl+Alt+4   | uninteresting     |
| Ctrl+Alt+5   | research          |

## How capture works

On a hotkey press, the collector:

1. Reads the **foreground window** (app + title) via Win32.
2. Enriches provenance through a small **app adapter**:
   - **SumatraPDF** → document path, page number (best-effort via UI Automation)
   - **Browser** (Chrome/Edge/Firefox/Brave) → URL (best-effort from address
     bar) + page title
   - **Generic** → app name + window title
3. Grabs the **selected text**: tries the UI Automation `TextPattern` first,
   then falls back to simulating `Ctrl+C`, reading the clipboard, and **restoring
   your original clipboard** so a hotkey never clobbers it.
4. Writes one row to SQLite.

A background **sampler thread** writes a `control_sample` every N minutes while
you're in a reading app - provenance for passages you saw but didn't label, so
you get neutral/negative examples rather than a dataset of only things you liked.

## Record format

Same shape regardless of app (example rows):

```json
{"kind":"highlight","rating":"very_interesting","app":"SumatraPDF",
 "source":"C:\\Books\\book.pdf","page":183,"selected_text":"...",
 "ts":"2026-08-13T07:18:49+00:00"}

{"kind":"highlight","rating":"interesting","app":"browser",
 "source":"https://example.com/article","url":"https://example.com/article",
 "title":"An Article","selected_text":"...","ts":"..."}

{"kind":"control_sample","app":"chrome","source":"https://example.com/other",
 "ts":"..."}
```

## Install & run (Windows)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install.ps1   # venv + deps + default config
powershell -ExecutionPolicy Bypass -File scripts\run.ps1       # launch hidden daemon
```

Requirements (auto-installed): `pynput`, `pywin32`, `uiautomation`, and optional
`pymupdf` for richer PDF context recovery.

Config lives at `%USERPROFILE%\.reading-collector\config.json` (hotkeys, adapters,
sampler interval, db path).

## Inspect / export

Cross-platform CLI (run from Hermes or anywhere Python works):

```bash
python scripts/manage.py stats                 # totals per rating
python scripts/manage.py recent                # last rows
python scripts/manage.py search "keyword"      # grep the dataset
python scripts/manage.py context 42            # recover surrounding text of row 42
python scripts/manage.py ratings               # current hotkey map

python exports/export.py --format jsonl --out dataset.jsonl  # json | jsonl | csv
```

`context` recovers the surrounding paragraph from a **local** PDF/text file
using the stored `source` + `page`, without storing whole documents at log time
(only the selected passage is saved).

## Project layout

```
collector/            the Windows daemon
  main.py             entry; wires hotkeys, capture, sampler
  capture.py          foreground window + selection capture (UIA → clipboard)
  adapters.py         SumatraPDF / browser / generic adapters
  clipboard.py        clipboard read + restore-safe Ctrl+C fallback
  sampler.py          control-sample thread (negative/neutral examples)
  datastore.py        SQLite schema + inserts   (cross-platform)
  config.py           JSON config               (cross-platform)
  context.py          recover surrounding context from local files (cross-platform)
exports/export.py     export to json / jsonl / csv (cross-platform)
scripts/              install.ps1, run.ps1, manage.py
tests/                stdlib unittest suite (runs on Linux too)
```

## Design notes / V1 scope

- **Lightweight log**: only the selected passage + source id are stored. Full
  context is recovered on demand later from the local file, never at log time.
- **Raw observations preserved**: no reduction into an interest profile.
- **Passive telemetry deferred**: rereading, dwell time, scroll-back, copy
  events are out of scope for V1 on purpose. The sampler's control rows are the
  only implicit signal.
- **Untested portability**: the cross-platform core (datastore, config, export,
  context, sampler logic) is unit-tested here on Linux. The Windows capture
  layer (Win32/UIA/clipboard/hotkeys) is written defensively but has **not been
  exercised on a real Windows desktop** from this environment - follow the
  smoke-test step below to verify on your machine.

## Quick smoke test (verify capture works on your Windows box)

```powershell
# 1. run the daemon, then select text in SumatraPDF or a browser
python -m collector.main --check                 # prints config + db path
# 2. select a sentence, press Ctrl+Alt+1
# 3. confirm the row landed:
python scripts\manage.py recent
```

## License

MIT
