"""System-tray presence for Wonuva Typer.

- The main window gets no taskbar button: it's made "owned" by a hidden
  window, and Windows never shows taskbar buttons for owned windows. This
  keeps the normal title bar (with its minimize button), unlike the
  tool-window style.
- A tray icon (pystray) shows/hides the window and exits the app.
"""

import ctypes
from ctypes import wintypes as wt

import pystray
from PIL import Image

_user32 = ctypes.WinDLL("user32", use_last_error=True)

_user32.CreateWindowExW.restype = wt.HWND
_user32.CreateWindowExW.argtypes = [
    wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD, ctypes.c_int, ctypes.c_int,
    ctypes.c_int, ctypes.c_int, wt.HWND, wt.HMENU, wt.HINSTANCE, wt.LPVOID]
_user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
_user32.GetWindowLongPtrW.argtypes = [wt.HWND, ctypes.c_int]
_user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
_user32.SetWindowLongPtrW.argtypes = [wt.HWND, ctypes.c_int, ctypes.c_ssize_t]

GWL_EXSTYLE = -20
GWLP_HWNDPARENT = -8   # for a top-level window this sets its *owner*
WS_EX_APPWINDOW = 0x00040000


def hide_from_taskbar(hwnd):
    """Remove the window's taskbar button. Call while the window is hidden.

    Returns the hidden owner window's handle (keep it for the app's lifetime).
    """
    owner = _user32.CreateWindowExW(0, "STATIC", "Wonuva Typer owner", 0,
                                    0, 0, 0, 0, None, None, None, None)
    ex = _user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
    _user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, ex & ~WS_EX_APPWINDOW)
    if owner:
        _user32.SetWindowLongPtrW(hwnd, GWLP_HWNDPARENT, owner)
    return owner


class Tray:
    """Tray icon with Show / Hide / Exit. Callbacks run on the Tk thread."""

    def __init__(self, root, title, icon_path, on_show, on_hide, on_exit):
        self._root = root
        self._title = title

        def on_tk(fn):
            # pystray calls menu actions on its own thread; hop to Tk's.
            return lambda: root.after(0, fn)

        menu = pystray.Menu(
            pystray.MenuItem(f"Show {title}", on_tk(on_show), default=True),
            pystray.MenuItem("Hide to tray", on_tk(on_hide)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit", on_tk(on_exit)),
        )
        self.icon = pystray.Icon("WonuvaTyper", Image.open(icon_path), title, menu)
        self.icon.run_detached()

    def set_tooltip(self, text):
        text = f"{self._title} — {text}" if text else self._title
        try:
            self.icon.title = text[:120]  # Windows caps tray tooltips at 127 chars
        except Exception:
            pass

    def notify(self, message):
        try:
            self.icon.notify(message, self._title)
        except Exception:
            pass

    def stop(self):
        try:
            self.icon.stop()
        except Exception:
            pass
