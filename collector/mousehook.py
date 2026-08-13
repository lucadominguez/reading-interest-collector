"""Windows low-level mouse hook that counts scroll-back (wheel-up) events.

A wheel-up (positive delta) while reading is treated as a "scroll back" - the
reader going up to re-read something. Feeds a BehaviorWatcher via a callback.

Windows-only: installs a SetWindowsHookEx(WH_MOUSE_LL) hook. Runs its own
message loop in a thread. Guarded imports so the module is importable anywhere.
"""

import ctypes
import threading
from ctypes import wintypes

# WM_MOUSEWHEEL = 0x020A
WM_MOUSEWHEEL = 0x020A
WH_MOUSE_LL = 14
# HIWORD(delta): positive means wheel scrolled up (towards the user = back).
WHEEL_DELTA = 120


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("pt", POINT), ("mouseData", wintypes.DWORD),
                ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]


class ScrollBackHook(threading.Thread):
    """Runs a low-level mouse hook and calls `on_scroll_back()` on wheel-up.

    Pass `active_cb` (callable -> bool) so events are only counted while a
    reading app is foreground.
    """

    def __init__(self, on_scroll_back, active_cb=None):
        super().__init__(daemon=True)
        self.on_scroll_back = on_scroll_back
        self.active_cb = active_cb or (lambda: True)
        self._hook = None
        self._msg_loop_thread = self
        # Keep a reference to the callback to avoid GC while the hook is live.
        self._callback = None

    def _is_scroll_up(self, mouse_data):
        # mouse_data holds the wheel delta in the high word, signed.
        signed = ctypes.c_short(mouse_data >> 16).value
        return signed > 0

    def _proc(self, nCode, wParam, lParam):
        if nCode >= 0 and wParam == WM_MOUSEWHEEL:
            data = ctypes.cast(lParam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
            try:
                if self._is_scroll_up(data.mouseData) and self.active_cb():
                    self.on_scroll_back()
            except Exception:
                pass
        # Always chain to the next hook.
        try:
            return ctypes.windll.user32.CallNextHookEx(
                self._hook, nCode, wParam, lParam)
        except Exception:
            return 0

    def run(self):
        try:
            import ctypes
            CMPFUNC = ctypes.CFUNCTYPE(
                ctypes.c_long, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
            self._callback = CMPFUNC(self._proc)
            self._hook = ctypes.windll.user32.SetWindowsHookExW(
                WH_MOUSE_LL, self._callback,
                ctypes.windll.kernel32.GetModuleHandleW(None), 0)
            if not self._hook:
                return
            # Low-level hooks need a message loop for callbacks to fire.
            msg = wintypes.MSG()
            while ctypes.windll.user32.GetMessageW(ctypes.byref(msg), 0, 0, 0) != 0:
                ctypes.windll.user32.TranslateMessage(ctypes.byref(msg))
                ctypes.windll.user32.DispatchMessageW(ctypes.byref(msg))
        except Exception:
            pass
        finally:
            try:
                if self._hook:
                    ctypes.windll.user32.UnhookWindowsHookEx(self._hook)
            except Exception:
                pass
