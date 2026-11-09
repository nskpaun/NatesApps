"""Monte Carlo path tracer for the light-ribbon scene (numpy, vectorised).

Two entry points:

* ``trace_camera`` traces paths backward from a pinhole eye. Everything is linear in the
  light sources, so one trace returns three separate "channels":
    - ``A``: a transfer matrix (pixels x band bins). Image luminance = A @ pattern, where
      pattern is the drive level (0..1) of each band bin and A already includes the band's
      full-white luminance. This is what lets software design the pattern.
    - ``ambient``: image luminance per 1 cd/m^2 of uniform room/sky luminance.
    - ``content``: image luminance per 1 cd/m^2 of main-screen content luminance.
* ``trace_forward`` emits rays from the band and reports where the flux ends up.

Radiometry: surfaces use Lambert + GGX microfacet BRDFs with multiple importance between the
two lobes; the reflector is an ideal specular mirror. Luminance is conserved along a path, so
the camera result is in cd/m^2 directly.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from .scene import MATERIALS, MAT_IDS, Scene, SCREEN_Z

MAT_LIST = list(MATERIALS.values())
_KIND = np.array([{"brdf": 0, "mirror": 1, "emit_band": 2, "emit_screen": 3}[m.kind] for m in MAT_LIST])
_RHO = np.array([m.rho_d for m in MAT_LIST])
_F0 = np.array([m.f0 for m in MAT_LIST])
_ALPHA = np.array([max(m.alpha, 1e-3) for m in MAT_LIST])
_REFL = np.array([m.reflectance for m in MAT_LIST])
# probability of sampling the specular lobe
_PSPEC = np.where(_RHO + _F0 > 0, np.maximum(_F0, 0.0) / np.maximum(_RHO + _F0, 1e-9), 0.0)
_PSPEC = np.where(_RHO == 0, 1.0, np.clip(_PSPEC * 2.0, 0.1, 0.9))

ESCAPE = -1
CAP = -2


# ---------------------------------------------------------------- geometry
def intersect(scene: Scene, o: np.ndarray, d: np.ndarray):
    """Nearest hit for rays o + t d (o, d: (N, 3) as x, y, z). Returns t, seg index, and
    whether the ray hit the segment's +normal side. Segment -1 = escape, -2 = end cap."""
    N = o.shape[0]
    oz, oy, ox = o[:, 2:3], o[:, 1:2], o[:, 0:1]
    dz, dy, dx = d[:, 2:3], d[:, 1:2], d[:, 0:1]
    p0z, p0y = scene.p0[None, :, 0], scene.p0[None, :, 1]
    ez = (scene.p1[:, 0] - scene.p0[:, 0])[None, :]
    ey = (scene.p1[:, 1] - scene.p0[:, 1])[None, :]
    denom = dz * ey - dy * ez
    wz, wy = p0z - oz, p0y - oy
    with np.errstate(divide="ignore", invalid="ignore"):
        t = (wz * ey - wy * ez) / denom
        s = (wz * dy - wy * dz) / denom
    ok = (np.abs(denom) > 1e-12) & (t > 1e-6) & (s >= 0) & (s <= 1)
    xh = ox + np.where(np.isfinite(t), t, 0.0) * dx
    half = scene.design.width / 2
    ok &= ~scene.finite[None, :] | (np.abs(xh) <= half)
    t = np.where(ok, t, np.inf)
    seg = np.argmin(t, axis=1)
    tbest = t[np.arange(N), seg]
    seg = np.where(np.isfinite(tbest), seg, ESCAPE)

    # end caps at x = +-half: only inside the cove polygon
    with np.errstate(divide="ignore", invalid="ignore"):
        tc = np.where(d[:, 0] > 0, (half - o[:, 0]) / d[:, 0], (-half - o[:, 0]) / d[:, 0])
    tc = np.where((np.abs(d[:, 0]) > 1e-12) & (tc > 1e-6), tc, np.inf)
    tcf = np.where(np.isfinite(tc), tc, 0.0)
    zc = o[:, 2] + tcf * d[:, 2]
    yc = o[:, 1] + tcf * d[:, 1]
    inside = _in_poly(zc, yc, scene.cap_poly) & np.isfinite(tc)
    use_cap = inside & (tc < tbest)
    tbest = np.where(use_cap, tc, tbest)
    seg = np.where(use_cap, CAP, seg)

    n2 = scene.normals
    nsel = n2[np.clip(seg, 0, None)]
    front = (d[:, 2] * nsel[:, 0] + d[:, 1] * nsel[:, 1]) < 0
    return tbest, seg, front


def _in_poly(z, y, poly):
    res = np.zeros(z.shape, bool)
    zf = np.where(np.isfinite(z), z, 1e9)
    yf = np.where(np.isfinite(y), y, 1e9)
    k = len(poly)
    for i in range(k):
        (z1, y1), (z2, y2) = poly[i], poly[(i + 1) % k]
        cond = (y1 > yf) != (y2 > yf)
        with np.errstate(divide="ignore", invalid="ignore"):
            zint = z1 + (yf - y1) * (z2 - z1) / (y2 - y1)
        res ^= cond & (zf < zint)
    return res


# ---------------------------------------------------------------- BRDF
def _ggx_D(nh, a):
    a2 = a * a
    den = nh * nh * (a2 - 1) + 1
    return a2 / (math.pi * den * den)


def _smith_G1(nv, a):
    a2 = a * a
    return 2 * nv / (nv + np.sqrt(a2 + (1 - a2) * nv * nv))


def sample_brdf(mat, wo_l, rng):
    """Sample an incoming direction in the local frame (z = normal). wo_l: (N,3) toward the
    viewer side. Returns wi_l (N,3) and weight = f * cos / pdf (N,)."""
    N = wo_l.shape[0]
    rho, f0, a, ps = _RHO[mat], _F0[mat], _ALPHA[mat], _PSPEC[mat]
    u1, u2, u3 = rng.random(N), rng.random(N), rng.random(N)
    choose_spec = u3 < ps
    # GGX half vector
    cth = np.sqrt((1 - u1) / (u1 * (a * a - 1) + 1))
    sth = np.sqrt(np.maximum(0, 1 - cth * cth))
    ph = 2 * math.pi * u2
    h = np.stack([sth * np.cos(ph), sth * np.sin(ph), cth], 1)
    wi_s = 2 * np.sum(wo_l * h, 1, keepdims=True) * h - wo_l
    # cosine hemisphere
    r = np.sqrt(u1)
    wi_d = np.stack([r * np.cos(ph), r * np.sin(ph), np.sqrt(np.maximum(0, 1 - u1))], 1)
    wi = np.where(choose_spec[:, None], wi_s, wi_d)

    nl = wi[:, 2]
    nv = np.clip(wo_l[:, 2], 1e-6, 1)
    valid = nl > 1e-6
    nl = np.clip(nl, 1e-6, 1)
    hv = wi + wo_l
    hv /= np.linalg.norm(hv, axis=1, keepdims=True) + 1e-12
    nh = np.clip(hv[:, 2], 1e-6, 1)
    vh = np.clip(np.sum(wo_l * hv, 1), 1e-6, 1)
    D = _ggx_D(nh, a)
    G = _smith_G1(nv, a) * _smith_G1(nl, a)
    F = f0 + (1 - f0) * (1 - vh) ** 5
    f_spec = F * D * G / (4 * nv * nl)
    f_diff = rho / math.pi * (1 - F)
    pdf_spec = D * nh / (4 * vh)
    pdf_diff = nl / math.pi
    pdf = ps * pdf_spec + (1 - ps) * pdf_diff
    w = (f_spec + f_diff) * nl / np.maximum(pdf, 1e-12)
    w = np.where(valid, w, 0.0)
    return wi, w


def lcd_emission(design, d_world, x_hit):
    """Relative luminance of the band/screen seen along ray direction d (toward the screen)."""
    cos_t = np.clip(-d_world[:, 2], 0, 1)
    g = cos_t ** design.lcd_exponent
    if design.louver_deg is not None:
        # louvers in the horizontal plane: transmission falls linearly with tan(horizontal angle)
        th = np.abs(d_world[:, 0]) / np.maximum(cos_t, 1e-6)
        g = g * design.louver_t * np.clip(1 - th / math.tan(math.radians(design.louver_deg)), 0, 1)
    return g


# ---------------------------------------------------------------- camera
@dataclass
class CameraResult:
    A: np.ndarray          # (H*W, nbins) cd/m^2 per unit drive of each band bin
    ambient: np.ndarray    # (H, W) per 1 cd/m^2 of room luminance
    content: np.ndarray    # (H, W) per 1 cd/m^2 of screen-content luminance
    H: int
    W: int
    nbx: int
    nby: int
    first_hit: np.ndarray  # (H, W) segment index seen first (for masks/labels)
    cam: dict
    x_world: np.ndarray = None  # (H, W) mean x (mm) of the first surface each pixel sees

    def image(self, pattern):
        return (self.A @ pattern).reshape(self.H, self.W)


def camera_rays(eye, target, hfov_deg, W, H, rng, spp):
    eye = np.asarray(eye, float)
    fwd = np.asarray(target, float) - eye
    fwd /= np.linalg.norm(fwd)
    right = np.cross(fwd, [0, 1, 0]); right /= np.linalg.norm(right)
    up = np.cross(right, fwd)
    tw = math.tan(math.radians(hfov_deg) / 2)
    th = tw * H / W
    pix = np.repeat(np.arange(W * H), spp)
    px = (pix % W + rng.random(pix.size)) / W * 2 - 1
    py = 1 - (pix // W + rng.random(pix.size)) / H * 2
    d = fwd[None] + px[:, None] * tw * right[None] + py[:, None] * th * up[None]
    d /= np.linalg.norm(d, axis=1, keepdims=True)
    o = np.repeat(eye[None], pix.size, 0)
    return o, d, pix


def _frame(n2):
    """World-space normal (0, ny, nz) from 2D (z, y) normals, plus tangents."""
    n = np.stack([np.zeros(len(n2)), n2[:, 1], n2[:, 0]], 1)
    t = np.zeros_like(n); t[:, 0] = 1
    b = np.cross(n, t)
    return n, t, b


def trace_camera(scene: Scene, *, W=320, H=110, spp=48, hfov=78.0, target=(0, 60, -40),
                 eye=None, nbx=128, nby=4, max_bounce=5, seed=1, chunk=400_000):
    d_ = scene.design
    eye = d_.eye if eye is None else eye
    rng = np.random.default_rng(seed)
    o_all, d_all, pix_all = camera_rays(eye, target, hfov, W, H, rng, spp)
    nb = nbx * nby
    A = np.zeros(W * H * nb)
    amb = np.zeros(W * H)
    con = np.zeros(W * H)
    first = np.full(W * H, ESCAPE)
    xsum = np.zeros(W * H); xcnt = np.zeros(W * H)
    half = d_.width / 2
    n2 = scene.normals
    for c0 in range(0, len(pix_all), chunk):
        o = o_all[c0:c0 + chunk].copy(); d = d_all[c0:c0 + chunk].copy(); pix = pix_all[c0:c0 + chunk]
        beta = np.full(len(pix), 1.0 / spp)
        alive = np.ones(len(pix), bool)
        for bounce in range(max_bounce):
            idx = np.nonzero(alive)[0]
            if idx.size == 0:
                break
            oo, dd = o[idx], d[idx]
            t, seg, front = intersect(scene, oo, dd)
            if bounce == 0:
                first[pix[idx]] = seg
                okx = seg != ESCAPE
                np.add.at(xsum, pix[idx[okx]], oo[okx, 0] + t[okx] * dd[okx, 0])
                np.add.at(xcnt, pix[idx[okx]], 1)
            esc = seg == ESCAPE
            np.add.at(amb, pix[idx[esc]], beta[idx[esc]])
            alive[idx[esc]] = False
            hit = ~esc
            ih, th_, sh, fh = idx[hit], t[hit], seg[hit], front[hit]
            p = oo[hit] + th_[:, None] * dd[hit]
            dh = dd[hit]
            iscap = sh == CAP
            mat = np.where(iscap, MAT_IDS["graphite"],
                           np.where(fh, scene.mat_front[np.clip(sh, 0, None)], scene.mat_back[np.clip(sh, 0, None)]))
            kind = _KIND[mat]
            # emitters
            e_band = kind == 2
            if e_band.any():
                g = lcd_emission(d_, dh[e_band], p[e_band, 0])
                xs = p[e_band, 0]
                g = np.where(np.abs(xs) < d_.seam_gap / 2, 0.0, g)
                bx = np.clip(((xs + half) / d_.width * nbx).astype(int), 0, nbx - 1)
                by = np.clip(((p[e_band, 1] - scene.band_y0) / (scene.band_y1 - scene.band_y0) * nby).astype(int), 0, nby - 1)
                key = pix[ih[e_band]] * nb + by * nbx + bx
                A += np.bincount(key, weights=beta[ih[e_band]] * g * d_.band_lum, minlength=A.size)
            e_scr = kind == 3
            if e_scr.any():
                g = lcd_emission(d_, dh[e_scr], p[e_scr, 0])
                np.add.at(con, pix[ih[e_scr]], beta[ih[e_scr]] * g)
            alive[ih[kind >= 2]] = False
            # mirror
            mir = kind == 1
            n2h = np.where(iscap[:, None], np.array([[0.0, 0.0]]), n2[np.clip(sh, 0, None)])
            nw = np.stack([np.zeros(len(sh)), n2h[:, 1], n2h[:, 0]], 1)
            capn = np.stack([-np.sign(dh[:, 0]), np.zeros(len(sh)), np.zeros(len(sh))], 1)
            nw = np.where(iscap[:, None], capn, nw)
            nw = np.where(fh[:, None] | iscap[:, None], nw, -nw)   # shading normal faces the ray origin
            if mir.any():
                dm = dh[mir]; nm = nw[mir]
                newd = dm - 2 * np.sum(dm * nm, 1, keepdims=True) * nm
                d[ih[mir]] = newd
                o[ih[mir]] = p[mir] + nm * 1e-3
                beta[ih[mir]] *= _REFL[mat[mir]]
            br = kind == 0
            if br.any():
                nb_ = nw[br]
                tx = np.zeros_like(nb_); tx[:, 0] = 1
                tx = np.where(iscap[br][:, None], np.array([[0, 0, 1.0]]), tx)
                bb = np.cross(nb_, tx)
                wo = -dh[br]
                wo_l = np.stack([np.sum(wo * tx, 1), np.sum(wo * bb, 1), np.sum(wo * nb_, 1)], 1)
                wi_l, w = sample_brdf(mat[br], wo_l, rng)
                wi = wi_l[:, :1] * tx + wi_l[:, 1:2] * bb + wi_l[:, 2:3] * nb_
                d[ih[br]] = wi
                o[ih[br]] = p[br] + nb_ * 1e-3
                beta[ih[br]] *= w
                dead = w <= 0
                alive[ih[br][dead]] = False
            # Russian roulette after 3 bounces
            if bounce >= 2:
                live = np.nonzero(alive)[0]
                q = np.clip(beta[live] * spp * 4, 0.05, 1)
                kill = rng.random(live.size) > q
                alive[live[kill]] = False
                beta[live[~kill]] /= q[~kill]
    return CameraResult(A.reshape(W * H, nb).astype(np.float32), amb.reshape(H, W), con.reshape(H, W),
                        H, W, nbx, nby, first.reshape(H, W),
                        dict(eye=eye, target=target, hfov=hfov),
                        (xsum / np.maximum(xcnt, 1)).reshape(H, W))


# ---------------------------------------------------------------- forward flux budget
def trace_forward(scene: Scene, n=400_000, seed=2, max_bounce=6):
    """Emit from the band (full white) and tally where the flux ends up.
    Returns fractions keyed by the label of the absorbing surface or the escape direction."""
    d_ = scene.design
    rng = np.random.default_rng(seed)
    half = d_.width / 2
    x = (rng.random(n) * 2 - 1) * half
    x = np.where(np.abs(x) < d_.seam_gap / 2, half * 0.9, x)
    y = scene.band_y0 + rng.random(n) * (scene.band_y1 - scene.band_y0)
    o = np.stack([x, y, np.full(n, SCREEN_Z + 1e-3)], 1)
    # cosine-weighted directions, then reweight by the LCD profile
    u1, u2 = rng.random(n), rng.random(n)
    r = np.sqrt(u1); ph = 2 * math.pi * u2
    d = np.stack([r * np.cos(ph), r * np.sin(ph), np.sqrt(1 - u1)], 1)
    beta = lcd_emission(d_, -d, x)
    beta /= beta.sum()
    tally: dict[str, float] = {}
    alive = np.ones(n, bool)
    labels = scene.labels
    n2 = scene.normals
    for bounce in range(max_bounce):
        idx = np.nonzero(alive)[0]
        if idx.size == 0:
            break
        t, seg, front = intersect(scene, o[idx], d[idx])
        esc = seg == ESCAPE
        dd = d[idx]
        for name, m in (("escapes up into the room", esc & (dd[:, 1] > 0)),
                        ("escapes sideways/down", esc & (dd[:, 1] <= 0))):
            tally[name] = tally.get(name, 0) + beta[idx[m]].sum()
        alive[idx[esc]] = False
        hit = ~esc
        ih, sh, fh = idx[hit], seg[hit], front[hit]
        p = o[ih] + t[hit][:, None] * d[ih]
        iscap = sh == CAP
        mat = np.where(iscap, MAT_IDS["graphite"],
                       np.where(fh, scene.mat_front[np.clip(sh, 0, None)], scene.mat_back[np.clip(sh, 0, None)]))
        kind = _KIND[mat]
        nw = np.stack([np.zeros(len(sh)), n2[np.clip(sh, 0, None), 1], n2[np.clip(sh, 0, None), 0]], 1)
        nw = np.where(iscap[:, None], np.stack([-np.sign(d[ih, 0]), 0 * sh, 0 * sh], 1), nw)
        nw = np.where(fh[:, None] | iscap[:, None], nw, -nw)
        # absorbed fraction per surface
        refl = np.zeros(len(ih))
        refl = np.where(kind == 1, _REFL[mat], refl)
        newd = d[ih].copy()
        mir = kind == 1
        newd[mir] = d[ih][mir] - 2 * np.sum(d[ih][mir] * nw[mir], 1, keepdims=True) * nw[mir]
        br = kind == 0
        if br.any():
            nb_ = nw[br]
            tx = np.zeros_like(nb_); tx[:, 0] = 1
            tx = np.where(iscap[br][:, None], np.array([[0, 0, 1.0]]), tx)
            bb = np.cross(nb_, tx)
            wo = -d[ih][br]
            wo_l = np.stack([np.sum(wo * tx, 1), np.sum(wo * bb, 1), np.sum(wo * nb_, 1)], 1)
            wi_l, w = sample_brdf(mat[br], wo_l, rng)
            w = np.clip(w, 0, 1)
            newd[br] = wi_l[:, :1] * tx + wi_l[:, 1:2] * bb + wi_l[:, 2:3] * nb_
            refl[br] = w
        absorbed = beta[ih] * (1 - refl)
        lab = np.array([("end cap" if s == CAP else labels[s]) for s in sh])
        for L in np.unique(lab):
            tally["absorbed: " + L] = tally.get("absorbed: " + L, 0) + absorbed[lab == L].sum()
        beta[ih] *= refl
        d[ih] = newd
        o[ih] = p + nw * 1e-3
        alive[ih[refl <= 0]] = False
    rest = beta[alive].sum()
    if rest > 0:
        tally["still bouncing"] = rest
    return tally
