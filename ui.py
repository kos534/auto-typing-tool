"""Wonuva fantasy theme: palette, fonts, sprites and custom widgets.

Tk's canvas draws shapes without anti-aliasing on Windows, so circles,
rounded ends and diagonals come out jagged. Every curved element here is
therefore rendered as an anti-aliased sprite with Pillow: drawn at 4x
("supersampled") and downscaled with a high-quality filter, at the exact
pixel size the current display DPI needs. Text is still drawn by Tk, which
uses ClearType and is already crisp.
"""

import ctypes
import functools
import os
import sys
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

from PIL import Image, ImageDraw, ImageFilter, ImageTk

# --- palette -----------------------------------------------------------------

BG = "#0c0919"          # night sky behind everything
PANEL = "#15102b"       # cards
PANEL_HI = "#1f1840"    # raised elements (buttons, keycaps)
INK = "#0f0b21"         # text area
BORDER = "#33295e"
BORDER_HI = "#5a4a9a"
TRACK = "#2a2150"
GOLD = "#f0c674"
GOLD_HI = "#ffe3a3"
GOLD_DIM = "#7d6a3f"
TEXT = "#ece7ff"
MUTED = "#9a90c6"
FAINT = "#6b6299"

# Sampled from the logo, left to right: blue -> violet -> magenta -> pink -> amber.
GRADIENT = ["#3d7bff", "#7b5cff", "#c74dff", "#ff4f9a", "#ff8a3d"]

STATE_COLORS = {
    "ready": "#5ad1c4",
    "waiting": GOLD,
    "typing": "#c74dff",
    "paused": "#ffb347",
    "done": "#6fe39a",
    "error": "#ff6b7a",
}


def _hex_to_rgb(c):
    return int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)


def _rgba(c, a=255):
    return (*_hex_to_rgb(c), a)


def mix(c1, c2, t):
    a, b = _hex_to_rgb(c1), _hex_to_rgb(c2)
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def gradient_at(t, stops=GRADIENT):
    t = min(max(t, 0.0), 1.0) * (len(stops) - 1)
    i = min(int(t), len(stops) - 2)
    return mix(stops[i], stops[i + 1], t - i)


def resource_path(relative):
    """Path to a bundled file, both from source and inside a PyInstaller exe."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative)


# --- platform polish ---------------------------------------------------------

def enable_dpi_awareness():
    """Must run before Tk() is created, or everything renders blurry on HiDPI."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def set_app_id(app_id):
    """Gives the taskbar our own icon/grouping instead of python.exe's."""
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        pass


def style_title_bar(hwnd, caption=BG, text=TEXT):
    """Dark title bar (Windows 10 1809+) tinted to match the theme (Windows 11)."""
    def colorref(c):
        r, g, b = _hex_to_rgb(c)
        return ctypes.c_int(r | (g << 8) | (b << 16))

    try:
        dwm = ctypes.windll.dwmapi
        dark = ctypes.c_int(1)
        for attr in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (new, old id)
            if dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(dark), 4) == 0:
                break
        dwm.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(colorref(caption)), 4)
        dwm.DwmSetWindowAttribute(hwnd, 36, ctypes.byref(colorref(text)), 4)
        dwm.DwmSetWindowAttribute(hwnd, 34, ctypes.byref(colorref(BORDER)), 4)
    except Exception:
        pass


# --- theme -------------------------------------------------------------------

def _pick(families, *candidates):
    for name in candidates:
        if name in families:
            return name
    return candidates[-1]


class Theme:
    def __init__(self, root: tk.Tk):
        self.scale = max(root.winfo_fpixels("1i") / 96.0, 1.0)
        fams = set(tkfont.families(root))
        display = _pick(fams, "Palatino Linotype", "Book Antiqua", "Constantia",
                        "Georgia", "Times New Roman")
        body = _pick(fams, "Segoe UI Variable Text", "Segoe UI", "Helvetica")
        mono = _pick(fams, "Cascadia Mono", "Consolas", "Courier New")

        self.f_title = tkfont.Font(root, family=display, size=19, weight="bold")
        self.f_brand = tkfont.Font(root, family=display, size=9, weight="bold")
        self.f_section = tkfont.Font(root, family=display, size=10, weight="bold")
        self.f_body = tkfont.Font(root, family=body, size=10)
        self.f_small = tkfont.Font(root, family=body, size=9)
        self.f_value = tkfont.Font(root, family=body, size=10, weight="bold")
        self.f_key = tkfont.Font(root, family=mono, size=9, weight="bold")
        self.f_text = tkfont.Font(root, family=mono, size=11)

        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("Wonuva.Vertical.TScrollbar", troughcolor=INK,
                        background=TRACK, bordercolor=INK, arrowcolor=MUTED,
                        lightcolor=TRACK, darkcolor=TRACK, gripcount=0,
                        arrowsize=self.s(12))
        style.map("Wonuva.Vertical.TScrollbar",
                  background=[("active", BORDER_HI), ("pressed", BORDER_HI)])

    def s(self, px):
        """Scale a 96-DPI pixel size to the current display."""
        return max(1, round(px * self.scale))


# --- sprites -----------------------------------------------------------------
#
# Each function returns a PIL RGBA image at final (device-pixel) size.
# Geometry is given in device pixels; drawing happens at SS times that.

SS = 4  # supersampling factor


def _big(w, h):
    return Image.new("RGBA", (max(1, round(w * SS)), max(1, round(h * SS))), (0, 0, 0, 0))


def _down(img, w, h):
    return img.resize((max(1, round(w)), max(1, round(h))), Image.Resampling.LANCZOS)


def _glow(size, box, color, alpha, blur):
    """A soft blurred ellipse on its own layer (all args in big-pixel units)."""
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).ellipse(box, fill=_rgba(color, alpha))
    return layer.filter(ImageFilter.GaussianBlur(blur))


def _gradient_fill(size, box, mask_draw_fn, t0=0.0, t1=1.0):
    """Horizontal logo gradient across ``box``, clipped by a mask shape."""
    x0, y0, x1, y1 = (round(v) for v in box)
    strip = Image.new("RGBA", (64, 1))
    for i in range(64):
        strip.putpixel((i, 0), _rgba(gradient_at(t0 + (t1 - t0) * i / 63)))
    strip = strip.resize((max(x1 - x0, 1), max(y1 - y0, 1)), Image.Resampling.BILINEAR)
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    layer.paste(strip, (x0, y0))
    mask = Image.new("L", size, 0)
    mask_draw_fn(ImageDraw.Draw(mask))
    out = Image.new("RGBA", size, (0, 0, 0, 0))
    out.paste(layer, (0, 0), mask)
    return out


def sprite_track(w, h, cy, x0, x1, thickness, frac, tick_r):
    """Slider track: rounded groove, gradient fill up to ``frac``, quarter dots."""
    img = _big(w, h)
    d = ImageDraw.Draw(img)
    r = thickness * SS / 2
    Y0, Y1 = cy * SS - r, cy * SS + r
    X0, X1 = x0 * SS, x1 * SS
    d.rounded_rectangle((X0 - r, Y0, X1 + r, Y1), radius=r, fill=_rgba(TRACK))
    fx = X0 + frac * (X1 - X0)
    if frac > 0:
        fill = _gradient_fill(
            img.size, (X0 - r, Y0, X1 + r, Y1 + 1),
            lambda m: m.rounded_rectangle((X0 - r, Y0, fx + r, Y1), radius=r, fill=255))
        img.alpha_composite(fill)
        d = ImageDraw.Draw(img)
    tr = tick_r * SS
    for q in (0.25, 0.5, 0.75):
        tx = X0 + q * (X1 - X0)
        color = _rgba("#ffffff", 150) if tx < fx else _rgba(BORDER_HI)
        d.ellipse((tx - tr, cy * SS - tr, tx + tr, cy * SS + tr), fill=color)
    return _down(img, w, h)


@functools.lru_cache(maxsize=256)
def sprite_thumb(r, pad, inner, active, scale):
    """Gem-like slider handle: soft shadow, gold rim, colored core, highlight."""
    size = 2 * (r + pad)
    img = _big(size, size)
    c = size * SS / 2
    R = r * SS
    if active:
        g = R + 4 * scale * SS
        img.alpha_composite(_glow(img.size, (c - g, c - g, c + g, c + g),
                                  GOLD, 120, 3 * scale * SS))
    sh = 1.5 * scale * SS
    img.alpha_composite(_glow(img.size, (c - R, c - R + sh, c + R, c + R + sh),
                              "#000000", 170, 2 * scale * SS))
    d = ImageDraw.Draw(img)
    d.ellipse((c - R, c - R, c + R, c + R), fill=_rgba(GOLD_HI if active else GOLD))
    rim = 1 * scale * SS
    d.ellipse((c - R, c - R, c + R, c + R), outline=_rgba(GOLD_DIM), width=round(rim))
    Ri = R - 3 * scale * SS
    d.ellipse((c - Ri, c - Ri, c + Ri, c + Ri), fill=_rgba(inner))
    # inner shading: darker lower-right, lighter upper-left, specular dot
    d.ellipse((c - Ri * 0.55, c - Ri * 0.15, c + Ri * 0.95, c + Ri * 0.95),
              fill=_rgba(mix(inner, "#000000", 0.25), 90))
    hl = Ri * 0.38
    hx, hy = c - Ri * 0.35, c - Ri * 0.35
    img.alpha_composite(_glow(img.size, (hx - hl, hy - hl, hx + hl, hy + hl),
                              "#ffffff", 230, 0.6 * scale * SS))
    return _down(img, size, size)


@functools.lru_cache(maxsize=16)
def sprite_toggle(w, h, on, scale):
    img = _big(w, h)
    W, H = w * SS, h * SS
    m = 1 * scale * SS
    box = (m, m, W - m, H - m)
    rad = (H - 2 * m) / 2
    d = ImageDraw.Draw(img)
    if on:
        img.alpha_composite(_gradient_fill(
            img.size, box, lambda mk: mk.rounded_rectangle(box, radius=rad, fill=255),
            0.1, 0.85))
    else:
        d.rounded_rectangle(box, radius=rad, fill=_rgba(TRACK),
                            outline=_rgba(BORDER_HI), width=round(scale * SS))
    kr = rad - 3 * scale * SS
    kx = W - m - rad if on else m + rad
    ky = H / 2
    sh = 1 * scale * SS
    img.alpha_composite(_glow(img.size, (kx - kr, ky - kr + sh, kx + kr, ky + kr + sh),
                              "#000000", 140, 1.5 * scale * SS))
    d = ImageDraw.Draw(img)
    d.ellipse((kx - kr, ky - kr, kx + kr, ky + kr), fill=_rgba("#fff6df" if on else MUTED))
    return _down(img, w, h)


@functools.lru_cache(maxsize=64)
def sprite_round_rect(w, h, radius, fill, outline, border, scale, shadow=None):
    """Rounded box; ``shadow`` draws a solid 'key travel' ledge underneath."""
    img = _big(w, h)
    d = ImageDraw.Draw(img)
    W, H, R = w * SS, h * SS, radius * SS
    bw = max(1, round(border * scale * SS))
    if shadow:
        ledge = 3 * scale * SS
        d.rounded_rectangle((0, ledge, W - 1, H - 1), radius=R, fill=_rgba(shadow))
        d.rounded_rectangle((0, 0, W - 1, H - 1 - ledge), radius=R, fill=_rgba(fill),
                            outline=_rgba(outline), width=bw)
    else:
        d.rounded_rectangle((0, 0, W - 1, H - 1), radius=R, fill=_rgba(fill),
                            outline=_rgba(outline), width=bw)
    return _down(img, w, h)


@functools.lru_cache(maxsize=16)
def sprite_orb(r, color, scale):
    pad = r
    size = 2 * (r + pad)
    img = _big(size, size)
    c, R = size * SS / 2, r * SS
    g = R + 3 * scale * SS
    img.alpha_composite(_glow(img.size, (c - g, c - g, c + g, c + g), color, 110,
                              3 * scale * SS))
    d = ImageDraw.Draw(img)
    d.ellipse((c - R, c - R, c + R, c + R), fill=_rgba(color))
    hl = R * 0.45
    img.alpha_composite(_glow(img.size, (c - R * 0.3 - hl, c - R * 0.3 - hl,
                                         c - R * 0.3 + hl, c - R * 0.3 + hl),
                              "#ffffff", 170, 0.8 * scale * SS))
    return _down(img, size, size)


@functools.lru_cache(maxsize=16)
def sprite_glyph(kind, size, color, scale):
    """Section ornaments: 'star' (four-point sparkle) or 'diamond' (framed gem)."""
    img = _big(size, size)
    c, R = size * SS / 2, size * SS * 0.46
    img.alpha_composite(_glow(img.size, (c - R * 0.7, c - R * 0.7, c + R * 0.7, c + R * 0.7),
                              color, 90, 2 * scale * SS))
    d = ImageDraw.Draw(img)
    if kind == "star":
        ri = R * 0.26
        pts = []
        for i in range(8):
            rr = R if i % 2 == 0 else ri
            # points at 0/90/180/270 degrees, waist at the diagonals
            dx, dy = [(0, -1), (0.707, -0.707), (1, 0), (0.707, 0.707),
                      (0, 1), (-0.707, 0.707), (-1, 0), (-0.707, -0.707)][i]
            pts.append((c + dx * rr, c + dy * rr))
        d.polygon(pts, fill=_rgba(color))
    else:
        o = R * 0.95
        d.polygon([(c, c - o), (c + o, c), (c, c + o), (c - o, c)],
                  outline=_rgba(color), width=round(1.3 * scale * SS))
        i = R * 0.45
        d.polygon([(c, c - i), (c + i, c), (c, c + i), (c - i, c)], fill=_rgba(color))
    return _down(img, size, size)


@functools.lru_cache(maxsize=8)
def sprite_dot(r, color, alpha, scale):
    size = 2 * r + 4
    img = _big(size, size)
    c, R = size * SS / 2, r * SS
    img.alpha_composite(_glow(img.size, (c - R * 2, c - R * 2, c + R * 2, c + R * 2),
                              color, alpha // 3, R))
    ImageDraw.Draw(img).ellipse((c - R, c - R, c + R, c + R), fill=_rgba(color, alpha))
    return _down(img, size, size)


class _SpriteCanvas(tk.Canvas):
    """Canvas that keeps references to its PhotoImages (Tk drops them otherwise)."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._photos = []

    def clear(self):
        self.delete("all")
        self._photos = []

    def sprite(self, pil_image, x, y, anchor="center"):
        photo = ImageTk.PhotoImage(pil_image, master=self)
        self._photos.append(photo)
        return self.create_image(x, y, image=photo, anchor=anchor)


def glyph_photo(master, theme, kind, color=GOLD):
    return ImageTk.PhotoImage(
        sprite_glyph(kind, theme.s(14), color, theme.scale), master=master)


# --- drawing helpers ---------------------------------------------------------

def hgradient(canvas, x0, y0, x1, y1, stops=GRADIENT, tags=None, step=1):
    """Straight gradient bar (vertical 1px lines don't need anti-aliasing)."""
    span = max(x1 - x0, 1)
    x = x0
    while x < x1:
        canvas.create_line(x, y0, x, y1, fill=gradient_at((x - x0) / span, stops),
                           width=step + 1, tags=tags)
        x += step


# --- widgets -----------------------------------------------------------------

class Header(_SpriteCanvas):
    """Logo, brand and title over a soft night-sky glow, with a rune divider."""

    def __init__(self, master, theme, logo, title, tagline):
        self.t = theme
        super().__init__(master, height=theme.s(92), bg=BG, highlightthickness=0, bd=0)
        self.logo, self.title, self.tagline = logo, title, tagline
        self.bind("<Configure>", lambda e: self._draw())

    def _draw(self):
        t, s = self.t, self.t.s
        w, h = self.winfo_width(), self.winfo_height()
        self.clear()
        for fx, fy, big in ((.62, .18, 0), (.71, .55, 1), (.83, .3, 0), (.9, .7, 0),
                            (.95, .2, 1), (.55, .7, 0), (.77, .12, 0)):
            self.sprite(sprite_dot(s(1.4 if big else 1), "#b9a8ff", 200 if big else 140,
                                   t.scale), w * fx, h * fy)

        pad = s(20)
        self.create_image(pad, h / 2 - s(4), image=self.logo, anchor="w")
        tx = pad + self.logo.width() + s(14)
        self.create_text(tx, h / 2 - s(15), text=self.title, anchor="w",
                         font=t.f_title, fill=TEXT)
        self.create_text(tx, h / 2 + s(11), text=self.tagline, anchor="w",
                         font=t.f_small, fill=MUTED)

        y = h - s(5)
        hgradient(self, pad, y, w - pad, y + s(1), step=2)
        cx, gs = w / 2, s(16)
        self.create_rectangle(cx - gs / 2 - s(4), y - s(2), cx + gs / 2 + s(4), y + s(2),
                              fill=BG, outline="")
        self.sprite(sprite_glyph("diamond", gs, GOLD, t.scale), cx, y)


class Card(tk.Frame):
    """Bordered panel with an ornament and a small-caps section heading."""

    def __init__(self, master, theme, title, glyph="star"):
        super().__init__(master, bg=PANEL, highlightbackground=BORDER,
                         highlightcolor=BORDER, highlightthickness=1)
        head = tk.Frame(self, bg=PANEL)
        head.pack(fill="x", padx=theme.s(14), pady=(theme.s(10), theme.s(6)))
        self._glyph = glyph_photo(self, theme, glyph)
        tk.Label(head, image=self._glyph, bg=PANEL).pack(side="left")
        tk.Label(head, text=" " + " ".join(title.upper()), bg=PANEL, fg=GOLD,
                 font=theme.f_section).pack(side="left", padx=(theme.s(4), 0))
        self.head = head
        self.body = tk.Frame(self, bg=PANEL)
        self.body.pack(fill="both", expand=True, padx=theme.s(14), pady=(0, theme.s(12)))


class Slider(_SpriteCanvas):
    """Gradient-track slider with a gem thumb.

    ``invert=True`` puts the low value on the right — used for delay-per-char
    so that dragging right means *faster*, as people expect.
    """

    def __init__(self, master, theme, variable, from_, to, step,
                 invert=False, labels=None, bg=PANEL):
        self.t = theme
        self.var, self.lo, self.hi, self.step = variable, from_, to, step
        self.invert, self.labels = invert, labels
        self.hover = self.drag = False
        height = theme.s(50 if labels else 34)
        super().__init__(master, height=height, bg=bg, highlightthickness=0,
                         bd=0, takefocus=1, cursor="hand2")
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Button-1>", self._press)
        self.bind("<B1-Motion>", self._move)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.bind("<MouseWheel>", self._wheel)
        self.bind("<FocusIn>", lambda e: self._draw())
        self.bind("<FocusOut>", lambda e: self._draw())
        for key, d in (("<Left>", -1), ("<Down>", -1), ("<Right>", 1), ("<Up>", 1)):
            self.bind(key, lambda e, d=d: self._nudge(d))
        variable.trace_add("write", lambda *_: self._draw())

    def _pad(self):
        return self.t.s(16)

    def _frac(self, v):
        f = (v - self.lo) / (self.hi - self.lo)
        return 1 - f if self.invert else f

    def _value_from_x(self, x):
        pad, w = self._pad(), self.winfo_width()
        f = min(max((x - pad) / max(w - 2 * pad, 1), 0), 1)
        if self.invert:
            f = 1 - f
        v = self.lo + f * (self.hi - self.lo)
        return round(round(v / self.step) * self.step, 4)

    def _set(self, v):
        v = min(max(v, self.lo), self.hi)
        if self.var.get() != v:
            self.var.set(v)

    def _press(self, e):
        self.focus_set()
        self.drag = True
        self._set(self._value_from_x(e.x))

    def _move(self, e):
        if self.drag:
            self._set(self._value_from_x(e.x))

    def _release(self, e):
        self.drag = False
        self._draw()

    def _set_hover(self, on):
        self.hover = on
        self._draw()

    def _nudge(self, direction):
        if self.invert:
            direction = -direction
        self._set(round(self.var.get() + direction * self.step, 4))
        return "break"

    def _wheel(self, e):
        self._nudge(1 if e.delta > 0 else -1)

    def _draw(self):
        t, s = self.t, self.t.s
        w, h = self.winfo_width(), self.winfo_height()
        if w <= 1:
            return
        self.clear()
        pad, cy = self._pad(), s(16)
        x0, x1 = pad, w - pad
        try:
            f = self._frac(float(self.var.get()))
        except (tk.TclError, ValueError):
            f = 0
        x = x0 + f * (x1 - x0)

        self.sprite(sprite_track(w, cy * 2, cy, x0, x1, s(6), f, s(1.3) * 1.0),
                    0, 0, anchor="nw")
        active = self.hover or self.drag or self.focus_get() is self
        self.sprite(sprite_thumb(s(9), s(6), gradient_at(f), active, t.scale), x, cy)

        if self.labels:
            left, right = self.labels
            ly = cy + s(20)
            self.create_text(x0 - s(4), ly, text=left, anchor="w",
                             font=t.f_small, fill=FAINT)
            self.create_text(x1 + s(4), ly, text=right, anchor="e",
                             font=t.f_small, fill=FAINT)


class Toggle(_SpriteCanvas):
    """Pill switch bound to a BooleanVar."""

    def __init__(self, master, theme, variable, bg=PANEL):
        self.t, self.var = theme, variable
        super().__init__(master, width=theme.s(46), height=theme.s(26), bg=bg,
                         highlightthickness=0, bd=0, cursor="hand2", takefocus=1)
        self.bind("<Button-1>", self._toggle)
        self.bind("<space>", self._toggle)
        self.bind("<Configure>", lambda e: self._draw())
        variable.trace_add("write", lambda *_: self._draw())

    def _toggle(self, e=None):
        self.var.set(not self.var.get())

    def _draw(self):
        self.clear()
        w, h = self.winfo_width(), self.winfo_height()
        if w <= 1:
            return
        self.sprite(sprite_toggle(w, h, bool(self.var.get()), self.t.scale), 0, 0,
                    anchor="nw")


class Button(_SpriteCanvas):
    """Rounded button with a gold rim on hover."""

    def __init__(self, master, theme, text, command, icon=None, bg=PANEL):
        self.t, self.command = theme, command
        self.hover = self.down = False
        self.label = f"{icon}  {text}" if icon else text
        width = theme.f_body.measure(self.label) + theme.s(28)
        super().__init__(master, width=width, height=theme.s(30), bg=bg,
                         highlightthickness=0, bd=0, cursor="hand2")
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Enter>", lambda e: self._state(hover=True))
        self.bind("<Leave>", lambda e: self._state(hover=False, down=False))
        self.bind("<Button-1>", lambda e: self._state(down=True))
        self.bind("<ButtonRelease-1>", self._click)

    def _state(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)
        self._draw()

    def _click(self, e):
        fire = self.down and self.hover
        self._state(down=False)
        if fire:
            self.command()

    def _draw(self):
        t = self.t
        w, h = self.winfo_width(), self.winfo_height()
        if w <= 1:
            return
        self.clear()
        fill = mix(PANEL_HI, BORDER, 0.5) if self.down else PANEL_HI
        self.sprite(sprite_round_rect(w, h, t.s(8), fill,
                                      GOLD if self.hover else BORDER_HI, 1, t.scale),
                    0, 0, anchor="nw")
        self.create_text(w / 2, h / 2, text=self.label, font=t.f_body,
                         fill=GOLD_HI if self.hover else TEXT)


class Keycap(_SpriteCanvas):
    """A small drawn key, e.g. [Ctrl] [Shift] [`]."""

    def __init__(self, master, theme, text, bg=PANEL):
        self.t, self.text = theme, text
        w = theme.f_key.measure(text) + theme.s(16)
        super().__init__(master, width=max(w, theme.s(26)), height=theme.s(26),
                         bg=bg, highlightthickness=0, bd=0)
        self.bind("<Configure>", lambda e: self._draw())

    def _draw(self):
        t, s = self.t, self.t.s
        w, h = self.winfo_width(), self.winfo_height()
        if w <= 1:
            return
        self.clear()
        self.sprite(sprite_round_rect(w, h, s(5), PANEL_HI, BORDER_HI, 1, t.scale,
                                      shadow=BORDER), 0, 0, anchor="nw")
        self.create_text(w / 2, (h - s(3)) / 2, text=self.text, font=t.f_key,
                         fill=GOLD_HI)


class StatusBar(_SpriteCanvas):
    """State orb, message and a gradient progress line."""

    def __init__(self, master, theme):
        self.t = theme
        self.message, self.state, self.progress = "", "ready", None
        super().__init__(master, height=theme.s(40), bg=PANEL,
                         highlightthickness=1, highlightbackground=BORDER, bd=0)
        self.bind("<Configure>", lambda e: self._draw())

    def set(self, message, state=None, progress=None):
        self.message = message
        if state:
            self.state = state
        self.progress = progress
        self._draw()

    def _draw(self):
        t, s = self.t, self.t.s
        w, h = self.winfo_width(), self.winfo_height()
        if w <= 1:
            return
        self.clear()
        cx, cy = s(18), h / 2 - s(1)
        self.sprite(sprite_orb(s(5), STATE_COLORS.get(self.state, MUTED), t.scale), cx, cy)
        self.create_text(cx + s(16), cy, text=self.message, anchor="w",
                         font=t.f_body, fill=TEXT)
        if self.progress is not None:
            y = h - s(3)
            self.create_line(0, y, w, y, fill=TRACK, width=s(3))
            px = w * min(max(self.progress, 0), 1)
            if px > 0:
                hgradient(self, 0, y - s(1), px, y + s(1), step=3)
