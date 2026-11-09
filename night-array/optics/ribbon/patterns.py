"""Band patterns: what RoseOS would paint on the feed rows. One sample per 0.5 mm along x, linear RGB 0..1."""
from __future__ import annotations

import numpy as np

from .designs import PANEL_W
from .study import srgb_to_linear

SEAM = 14.0                                   # gap between the two active areas
X0, X1 = -(PANEL_W + SEAM / 2), PANEL_W + SEAM / 2
STEP = 0.5
XS = np.arange(X0 + STEP / 2, X1, STEP)


def _seam(p):
    p = np.array(p, float)
    p[np.abs(XS) < SEAM / 2] = 0.0
    return p


def solid(rgb=(255, 255, 255)):
    return _seam(np.tile(srgb_to_linear(rgb), (len(XS), 1)))


def glow():
    """The concept picture's band: amber on the left, a white-hot core left of centre, rose, then oxblood."""
    u = (XS - X0) / (X1 - X0)
    stops = [(0.00, (200, 110, 30)), (0.22, (255, 170, 60)), (0.40, (255, 236, 205)), (0.50, (255, 150, 110)),
             (0.68, (235, 70, 110)), (0.86, (170, 35, 60)), (1.00, (110, 22, 40))]
    pos = np.array([s[0] for s in stops])
    col = np.array([srgb_to_linear(s[1]) for s in stops])
    rgb = np.stack([np.interp(u, pos, col[:, c]) for c in range(3)], 1)
    env = 0.55 + 0.45 * np.exp(-((u - 0.40) / 0.16) ** 2)          # brightest around the hot core
    env *= np.clip(np.minimum(u, 1 - u) / 0.05, 0, 1) ** 0.7       # fades out at both ends
    return _seam(rgb * env[:, None])


def bars():
    """Resolution chart: groups of white bars 80, 40, 20, 10, 5 and 2.5 mm wide (gaps the same width)."""
    p = np.zeros((len(XS), 3))
    x = X0 + 40.0
    for w in (80, 40, 20, 10, 5, 2.5):
        for _ in range(4 if w > 5 else 8):
            p[(XS >= x) & (XS < x + w)] = 1.0
            x += 2 * w
        x += 50
    return _seam(p)


ALL = {"white": solid(), "glow": glow(), "bars": bars()}
