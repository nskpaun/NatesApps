"""Screen content for the renders: one 5120 x 1440 canvas spanning both panels (u 0..0.5 left,
0.5..1 right, like an OS spanning two displays), with the light band in its bottom rows.

Rows from the bottom of the canvas (pixel pitch 0.2331 mm):
  0 .. BAND_ROWS          light band (12 mm), drawn by `band_colors(mode)`
  BAND_ROWS .. HIDDEN     inside the reflector, held black
  above                   the desktop (RoseOS-style concept UI)
"""
from __future__ import annotations

import math
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 5120, 1440
PITCH = 596.7 / 2560
BAND_ROWS = round(12.0 / PITCH)          # 51
HIDDEN_ROWS = round(26.4 / PITCH)        # reflector top edge sits 26.4 mm above the active area's bottom
FONT_DIR = "/usr/share/fonts/opentype/inter"


def font(size, weight="Regular"):
    try:
        return ImageFont.truetype(os.path.join(FONT_DIR, f"Inter-{weight}.otf"), size)
    except OSError:
        return ImageFont.load_default()


# ------------------------------------------------------------------ band patterns
def band_colors(mode: str, t: float = 0.0) -> np.ndarray:
    """(W, 3) linear RGB 0..1 for each band column. x is mm along the station, seam at 0."""
    u = (np.arange(W) + 0.5) / W
    x = (u - 0.5) * 2 * (596.7 + 7)
    if mode == "off":
        return np.zeros((W, 3))
    if mode == "concept":   # amber -> warm white -> magenta, with two glows (the concept render)
        s = np.clip((x + 600) / 1200, 0, 1)[:, None]
        amber = np.array([1.0, 0.36, 0.05]); white = np.array([1.0, 0.78, 0.55]); mag = np.array([0.95, 0.06, 0.32])
        c = np.where(s < 0.42, amber + (white - amber) * (s / 0.42), white + (mag - white) * ((s - 0.42) / 0.58))
        g = 0.30 + 0.70 * np.exp(-((x + 140) / 230) ** 2) + 0.55 * np.exp(-((x - 330) / 170) ** 2)
        return c * np.clip(g, 0, 1)[:, None]
    if mode == "bass":      # one slow, broad swell (low notes), warm
        g = np.exp(-((x + 180) / 300) ** 2)
        return np.array([1.0, 0.42, 0.10])[None] * g[:, None]
    if mode == "treble":    # delicate highlights (high notes) over a dim rose bed
        bed = 0.12 * np.array([0.9, 0.12, 0.3])[None] * np.ones((W, 1))
        hi = np.zeros(W)
        for x0, a in ((-420, 1.0), (-130, 0.8), (90, 1.0), (360, 0.9), (520, 0.6)):
            hi += a * np.exp(-((x - x0) / 28) ** 2)
        return bed + np.clip(hi, 0, 1)[:, None] * np.array([1.0, 0.85, 0.9])[None]
    if mode == "dock":      # the docking sweep, caught mid-way, travelling right
        x0 = -600 + 1200 * t
        g = np.exp(-((x - x0) / 90) ** 2) + 0.35 * np.exp(-((x - x0 + 160) / 200) ** 2) * (x < x0)
        return np.clip(g, 0, 1)[:, None] * np.array([1.0, 0.55, 0.2])[None]
    if mode == "white":
        return np.ones((W, 3))
    raise ValueError(mode)


# ------------------------------------------------------------------ desktop
ROSE = (196, 54, 92)
ROSE_DK = (136, 30, 58)
INK = (34, 30, 33)
INK2 = (96, 90, 95)
PAPER = (246, 243, 242)
DARK = (34, 31, 34)
DARK2 = (46, 42, 46)
LINE = (66, 61, 66)


def rounded(d, box, r, fill, outline=None, width=1):
    d.rounded_rectangle(box, r, fill=fill, outline=outline, width=width)


def checkbox(d, x, y, done, s=34):
    if done:
        rounded(d, (x, y, x + s, y + s), 7, fill=ROSE_DK)
        d.line((x + 8, y + 18, x + 15, y + 25, x + 27, y + 10), fill=(255, 255, 255), width=4)
    else:
        rounded(d, (x, y, x + s, y + s), 7, fill=None, outline=(170, 165, 168), width=3)


def window_chrome(d, box, title, dark):
    x0, y0, x1, y1 = box
    rounded(d, box, 26, fill=DARK if dark else PAPER, outline=LINE if dark else (220, 214, 214), width=2)
    for i, c in enumerate(((236, 95, 87), (243, 190, 75), (95, 196, 92))):
        d.ellipse((x0 + 34 + i * 40, y0 + 34, x0 + 58 + i * 40, y0 + 58), fill=c)
    d.text((x0 + 190, y0 + 28), title, font=font(30, "SemiBold"), fill=(230, 226, 228) if dark else INK)


def desktop() -> Image.Image:
    img = Image.new("RGB", (W, H), (22, 18, 20))
    # wallpaper: soft rose/amber dusk gradient, very dark
    yy, xx = np.mgrid[0:H, 0:W]
    g = (np.exp(-(((xx - 3900) / 1500) ** 2 + ((yy - 1200) / 700) ** 2)) * np.array([60, 18, 30])[:, None, None]
         + np.exp(-(((xx - 900) / 1300) ** 2 + ((yy - 1300) / 600) ** 2)) * np.array([55, 30, 12])[:, None, None])
    base = np.stack([np.full((H, W), 20), np.full((H, W), 17), np.full((H, W), 20)])
    img = Image.fromarray(np.clip(base + g, 0, 255).transpose(1, 2, 0).astype(np.uint8))
    d = ImageDraw.Draw(img)

    # menu bars (one per display)
    for p0 in (0, 2560):
        d.rectangle((p0, 0, p0 + 2560, 64), fill=(14, 12, 14))
        if p0 == 0:
            d.ellipse((34, 16, 66, 48), fill=ROSE)
            d.text((86, 14), "RoseOS", font=font(30, "SemiBold"), fill=(240, 236, 238))
            x = 240
            for m in ("File", "Edit", "View", "Go", "Window", "Help"):
                d.text((x, 15), m, font=font(28), fill=(205, 200, 203))
                x += d.textlength(m, font=font(28)) + 48
        else:
            d.text((p0 + 2560 - 420, 15), "Tue Jan 28   10:24 AM", font=font(28), fill=(215, 210, 213))

    # -- left display: Studio notes + Today board
    nb = (60, 110, 1150, 1180)
    window_chrome(d, nb, "Studio notes", dark=False)
    dd = d
    dd.text((nb[0] + 70, nb[1] + 130), "Studio notes", font=font(64, "Bold"), fill=INK)
    dd.text((nb[0] + 70, nb[1] + 225), "Direction for the Q1 release: a focused, refined update", font=font(30), fill=INK2)
    dd.text((nb[0] + 70, nb[1] + 265), "that improves everyday flow.", font=font(30), fill=INK2)
    items = (("Finalize interaction specs", True), ("Review prototype with design", True),
             ("Update asset list and handoff", False), ("Prepare release notes (draft)", False))
    for i, (t, done) in enumerate(items):
        y = nb[1] + 345 + i * 62
        checkbox(dd, nb[0] + 70, y, done)
        dd.text((nb[0] + 130, y - 2), t, font=font(32), fill=INK)
    dd.line((nb[0] + 70, nb[1] + 620, nb[2] - 70, nb[1] + 620), fill=(220, 214, 214), width=2)
    dd.text((nb[0] + 70, nb[1] + 660), "Key points", font=font(38, "Bold"), fill=INK)
    for i, t in enumerate(("Keep the experience clean, fast, and consistent.",
                           "Validate changes with a small user group this week.",
                           "Aim for release candidate by Feb 7.")):
        y = nb[1] + 735 + i * 56
        dd.ellipse((nb[0] + 78, y + 14, nb[0] + 90, y + 26), fill=ROSE_DK)
        dd.text((nb[0] + 110, y), t, font=font(30), fill=INK)

    kb = (1210, 110, 2500, 1180)
    window_chrome(d, kb, "Project / Today", dark=True)
    d.text((kb[0] + 60, kb[1] + 120), "Today", font=font(66, "Bold"), fill=(244, 240, 242))
    d.text((kb[0] + 60, kb[1] + 205), "Work in progress · Q1 release", font=font(30), fill=(185, 180, 183))
    rounded(d, (kb[2] - 280, kb[1] + 125, kb[2] - 50, kb[1] + 195), 30, fill=ROSE_DK)
    d.text((kb[2] - 245, kb[1] + 140), "+  Add card", font=font(30, "SemiBold"), fill=(255, 240, 244))
    cols = (("To do", (150, 145, 148), ("Polish onboarding copy", "Update design system", "Plan beta feedback")),
            ("In progress", ROSE, ("Refine window layout", "Implement Ribbon control")),
            ("Done", (95, 196, 92), ("Confirm scope", "Ship prototype v2", "Review with team", "Update project brief")))
    cw = (kb[2] - kb[0] - 120 - 40) // 3
    for ci, (name, dot, cards) in enumerate(cols):
        cx = kb[0] + 60 + ci * (cw + 20)
        rounded(d, (cx, kb[1] + 280, cx + cw, kb[3] - 50), 18, fill=DARK2)
        d.ellipse((cx + 26, kb[1] + 310, cx + 44, kb[1] + 328), fill=dot)
        d.text((cx + 60, kb[1] + 300), f"{name}   {len(cards)}", font=font(28, "SemiBold"), fill=(225, 220, 223))
        for i, t in enumerate(cards):
            y = kb[1] + 360 + i * 120
            rounded(d, (cx + 16, y, cx + cw - 16, y + 104), 14, fill=(30, 27, 30), outline=LINE, width=2)
            checkbox(d, cx + 36, y + 22, name == "Done", s=28)
            d.text((cx + 80, y + 18), t, font=font(26), fill=(232, 228, 230))
            if name != "Done":
                rounded(d, (cx + 80, y + 60, cx + 210, y + 92), 12, fill=(64, 59, 64))
                d.text((cx + 96, y + 62), ("Product", "Design", "Research", "Platform")[i % 4], font=font(20), fill=(210, 205, 208))

    # -- right display: Rose assistant + now playing + a wide canvas
    rb = (2620, 110, 3700, 790)
    rounded(d, rb, 26, fill=(240, 222, 226), outline=(225, 200, 206), width=2)
    d.ellipse((rb[0] + 40, rb[1] + 36, rb[0] + 76, rb[1] + 72), fill=ROSE)
    d.text((rb[0] + 96, rb[1] + 32), "Rose", font=font(36, "SemiBold"), fill=INK)
    d.text((rb[0] + 50, rb[1] + 130), "Comparing three references", font=font(40, "Bold"), fill=INK)
    for i, t in enumerate(("Here's a concise comparison of the three references",
                           "you shared, focused on layout, interaction, and tone.")):
        d.text((rb[0] + 50, rb[1] + 200 + i * 44), t, font=font(28), fill=(70, 60, 64))
    for i, t in enumerate(("Reference A  —  Minimal, efficient", "Reference B  —  Richer, more expressive",
                           "Reference C  —  Balanced, closest fit")):
        y = rb[1] + 320 + i * 56
        rounded(d, (rb[0] + 50, y + 4, rb[0] + 74, y + 34), 4, fill=None, outline=ROSE_DK, width=2)
        d.text((rb[0] + 96, y), t, font=font(28), fill=INK)
    rounded(d, (rb[0] + 50, rb[1] + 520, rb[0] + 380, rb[1] + 590), 34, fill=None, outline=ROSE_DK, width=3)
    d.text((rb[0] + 84, rb[1] + 536), "View comparison  →", font=font(28, "SemiBold"), fill=INK)

    mb = (2620, 820, 3700, 1180)
    rounded(d, mb, 26, fill=(236, 214, 219), outline=(225, 200, 206), width=2)
    art = Image.new("RGB", (220, 220))
    ay, ax = np.mgrid[0:220, 0:220]
    wave = np.exp(-((ay - 120 - 25 * np.sin(ax / 30)) / 18) ** 2)
    arr = np.stack([60 + 190 * wave, 20 + 60 * wave, 40 + 80 * wave], -1)
    art = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    img.paste(art, (mb[0] + 50, mb[1] + 70))
    d.text((mb[0] + 310, mb[1] + 80), "Now playing", font=font(26), fill=(110, 95, 100))
    d.text((mb[0] + 310, mb[1] + 122), "Quiet Hours", font=font(44, "Bold"), fill=INK)
    d.text((mb[0] + 310, mb[1] + 182), "Arden Vale", font=font(30), fill=(90, 80, 84))
    d.ellipse((mb[0] + 820, mb[1] + 120, mb[0] + 920, mb[1] + 220), fill=ROSE_DK)
    d.rectangle((mb[0] + 852, mb[1] + 148, mb[0] + 864, mb[1] + 192), fill=(255, 255, 255))
    d.rectangle((mb[0] + 876, mb[1] + 148, mb[0] + 888, mb[1] + 192), fill=(255, 255, 255))
    rounded(d, (mb[0] + 310, mb[1] + 270, mb[2] - 60, mb[1] + 280), 5, fill=(205, 180, 188))
    rounded(d, (mb[0] + 310, mb[1] + 270, mb[0] + 640, mb[1] + 280), 5, fill=ROSE_DK)

    # wide canvas window: the Ribbon editor
    cb = (3760, 110, 5060, 1180)
    window_chrome(d, cb, "Ribbon · Music", dark=True)
    d.text((cb[0] + 60, cb[1] + 120), "Ribbon", font=font(62, "Bold"), fill=(244, 240, 242))
    d.text((cb[0] + 60, cb[1] + 200), "Bass → slow swells   ·   Highs → highlights   ·   Pan → position",
           font=font(26), fill=(185, 180, 183))
    # spectrum bars
    for i in range(48):
        h = 60 + 380 * abs(math.sin(i * 0.37) * math.exp(-i / 40)) + 40 * (i % 3)
        x = cb[0] + 70 + i * 24
        col = (int(235 - i * 1.5), int(110 - i * 1.6), int(40 + i * 2.0))
        rounded(d, (x, cb[1] + 760 - h, x + 14, cb[1] + 760), 6, fill=col)
    d.line((cb[0] + 60, cb[1] + 800, cb[2] - 60, cb[1] + 800), fill=LINE, width=2)
    for i, (k, v) in enumerate((("Swell", "0.8 s"), ("Highlights", "Delicate"), ("Brightness", "Auto (room)"))):
        d.text((cb[0] + 60, cb[1] + 840 + i * 60), k, font=font(28), fill=(185, 180, 183))
        d.text((cb[0] + 420, cb[1] + 840 + i * 60), v, font=font(28, "SemiBold"), fill=(240, 236, 238))

    # taskbar, just above the rows hidden by the reflector
    ty1 = H - HIDDEN_ROWS - 18
    ty0 = ty1 - 92
    for p0 in (0, 2560):
        rounded(d, (p0 + 40, ty0, p0 + 2520, ty1), 30, fill=(16, 14, 16), outline=(48, 44, 48), width=2)
    for i, t in enumerate(("Home", "Files", "Projects", "Notes", "Rose")):
        x = 260 + i * 230
        if i == 0:
            rounded(d, (x - 30, ty0 + 16, x + 150, ty1 - 16), 26, fill=ROSE_DK)
        d.text((x + 10, ty0 + 26), t, font=font(30, "Medium"), fill=(236, 232, 234))
    d.text((2560 + 1700, ty0 + 26), "Ribbon · Music  ⌄", font=font(30, "Medium"), fill=(220, 215, 218))
    rounded(d, (2560 + 2050, ty0 + 42, 2560 + 2440, ty0 + 50), 4, fill=(90, 84, 90))
    rounded(d, (2560 + 2050, ty0 + 42, 2560 + 2340, ty0 + 50), 4, fill=(220, 215, 218))
    return img


def screen_image(mode: str, t: float = 0.0, ui: Image.Image | None = None) -> np.ndarray:
    """Float32 (H, W, 3) linear-light image, top row first."""
    ui = ui or desktop()
    arr = (np.asarray(ui).astype(np.float32) / 255.0) ** 2.2
    arr[H - HIDDEN_ROWS:] = 0.0
    band = band_colors(mode, t).astype(np.float32)
    arr[H - BAND_ROWS:] = band[None]
    return arr


if __name__ == "__main__":
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
    os.makedirs(out, exist_ok=True)
    a = screen_image("concept")
    Image.fromarray((np.clip(a, 0, 1) ** (1 / 2.2) * 255).astype(np.uint8)).resize((2560, 720)).save(
        os.path.join(out, "screen-preview.png"))
    print("ok", BAND_ROWS, HIDDEN_ROWS)
