"""Small application adapters for the Windows collector.

Each adapter enriches a capture context dict with the fields it can cheaply
recover from the foreground window - WITHOUT reading the whole document. This
keeps logging lightweight; full context is recovered later from the source
file by collector/context.py.

Coverage in V1 (per the brief): generic Windows support, SumatraPDF, and
browsers. Everything is best-effort and degrades to window title on failure.
"""

BROWSER_APPS = {"chrome", "msedge", "edge", "firefox", "brave",
                "opera", "vivaldi", "chromium"}


def _uia_edit_value(hwnd, name_fragment=None):
    """Best-effort read of an editable field's value via UI Automation."""
    try:
        import uiautomation as auto
    except Exception:
        return None
    try:
        root = auto.ControlFromHandle(hwnd)
        for ctrl in root.GetChildren():
            if ctrl.ControlType == auto.ControlType.EditControl:
                val = ctrl.GetValuePattern()
                if val is not None:
                    text = val.Value()
                    if text:
                        if name_fragment is None or name_fragment in (ctrl.Name or ""):
                            return text
        return None
    except Exception:
        return None


def _sumatrapdf_page(hwnd):
    """SumatraPDF exposes pages through UI Automation; pull the current one.

    Best effort - if the tree doesn't expose it, return None.
    """
    try:
        import uiautomation as auto
    except Exception:
        return None
    try:
        root = auto.ControlFromHandle(hwnd)
        tree = root.GetChildren()
        stack = list(tree)
        while stack:
            ctrl = stack.pop()
            try:
                name = ctrl.Name or ""
            except Exception:
                name = ""
            low = name.lower()
            if low.startswith("page") and any(ch.isdigit() for ch in low):
                import re
                m = re.search(r"(\d+)", low)
                if m:
                    return int(m.group(1))
            try:
                stack.extend(ctrl.GetChildren())
            except Exception:
                pass
        return None
    except Exception:
        return None


def _adapt_sumatrapdf(app, title, hwnd, ctx):
    ctx["app"] = "SumatraPDF"
    # Title is typically "<document> - SumatraPDF" or just "<document>".
    source = title
    for marker in (" - SumatraPDF", " - Sumatra PDF", "- SumatraPDF"):
        if marker in title:
            source = title.split(marker)[0].strip()
            break
    ctx["source"] = source or title
    if hwnd is not None:
        try:
            ctx["page"] = _sumatrapdf_page(hwnd)
        except Exception:
            ctx["page"] = None
    return ctx


def _adapt_browser(app, title, hwnd, ctx):
    ctx["app"] = "browser"
    # Title is usually "<page title> - <Browser>".
    short = title
    for marker in (" - Google Chrome", " - Microsoft Edge", " - Firefox",
                   " - Brave", " - Opera", " - Vivaldi"):
        if short.endswith(marker):
            short = short[: -len(marker)].strip()
            break
    ctx["title"] = short or title
    if hwnd is not None:
        url = _uia_edit_value(hwnd, name_fragment="address")
        if not url:
            url = _uia_edit_value(hwnd)
        if url:
            ctx["url"] = url.strip()
            ctx["source"] = url.strip()
    if not ctx.get("source"):
        ctx["source"] = ctx.get("title") or title
    return ctx


def _adapt_generic(app, title, hwnd, ctx):
    # Generic: window title + app name is all we reliably know.
    ctx["app"] = app or "unknown"
    ctx["title"] = title
    ctx["source"] = title
    return ctx


def adapt(app, title, hwnd, ctx):
    """Dispatch to the right adapter based on the active app."""
    app_l = (app or "").lower()
    if "sumatra" in app_l:
        return _adapt_sumatrapdf(app, title, hwnd, ctx)
    if app_l in BROWSER_APPS or any(b in app_l for b in ("chrome", "msedge", "firefox")):
        return _adapt_browser(app, title, hwnd, ctx)
    return _adapt_generic(app, title, hwnd, ctx)
