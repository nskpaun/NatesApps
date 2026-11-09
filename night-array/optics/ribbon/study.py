"""Measurements on a traced scene: what the seated eye sees, in numbers."""
from __future__ import annotations

import numpy as np

from . import designs as D
from .trace import intersect, luma, render, trace

# Room presets: illuminance on the desk (lux). The room is modelled as a uniform sky of luminance E / pi
# (the luminance that produces E on a horizontal surface), with everything below the horizon at a quarter of it.
ROOMS = {"dark": 2.0, "evening": 25.0, "home office": 200.0, "office": 500.0, "by a window": 2000.0}

# Band colours (sRGB 0-255). Luminance relative to white is what decides daylight visibility.
COLOURS = {"white": (255, 255, 255), "amber": (255, 170, 60), "rose": (240, 90, 120), "oxblood": (150, 30, 45)}


def srgb_to_linear(c):
    c = np.asarray(c, float) / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(c):
    c = np.clip(np.asarray(c, float), 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)


def colour_luma(name):
    return float(luma(srgb_to_linear(COLOURS[name])))


def eye_of(scene, x=0.0, y=None, z=None):
    ez, ey = scene.meta["eye"]
    return np.array([x, ey if y is None else y, ez if z is None else z])


def project_y(eye, pt_zy):
    """Height at which the sight line from the eye to a (z, y) point crosses the screen plane z = 0."""
    ez, ey = eye[2], eye[1]
    z, y = pt_zy
    return ey + (y - ey) * ez / (ez - z)


def window(scene, eye):
    """Apparent-height range (on the screen plane) covered by the surface that carries the ribbon."""
    if scene.meta["kind"] == "deck":
        pts = np.array([[D.BASE_Z[0], D.BASE_TOP_Y], [D.BASE_Z[1], D.BASE_TOP_Y]])
    else:
        pts = np.array(scene.meta["cove"])
    ys = [project_y(eye, p) for p in pts]
    return min(ys), max(ys)


def column(scene, eye=None, x=0.0, spp=800, n=400, pad=6.0, seed=7, ys=None):
    """Luminance along a vertical line of sight sweep at lateral position x, across the ribbon surface.

    Returns ys (apparent height on the screen plane, mm) and band / ambient / content luminance factors."""
    eye = eye_of(scene) if eye is None else np.asarray(eye, float)
    if ys is None:
        y0, y1 = window(scene, eye)
        ys = np.linspace(y0 - pad, y1 + pad, n)
    r = render(scene, eye, [x], ys, spp=spp, jitter=False, rng=np.random.default_rng(seed))
    return dict(ys=ys, band=luma(r["band"]["white"][:, 0]), ambient=luma(r["ambient"][:, 0]),
                content=luma(r["content"][:, 0]))


def metrics(col, lo=None, hi=None):
    """Ribbon numbers from a column: peak, mean over the half-maximum region, apparent height, and the room
    and screen-content responses over that same region. Luminances are factors of the panel's white."""
    ys, b = col["ys"], col["band"]
    m = np.ones(len(ys), bool)
    if lo is not None:
        m &= (ys >= lo) & (ys <= hi)
    dy = ys[1] - ys[0]
    # smooth a little before taking the peak so Monte Carlo noise does not inflate it
    k = np.ones(5) / 5
    bs = np.convolve(b, k, mode="same") * m
    peak = bs.max()
    core = bs >= 0.5 * peak
    return dict(peak=float(peak), mean=float(b[core].mean()), height=float(core.sum() * dy),
                integral=float((b * m).sum() * dy), ambient=float(col["ambient"][core].mean()),
                content=float(col["content"][core].mean()), y_lo=float(ys[core].min()), y_hi=float(ys[core].max()))


def contrast(m, nits=D.PANEL_NITS, colour="white", lux=500.0, content_nits=120.0):
    """Ribbon vs its own background on the same surface. Returns ribbon nits, background nits and the Weber
    contrast (ribbon / background). content_nits is the average luminance of whatever else is on screen."""
    ribbon = m["mean"] * nits * colour_luma(colour)
    background = m["ambient"] * lux / np.pi + m["content"] * content_nits
    black = m["mean"] * nits / 1000.0                           # an IPS "black" band still leaks (1000:1)
    return dict(ribbon=float(ribbon), background=float(background + black), weber=float(ribbon / (background + black)))


def verdict(weber):
    """Plain-language tiers for a large, soft-edged, coloured patch. The tier boundaries are judgement calls,
    not standards: around 2 % is the detection threshold for a large soft patch under good conditions."""
    if weber < 0.05:
        return "invisible"
    if weber < 0.2:
        return "faint"
    if weber < 0.6:
        return "visible"
    if weber < 2.0:
        return "clear"
    return "vivid"


# ----------------------------------------------------------------------------------------------- lateral blur
def lateral_psf(scene, x=0.0, spp=250000, seed=11, bins=np.arange(-150.25, 150.5, 0.5)):
    """Where on the band (along x) does the light in the ribbon's brightest line of sight come from?

    Returns bin centres (mm, relative to the lateral position being looked at), the normalised weight per bin,
    the mean offset and the full width at half maximum."""
    eye = eye_of(scene)
    col = column(scene, eye, x=x, spp=200, n=160)
    y_pk = col["ys"][np.argmax(np.convolve(col["band"], np.ones(5) / 5, mode="same"))]
    tg = np.tile([x, y_pk, 0.0], (spp, 1))
    eo = np.tile(eye, (spp, 1))
    r = trace(scene, eo, tg - eo, np.random.default_rng(seed), collect_hits=True)
    xs = np.concatenate([h[1] for h in r["hits"]]) - x
    w = np.concatenate([luma(h[3]) for h in r["hits"]])
    hist, _ = np.histogram(xs, bins=bins, weights=w)
    c = 0.5 * (bins[1:] + bins[:-1])
    hist = hist / hist.sum()
    sm = np.convolve(hist, np.ones(5) / 5, mode="same")
    above = c[sm >= 0.5 * sm.max()]
    return dict(x=c, w=hist, mean=float((c * hist).sum()), fwhm=float(above.max() - above.min()),
                w80=float(np.interp(0.9, np.cumsum(hist), c) - np.interp(0.1, np.cumsum(hist), c)))


# ----------------------------------------------------------------------------------------------- drawings
def forward_fan(scene, origins, angles_deg, max_bounces=8):
    """Illustrative rays leaving screen points (z = 0, given heights) at given angles above the screen normal,
    followed through mirrors, with the satin surface treated as a mirror (the centre of its lobe).
    Returns a list of polylines [[z, y], ...] and the label of the last surface each ray met."""
    kinds = np.array([m.kind for m in scene.materials])
    out = []
    for y0 in origins:
        for a in angles_deg:
            o = np.array([[0.0, y0, 1e-4]])
            d = np.array([[0.0, np.sin(np.radians(a)), np.cos(np.radians(a))]])
            path, last = [[o[0, 2], o[0, 1]]], "room"
            for _ in range(max_bounces):
                t, idx, s = intersect(scene, o, d)
                if not np.isfinite(t[0]):
                    end = o[0] + d[0] * 700
                    path.append([end[2], end[1]])
                    last = "room"
                    break
                p = o[0] + t[0] * d[0]
                path.append([p[2], p[1]])
                i = idx[0]
                e = scene.b[i] - scene.a[i]
                ng = np.array([-e[1], e[0]]) / np.hypot(*e)
                n2 = (1 - s[0]) * scene.na[i] + s[0] * scene.nb[i]
                n2 /= np.hypot(*n2)
                facing = -(d[0, 2] * ng[0] + d[0, 1] * ng[1])
                mi = scene.front[i] if facing > 0 else scene.back[i]
                last = scene.labels[i]
                if kinds[mi] not in ("mirror", "ggx") or (kinds[mi] == "ggx" and scene.labels[i] != "cove"):
                    break
                n3 = np.array([0.0, n2[1], n2[0]]) * (1 if facing > 0 else -1)
                d = (d[0] - 2 * (d[0] @ n3) * n3)[None]
                o = (p + n3 * 1e-5)[None]
            out.append((np.array(path), last))
    return out
