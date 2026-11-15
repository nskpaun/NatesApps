"""Draws the app icon: stolen fire. A flame built from thousands of glowing splats, with a small world burning
at its heart, on a dark sky. Light is added up like real light, then tone-mapped. Writes icon_1024.png."""
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
N = 1024; rng = np.random.default_rng(11)
yy, xx = np.mgrid[0:N, 0:N].astype(np.float32)
img = np.zeros((N, N, 3), np.float32)

def splat(x, y, r, col, a=1.0):                 # add one soft round light
    R = int(r * 3) + 1; x0, x1, y0, y1 = max(0, int(x) - R), min(N, int(x) + R + 1), max(0, int(y) - R), min(N, int(y) + R + 1)
    if x0 >= x1 or y0 >= y1: return
    g = np.exp(-((xx[y0:y1, x0:x1] - x) ** 2 + (yy[y0:y1, x0:x1] - y) ** 2) / (2 * r * r))
    img[y0:y1, x0:x1] += g[..., None] * (np.asarray(col, np.float32) * a)

def heat(t):                                    # 0 = cool edge, 1 = white-hot core
    stops = np.array([[0.00, 0.22, 0.01, 0.16], [0.22, 0.75, 0.05, 0.06], [0.50, 1.00, 0.33, 0.03], [0.78, 1.00, 0.72, 0.16], [1.00, 1.00, 0.95, 0.70]])
    return np.array([np.interp(t, stops[:, 0], stops[:, k]) for k in (1, 2, 3)])

# sky: near-black blue with a warm bloom behind the fire and a cold one in the corner
d = np.hypot(xx - 512, yy - 600) / N
img += np.array([0.020, 0.022, 0.050]) + np.exp(-(d / 0.42) ** 2)[..., None] * np.array([0.11, 0.025, 0.03])
img += np.exp(-(np.hypot(xx - 240, yy - 230) / 330) ** 2)[..., None] * np.array([0.02, 0.05, 0.11])
for _ in range(140):                            # stars
    splat(rng.uniform(110, 914), rng.uniform(110, 914), rng.uniform(0.8, 1.9), [0.8, 0.9, 1.0], rng.uniform(0.15, 0.7))

CX, BASE, TOP = 512, 760, 150                   # the flame runs from BASE up to TOP
def flame(n, lean, width, cx, base, top, power, seed):
    r = np.random.default_rng(seed)
    for _ in range(n):
        t = r.beta(1.25, 2.1)                   # height along the flame, 0 at the base; denser low down
        half = width * np.sin(np.pi * min(1, t * 1.02) ** 0.62) ** 1.15 * (1 - 0.25 * t)      # teardrop outline
        u = np.clip(r.normal(0, 0.42), -1, 1)   # across the flame, denser in the middle
        sway = lean * np.sin(t * 3.4 + seed) * t + 46 * np.sin(t * 7.5 + seed * 2.1) * t * t     # the tongue curls as it rises
        x, y = cx + sway + u * half, base - t * (base - top)
        core = (1 - abs(u)) ** 1.3 * (1 - t) ** 0.8
        splat(x, y, r.uniform(4, 13) * (1.15 - 0.6 * t), heat(np.clip(core * 1.15 + r.normal(0, 0.07), 0, 1)), power * (0.035 + 0.075 * core))
flame(9000, 58, 225, CX, BASE, TOP, 1.0, 1)                 # the body
flame(2600, -70, 115, CX - 92, BASE - 10, 330, 0.9, 5)      # a smaller tongue on the left
flame(2300, 64, 100, CX + 104, BASE - 6, 380, 0.9, 9)       # and one on the right
flame(2200, 22, 85, CX, BASE - 20, 330, 1.0, 3)            # white-hot heart

# embers carried up and away
for _ in range(150):
    t = rng.uniform(0, 1) ** 0.7; a = rng.uniform(-1, 1)
    x, y = CX + a * (150 + 250 * t) + 60 * np.sin(t * 5 + a * 3), 640 - t * 560
    splat(x, y, rng.uniform(1.6, 5.5) * (1 - 0.5 * t), heat(rng.uniform(0.45, 0.9)), rng.uniform(0.25, 1.0) * (1 - 0.6 * t))

# the world at the heart of the fire: a small globe of splats, sea in deep blue and land catching the firelight
WX, WY, WR = CX, 672, 132
fire = img; img = np.zeros((N, N, 3), np.float32)        # the globe is painted on its own layer and laid over the fire
pts = rng.normal(size=(7000, 3)); pts /= np.linalg.norm(pts, axis=1, keepdims=True)
a = np.radians(-28); pts = pts @ np.array([[np.cos(a), 0, np.sin(a)], [0, 1, 0], [-np.sin(a), 0, np.cos(a)]]).T
land = lambda p: np.sin(3.3 * p[0] + 0.7) * np.cos(2.9 * p[1] - 0.5) + 0.55 * np.sin(4.6 * p[2] + 2.2 * p[0]) > 0.12
key = np.array([-0.25, -0.62, 0.74]); key /= np.linalg.norm(key)            # firelight from above and in front
for p in pts[np.argsort(pts[:, 2])]:
    if p[2] < 0: continue
    k = max(0.0, float(p @ key)) ** 1.4; edge = (1 - p[2]) ** 2.5 * max(0.0, 0.5 - p[1])   # plus a hot rim round the top
    col = (np.array([1.00, 0.66, 0.24]) if land(p) else np.array([0.05, 0.22, 0.62])) * (0.06 + 1.0 * k) + np.array([1.0, 0.50, 0.12]) * edge * 1.3
    splat(WX + p[0] * WR, WY + p[1] * WR, 3.4 + 1.6 * p[2], col, 0.26)
globe = 1 - np.exp(-img * 1.6); img = fire
cover = np.clip((WR * 1.01 - np.hypot(xx - WX, yy - WY)) / 3, 0, 1)[..., None]

# bloom, tone map, a little vignette
out = 1 - np.exp(-img * 1.25)
im = Image.fromarray((out * 255).astype(np.uint8))
bloom = np.asarray(im.filter(ImageFilter.GaussianBlur(28)), np.float32) / 255
out = 1 - (1 - out) * (1 - 0.30 * bloom)
out = out * (1 - cover) + globe * cover                    # the world sits in front of the fire
halo = np.exp(-((np.hypot(xx - WX, yy - WY) - WR) / 5) ** 2) * np.clip((WY + 40 - yy) / 160, 0, 1)
out += halo[..., None] * np.array([1.0, 0.70, 0.30]) * 0.55
out *= (1 - 0.35 * np.clip((np.hypot(xx - 512, yy - 512) - 330) / 400, 0, 1) ** 2)[..., None]
im = Image.fromarray((np.clip(out, 0, 1) ** 0.92 * 255).astype(np.uint8)).convert("RGBA")
# macOS rounded-square mask with margin, and a faint lit edge
mask = Image.new("L", (N * 2, N * 2), 0); ImageDraw.Draw(mask).rounded_rectangle([200, 200, N * 2 - 200, N * 2 - 200], radius=370, fill=255); mask = mask.resize((N, N), Image.LANCZOS)
edge = Image.new("RGBA", (N, N), (0, 0, 0, 0)); ImageDraw.Draw(edge).rounded_rectangle([101, 101, N - 101, N - 101], radius=184, outline=(255, 190, 120, 70), width=3)
im.alpha_composite(edge)
res = Image.new("RGBA", (N, N), (0, 0, 0, 0)); res.paste(im, (0, 0), mask); res.save("icon_1024.png")
