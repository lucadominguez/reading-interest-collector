---
name: reading-interest-collector
description: "Collect a reading-interest dataset via global hotkeys."
version: 0.2.0
author: lucadominguez, Hermes Agent
license: MIT
platforms: [windows]
metadata:
  hermes:
    tags: [reading, dataset, windows, hotkeys, data-collection]
    related_skills: []
---

# Reading-Interest Collector Skill

Manages a small Windows background daemon that logs what the user reacts to
while reading in any app: select text, press a hotkey, keep reading. The output
is a clean SQLite dataset of labelled passages + provenance for later
fine-tuning / preference training / retrieval experiments.

This skill is NOT a reading app and NOT a recommendation engine. It installs,
runs, configures, inspects, and exports the collector. The dataset is the point.

## When to Use

- User asks to start/stop the reading-interest collector.
- User asks to configure rating hotkeys or app adapters.
- User asks to inspect the collected dataset (stats, recent, search).
- User asks to recover surrounding context for a stored passage.
- User asks to export the dataset for model training.
- Don't use for: reading the document itself, analysis of the dataset, or
  building recommendation/inference on top of it.

## Prerequisites

- Repo cloned: `git clone https://github.com/lucadominguez/reading-interest-collector ~/reading-interest-collector`
- On the Windows box: Python 3.9+ and PowerShell.
- Dependencies (`pynput`, `pywin32`, `uiautomation`) installed by `scripts/install.ps1`.
- Config file: `%USERPROFILE%\.reading-collector\config.json` (created by install).

## How to Run

On the Windows machine (native PowerShell, or from WSL via
`powershell.exe -ExecutionPolicy Bypass -File ...`):

```powershell
scripts\install.ps1     # first time: venv + deps + default config
scripts\run.ps1         # launch hidden background daemon
```

The daemon runs everything: hotkeys, explicit highlights, a dwell/scroll-back
watcher, and the control-sample sampler. `manage.py` reports dwell totals too.

Inspection/export are cross-platform and can be run from Hermes anywhere:

```bash
python3 scripts/manage.py stats
python3 scripts/manage.py recent --limit 20
python3 scripts/manage.py search "nootropic"
python3 scripts/manage.py context 42
python3 exports/export.py --db ~/reading_interest.db --format jsonl --out dataset.jsonl
```

## Quick Reference

| Task | Command |
|------|---------|
| Install (Windows) | `powershell.exe -ExecutionPolicy Bypass -File scripts/install.ps1` |
| Start daemon | `powershell.exe -ExecutionPolicy Bypass -File scripts/run.ps1` |
| Verify config | `python3 -m collector.main --check` |
| Stats | `python3 scripts/manage.py stats` |
| Recent rows | `python3 scripts/manage.py recent` |
| Search dataset | `python3 scripts/manage.py search "<kw>"` |
| Context recovery | `python3 scripts/manage.py context <obs_id>` |
| Export jsonl | `python3 exports/export.py --format jsonl --out out.jsonl` |
| Export csv | `python3 exports/export.py --format csv --out out.csv` |
| Stop daemon | `Get-Process python | Where-Object { $_.Path -like "*reading-interest-collector*" } | Stop-Process` |

Run all cross-platform commands with `workdir` set to the cloned repo root.

## Procedure

1. **Setup** (first time): clone the repo, then on Windows run
   `scripts/install.ps1`. It creates `.venv`, installs deps, writes the default
   config. Completion check: `collector.main --check` prints the db path and all
   five hotkeys.
2. **Start**: `scripts/run.ps1` launches the hidden daemon.
   Completion check: `manage.py recent` shows rows after a hotkey test.
3. **Smoke test on Windows**: select a sentence in SumatraPDF or a browser, press
   `Ctrl+Alt+1` (very_interesting), then `manage.py recent` shows the row with
   `source` + `selected_text`.
4. **Verify behavioral telemetry**: keep one passage selected for >2s then move
   on, and scroll *up* while reading. `manage.py recent` should show a `dwell`
   row (`dwell=N s sb=M`) and highlights carrying dwell/scroll-back counts.
5. **Configure hotkeys/adapters/behavior**: edit the JSON config, then restart
   the daemon. `ratings` map label→hotkey; `app_adapters` is the enabled adapter
   list (`sumatrapdf`, `browser`, `generic`); `behavior` sets the dwell threshold
   and sampling interval. Completion check: `manage.py ratings` reflects the new
   map, `manage.py stats` shows dwell totals.
6. **Inspect**: `manage.py stats` for per-rating + dwell totals, `manage.py
   search` for grep (shows dwell/scroll-back on matches), `manage.py context
   <id>` to pull the surrounding paragraph from the local source file.
7. **Export**: `exports/export.py --format jsonl|csv|json --out <path>`.
   Completion check: the output file exists and row count matches `stats`.

## Pitfalls

- **Windows capture is best-effort.** UIA `TextPattern` doesn't exist in every
  app; the clipboard fallback (simulated Ctrl+C + restore) covers most cases but
  apps that don't expose a selection yield `selected_text: null`. Prefer
  SumatraPDF and real browsers for the most reliable capture.
- **The clipboard is restored** after a fallback capture, but if you had
  non-text (e.g. an image) on the clipboard it is replaced - avoid a hotkey
  immediately after copying a screenshot.
- **SumatraPDF page number** and **browser URL** are recovered via UI Automation
  and can be missing in some versions. `manage.py context` recovers surrounding
  text from the local file when `source` is a local path; web sources have no
  local copy, so only the stored passage is available.
- **Sampler writes control samples** (neutral/negative examples) only when a
  reading app is in the foreground and the sampler is enabled. It never touches
  your clipboard.
- **Dwell tracking** samples the current selection via UI Automation every
  `behavior.sample_seconds`; if the app/reader does not expose a selection it
  falls back to (source, page, url). It never simulates Ctrl+C, so it can't
  disrupt reading or clobber the clipboard.
- **Scroll-back counting** needs the Windows LL mouse hook
  (`collector/mousehook.py`); if mousewheel events aren't delivered, only wheel
  events while a reading app is foreground are counted and failures degrade to
  `scroll_backs=0`. Verify with a quick wheel-up during the smoke test.
- **The collector must be running** for hotkeys to fire. If hotkeys do nothing,
  confirm the daemon process is alive before editing config.
- The core (datastore/config/export/context/sampler) is unit-tested on Linux; the
  Windows capture layer is written defensively but verify with the smoke test on
  the actual desktop.

## Verification

- `collector.main --check` prints db path + 5 hotkeys. ✓ config wired
- After a hotkey test, `manage.py recent` shows a `highlight` row with rating,
  source, and selected_text. ✓ capture path
- `manage.py stats` reports `total = highlights + control_samples`. ✓ consistency
- `exports/export.py` produces a file with the expected row count. ✓ exportable
