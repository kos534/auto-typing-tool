"""Single-instance guard for Wonuva Typer (Windows).

The first instance owns a named mutex. A second launch detects it, signals a
named event, and exits; the first instance waits on that event and brings its
window back (even from the tray). Both objects are per-user-session
("Local\\"), so other users on the same machine aren't affected.
"""

import ctypes
import threading
from ctypes import wintypes as wt

_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_k32.CreateMutexW.restype = wt.HANDLE
_k32.CreateMutexW.argtypes = [wt.LPVOID, wt.BOOL, wt.LPCWSTR]
_k32.CreateEventW.restype = wt.HANDLE
_k32.CreateEventW.argtypes = [wt.LPVOID, wt.BOOL, wt.BOOL, wt.LPCWSTR]
_k32.OpenEventW.restype = wt.HANDLE
_k32.OpenEventW.argtypes = [wt.DWORD, wt.BOOL, wt.LPCWSTR]
_k32.SetEvent.argtypes = [wt.HANDLE]
_k32.WaitForSingleObject.argtypes = [wt.HANDLE, wt.DWORD]
_k32.WaitForSingleObject.restype = wt.DWORD
_k32.CloseHandle.argtypes = [wt.HANDLE]

ERROR_ALREADY_EXISTS = 183
EVENT_MODIFY_STATE = 0x0002
WAIT_OBJECT_0 = 0
ASFW_ANY = -1

MUTEX_NAME = "Local\\Wonuva.Typer.SingleInstance"
EVENT_NAME = "Local\\Wonuva.Typer.ShowWindow"


class SingleInstance:
    """Held by the running instance for its whole lifetime."""

    def __init__(self, mutex):
        self._mutex = mutex
        # Auto-reset event: each SetEvent wakes the waiter exactly once.
        self._event = _k32.CreateEventW(None, False, False, EVENT_NAME)

    def on_show_request(self, callback):
        """Call ``callback`` (on a background thread) whenever a second launch happens."""
        if not self._event:
            return

        def wait():
            while True:
                if _k32.WaitForSingleObject(self._event, 0xFFFFFFFF) == WAIT_OBJECT_0:
                    try:
                        callback()
                    except Exception:
                        pass  # e.g. the window is already closing

        threading.Thread(target=wait, daemon=True, name="single-instance").start()


def acquire():
    """Return a SingleInstance if we're the first instance, else None."""
    mutex = _k32.CreateMutexW(None, False, MUTEX_NAME)
    if mutex and ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        _k32.CloseHandle(mutex)
        return None
    # If the mutex couldn't be created at all, don't block the app from starting.
    return SingleInstance(mutex)


def signal_existing():
    """Ask the running instance to show its window."""
    # We're the process the user just launched, so we may hand foreground
    # rights to the running instance — otherwise Windows would only flash it.
    try:
        ctypes.windll.user32.AllowSetForegroundWindow(ASFW_ANY)
    except Exception:
        pass
    event = _k32.OpenEventW(EVENT_MODIFY_STATE, False, EVENT_NAME)
    if event:
        _k32.SetEvent(event)
        _k32.CloseHandle(event)
