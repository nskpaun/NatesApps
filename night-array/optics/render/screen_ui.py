"""Paints what the two panels show: a RoseOS desktop (5120 x 1440, one canvas across both 27" QHD panels),
the visible light band above the sill, and, as a separate image, the hidden feed rows that make the ribbon.

    python screen_ui.py out_dir        -> out_dir/screen.png  (feed rows black)
                                          out_dir/band.png    (the feed rows only, 5120 x 51)
                                          out_dir/band_white.png (same size, solid white: for calibration)
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 5120, 1440
PW = 2560                       # one panel
ROW_MM = 335.7 / 1440
FEED_ROWS = 51                  # 12 mm of hidden feed rows (Balanced preset)
HIDDEN_ROWS = 63                # feed rows + the rows under the sill's wall
ECHO_ROWS = 86                  # 20 mm visible band
FONT_DIR = Path("/usr/share/fonts/opentype/inter")


def font(size, weight="Regular"):
    for name in (f"Inter-{weight}.otf", "Inter-Regular.otf"):
        p = FONT_DIR / name
        if p.exists():
            return ImageFont.truetype(str(p), size)
    return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size)


INK, PAPER, ROSE = (34, 26, 24), (246, 240, 234), (150, 44, 62)
DARK, DARK2, DARK3 = (30, 25, 23), (42, 36, 33), (58, 50, 46)
MUTED, LINE = (150, 138, 130), (70, 61, 56)


def srgb_to_linear(c):
    c = np.asarray(c, float) / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)


def glow(n=W):
    """The concept picture's band, in linear RGB: amber, a white-hot core left of centre, rose, oxblood.
    Same recipe as ribbon/patterns.py, sampled per pixel column across both panels."""
    u = (np.arange(n) + 0.5) / n
    stops = [(0.00, (200, 110, 30)), (0.22, (255, 170, 60)), (0.40, (255, 236, 205)), (0.50, (255, 150, 110)),
             (0.68, (235, 70, 110)), (0.86, (170, 35, 60)), (1.00, (110, 22, 40))]
    pos = np.array([s[0] for s in stops])
    col = np.array([srgb_to_linear(s[1]) for s in stops])
    rgb = np.stack([np.interp(u, pos, col[:, c]) for c in range(3)], 1)
    env = 0.55 + 0.45 * np.exp(-((u - 0.40) / 0.16) ** 2)
    env *= np.clip(np.minimum(u, 1 - u) / 0.05, 0, 1) ** 0.7
    return rgb * env[:, None]


def window(d, box, fill, radius=22, title=None, dark=False):
    x0, y0, x1, y1 = box
    d.rounded_rectangle(box, radius, fill=fill, outline=LINE if dark else (214, 204, 196), width=2)
    for i, c in enumerate(((236, 96, 86), (244, 190, 80), (98, 196, 84))):
        d.ellipse((x0 + 30 + i * 34, y0 + 28, x0 + 52 + i * 34, y0 + 50), fill=c)
    if title:
        d.text((x0 + 160, y0 + 22), title, font=font(30, "Medium"), fill=(232, 224, 216) if dark else INK)
    d.line((x0, y0 + 76, x1, y0 + 76), fill=LINE if dark else (222, 212, 204), width=2)


def checkbox(d, x, y, text, done, dark=False, size=34):
    c = ROSE if done else None
    d.rounded_rectangle((x, y, x + 30, y + 30), 6, fill=c, outline=ROSE if done else MUTED, width=3)
    if done:
        d.line((x + 7, y + 16, x + 13, y + 22, x + 24, y + 9), fill=(255, 255, 255), width=4)
    d.text((x + 48, y - 6), text, font=font(size), fill=(226, 218, 210) if dark else INK)


def menubar(d, x0, name="RoseOS"):
    d.rectangle((x0, 0, x0 + PW, 62), fill=(22, 18, 17))
    d.ellipse((x0 + 44, 16, x0 + 74, 46), fill=ROSE)
    d.text((x0 + 96, 12), name, font=font(32, "SemiBold"), fill=(240, 232, 224))
    x = x0 + 250
    for item in ("File", "Edit", "View", "Go", "Window", "Help"):
        d.text((x, 14), item, font=font(30), fill=(214, 206, 198))
        x += d.textlength(item, font=font(30)) + 44
    d.text((x0 + PW - 420, 14), "Tue Jan 28   10:24 AM", font=font(30), fill=(214, 206, 198))


def dock(d, x0, y, active="Home", extra=None):
    d.rectangle((x0, y, x0 + PW, y + 96), fill=(20, 17, 16))
    x = x0 + 150
    for item in ("Home", "Files", "Projects", "Notes", "Rose"):
        w = d.textlength(item, font=font(30, "Medium"))
        if item == active:
            d.rounded_rectangle((x - 30, y + 20, x + w + 30, y + 76), 28, fill=(96, 34, 44))
        d.text((x, y + 28), item, font=font(30, "Medium"), fill=(240, 230, 224))
        x += w + 96
    if extra:
        d.text((x0 + PW - 900, y + 28), extra, font=font(30), fill=(214, 206, 198))
        d.rounded_rectangle((x0 + PW - 520, y + 44, x0 + PW - 120, y + 52), 4, fill=(120, 110, 104))
        d.ellipse((x0 + PW - 250, y + 34, x0 + PW - 222, y + 62), fill=(240, 232, 224))


def desktop():
    img = Image.new("RGB", (W, H), (18, 14, 13))
    # wallpaper: a low warm gradient
    yy, xx = np.mgrid[0:H, 0:W]
    wall = np.zeros((H, W, 3))
    g = np.exp(-((xx / W - 0.42) ** 2) / 0.09 - ((yy / H - 0.95) ** 2) / 0.35)
    wall += np.array([38, 22, 20]) + g[..., None] * np.array([52, 22, 18])
    img = Image.fromarray(np.clip(wall, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(img)
    for x0 in (0, PW):
        menubar(d, x0)

    # ---- left panel: notes + project board
    window(d, (90, 118, 1010, 1040), PAPER, title="Studio notes")
    d.text((150, 236), "Studio notes", font=font(58, "SemiBold"), fill=INK)
    d.text((150, 322), "Direction for the Q1 release: a focused, refined", font=font(34), fill=INK)
    d.text((150, 368), "update that improves everyday flow.", font=font(34), fill=INK)
    for i, (t, done) in enumerate((("Finalize interaction specs", True), ("Review prototype with design", True),
                                   ("Update asset list and handoff", False), ("Prepare release notes (draft)", False))):
        checkbox(d, 154, 452 + i * 60, t, done)
    d.line((150, 716, 950, 716), fill=(220, 210, 202), width=2)
    d.text((150, 742), "Key points", font=font(36, "SemiBold"), fill=INK)
    for i, t in enumerate(("Keep the experience clean, fast, and consistent.", "Validate changes with a small user group this week.",
                           "Aim for release candidate by Feb 7.")):
        d.ellipse((160, 824 + i * 54, 172, 836 + i * 54), fill=ROSE)
        d.text((196, 808 + i * 54), t, font=font(31), fill=INK)

    window(d, (1064, 118, 2470, 1040), DARK, title="Project / Today", dark=True)
    d.text((1124, 222), "Today", font=font(58, "SemiBold"), fill=(240, 232, 224))
    d.text((1124, 304), "Work in progress · Q1 release", font=font(30), fill=MUTED)
    d.rounded_rectangle((2150, 232, 2400, 296), 30, fill=(150, 44, 62))
    d.text((2186, 244), "+ Add card", font=font(30, "Medium"), fill=(255, 244, 240))
    cols = (("To do", (130, 122, 116), ("Polish onboarding copy", "Update design system", "Plan beta feedback")),
            ("In progress", (232, 84, 96), ("Refine window layout", "Implement Ribbon control")),
            ("Done", (98, 196, 84), ("Confirm scope", "Ship prototype v2", "Review with team", "Update project brief")))
    for ci, (name, dot, cards) in enumerate(cols):
        x = 1110 + ci * 452
        d.rounded_rectangle((x, 372, x + 424, 992), 18, fill=DARK2)
        d.ellipse((x + 26, 398, x + 46, 418), fill=dot)
        d.text((x + 62, 388), f"{name}   {len(cards)}", font=font(30, "Medium"), fill=(226, 218, 210))
        for k, t in enumerate(cards):
            y = 448 + k * (132 if ci < 2 else 92)
            hgt = 116 if ci < 2 else 76
            d.rounded_rectangle((x + 16, y, x + 408, y + hgt), 12, fill=DARK3)
            checkbox(d, x + 34, y + 22, t, ci == 2, dark=True, size=28)
            if ci < 2:
                tag = ("Product", "Design", "Research", "Design", "Platform")[(k + ci * 3) % 5]
                d.rounded_rectangle((x + 82, y + 66, x + 82 + 30 + d.textlength(tag, font=font(24)), y + 104), 18, fill=(78, 68, 63))
                d.text((x + 97, y + 70), tag, font=font(24), fill=(214, 206, 198))

    # ---- right panel: Rose + now playing
    window(d, (PW + 80, 118, PW + 1630, 1040), (243, 233, 230), title="Rose")
    d.text((PW + 150, 236), "Comparing three references", font=font(52, "SemiBold"), fill=INK)
    d.text((PW + 150, 326), "Here's a concise comparison of the three references you shared,", font=font(36), fill=INK)
    d.text((PW + 150, 376), "focused on layout, interaction, and tone.", font=font(36), fill=INK)
    for i, t in enumerate(("Reference A — Minimal, efficient", "Reference B — Richer, more expressive",
                           "Reference C — Balanced, closest fit")):
        y = 478 + i * 84
        d.rounded_rectangle((PW + 156, y, PW + 196, y + 50), 8, outline=ROSE, width=4)
        d.text((PW + 240, y + 2), t, font=font(38), fill=INK)
    d.rounded_rectangle((PW + 150, 760, PW + 640, 844), 42, outline=ROSE, width=4)
    d.text((PW + 200, 778), "View comparison  →", font=font(38, "Medium"), fill=ROSE)

    cx0 = PW + 1690
    d.rounded_rectangle((cx0, 118, PW + 2470, 1040), 22, fill=(238, 226, 224), outline=(214, 204, 196), width=2)
    d.text((cx0 + 56, 160), "Now playing", font=font(32), fill=INK)
    art = np.zeros((300, 300, 3))
    ay, ax = np.mgrid[0:300, 0:300]
    wave = 150 + 26 * np.sin(ax / 40.0) + 10 * np.sin(ax / 13.0)
    art[:] = np.array([112, 28, 44])
    art += np.exp(-((ay - wave) / 18.0) ** 2)[..., None] * np.array([120, 70, 60])
    img.paste(Image.fromarray(np.clip(art, 0, 255).astype(np.uint8)), (cx0 + 240, 250))
    d.text((cx0 + 250, 590), "Quiet Hours", font=font(42, "SemiBold"), fill=INK)
    d.text((cx0 + 290, 650), "Arden Vale", font=font(32), fill=(92, 80, 76))
    d.rounded_rectangle((cx0 + 70, 742, cx0 + 710, 750), 4, fill=(190, 176, 172))
    d.rounded_rectangle((cx0 + 70, 742, cx0 + 400, 750), 4, fill=ROSE)
    d.ellipse((cx0 + 388, 734, cx0 + 412, 758), fill=ROSE)
    d.text((cx0 + 70, 772), "2:14", font=font(26), fill=(92, 80, 76))
    d.text((cx0 + 660, 772), "4:28", font=font(26), fill=(92, 80, 76))
    d.ellipse((cx0 + 330, 850, cx0 + 450, 970), fill=ROSE)
    d.rectangle((cx0 + 372, 884, cx0 + 384, 936), fill=(255, 244, 240))
    d.rectangle((cx0 + 396, 884, cx0 + 408, 936), fill=(255, 244, 240))

    dock(d, 0, 1090)
    dock(d, PW, 1090, extra="Ribbon · Music")
    return img


def main(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    img = np.asarray(desktop(), float) / 255.0
    lin = srgb_to_linear(img * 255)
    g = glow()
    # the visible band: the same pattern RoseOS paints on the feed rows, fading in at its top edge
    y1 = H - HIDDEN_ROWS
    y0 = y1 - ECHO_ROWS
    fade = np.clip((np.arange(ECHO_ROWS) + 1) / 30.0, 0, 1)[:, None, None] ** 1.5
    lin[y0:y1] = lin[y0:y1] * (1 - fade) + g[None] * fade
    lin[y1:] = 0.0                                              # hidden rows: black here, painted in band.png
    Image.fromarray((linear_to_srgb(lin) * 255 + 0.5).astype(np.uint8)).save(out / "screen.png")
    band = np.repeat(g[None], FEED_ROWS, 0)
    Image.fromarray((linear_to_srgb(band) * 255 + 0.5).astype(np.uint8)).save(out / "band.png")
    Image.fromarray(np.full((FEED_ROWS, W, 3), 255, np.uint8)).save(out / "band_white.png")
    print("wrote", out / "screen.png", out / "band.png")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "out")
