"""Metrics and pattern design on top of a CameraResult."""
from __future__ import annotations

import math

import numpy as np

from .tracer import CameraResult

LUX_LEVELS = {"dim room (50 lux)": 50, "evening lamp (150 lux)": 150, "office (500 lux)": 500,
              "bright office (1000 lux)": 1000, "near a sunny window (5000 lux)": 5000}


def room_luminance(lux: float) -> float:
    """Luminance of a uniform room that produces `lux` on a horizontal surface."""
    return lux / math.pi


def ribbon_mask(res: CameraResult, frac=0.3, cols=None):
    img = res.image(np.ones(res.A.shape[1]))
    sub = img if cols is None else img[:, cols]
    pk = np.percentile(sub[sub > 0], 99.5) if (sub > 0).any() else 0.0
    m = img >= frac * pk if pk > 0 else np.zeros_like(img, bool)
    return img, m, pk


def metrics(res: CameraResult, content_lum=60.0, lux=(50, 150, 500, 1000, 5000)):
    """Ribbon luminance with the band at full white, and how it compares with the ambient light
    and the main-screen spill that land on the same part of the surface."""
    img, m, pk = ribbon_mask(res)
    if not m.any():
        return dict(peak=0.0, mean=0.0, area_px=0, k_amb=float("nan"), k_content=float("nan"), contrast={})
    mean = float(img[m].mean())
    k_amb = float(res.ambient[m].mean())
    k_con = float(res.content[m].mean())
    contrast = {}
    for E in lux:
        bg = k_amb * room_luminance(E) + k_con * content_lum
        contrast[E] = (mean + bg) / max(bg, 1e-9)
    rows = np.nonzero(m.any(1))[0]
    return dict(peak=float(np.percentile(img[m], 95)), mean=mean, area_px=int(m.sum()),
                height_px=int(np.ptp(rows) + 1) if rows.size else 0,
                k_amb=k_amb, k_content=k_con, contrast=contrast)


def band_needed(res: CameraResult, target_contrast, lux, band_lum, content_lum=60.0):
    """Full-white band luminance needed to reach a contrast target at a given illuminance."""
    img, m, _ = ribbon_mask(res)
    per_nit = img[m].mean() / band_lum
    bg = res.ambient[m].mean() * room_luminance(lux) + res.content[m].mean() * content_lum
    return (target_contrast - 1) * bg / per_nit


def x_response(res: CameraResult, x_world: np.ndarray, width: float, col_bin: int):
    """Horizontal profile of the ribbon when a single band column (all rows) is lit.
    Returns (x positions, luminance profile along the ribbon's brightest image row)."""
    nbx, nby = res.nbx, res.nby
    p = np.zeros(nbx * nby)
    for r in range(nby):
        p[r * nbx + col_bin] = 1.0
    img = res.image(p)
    full, m, _ = ribbon_mask(res)
    # average over the ribbon rows, weighted by the full-white ribbon
    w = np.where(m, full, 0.0)
    prof = (img * w).sum(0) / np.maximum(w.sum(0), 1e-9)
    xs = np.nanmean(np.where(m, x_world, np.nan), axis=0)
    return xs, prof


def energy_width(xs, prof, frac=0.76):
    """Width holding the central `frac` of the light (0.76 = FWHM for a Gaussian); robust to noise."""
    ok = np.isfinite(xs) & np.isfinite(prof)
    xs, prof = xs[ok], np.clip(prof[ok], 0, None)
    o = np.argsort(xs); xs, prof = xs[o], prof[o]
    c = np.cumsum(prof)
    if c[-1] <= 0:
        return float("nan")
    c /= c[-1]
    lo = np.interp((1 - frac) / 2, c, xs); hi = np.interp(1 - (1 - frac) / 2, c, xs)
    return float(hi - lo)


def psf_width(res, cols):
    """Mean energy width over several single-column responses."""
    w = []
    for cb in cols:
        xs, pr = x_response(res, res.x_world, 0, cb)
        w.append(energy_width(xs, pr))
    return float(np.nanmedian(w))


def fwhm(xs, prof):
    ok = np.isfinite(xs)
    xs, prof = xs[ok], prof[ok]
    if prof.max() <= 0:
        return float("nan")
    i = int(np.argmax(prof)); half = prof[i] / 2
    l = i
    while l > 0 and prof[l] > half:
        l -= 1
    r = i
    while r < len(prof) - 1 and prof[r] > half:
        r += 1
    return float(abs(xs[r] - xs[l]))


def design_pattern(res: CameraResult, target: np.ndarray, weight=None, smooth=1e-3, iters=600):
    """Solve for band drive levels p in [0, 1] so that A p matches the target image (cd/m^2)
    on the ribbon. Projected gradient (FISTA) on the normal equations."""
    A = res.A.astype(np.float64)
    t = target.reshape(-1)
    if weight is not None:
        w = weight.reshape(-1).astype(np.float64)
        A = A * w[:, None]; t = t * w
    AtA = A.T @ A
    Atb = A.T @ t
    n = AtA.shape[0]
    # smoothness along x within each row of bins
    D = np.zeros((n, n))
    for r in range(res.nby):
        for c in range(res.nbx - 1):
            i = r * res.nbx + c
            D[i, i] += 1; D[i + 1, i + 1] += 1; D[i, i + 1] -= 1; D[i + 1, i] -= 1
    H = AtA + smooth * np.trace(AtA) / n * D
    L = np.linalg.eigvalsh(H).max()
    p = np.full(n, 0.5); y = p.copy(); tk = 1.0
    for _ in range(iters):
        g = H @ y - Atb
        pn = np.clip(y - g / L, 0, 1)
        tn = (1 + math.sqrt(1 + 4 * tk * tk)) / 2
        y = pn + (tk - 1) / tn * (pn - p)
        p, tk = pn, tn
    return p
