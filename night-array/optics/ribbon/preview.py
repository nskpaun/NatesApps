"""Fast preview of the station's lower edge as seen from the seat.

The full tracer renders a pattern directly (`direct`). The page's live explorer cannot run the tracer, so it
uses a separable shortcut built from traced data (`compose`): because the optics are extruded, the ribbon at
lateral position x is the band's pattern, shifted and blurred sideways by a traced point-spread function,
times a traced vertical profile. `compose` here is the reference implementation of that shortcut; run.py
measures how far it is from the direct render.
"""
from __future__ import annotations

import numpy as np

from . import designs as D
from . import patterns as P
from .study import eye_of, lateral_psf, linear_to_srgb
from .trace import luma, render, trace

VIEW_Y = np.arange(-176.0, 47.0, 1.0)            # apparent height on the screen plane, mm
STATIONS = np.array([0.0, 150.0, 300.0, 450.0, 600.0])
KERNEL_X = np.arange(-40.0, 40.5, 1.0)
WALL = 0.5                                       # wall behind the station, relative to the sky luminance


def stations(scene, spp=1200, seed=3, reps=400):
    """Traced columns, lateral point-spread function and per-row lateral shift at a few lateral positions
    (uniform, endless band)."""
    eye = eye_of(scene)
    ny = len(VIEW_Y)
    out = []
    for i, x in enumerate(STATIONS):
        r = render(scene, eye, [x], VIEW_Y, spp=spp, jitter=False, rng=np.random.default_rng(seed + i))
        psf = lateral_psf(scene, x=x, spp=150000, seed=seed + 20 + i)
        k = np.interp(KERNEL_X + psf["mean"], psf["x"], psf["w"])
        k = 0.5 * (k + k[::-1])
        # where on the band each row of the view looks, sideways (the ribbon is an image at depth, so this
        # grows with x and differs from row to row)
        tg = np.repeat(np.stack([np.full(ny, x), VIEW_Y, np.zeros(ny)], 1), reps, 0)
        eo = np.tile(eye, (len(tg), 1))
        h = trace(scene, eo, tg - eo, np.random.default_rng(seed + 40 + i), collect_hits=True)["hits"]
        num, den = np.zeros(ny), np.zeros(ny)
        for idx, hx, _, w in h:
            np.add.at(num, idx // reps, luma(w) * (hx - x))
            np.add.at(den, idx // reps, luma(w))
        ok = den > 0.03 * den.max()
        rowshift = np.where(ok, num / np.maximum(den, 1e-12), psf["mean"])
        rowshift = np.convolve(np.pad(rowshift, 2, mode="edge"), np.ones(5) / 5, mode="valid")
        out.append(dict(x=float(x), band=r["band"]["white"][:, 0], echo=luma(r["echo"]["white"][:, 0]),
                        content=luma(r["content"][:, 0]), ambient=r["ambient"][:, 0],
                        shift=psf["mean"], fwhm=psf["fwhm"], kernel=k / k.sum(), rowshift=rowshift))
    return out


def _interp_station(st, key, ax):
    """Linear interpolation of a per-station array at lateral positions |x| = ax -> [len(ax), ...]."""
    xs = np.array([s["x"] for s in st])
    v = np.array([np.asarray(s[key], float) for s in st])
    i = np.clip(np.searchsorted(xs, ax) - 1, 0, len(xs) - 2)
    t = np.clip((ax - xs[i]) / (xs[i + 1] - xs[i]), 0, 1)
    t = t.reshape((-1,) + (1,) * (v.ndim - 1))
    return v[i] * (1 - t) + v[i + 1] * t


def compose(st, pattern, xs, lux=200.0, nits=D.PANEL_NITS, content_nits=40.0, echo=True, level=1.0):
    """Luminance image [len(VIEW_Y), len(xs), 3] in nits (linear RGB) from station data and a band pattern
    (array [len(P.XS), 3], linear RGB 0..1). The page's script does exactly this:
    ribbon(x, y) = traced column(|x|, y) * blurred pattern(x + sign(x) * rowshift(|x|, y))."""
    ax = np.abs(xs)
    band = _interp_station(st, "band", ax)               # [nx, ny, 3]
    amb = _interp_station(st, "ambient", ax)
    ech = _interp_station(st, "echo", ax)                # [nx, ny]
    con = _interp_station(st, "content", ax)
    rsh = _interp_station(st, "rowshift", ax) * np.sign(xs)[:, None]      # [nx, ny]
    # the pattern blurred with the centre kernel and with the end kernel; blended by |x|
    step = P.XS[1] - P.XS[0]
    kx = np.arange(KERNEL_X[0], KERNEL_X[-1] + step / 2, step)
    blur = []
    for s in (st[0], st[-1]):
        k = np.interp(kx, KERNEL_X, s["kernel"])
        k /= k.sum()
        blur.append(np.stack([np.convolve(pattern[:, c], k, mode="same") for c in range(3)], 1))
    mixw = np.clip(ax / st[-1]["x"], 0, 1)[:, None]
    src = xs[:, None] + rsh                                              # [nx, ny]
    pat = np.zeros(src.shape + (3,))
    for c in range(3):
        b0 = np.interp(src, P.XS, blur[0][:, c], left=0.0, right=0.0)
        b1 = np.interp(src, P.XS, blur[1][:, c], left=0.0, right=0.0)
        pat[..., c] = b0 * (1 - mixw) + b1 * mixw
    direct = np.stack([np.interp(xs, P.XS, pattern[:, c], left=0.0, right=0.0) for c in range(3)], 1)
    on_screen = ((ax <= P.X1) & (ax >= P.SEAM / 2)).astype(float)
    sky = lux / np.pi
    img = (band * pat * nits * level
           + (ech[:, :, None] * direct[:, None, :] * nits * level if echo else 0.0)
           + con[:, :, None] * on_screen[:, None, None] * content_nits
           + amb * sky)
    return np.transpose(img, (1, 0, 2))


def direct(scene_fn, xs, spp=40, seed=5, **kw):
    """Full-tracer render of the same view with the real, finite band patterns (seam and ends included)."""
    sc = scene_fn(patterns=P.ALL, x_span=(P.X0, P.X1), **kw)
    return render(sc, eye_of(sc), xs, VIEW_Y, spp=spp, rng=np.random.default_rng(seed))


def combine(r, name, lux=200.0, nits=D.PANEL_NITS, content_nits=40.0, echo=True):
    sky = lux / np.pi
    return (r["band"][name] * nits + (r["echo"][name] * nits if echo else 0.0)
            + r["content"] * content_nits + r["ambient"] * sky)


def tonemap(img_nits, white=D.PANEL_NITS):
    """Screen-referred: the panel's own white maps to display white. No auto-exposure."""
    return (linear_to_srgb(img_nits / white)[::-1] * 255 + 0.5).astype(np.uint8)
