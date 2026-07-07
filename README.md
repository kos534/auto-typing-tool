# Auto Typing Tool

Types text into any input field in any application, triggered by a global hotkey.
Typing is humanized: keystroke timing is randomized, punctuation and newlines get
natural pauses, and it can make occasional typos that it notices and corrects.

## Setup

```
pip install -r requirements.txt
python main.py
```

Or run `run.bat`, or use the standalone `dist\AutoTypingTool.exe` (no Python needed).

## Usage

1. Paste the text you want typed into the app window.
2. Click into the target input field in any application (browser, editor, chat, etc.).
3. Press **Ctrl+Shift+`** — after the start delay, typing begins.
4. Press **Esc** to pause; press **Esc** again to resume.
5. Press **Ctrl+Shift+`** again to stop completely.

## Options

- **Avg speed (ms/char)** — average time per character; actual keystrokes vary
  randomly around this (default 100 ms ≈ 120 characters/min).
- **Start delay (s)** — countdown after the hotkey fires, giving you time to make
  sure the right field is focused.
- **Simulate typos** — occasionally types an adjacent wrong key, pauses as if
  noticing it, backspaces, and retypes the correct character.

## Notes

- The app window stays on top so you can watch the status bar while working in other apps.
- Newlines are sent as Enter and tabs as Tab, so multi-line text works in forms and editors.
- Sentence endings, commas, and new lines get longer natural pauses; there are also
  rare longer "thinking" pauses between words.
- To type into applications running as Administrator, run this tool as Administrator
  too (Windows blocks synthetic input to elevated windows otherwise).

## Rebuilding the exe

```
pyinstaller AutoTypingTool.spec
```
