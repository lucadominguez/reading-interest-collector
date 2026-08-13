"""Clipboard helpers for the Windows collector.

Provides:
  - read_clipboard_text(): non-greedy read of the current clipboard.
  - capture_selection_via_clipboard(): simulate Ctrl+C, read the clipboard,
    then restore the ORIGINAL clipboard contents so the user's clipboard is
    never clobbered by a hotkey press.

Windows-only; guarded so the module is importable elsewhere (imports happen
inside functions).
"""

import time


def read_clipboard_text():
    try:
        import win32clipboard
    except Exception:
        return None
    try:
        win32clipboard.OpenClipboard()
        try:
            if win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_UNICODETEXT):
                data = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
                return data
            if win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_TEXT):
                data = win32clipboard.GetClipboardData(win32clipboard.CF_TEXT)
                return data.decode("utf-8", "replace")
        finally:
            win32clipboard.CloseClipboard()
    except Exception:
        return None
    return None


def _send_ctrl_c():
    try:
        import win32api
        import win32con
        import time as _t
        win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
        win32api.keybd_event(ord("C"), 0, 0, 0)
        win32api.keybd_event(ord("C"), 0, win32con.KEYEVENTF_KEYUP, 0)
        win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
        return True
    except Exception:
        return False


def capture_selection_via_clipboard(retries=3, delay=0.12):
    """Copy the current selection to the clipboard, read it, restore original.

    Returns the selected text, or None if nothing was selected / it failed.
    """
    import win32clipboard

    original = read_clipboard_text()
    try:
        for attempt in range(retries):
            # Clear the clipboard so stale content is not mistaken for a new copy.
            try:
                win32clipboard.OpenClipboard()
                win32clipboard.EmptyClipboard()
            finally:
                try:
                    win32clipboard.CloseClipboard()
                except Exception:
                    pass
            if not _send_ctrl_c():
                break
            time.sleep(delay)
            got = read_clipboard_text()
            if got and got.strip() and got != original:
                return got
        return None
    finally:
        # Restore whatever was on the clipboard before we touched it.
        try:
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            if original:
                win32clipboard.SetClipboardData(win32clipboard.CF_UNICODETEXT, original)
        except Exception:
            pass
        finally:
            try:
                win32clipboard.CloseClipboard()
            except Exception:
                pass
