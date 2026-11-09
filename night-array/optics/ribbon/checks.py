"""Checks of the tracer against cases with closed-form answers, plus one independent cross-check.

Run:  python -m ribbon.checks        (exits non-zero if any check fails)
"""
from __future__ import annotations

import sys

import numpy as np

from . import designs as D
from .trace import BLACK, Band, Builder, Lcd, Material, intersect, luma, trace

WHITE = {"white": np.array([1.0, 1.0, 1.0])}
BIG = (-1e7, 1e7)


def _result(name, got, want, tol):
    ok = abs(got - want) <= tol
    print(f"  {'ok  ' if ok else 'FAIL'}  {name}: got {got:.4f}, expected {want:.4f} (tolerance {tol:g})")
    return ok


def check_mirror():
    """A mirror shows the band at R x the panel's luminance at the emission angle. Nothing else."""
    lcd = Lcd()
    b = Builder()
    b.seg((0, 50), (0, 0), D.SCREEN, BLACK)
    b.seg((0, -100), (300, -100), Material("m", "mirror", (0.9,) * 3), BLACK)      # floor mirror, faces up
    sc = b.build(lcd, [Band(0, 50, *BIG, WHITE)], BIG)
    eye = np.array([[0.0, 150.0, 400.0]])
    # aim at the mirror image of the band centre (y = -225)
    tgt = np.array([[0.0, -225.0, 0.0]])
    r = trace(sc, eye, tgt - eye, np.random.default_rng(0))
    d = (tgt - eye)[0]
    d /= np.linalg.norm(d)
    want = 0.9 * float(lcd.rel(0.0, d[1], abs(d[2])))
    return _result("mirror image of the band", luma(r["band"]["white"][0]), want, 1e-6)


def check_view_factor():
    """Lambertian strip lighting a matte floor: L = rho * (sin(phi1) - sin(phi2)) / 2 (strip view factor)."""
    lcd = Lcd(kappa_v=0.0, kappa_h=0.0)
    rho, h, g, z0 = 0.5, 30.0, 40.0, 60.0
    b = Builder()
    b.seg((0, h), (0, 0), D.SCREEN, BLACK)
    b.seg((-50, -g), (500, -g), Material("floor", "matte", (rho,) * 3), BLACK)
    sc = b.build(lcd, [Band(0, h, *BIG, WHITE)], BIG)
    n = 400000
    eye = np.tile([0.0, 300.0, 500.0], (n, 1))
    tgt = np.tile([0.0, -g, z0], (n, 1))
    r = trace(sc, eye, tgt - eye, np.random.default_rng(1), max_bounces=1)
    got = luma(r["band"]["white"].mean(0))
    want = rho * 0.5 * (np.sin(np.arctan2(z0, g)) - np.sin(np.arctan2(z0, g + h)))
    return _result("matte floor under a Lambertian strip", got, want, 0.004 * want + 5e-4)


def _ggx_albedo(wo, ax, at, n=1200):
    """Directional albedo of the GGX lobe by brute-force quadrature of D * G2 / (4 cos_o cos_i)."""
    th = (np.arange(n) + 0.5) / n * np.pi / 2
    ph = (np.arange(2 * n) + 0.5) / (2 * n) * 2 * np.pi
    t, p = np.meshgrid(th, ph, indexing="ij")
    wi = np.stack([np.sin(t) * np.cos(p), np.sin(t) * np.sin(p), np.cos(t)], -1)
    h = wi + wo
    h /= np.linalg.norm(h, axis=-1, keepdims=True)
    d = 1 / (np.pi * ax * at * ((h[..., 0] / ax) ** 2 + (h[..., 1] / at) ** 2 + h[..., 2] ** 2) ** 2)
    lam = lambda w: 0.5 * (-1 + np.sqrt(1 + ((ax * w[..., 0]) ** 2 + (at * w[..., 1]) ** 2) / w[..., 2] ** 2))
    f = d / (1 + lam(wo) + lam(wi)) / (4 * wo[2] * wi[..., 2])
    return float((f * wi[..., 2] * np.sin(t)).sum() * (np.pi / 2 / n) * (np.pi / n))


def check_furnace():
    """A loss-free satin surface in a uniform room. The tracer samples the lobe; the reference integrates the
    same microfacet model on a grid without using the sampler. (Single-scatter GGX is not energy-conserving:
    it returns 0.97 at the default brushed roughness and 0.92 at 0.2, which makes the model slightly
    pessimistic about a real surface.)"""
    ok = True
    for ax, at in ((0.05, 0.14), (0.2, 0.2), (0.35, 0.35)):
        b = Builder()
        b.seg((-1e5, 0), (1e5, 0), Material("s", "ggx", (1.0,) * 3, ax, at), BLACK)
        sc = b.build(Lcd(), [], BIG, sky_down=1.0)
        n = 300000
        eye = np.tile([30.0, 100.0, 100.0], (n, 1))
        r = trace(sc, eye, np.tile([40.0, -100.0, -100.0], (n, 1)), np.random.default_rng(2))
        wo = np.array([-40.0, 100.0, 100.0]) / np.linalg.norm([40.0, 100.0, 100.0])   # x, in-plane tangent, normal
        ok &= _result(f"furnace, roughness {ax}/{at}", luma(r["ambient"].mean(0)), _ggx_albedo(wo, ax, at), 0.004)
    return ok


def check_smooth_limit():
    """As roughness goes to zero the satin surface becomes the mirror."""
    out = []
    for mat in (Material("m", "mirror", (0.8,) * 3), Material("s", "ggx", (0.8,) * 3, 1e-4, 1e-4)):
        b = Builder()
        b.seg((0, 50), (0, 0), D.SCREEN, BLACK)
        b.seg((0, -100), (300, -100), mat, BLACK)
        sc = b.build(Lcd(), [Band(0, 50, *BIG, WHITE)], BIG)
        eye = np.tile([0.0, 150.0, 400.0], (20000, 1))
        tgt = np.tile([0.0, -225.0, 0.0], (20000, 1))
        out.append(luma(trace(sc, eye, tgt - eye, np.random.default_rng(3))["band"]["white"].mean(0)))
    # Schlick Fresnel lifts the satin reflectance slightly at this 43 degree incidence: (1 - 0.8) * (1 - cos)^5
    return _result("roughness -> 0 equals the mirror", out[1], out[0] * (0.8 + 0.2 * (1 - np.cos(np.radians(43.2))) ** 5) / 0.8, 2e-3)


def check_forward_backward(n=600000):
    """Independent cross-check of the whole sill chain. Photons are emitted FORWARD from the feed rows
    (weighted by the panel's angular model), followed through the mirrors, and binned where they land on a
    matte-white cove: that gives illuminance E, and a matte surface has L = rho * E / pi. The backward tracer
    looks at the same cove from the eye. The two share only the segment intersector."""
    rho = 0.8
    sc = D.sill(cove="matte", echo=0.0)
    lab = np.array(sc.labels)
    cove = np.flatnonzero(lab == "cove")
    rng = np.random.default_rng(4)
    h = sc.bands[0].y1
    # forward: uniform positions on the band, directions uniform over the hemisphere (pdf 1 / 2pi)
    o = np.stack([np.zeros(n), rng.random(n) * h, np.full(n, 1e-4)], 1)
    u, phi = rng.random(n), 2 * np.pi * rng.random(n)
    st = np.sqrt(1 - u * u)
    d = np.stack([st * np.cos(phi), st * np.sin(phi), u], 1)
    w = sc.lcd.rel(d[:, 0], d[:, 1], d[:, 2]) * d[:, 2] * 2 * np.pi          # radiance * cos / pdf, per unit area
    kinds = np.array([m.kind for m in sc.materials])
    seg_len = np.linalg.norm(sc.b - sc.a, axis=1)
    flux = np.zeros(len(sc.a))
    alive = np.ones(n, bool)
    for _ in range(12):
        ia = np.flatnonzero(alive)
        if not len(ia):
            break
        t, idx, s = intersect(sc, o[ia], d[ia])
        hit = np.isfinite(t)
        alive[ia[~hit]] = False
        ia, t, idx = ia[hit], t[hit], idx[hit]
        e = sc.b[idx] - sc.a[idx]
        ng = np.stack([-e[:, 1], e[:, 0]], 1) / np.linalg.norm(e, axis=1, keepdims=True)
        facing = -(d[ia, 2] * ng[:, 0] + d[ia, 1] * ng[:, 1])
        mi = np.where(facing > 0, sc.front[idx], sc.back[idx])
        k = kinds[mi]
        on_cove = np.isin(idx, cove) & (facing > 0)
        np.add.at(flux, idx[on_cove], w[ia[on_cove]])
        mir = (k == "mirror")
        im = ia[mir]
        n3 = np.stack([np.zeros(mir.sum()), ng[mir, 1], ng[mir, 0]], 1) * np.sign(facing[mir])[:, None]
        o[im] = o[im] + t[mir, None] * d[im]
        d[im] = d[im] - 2 * np.sum(d[im] * n3, 1)[:, None] * n3
        o[im] += n3 * 1e-5
        w[im] *= np.array([sc.materials[m].refl[0] for m in mi[mir]])
        alive[ia[~mir]] = False
    # E on each cove segment (per unit panel luminance): flux per unit x-length = sum(w) * h / n
    e_seg = flux[cove] * h / n / seg_len[cove]
    l_fwd = rho * e_seg / np.pi
    # backward: look at the middle of each cove segment from the eye, first bounce only (no inter-reflection)
    mid = 0.5 * (sc.a[cove] + sc.b[cove])
    eye = np.array([0.0, sc.meta["eye"][1], sc.meta["eye"][0]])
    reps = 1500
    tg = np.repeat(np.stack([np.zeros(len(mid)), mid[:, 1], mid[:, 0]], 1), reps, 0)
    eo = np.tile(eye, (len(tg), 1))
    r = trace(sc, eo, tg - eo, np.random.default_rng(5), max_bounces=6)
    l_bwd = luma(r["band"]["white"]).reshape(len(mid), reps).mean(1)
    # compare the means over the part of the cove the eye can see (the apron hides the deepest part)
    seen = l_bwd > 0.25 * l_bwd.max()
    got, want = l_bwd[seen].mean(), l_fwd[seen].mean()
    return _result("sill: backward tracer vs forward photon count (matte cove)", got, want, 0.03 * want)


def main():
    print("ribbon tracer checks")
    ok = all([check_mirror(), check_view_factor(), check_furnace(), check_smooth_limit(), check_forward_backward()])
    print("all checks passed" if ok else "CHECKS FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
