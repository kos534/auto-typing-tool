# Wonuva Typer

Types text into any input field in any application, triggered by a global hotkey.
Typing is humanized: keystroke timing is randomized, punctuation and newlines get
natural pauses, and it can make occasional typos that it notices and corrects.

## Setup

```
pip install -r requirements.txt
python main.py
```

Or run `run.bat`, or use the standalone `dist\WonuvaTyper.exe` (no Python needed).

## Usage

1. Paste the text you want typed into the app window (or click **Paste**).
2. Click into the target input field in any application (browser, editor, chat, etc.).
3. Press **Ctrl+Shift+`** — after the start delay, typing begins.
4. Press **Esc** to pause; press **Esc** again to resume.
5. Press **Ctrl+Shift+`** again to stop completely.

## Options

- **Typing speed** — slider from *Leisurely* (500 ms/char) to *Swift* (20 ms/char).
  Actual keystrokes vary randomly around this (default 100 ms/char ≈ 120 WPM before
  natural pauses). The text panel shows an estimated total typing time.
- **Start delay** — slider (0–10 s): countdown after the hotkey fires, giving you
  time to make sure the right field is focused.
- **Simulate typos** — occasionally types an adjacent wrong key, pauses as if
  noticing it, backspaces, and retypes the correct character.

Sliders also respond to the mouse wheel and arrow keys.

**Changing speed while typing:** speed changes take effect on the next keystroke.
Either scroll the mouse wheel over the speed slider (typing keeps going), or click
into the Wonuva Typer window — typing pauses automatically so no keys land in the
wrong place — adjust the slider, then press **Esc** to resume.

## Notes

- The app window stays on top so you can watch the status bar while working in other apps.
- Newlines are sent as Enter and tabs as Tab, so multi-line text works in forms and editors.
- Sentence endings, commas, and new lines get longer natural pauses; there are also
  rare longer "thinking" pauses between words.
- To type into applications running as Administrator, run this tool as Administrator
  too (Windows blocks synthetic input to elevated windows otherwise).

## Rebuilding the exe

Run `build.bat`, or:

```
pyinstaller WonuvaTyper.spec
```

The spec bundles `assets/` (logo and `icon.ico`) and embeds the Wonuva version
info from `version_info.txt`.
