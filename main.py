"""Auto Typing Tool.

Paste text into the window, click into any input field in any application,
then press Ctrl+Shift+` to start typing. Press Esc to pause/resume,
Ctrl+Shift+` again to stop.

Typing is humanized: keystroke timing is randomized, punctuation and
newlines get natural pauses, and (optionally) occasional typos are made
and corrected with backspace.
"""

import random
import threading
import time
import tkinter as tk
from tkinter import ttk, scrolledtext

import keyboard

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


class AutoTyper:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.typing = False
        self.paused = False
        self._stop_event = threading.Event()

        root.title("Auto Typing Tool")
        root.geometry("560x520")
        root.attributes("-topmost", True)

        main = ttk.Frame(root, padding=10)
        main.pack(fill="both", expand=True)

        ttk.Label(main, text="Text to type:").pack(anchor="w")
        self.text_box = scrolledtext.ScrolledText(main, wrap="word", height=14)
        self.text_box.pack(fill="both", expand=True, pady=(4, 10))

        opts = ttk.Frame(main)
        opts.pack(fill="x", pady=(0, 10))

        ttk.Label(opts, text="Avg speed (ms/char):").grid(row=0, column=0, sticky="w")
        self.char_delay = tk.IntVar(value=100)
        ttk.Spinbox(opts, from_=10, to=1000, increment=10,
                    textvariable=self.char_delay, width=8).grid(row=0, column=1, padx=(6, 20))

        ttk.Label(opts, text="Start delay (s):").grid(row=0, column=2, sticky="w")
        self.start_delay = tk.DoubleVar(value=1.0)
        ttk.Spinbox(opts, from_=0, to=10, increment=0.5,
                    textvariable=self.start_delay, width=8).grid(row=0, column=3, padx=6)

        self.make_typos = tk.BooleanVar(value=True)
        ttk.Checkbutton(opts, text="Simulate typos (typed and corrected)",
                        variable=self.make_typos).grid(row=1, column=0, columnspan=4,
                                                       sticky="w", pady=(8, 0))

        self.status = tk.StringVar(
            value=f"Ready — focus an input field and press {HOTKEY.upper()}")
        status_bar = ttk.Label(main, textvariable=self.status, relief="sunken",
                               anchor="w", padding=(6, 4))
        status_bar.pack(fill="x", side="bottom")

        keyboard.add_hotkey(HOTKEY, self.toggle_start_stop)
        keyboard.add_hotkey(PAUSE_KEY, self.toggle_pause)

        root.protocol("WM_DELETE_WINDOW", self.on_close)

    # --- hotkey callbacks (run on keyboard's listener thread) ---

    def toggle_start_stop(self):
        if self.typing:
            self._stop_event.set()
        else:
            threading.Thread(target=self._type_worker, daemon=True).start()

    def toggle_pause(self):
        if self.typing:
            self.paused = not self.paused

    # --- pause/stop-aware waiting ---

    def _wait(self, seconds: float) -> bool:
        """Sleep in slices, honoring pause and stop. Returns False if stopped."""
        end = time.monotonic() + seconds
        while True:
            if self._stop_event.is_set():
                return False
            if self.paused and not self._wait_while_paused():
                return False
            remaining = end - time.monotonic()
            if remaining <= 0:
                return True
            time.sleep(min(remaining, 0.05))

    def _wait_while_paused(self) -> bool:
        self.set_status(f"Paused — press {PAUSE_KEY.upper()} to resume, "
                        f"{HOTKEY.upper()} to stop")
        while self.paused:
            if self._stop_event.is_set():
                return False
            time.sleep(0.05)
        # Focus may have changed while paused; drop stray modifiers.
        self._release_modifiers()
        return True

    @staticmethod
    def _release_modifiers():
        for key in ("ctrl", "shift", "alt"):
            keyboard.release(key)

    # --- human-like timing ---

    def _char_delay(self, prev_char: str) -> float:
        base = max(self.char_delay.get(), 10) / 1000
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

    def _send_char(self, ch: str):
        if ch == "\n":
            keyboard.send("enter")
        elif ch == "\t":
            keyboard.send("tab")
        else:
            # exact=False sends real key events (scan codes), which remote
            # desktops (Chrome Remote Desktop, VMs, games) can forward —
            # unlike the default Windows unicode-packet injection.
            keyboard.write(ch, exact=False)

    def _maybe_typo(self, ch: str) -> bool:
        """Type a wrong neighbor key, notice it, backspace, retype. Returns False if stopped."""
        wrong = random.choice(NEIGHBORS[ch.lower()])
        if ch.isupper():
            wrong = wrong.upper()
        keyboard.write(wrong, exact=False)
        if not self._wait(random.uniform(0.15, 0.45)):  # time to "notice" the typo
            return False
        keyboard.send("backspace")
        return self._wait(random.uniform(0.08, 0.2))

    # --- typing worker ---

    def _type_worker(self):
        text = self.text_box.get("1.0", "end-1c")
        if not text.strip():
            self.set_status("Nothing to type — paste some text first.")
            return

        self.typing = True
        self.paused = False
        self._stop_event.clear()

        delay = max(self.start_delay.get(), 0)
        if delay:
            for remaining in range(int(delay * 10), 0, -1):
                if not self._wait(0.1):
                    self._finish("Cancelled.")
                    return
                self.set_status(f"Typing starts in {remaining / 10:.1f}s… "
                                f"(press {HOTKEY.upper()} to cancel)")

        self._release_modifiers()

        total = len(text)
        prev = ""
        for i, ch in enumerate(text, 1):
            if not self._wait(self._char_delay(prev)):
                self._finish(f"Stopped at character {i - 1}/{total}.")
                return

            if (self.make_typos.get() and ch.lower() in NEIGHBORS
                    and random.random() < 0.03):
                if not self._maybe_typo(ch):
                    self._finish(f"Stopped at character {i - 1}/{total}.")
                    return

            self._send_char(ch)
            prev = ch
            self.set_status(f"Typing… {i}/{total}  "
                            f"({PAUSE_KEY.upper()}=pause, {HOTKEY.upper()}=stop)")

        self._finish(f"Done — typed {total} characters.")

    def _finish(self, message: str):
        self.typing = False
        self.paused = False
        self._stop_event.clear()
        self.set_status(message)

    def set_status(self, message: str):
        self.root.after(0, self.status.set, message)

    def on_close(self):
        self._stop_event.set()
        keyboard.unhook_all()
        self.root.destroy()


def main():
    root = tk.Tk()
    AutoTyper(root)
    root.mainloop()


if __name__ == "__main__":
    main()
