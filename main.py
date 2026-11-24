"""Wonuva Typer.

Paste text into the window, click into any input field in any application,
then press Ctrl+Shift+` to start typing. Press Esc to pause/resume,
Ctrl+Shift+` again to stop.

Typing is humanized: keystroke timing is randomized, punctuation and
newlines get natural pauses, and (optionally) occasional typos are made
and corrected with backspace.
"""

import ctypes
import random
import threading
import time
import tkinter as tk
from tkinter import ttk

import keyboard

import ui
from ui import BG, PANEL, INK, BORDER, GOLD, TEXT, MUTED, FAINT

APP_NAME = "Wonuva Typer"
APP_VERSION = "1.1.0"

_user32 = ctypes.WinDLL("user32", use_last_error=True)
GetForegroundWindow = _user32.GetForegroundWindow
SetForegroundWindow = _user32.SetForegroundWindow
IsWindow = _user32.IsWindow

MapVirtualKeyW = _user32.MapVirtualKeyW
MAPVK_VSC_TO_VK_EX = 3
NUMPAD_VK_FIRST, NUMPAD_VK_LAST = 0x60, 0x6F  # VK_NUMPAD0 .. VK_DIVIDE


def _scan_code_to_vk(code: int) -> int:
    return MapVirtualKeyW(code & 0xFF, MAPVK_VSC_TO_VK_EX) if code > 0 else 0


HOTKEY = "ctrl+shift+`"
PAUSE_KEY = "esc"

# QWERTY neighbors used to pick realistic wrong keys for simulated typos.
NEIGHBORS = {
    "q": "wa", "w": "qes", "e": "wrd", "r": "etf", "t": "ryg", "y": "tuh",
    "u": "yij", "i": "uok", "o": "ipl", "p": "ol",
    "a": "qsz", "s": "awdx", "d": "sefc", "f": "drgv", "g": "fthb",
    "h": "gyjn", "j": "hukm", "k": "jil", "l": "kop",
    "z": "asx", "x": "zsdc", "c": "xdfv", "v": "cfgb", "b": "vghn",
    "n": "bhjm", "m": "njk",
}

SENTENCE_PUNCT = ".!?"
CLAUSE_PUNCT = ",;:"

# Shifted symbols on a US QWERTY layout, mapped to their unshifted key.
SHIFT_SYMBOLS = {
    "!": "1", "@": "2", "#": "3", "$": "4", "%": "5", "^": "6", "&": "7",
    "*": "8", "(": "9", ")": "0", "_": "-", "+": "=", "{": "[", "}": "]",
    "|": "\\", ":": ";", '"': "'", "<": ",", ">": ".", "?": "/", "~": "`",
}


class WonuvaTyper:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.typing = False
        self.paused = False
        self._stop_event = threading.Event()
        self.target_hwnd = None  # window focused when typing started; kept in focus until stop
        self._progress = None
        self._auto_paused = False  # paused because the user clicked into this window
        self._base_delay = 0.1     # seconds/char; read live by the typing thread

        self.char_delay = tk.DoubleVar(value=100)
        self.start_delay = tk.DoubleVar(value=1.0)
        self.make_typos = tk.BooleanVar(value=True)
        # Speed changes apply immediately, even in the middle of typing.
        self.char_delay.trace_add("write", lambda *_: self._apply_live_speed())

        # Build hidden: the title-bar colors only take effect if they're set
        # before Windows first paints the frame.
        root.withdraw()
        self.theme = ui.Theme(root)
        self._build_window()
        self._build_ui()

        root.update_idletasks()
        self.own_hwnd = int(root.wm_frame(), 16)
        ui.style_title_bar(self.own_hwnd)
        root.deiconify()

        keyboard.add_hotkey(HOTKEY, self.toggle_start_stop)
        keyboard.add_hotkey(PAUSE_KEY, self.toggle_pause)

        root.protocol("WM_DELETE_WINDOW", self.on_close)

    # --- UI ---

    def _build_window(self):
        s, root = self.theme.s, self.root
        root.title(APP_NAME)
        root.configure(bg=BG)
        root.geometry(f"{s(620)}x{s(780)}")
        root.minsize(s(520), s(700))
        root.attributes("-topmost", True)
        try:
            root.iconbitmap(default=ui.resource_path("assets/icon.ico"))
        except tk.TclError:
            pass
        # (Don't also call iconphoto(): on Windows it replaces the .ico's
        # crisp small sizes with a generic placeholder in the title bar.)
        # Logo for the header: pick the source closest to ~52px at this DPI.
        if s(52) < 60:
            self._logo = tk.PhotoImage(file=ui.resource_path("assets/icon48.png"))
        else:
            self._logo = tk.PhotoImage(
                file=ui.resource_path("assets/icon128.png")).subsample(2)

    def _build_ui(self):
        t, s, root = self.theme, self.theme.s, self.root

        ui.Header(root, t, self._logo, APP_NAME,
                  "Humanlike keystrokes, conjured into any window.").pack(fill="x")

        content = tk.Frame(root, bg=BG)
        content.pack(fill="both", expand=True, padx=s(18), pady=(s(14), 0))

        # status + footer are packed first so they always stay visible
        footer = tk.Frame(content, bg=BG)
        footer.pack(side="bottom", fill="x", pady=(s(6), s(8)))
        tk.Label(footer, text=f"© Wonuva  ·  v{APP_VERSION}", bg=BG, fg=FAINT,
                 font=t.f_small).pack(side="right")
        tk.Label(footer, text="Run as Administrator to type into elevated apps.",
                 bg=BG, fg=FAINT, font=t.f_small).pack(side="left")

        self.status_bar = ui.StatusBar(content, t)
        self.status_bar.pack(side="bottom", fill="x", pady=(s(12), 0))
        self.status_bar.set(f"Ready — click into any text field, then press "
                            f"{self._hotkey_label()}", "ready")

        # Packed bottom-up so the text area (packed last) is what shrinks
        # when the window is small, never the settings.
        self._build_hotkeys(content)
        self._build_settings(content)
        self._build_text_card(content)

    def _build_text_card(self, parent):
        t, s = self.theme, self.theme.s
        card = ui.Card(parent, t, "Text to type")
        card.pack(side="top", fill="both", expand=True)

        actions = tk.Frame(card.head, bg=PANEL)
        actions.pack(side="right")
        ui.Button(actions, t, "Clear", self._clear_text, icon="✕").pack(side="right")
        ui.Button(actions, t, "Paste", self._paste_text, icon="⎘").pack(
            side="right", padx=(0, s(8)))

        frame = tk.Frame(card.body, bg=INK, highlightthickness=1,
                         highlightbackground=BORDER, highlightcolor=GOLD)
        frame.pack(fill="both", expand=True)
        self.text_box = tk.Text(
            frame, wrap="word", height=8, bg=INK, fg=TEXT, font=t.f_text,
            insertbackground=GOLD, selectbackground="#5b3fb8",
            selectforeground="#ffffff", relief="flat", bd=0,
            padx=s(12), pady=s(10), undo=True, highlightthickness=0)
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.text_box.yview,
                               style="Wonuva.Vertical.TScrollbar")
        self.text_box.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.text_box.pack(side="left", fill="both", expand=True)
        self.text_box.bind("<FocusIn>", lambda e: frame.configure(highlightbackground=GOLD))
        self.text_box.bind("<FocusOut>", lambda e: frame.configure(highlightbackground=BORDER))

        self._placeholder = tk.Label(
            self.text_box, text="Paste or write the text you want typed…",
            bg=INK, fg=FAINT, font=t.f_text, cursor="xterm")
        self._placeholder.bind("<Button-1>", lambda e: self.text_box.focus_set())

        self.counter = tk.Label(card.body, bg=PANEL, fg=MUTED, font=t.f_small,
                                anchor="e")
        self.counter.pack(fill="x", pady=(s(6), 0))

        self.text_box.bind("<<Modified>>", self._on_text_modified)
        self.char_delay.trace_add("write", lambda *_: self._update_counter())
        self.make_typos.trace_add("write", lambda *_: self._update_counter())
        self._update_counter()

    def _build_settings(self, parent):
        t, s = self.theme, self.theme.s
        card = ui.Card(parent, t, "Settings", glyph="diamond")
        card.pack(side="bottom", fill="x", pady=(s(12), 0))
        body = card.body
        body.columnconfigure(0, weight=1)

        def row_label(r, title, var_label):
            head = tk.Frame(body, bg=PANEL)
            head.grid(row=r, column=0, sticky="ew")
            tk.Label(head, text=title, bg=PANEL, fg=TEXT, font=t.f_body).pack(side="left")
            value = tk.Label(head, bg=PANEL, fg=GOLD, font=t.f_value)
            value.pack(side="right")
            var_label(value)

        row_label(0, "Typing speed", lambda w: setattr(self, "_speed_value", w))
        ui.Slider(body, t, self.char_delay, 20, 500, 5, invert=True,
                  labels=("Leisurely", "Swift")).grid(row=1, column=0, sticky="ew",
                                                      pady=(s(2), s(6)))

        row_label(2, "Start delay", lambda w: setattr(self, "_delay_value", w))
        ui.Slider(body, t, self.start_delay, 0, 10, 0.5).grid(
            row=3, column=0, sticky="ew", pady=(s(2), s(8)))

        typo = tk.Frame(body, bg=PANEL)
        typo.grid(row=4, column=0, sticky="ew")
        ui.Toggle(typo, t, self.make_typos).pack(side="right")
        text = tk.Frame(typo, bg=PANEL)
        text.pack(side="left", fill="x")
        tk.Label(text, text="Simulate typos", bg=PANEL, fg=TEXT,
                 font=t.f_body).pack(anchor="w")
        tk.Label(text, text="Now and then hits a neighboring key, notices, and corrects it.",
                 bg=PANEL, fg=MUTED, font=t.f_small).pack(anchor="w")

        self.char_delay.trace_add("write", lambda *_: self._update_setting_labels())
        self.start_delay.trace_add("write", lambda *_: self._update_setting_labels())
        self._update_setting_labels()

    def _build_hotkeys(self, parent):
        t, s = self.theme, self.theme.s
        bar = tk.Frame(parent, bg=BG)
        bar.pack(side="bottom", fill="x", pady=(s(12), 0))

        def chord(keys, action, side):
            group = tk.Frame(bar, bg=BG)
            group.pack(side=side)
            for i, k in enumerate(keys):
                if i:
                    tk.Label(group, text="+", bg=BG, fg=FAINT,
                             font=t.f_small).pack(side="left", padx=s(2))
                ui.Keycap(group, t, k, bg=BG).pack(side="left")
            tk.Label(group, text=action, bg=BG, fg=MUTED,
                     font=t.f_small).pack(side="left", padx=(s(8), 0))

        chord(["Ctrl", "Shift", "`"], "Start / Stop", "left")
        chord(["Esc"], "Pause / Resume", "right")

    # --- UI helpers ---

    @staticmethod
    def _hotkey_label():
        return " + ".join(k.capitalize() if len(k) > 1 else k for k in HOTKEY.split("+"))

    @staticmethod
    def _pace_name(ms):
        for limit, name in ((40, "Lightning"), (70, "Swift"), (130, "Steady"),
                            (250, "Measured")):
            if ms <= limit:
                return name
        return "Leisurely"

    def _update_setting_labels(self):
        try:
            ms = float(self.char_delay.get())
            delay = float(self.start_delay.get())
        except (tk.TclError, ValueError):
            return
        wpm = 60000 / ms / 5
        self._speed_value.configure(
            text=f"{self._pace_name(ms)}  ·  {ms:.0f} ms/char  ·  ≈{wpm:.0f} WPM")
        self._delay_value.configure(text="Immediately" if delay == 0 else f"{delay:.1f} s")

    def _on_text_modified(self, _event=None):
        self.text_box.edit_modified(False)
        self._update_counter()

    def _update_counter(self):
        text = self.text_box.get("1.0", "end-1c")
        if text:
            self._placeholder.place_forget()
        else:
            self._placeholder.place(x=self.theme.s(12), y=self.theme.s(10))
        n = len(text)
        words = len(text.split())
        secs = self._estimate_seconds(text)
        est = (f"{secs:.0f} s" if secs < 60 else
               f"{secs // 60:.0f} min {secs % 60:.0f} s")
        self.counter.configure(
            text=f"{n:,} characters  ·  {words:,} words  ·  est. {est}" if n
            else "Nothing to type yet")

    def _estimate_seconds(self, text):
        """Rough duration using the same pause rules as the typing loop."""
        try:
            base = max(float(self.char_delay.get()), 10) / 1000
        except (tk.TclError, ValueError):
            base = 0.1
        secs = len(text) * base
        secs += text.count("\n") * 0.65
        secs += sum(text.count(c) for c in SENTENCE_PUNCT) * 0.5
        secs += sum(text.count(c) for c in CLAUSE_PUNCT) * 0.275
        secs += text.count(" ") * 0.02 * 1.0
        if self.make_typos.get():
            secs += sum(ch.lower() in NEIGHBORS for ch in text) * 0.03 * (0.5 + 2 * base)
        return secs

    def _paste_text(self):
        try:
            clip = self.root.clipboard_get()
        except tk.TclError:
            self.set_status("Clipboard is empty or doesn't contain text.", "error")
            return
        self.text_box.delete("1.0", "end")
        self.text_box.insert("1.0", clip)
        self.text_box.focus_set()

    def _clear_text(self):
        self.text_box.delete("1.0", "end")
        self.text_box.focus_set()

    # --- hotkey callbacks (run on keyboard's listener thread) ---

    def toggle_start_stop(self):
        if self.typing:
            self._stop_event.set()
            return
        # Remember whatever window is focused right now — the one the
        # user clicked into before pressing the hotkey — and keep it in
        # focus for the whole typing session.
        hwnd = GetForegroundWindow()
        if hwnd == self.own_hwnd:
            self.set_status("Click into the target app's text field first, "
                            f"then press {self._hotkey_label()}", "waiting")
            return
        # Mark as typing before the thread starts so a quick double press
        # can't launch two workers typing over each other.
        self.typing = True
        self.paused = False
        self._stop_event.clear()
        self.target_hwnd = hwnd
        threading.Thread(target=self._type_worker, daemon=True).start()

    def toggle_pause(self):
        if self.typing:
            self.paused = not self.paused

    def _apply_live_speed(self):
        try:
            self._base_delay = max(float(self.char_delay.get()), 10) / 1000
        except (tk.TclError, ValueError):
            pass

    # --- pause/stop-aware waiting ---

    def _wait(self, seconds: float) -> bool:
        """Sleep in slices, honoring pause and stop. Returns False if stopped.

        ``_wait(0)`` is a checkpoint: it returns only once the target window
        has focus and typing isn't paused, so it's safe to send a key.
        """
        end = time.monotonic() + seconds
        while True:
            if self._stop_event.is_set():
                return False
            self._ensure_target_focused()
            if self.paused:
                if not self._wait_while_paused():
                    return False
                continue
            remaining = end - time.monotonic()
            if remaining <= 0:
                return True
            time.sleep(min(remaining, 0.05))

    def _wait_while_paused(self) -> bool:
        if self._auto_paused:
            msg = "Paused while you adjust settings — press Esc to resume"
        else:
            msg = f"Paused — press Esc to resume, {self._hotkey_label()} to stop"
        self.set_status(msg, "paused", self._progress)
        # Don't hold focus while paused, so the user can actually use other
        # windows; focus is pulled back to the target on resume.
        while self.paused:
            if self._stop_event.is_set():
                return False
            time.sleep(0.05)
        self._auto_paused = False
        self._ensure_target_focused()
        time.sleep(0.15)  # let the focus switch settle before keys go out
        # Focus may have changed while paused; drop stray modifiers.
        self._release_modifiers()
        return True

    @staticmethod
    def _release_modifiers():
        for key in ("ctrl", "shift", "alt"):
            keyboard.release(key)

    def _ensure_target_focused(self):
        """Steal focus back to the window typing started in, if it drifted.

        Exception: if the user clicked into *this* window (e.g. to drag the
        speed slider), pause instead of fighting over focus — otherwise keys
        could land in our own text box.
        """
        hwnd = self.target_hwnd
        if not hwnd or not IsWindow(hwnd):
            return
        fg = GetForegroundWindow()
        if fg == hwnd:
            return
        if fg == self.own_hwnd:
            if self.typing and not self.paused:
                self._auto_paused = True
                self.paused = True
            return
        if not self.paused:
            SetForegroundWindow(hwnd)

    # --- human-like timing ---

    def _char_delay(self, prev_char: str) -> float:
        base = self._base_delay
        delay = random.gauss(base, base * 0.35)
        delay = max(delay, base * 0.3)

        if prev_char == "\n":
            delay += random.uniform(0.4, 0.9)
        elif prev_char in SENTENCE_PUNCT:
            delay += random.uniform(0.3, 0.7)
        elif prev_char in CLAUSE_PUNCT:
            delay += random.uniform(0.15, 0.4)
        elif prev_char == " " and random.random() < 0.02:
            # Occasional "thinking" pause between words.
            delay += random.uniform(0.5, 1.5)
        return delay

    def _send_char(self, ch: str) -> bool:
        """Type one character. Returns False if typing was stopped first."""
        # Checkpoint: target focused and not paused (or wait until it is).
        if not self._wait(0):
            return False
        # Drop any modifier the `keyboard` library thinks is still held
        # before every keystroke — otherwise a stuck shift/ctrl can turn
        # Enter into Ctrl+Enter, or a letter like N into a browser hotkey
        # (Ctrl+N), instead of being typed.
        self._release_modifiers()

        if ch == "\n":
            keyboard.send("enter")
        elif ch == "\t":
            keyboard.send("tab")
        elif "A" <= ch <= "Z":
            self._send_shifted(ch.lower())
        elif ch in SHIFT_SYMBOLS:
            self._send_shifted(SHIFT_SYMBOLS[ch])
        else:
            self._send_key(ch)
        return True

    @staticmethod
    def _scan_code(key: str):
        try:
            codes = keyboard.key_to_scan_codes(key)
        except ValueError:
            return None
        # Some characters map to several physical keys, and the numpad one
        # can come first (e.g. "-" -> numpad minus, "/" -> numpad divide).
        # Numpad keys ignore Shift, so "_" would come out as "-" and "?" as
        # "/". Prefer a main-keyboard key whenever one exists.
        for code in codes:
            vk = _scan_code_to_vk(code)
            if code < 0xE000 and not (NUMPAD_VK_FIRST <= vk <= NUMPAD_VK_LAST):
                return code
        return codes[0] if codes else None

    def _send_key(self, key: str):
        # Press/release a raw scan code directly rather than going through
        # keyboard.send()'s hotkey-string parser: that parser splits on
        # both "+" (key separator) and "," (step separator), so any base
        # key that happens to be a comma or plus (e.g. "<" -> ",") gets
        # silently mangled instead of typed.
        code = self._scan_code(key)
        if code is None:
            # No physical key for this character on the current keyboard
            # layout (e.g. non-ASCII, emoji) — inject it directly.
            keyboard.write(key)
            return
        keyboard.press(code)
        keyboard.release(code)

    def _send_shifted(self, base: str):
        code = self._scan_code(base)
        if code is None:
            keyboard.write(base)
            return
        keyboard.press("shift")
        keyboard.press(code)
        keyboard.release(code)
        keyboard.release("shift")

    def _maybe_typo(self, ch: str) -> bool:
        """Type a wrong neighbor key, notice it, backspace, retype. Returns False if stopped."""
        wrong = random.choice(NEIGHBORS[ch.lower()])
        if ch.isupper():
            wrong = wrong.upper()
        if not self._send_char(wrong):
            return False
        if not self._wait(random.uniform(0.15, 0.45)):  # time to "notice" the typo
            return False
        if not self._wait(0):  # checkpoint, as in _send_char
            return False
        keyboard.send("backspace")
        return self._wait(random.uniform(0.08, 0.2))

    # --- typing worker ---

    def _type_worker(self):
        try:
            self._type_text()
        except Exception as exc:  # never leave the tool stuck in "typing"
            self._release_modifiers()
            self._finish(f"Error: {exc}", "error")

    def _read_settings(self):
        """Snapshot the UI settings; returns the start delay, or None if invalid."""
        try:
            char_ms = float(self.char_delay.get())
            start_delay = float(self.start_delay.get())
        except (tk.TclError, ValueError):
            return None
        self._base_delay = max(char_ms, 10) / 1000
        self._typos = bool(self.make_typos.get())
        return max(start_delay, 0)

    def _type_text(self):
        text = self.text_box.get("1.0", "end-1c")
        if not text.strip():
            self._finish("Nothing to type — paste some text first.", "error")
            return

        delay = self._read_settings()
        if delay is None:
            self._finish("Invalid speed or start delay.", "error")
            return
        if delay:
            for remaining in range(int(delay * 10), 0, -1):
                self.set_status(f"Starting in {remaining / 10:.1f} s…  "
                                f"(press {self._hotkey_label()} to cancel)", "waiting")
                if not self._wait(0.1):
                    self._finish("Cancelled.")
                    return

        self._release_modifiers()

        total = len(text)
        prev = ""
        for i, ch in enumerate(text, 1):
            if not self._wait(self._char_delay(prev)):
                self._finish(f"Stopped at character {i - 1}/{total}.")
                return

            if (self._typos and ch.lower() in NEIGHBORS
                    and random.random() < 0.03):
                if not self._maybe_typo(ch):
                    self._finish(f"Stopped at character {i - 1}/{total}.")
                    return

            if not self._send_char(ch):
                self._finish(f"Stopped at character {i - 1}/{total}.")
                return
            prev = ch
            self._progress = i / total
            self.set_status(f"Typing…  {i:,} / {total:,}  ·  {self._progress:.0%}"
                            f"  ·  {self._base_delay * 1000:.0f} ms/char",
                            "typing", self._progress)

        self._finish(f"Done — typed {total:,} characters.", "done", 1.0)

    def _finish(self, message: str, state: str = "ready", progress=None):
        self.typing = False
        self.paused = False
        self._auto_paused = False
        self._stop_event.clear()
        self.target_hwnd = None
        self._progress = None
        self.set_status(message, state, progress)

    def set_status(self, message: str, state: str = None, progress=None):
        """Thread-safe: may be called from the hotkey or typing threads."""
        try:
            self.root.after(0, self.status_bar.set, message, state, progress)
        except (tk.TclError, RuntimeError):
            pass  # window already closed

    def on_close(self):
        self._stop_event.set()
        keyboard.unhook_all()
        self.root.destroy()


def main():
    ui.enable_dpi_awareness()
    ui.set_app_id("Wonuva.Typer")
    root = tk.Tk()
    WonuvaTyper(root)
    root.mainloop()


if __name__ == "__main__":
    main()
