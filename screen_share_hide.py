"""Keep the caption window out of screen sharing and screen recording (Windows).

Uses SetWindowDisplayAffinity on the caption window itself:
  - WDA_EXCLUDEFROMCAPTURE (Windows 10 version 2004+): the window is invisible in screen shares,
    recordings and screenshots (Teams, Zoom, Meet, OBS, Snipping Tool, ...); viewers see what's
    behind it. It stays fully visible on your own screen.
  - WDA_MONITOR (older Windows): fallback; captures show a black box where the window is.
"""

import ctypes
import logging

log = logging.getLogger(__name__)

WDA_NONE = 0x00
WDA_MONITOR = 0x01
WDA_EXCLUDEFROMCAPTURE = 0x11
GA_ROOT = 2


def _top_level_hwnd(root) -> int:
    """The Win32 handle of a Tk root window's top-level frame (what screen capture sees)."""
    root.update_idletasks()  # make sure the native window exists
    user32 = ctypes.windll.user32
    user32.GetAncestor.restype = ctypes.c_void_p
    user32.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    return user32.GetAncestor(root.winfo_id(), GA_ROOT) or root.winfo_id()


def hide_window_from_screen_share(window) -> bool:
    """Hide the given CaptionWindow (or Tk root) from screen capture. Returns True on success.

    Only this app's own window is changed. Failure is logged and harmless: the window just
    stays visible in screen shares.
    """
    root = getattr(window, "root", window)
    try:
        user32 = ctypes.windll.user32
        user32.SetWindowDisplayAffinity.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        user32.SetWindowDisplayAffinity.restype = ctypes.c_bool
        hwnd = _top_level_hwnd(root)
        for mode, name in ((WDA_EXCLUDEFROMCAPTURE, "excluded from capture"), (WDA_MONITOR, "black in captures")):
            if user32.SetWindowDisplayAffinity(hwnd, mode):
                log.info("Caption window hidden from screen sharing (%s)", name)
                return True
        log.warning("Could not hide the caption window from screen sharing (error %d)", ctypes.GetLastError())
    except Exception:
        log.exception("Could not hide the caption window from screen sharing")
    return False


def show_window_in_screen_share(window) -> bool:
    """Undo hide_window_from_screen_share: the window shows up in captures again."""
    root = getattr(window, "root", window)
    try:
        user32 = ctypes.windll.user32
        user32.SetWindowDisplayAffinity.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        user32.SetWindowDisplayAffinity.restype = ctypes.c_bool
        if user32.SetWindowDisplayAffinity(_top_level_hwnd(root), WDA_NONE):
            log.info("Window visible in screen sharing again")
            return True
        log.warning("Could not make the window visible in screen sharing (error %d)",
                    ctypes.GetLastError())
    except Exception:
        log.exception("Could not make the window visible in screen sharing")
    return False
