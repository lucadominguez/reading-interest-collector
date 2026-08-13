"""Windows foreground-window and selection capture.

build_context() returns a dict describing the current reading context at the
instant a hotkey fires:

    app, source, url, title, page, location, selected_text

Capture strategy (config.capture):
  - method "uia": try to find the selected text through UI Automation's
    TextPattern for the focused control. Many apps (editors, some readers,
    browsers' inputs) expose it; not all do.
  - clipboard_fallback: if UIA yields nothing, simulate Ctrl+C, read the
    clipboard, and restore it. This is the most universal path.

App adapters (adapters.py) enrich `source`/`url`/`title` from the foreground
window without reading the whole document. Everything is defensive: any single
failure degrades to whatever fields we could recover.
"""

import os

try:
    from collector import adapters as _adapters_mod
except ImportError:  # running from inside the package dir
    import adapters as _adapters_mod


def _foreground_window_info():
    try:
        import win32gui
        import win32process
    except Exception:
        return {}
    info = {"app": None, "title": None, "pid": None, "exe": None, "hwnd": None}
    try:
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return info
        info["hwnd"] = hwnd
        info["title"] = win32gui.GetWindowText(hwnd)
        pid = win32process.GetWindowThreadProcessId(hwnd)[1]
        info["pid"] = pid
        info["exe"] = _process_exe_name(pid)
        info["app"] = os.path.basename(info["exe"] or "").lower() or info["title"]
    except Exception:
        pass
    return info


def _process_exe_name(pid):
    try:
        import win32api
        import win32con
        import win32process
        PROCESS_QUERY_INFORMATION = 0x0400
        PROCESS_VM_READ = 0x0010
        h = win32api.OpenProcess(
            PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
        try:
            return win32process.GetModuleFileNameEx(h, 0)
        finally:
            win32api.CloseHandle(h)
    except Exception:
        return None


def _uia_selected_text(hwnd):
    """Best-effort UI Automation selected text of the focused control."""
    try:
        import uiautomation as auto
    except Exception:
        return None
    try:
        control = auto.ControlFromHandle(hwnd)
        focused = control.GetFocusedControl()
        if focused is None:
            focused = control
        pattern = focused.GetPattern(auto.PatternId.TextPattern)
        if pattern is None:
            # Try descendants that might hold the caret/selection.
            return None
        ranges = pattern.GetSelection()
        if ranges:
            return ranges[0].GetText(-1)
        # Some apps only report the caret position, not a selection.
        return None
    except Exception:
        return None


def build_context(cfg, hwnd=None):
    """Return the full context dict for a hotkey capture."""
    fg = _foreground_window_info()
    if hwnd is None:
        hwnd = fg.get("hwnd")
    app = fg.get("app")
    title = fg.get("title")

    ctx = {
        "app": app,
        "source": None,
        "url": None,
        "title": title,
        "page": None,
        "location": None,
        "selected_text": None,
    }

    # App adapter enriches source/url/page/location from the window.
    try:
        ctx = _adapters_mod.adapt(app, title, hwnd, ctx)
    except Exception:
        pass  # keep whatever we have

    # Selected text: UIA first, clipboard fallback second.
    method = cfg.get("capture", {}).get("method", "uia")
    if method == "uia" and hwnd:
        ctx["selected_text"] = _uia_selected_text(hwnd)
    if not ctx["selected_text"] and cfg.get("capture", {}).get("clipboard_fallback", True):
        try:
            from collector.clipboard import capture_selection_via_clipboard
            ctx["selected_text"] = capture_selection_via_clipboard()
        except Exception:
            pass

    return ctx
