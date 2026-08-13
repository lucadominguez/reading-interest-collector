"""Configuration for the reading-interest collector.

Stored as a single human-readable JSON file so it is trivial to inspect and edit.
Cross-platform: this module touches no Windows APIs.

Default hotkeys map a rating to a pynput-style hotkey string. They are per-label
so new labels can be added without touching code.
"""

import json
import os

DEFAULT_CONFIG = {
    # Rating label -> global hotkey. pynput `Key` names or single characters.
    "ratings": {
        "very_interesting": "ctrl+alt+1",
        "interesting": "ctrl+alt+2",
        "already_knew": "ctrl+alt+3",
        "uninteresting": "ctrl+alt+4",
        "research": "ctrl+alt+5",
    },
    # Which app adapters to enable. Order matters only for logging.
    "app_adapters": ["sumatrapdf", "browser", "generic"],
    # How to grab selected text. "uia" tries the UI Automation Text pattern
    # first, then falls back to a simulated Ctrl+C + clipboard read.
    "capture": {
        "method": "uia",
        "clipboard_fallback": True,
    },
    # Sampling of passages you encountered but did NOT highlight, so we get
    # control / negative examples instead of a dataset of only things you liked.
    "sampler": {
        "enabled": True,
        "interval_minutes": 5,
        # Only sample when the foreground app looks like a reader/browser.
        "only_reading_apps": True,
    },
    # SQLite database file. ~ is expanded.
    "db_path": "~/reading_interest.db",
    # Browser executables we recognise and treat as reading apps for sampling.
    "reading_apps": [
        "chrome",
        "msedge",
        "firefox",
        "brave",
        "sumatrapdf",
        "adobe",
        "acrobat",
        "foxit",
    ],
}


def default_db_path():
    return os.path.expanduser(DEFAULT_CONFIG["db_path"])


def load_config(path=None):
    """Load config from `path` (default: alongside the package data dir).

    Missing file -> defaults. Unknown keys are ignored so older configs keep
    working; missing keys are filled in from defaults.
    """
    if path is None:
        path = default_config_path()
    if not os.path.exists(path):
        cfg = dict(DEFAULT_CONFIG)
        return cfg
    with open(path, "r", encoding="utf-8") as fh:
        loaded = json.load(fh)
    cfg = dict(DEFAULT_CONFIG)
    cfg.update({k: v for k, v in loaded.items() if k in cfg})
    _deep_fill(cfg, DEFAULT_CONFIG)
    return cfg


def _deep_fill(cfg, defaults):
    for key, value in defaults.items():
        if isinstance(value, dict):
            if not isinstance(cfg.get(key), dict):
                cfg[key] = {}
            _deep_fill(cfg[key], value)
        elif key not in cfg:
            cfg[key] = value


def save_config(cfg, path=None):
    if path is None:
        path = default_config_path()
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    return path


def default_config_path():
    base = os.environ.get("READING_COLLECTOR_CONFIG_DIR", os.path.expanduser("~/.reading-collector"))
    return os.path.join(base, "config.json")


def ratings_for_keys(cfg):
    """Return {hotkey_string: rating_label} for the current config."""
    return {hk: label for label, hk in cfg["ratings"].items()}
