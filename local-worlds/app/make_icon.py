"""Draws the app icon: a little world made of soft splats over a night-to-teal gradient. Writes icon_1024.png."""
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
N = 1024; rng = np.random.default_rng(7)
yy, xx = np.mgrid[0:N, 0:N] / (N - 1)
top, bot = np.array([28, 22, 74]), np.array([16, 120, 132])
bg = top + (bot - top) * (0.65 * yy + 0.35 * xx)[..., None]
bg += 26 * np.exp(-(((xx - 0.3) ** 2 + (yy - 0.25) ** 2) / 0.08))[..., None]
img = Image.fromarray(np.clip(bg, 0, 255).astype(np.uint8)).convert("RGBA")
# the world: points on a sphere, drawn back to front as soft discs, lit from the upper left
pts = rng.normal(size=(2600, 3)); pts /= np.linalg.norm(pts, axis=1, keepdims=True)
a = np.radians(24); R = np.array([[np.cos(a), 0, np.sin(a)], [0, 1, 0], [-np.sin(a), 0, np.cos(a)]]); pts = pts @ R.T
light = np.array([-0.5, -0.6, 0.62]); light /= np.linalg.norm(light)
layer = Image.new("RGBA", (N, N), (0, 0, 0, 0)); d = ImageDraw.Draw(layer)
land = lambda p: np.sin(3.1 * p[0] + 1.3) * np.cos(2.7 * p[1] - 0.4) + 0.6 * np.sin(4.3 * p[2] + p[0] * 2) > 0.15
for p in pts[np.argsort(pts[:, 2])]:
    if p[2] < -0.15: continue
    lit = max(0.0, float(p @ light)); base = np.array([255, 196, 92]) if land(p) else np.array([92, 214, 255])
    c = (base * (0.28 + 0.85 * lit)).clip(0, 255).astype(int)
    x, y, r = N / 2 + p[0] * 318, N / 2 + 18 + p[1] * 318, 9 + 11 * (p[2] + 0.15) + rng.uniform(0, 5)
    d.ellipse([x - r, y - r, x + r, y + r], fill=(*c, int(120 + 110 * max(p[2], 0))))
glow = layer.filter(ImageFilter.GaussianBlur(26)); img.alpha_composite(glow); img.alpha_composite(layer.filter(ImageFilter.GaussianBlur(1.2)))
# a few loose splats drifting off, to say "made of splats"
d2 = ImageDraw.Draw(img, "RGBA")
for _ in range(46):
    ang, rad = rng.uniform(0, 2 * np.pi), rng.uniform(345, 440); r = rng.uniform(4, 13)
    x, y = N / 2 + np.cos(ang) * rad, N / 2 + 18 + np.sin(ang) * rad * 0.92
    d2.ellipse([x - r, y - r, x + r, y + r], fill=(255, 226, 160, int(rng.uniform(60, 170))) if rng.random() < 0.5 else (140, 228, 255, int(rng.uniform(60, 170))))
# macOS rounded-square mask with margin
mask = Image.new("L", (N, N), 0); ImageDraw.Draw(mask).rounded_rectangle([100, 100, N - 100, N - 100], radius=185, fill=255)
out = Image.new("RGBA", (N, N), (0, 0, 0, 0)); out.paste(img, (0, 0), mask); out.save("icon_1024.png")
