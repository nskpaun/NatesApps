"""Path tracer for the light-ribbon cross-section.

The station's optics are extruded along x (the long axis of the display), so the geometry is a set of 2D
line segments in the (z, y) plane: z points at the user, y is up, units are mm. Rays are fully 3D: a ray's
x component matters for the LCD's angular falloff, for the satin surface's lobe and for how far a pattern
smears sideways, but it never changes which surface the ray meets.

Rays are traced BACKWARD from the eye. Every path ends on one of three sources, and the three are kept
apart so a single trace can be recombined for any band brightness, screen content and room:

    band     the feed rows of the screen (the pixels that make the ribbon)          -> per named pattern, RGB
    content  the rest of the screen (whatever the user is working on)               -> per unit luminance
    ambient  the room (uniform luminance sky + a desk it lights)                    -> per unit sky luminance

Radiometry is in "luminance-like" units: a white band value of 1.0 means the panel's on-axis white. Multiply
by the panel's nits afterwards. RGB is linear and unweighted (white = 1, 1, 1); use `luma()` for nits.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

EPS = 1e-6
LUMA = np.array([0.2126, 0.7152, 0.0722])          # Rec. 709 luminance weights for linear RGB


def luma(rgb):
    return np.asarray(rgb) @ LUMA


# ----------------------------------------------------------------------------------------------- materials
@dataclass
class Material:
    name: str
    kind: str                      # "screen" | "mirror" | "ggx" | "matte" | "black"
    refl: tuple = (0.0, 0.0, 0.0)  # mirror reflectance, GGX F0, or matte albedo (linear RGB)
    ax: float = 0.1                # GGX roughness along x (the extrusion / brushing direction)
    at: float = 0.1                # GGX roughness across it (in the cross-section plane)
    diffuse: tuple = (0.0, 0.0, 0.0)   # extra Lambertian term under a GGX lobe (haze, dirt)


BLACK = Material("black", "black")


# ----------------------------------------------------------------------------------------------- LCD model
@dataclass
class Lcd:
    """Angular emission of the panel, relative to on-axis white.

    L(theta) / L(0) = exp(kappa * (cos(theta) - 1)), the form Zele et al. (arXiv 2007.11151) fitted to two 24"
    IPS desktop monitors measured out to 60 degrees: kappa 2.6 to 3.4, about the same vertically and
    horizontally. 2.9 gives 0.91 / 0.68 / 0.43 / 0.24 at 15 / 30 / 45 / 60 degrees. Beyond 60 degrees this is an
    extrapolation. Luminance, not intensity: a Lambertian emitter would be 1.0 at every angle (kappa = 0).
    """
    kappa_v: float = 2.9
    kappa_h: float = 2.9

    def rel(self, dx, dy, dz):
        """Relative luminance for unit directions leaving the screen (dz > 0 is the screen normal)."""
        dz = np.clip(dz, 0.0, 1.0)
        fv = np.exp(self.kappa_v * (dz - 1))
        fh = np.exp(self.kappa_h * (dz - 1))
        s2 = dx * dx + dy * dy
        wv = np.where(s2 > 1e-12, dy * dy / np.maximum(s2, 1e-12), 0.5)   # sin^2(azimuth): 1 = vertical plane
        return wv * fv + (1 - wv) * fh


# ----------------------------------------------------------------------------------------------- scene
@dataclass
class Band:
    """A horizontal strip of the screen with its own patterns. y0..y1 in mm, patterns are sampled along x."""
    y0: float
    y1: float
    x0: float
    x1: float
    patterns: dict = field(default_factory=dict)   # name -> array [nx, 3] or [ny, nx, 3], linear RGB, 0..1
    tag: str = "band"                               # "band" (feeds the ribbon) or "echo" (visible, decorative)


@dataclass
class Scene:
    a: np.ndarray            # [n, 2] segment starts (z, y)
    b: np.ndarray            # [n, 2] segment ends
    na: np.ndarray           # [n, 2] shading normal at a (unit, points to the FRONT side)
    nb: np.ndarray           # [n, 2] shading normal at b
    front: np.ndarray        # [n] material index hit from the front side
    back: np.ndarray         # [n] material index hit from the back side
    materials: list
    labels: list
    lcd: Lcd
    bands: list              # Band objects on the screen plane (z = 0)
    screen_x: tuple          # (x0, x1) lit width of the screen
    sky_down: float = 0.25   # luminance of whatever is below the horizon, relative to the sky
    meta: dict = field(default_factory=dict)


class Builder:
    """Collects segments. The front side of a segment a->b is on its LEFT when walking from a to b
    in a (z right, y up) drawing, i.e. normal = (-(by - ay), bz - az) / length."""

    def __init__(self):
        self.a, self.b, self.na, self.nb, self.front, self.back, self.labels = [], [], [], [], [], [], []
        self.materials = [BLACK]

    def mat(self, m: Material) -> int:
        for i, x in enumerate(self.materials):
            if x is m:
                return i
        self.materials.append(m)
        return len(self.materials) - 1

    def seg(self, a, b, front: Material, back: Material = BLACK, label=""):
        a, b = np.asarray(a, float), np.asarray(b, float)
        e = b - a
        n = np.array([-e[1], e[0]]) / np.hypot(*e)
        self.a.append(a); self.b.append(b); self.na.append(n); self.nb.append(n)
        self.front.append(self.mat(front)); self.back.append(self.mat(back)); self.labels.append(label)

    def curve(self, pts, front: Material, back: Material = BLACK, label="", normals=None):
        """Polyline with smooth (interpolated) normals, so a curved mirror or cove has no facet banding."""
        pts = np.asarray(pts, float)
        if normals is None:
            t = np.gradient(pts, axis=0)
            normals = np.stack([-t[:, 1], t[:, 0]], 1)
        normals = normals / np.linalg.norm(normals, axis=1, keepdims=True)
        for i in range(len(pts) - 1):
            self.a.append(pts[i]); self.b.append(pts[i + 1])
            self.na.append(normals[i]); self.nb.append(normals[i + 1])
            self.front.append(self.mat(front)); self.back.append(self.mat(back)); self.labels.append(label)

    def build(self, lcd, bands, screen_x, **kw) -> Scene:
        return Scene(np.array(self.a), np.array(self.b), np.array(self.na), np.array(self.nb),
                     np.array(self.front), np.array(self.back), self.materials, self.labels, lcd, bands,
                     screen_x, **kw)


# ----------------------------------------------------------------------------------------------- intersection
def intersect(scene: Scene, o, d):
    """Nearest hit of rays (o, d: [n, 3] as x, y, z) with the extruded segments.

    Returns t [n] (inf = miss), segment index [n], and the segment parameter s [n]."""
    pz, py = o[:, 2:3], o[:, 1:2]
    vz, vy = d[:, 2:3], d[:, 1:2]
    az, ay = scene.a[None, :, 0], scene.a[None, :, 1]
    ez, ey = (scene.b - scene.a)[None, :, 0], (scene.b - scene.a)[None, :, 1]
    den = vz * ey - vy * ez
    ok = np.abs(den) > 1e-12
    den = np.where(ok, den, 1.0)
    wz, wy = az - pz, ay - py
    t = (wz * ey - wy * ez) / den
    s = (wz * vy - wy * vz) / den
    ok &= (t > EPS) & (s >= -1e-9) & (s <= 1 + 1e-9)
    t = np.where(ok, t, np.inf)
    idx = np.argmin(t, axis=1)
    rows = np.arange(len(o))
    return t[rows, idx], idx, np.clip(s[rows, idx], 0.0, 1.0)


# ----------------------------------------------------------------------------------------------- BSDF sampling
def _ggx_reflect(wo, ax, at, rng):
    """Sample a GGX visible normal (Heitz 2018) and reflect. Local frame: x = extrusion axis, y = in-plane
    tangent, z = surface normal. Returns wi and the scalar weight G2 / G1 (Fresnel applied by the caller,
    with cos_d = wo . m, also returned)."""
    n = len(wo)
    u1, u2 = rng.random(n), rng.random(n)
    vh = np.stack([ax * wo[:, 0], at * wo[:, 1], wo[:, 2]], 1)
    vh /= np.linalg.norm(vh, axis=1, keepdims=True)
    lensq = vh[:, 0] ** 2 + vh[:, 1] ** 2
    inv = 1.0 / np.sqrt(np.maximum(lensq, 1e-20))
    t1 = np.where((lensq > 1e-20)[:, None], np.stack([-vh[:, 1] * inv, vh[:, 0] * inv, np.zeros(n)], 1),
                  np.array([1.0, 0.0, 0.0]))
    t2 = np.cross(vh, t1)
    r = np.sqrt(u1)
    phi = 2 * np.pi * u2
    p1, p2 = r * np.cos(phi), r * np.sin(phi)
    s = 0.5 * (1 + vh[:, 2])
    p2 = (1 - s) * np.sqrt(np.maximum(0, 1 - p1 * p1)) + s * p2
    nh = p1[:, None] * t1 + p2[:, None] * t2 + np.sqrt(np.maximum(0, 1 - p1 * p1 - p2 * p2))[:, None] * vh
    m = np.stack([ax * nh[:, 0], at * nh[:, 1], np.maximum(nh[:, 2], 1e-9)], 1)
    m /= np.linalg.norm(m, axis=1, keepdims=True)
    cos_d = np.sum(wo * m, 1)
    wi = 2 * cos_d[:, None] * m - wo

    def lam(w):
        t2_ = (ax * w[:, 0]) ** 2 + (at * w[:, 1]) ** 2
        return 0.5 * (-1 + np.sqrt(1 + t2_ / np.maximum(w[:, 2] ** 2, 1e-20)))

    lo, li = lam(wo), lam(wi)
    weight = np.where(wi[:, 2] > 0, (1 + lo) / (1 + lo + li), 0.0)
    return wi, weight, cos_d


def _cosine(n, rng):
    u1, u2 = rng.random(n), rng.random(n)
    r, phi = np.sqrt(u1), 2 * np.pi * u2
    return np.stack([r * np.cos(phi), r * np.sin(phi), np.sqrt(np.maximum(0, 1 - u1))], 1)


# ----------------------------------------------------------------------------------------------- tracer
def _pattern_lookup(p, x, y, band: Band):
    """Nearest-sample lookup of a band pattern at screen positions (x, y)."""
    p = np.asarray(p, float)
    if p.ndim == 1:
        return np.broadcast_to(p, (len(x), 3))
    u = (x - band.x0) / (band.x1 - band.x0)
    if p.ndim == 2:
        i = np.clip((u * len(p)).astype(int), 0, len(p) - 1)
        return p[i]
    v = (y - band.y0) / (band.y1 - band.y0)
    j = np.clip((v * p.shape[0]).astype(int), 0, p.shape[0] - 1)
    i = np.clip((u * p.shape[1]).astype(int), 0, p.shape[1] - 1)
    return p[j, i]


def trace(scene: Scene, o, d, rng, max_bounces=10, collect_hits=False):
    """Radiance arriving along rays that START at o and travel along d (the eye's lines of sight).

    Returns a dict:
      band[name]  [n, 3]   linear RGB, in units of the panel's on-axis white, for each pattern of the feed band
      echo[name]  [n, 3]   same for the visible "echo" band (decorative, on the open screen)
      content     [n, 3]   per unit luminance of the remaining screen area
      ambient     [n, 3]   per unit sky luminance
      hits (optional)      per feed-band arrival: ray index, x on the band, y on the band, RGB weight
    """
    n = len(o)
    o = np.array(o, float)
    d = np.array(d, float)
    d /= np.linalg.norm(d, axis=1, keepdims=True)
    T = np.ones((n, 3))
    alive = np.ones(n, bool)
    names = sorted({k for b in scene.bands for k in b.patterns})
    out = {"band": {k: np.zeros((n, 3)) for k in names}, "echo": {k: np.zeros((n, 3)) for k in names},
           "content": np.zeros((n, 3)), "ambient": np.zeros((n, 3))}
    hits = []
    mat_kind = np.array([m.kind for m in scene.materials])
    seg_t = scene.b - scene.a
    seg_t = seg_t / np.linalg.norm(seg_t, axis=1, keepdims=True)

    for _ in range(max_bounces + 1):
        ia = np.flatnonzero(alive)
        if len(ia) == 0:
            break
        oo, dd = o[ia], d[ia]
        t, idx, s = intersect(scene, oo, dd)
        miss = ~np.isfinite(t)
        if miss.any():                                              # left the station: sees the room
            im = ia[miss]
            sky = np.where(dd[miss, 1] >= 0, 1.0, scene.sky_down)
            out["ambient"][im] += T[im] * sky[:, None]
            alive[im] = False
        hit = ~miss
        ia, oo, dd, t, idx, s = ia[hit], oo[hit], dd[hit], t[hit], idx[hit], s[hit]
        if len(ia) == 0:
            break
        p = oo + t[:, None] * dd
        n2 = (1 - s)[:, None] * scene.na[idx] + s[:, None] * scene.nb[idx]          # (z, y) shading normal
        n2 /= np.linalg.norm(n2, axis=1, keepdims=True)
        ng = np.stack([-seg_t[idx, 1], seg_t[idx, 0]], 1)                           # geometric normal
        facing = -(dd[:, 2] * ng[:, 0] + dd[:, 1] * ng[:, 1])                       # > 0: hit from the front
        mi = np.where(facing > 0, scene.front[idx], scene.back[idx])
        sgn = np.where(facing > 0, 1.0, -1.0)
        nrm = np.stack([np.zeros(len(ia)), n2[:, 1] * sgn, n2[:, 0] * sgn], 1)      # (x, y, z), faces the ray
        # a smooth normal must never face away from the incoming ray
        bad = np.sum(nrm * dd, 1) > -1e-6
        if bad.any():
            nrm[bad] = np.stack([np.zeros(bad.sum()), ng[bad, 1] * sgn[bad], ng[bad, 0] * sgn[bad]], 1)
        kind = mat_kind[mi]

        # ---- absorbers
        alive[ia[kind == "black"]] = False

        # ---- the screen: emits, reflects nothing
        k = kind == "screen"
        if k.any():
            ik = ia[k]
            px, py = p[k, 0], p[k, 1]
            f = scene.lcd.rel(-dd[k, 0], -dd[k, 1], -dd[k, 2])
            inx = (px >= scene.screen_x[0]) & (px <= scene.screen_x[1])
            claimed = np.zeros(len(ik), bool)
            for band in scene.bands:
                inb = inx & (py >= band.y0) & (py <= band.y1) & (px >= band.x0) & (px <= band.x1)
                if not inb.any():
                    continue
                claimed |= inb
                for name, pat in band.patterns.items():
                    c = _pattern_lookup(pat, px[inb], py[inb], band)
                    out[band.tag][name][ik[inb]] += T[ik[inb]] * c * f[inb, None]
                if collect_hits and band.tag == "band":
                    hits.append((ik[inb], px[inb], py[inb], T[ik[inb]] * f[inb, None]))
            rest = inx & ~claimed & (py >= scene.meta.get("content_y0", 1e9))
            out["content"][ik[rest]] += T[ik[rest]] * f[rest, None]
            alive[ik] = False

        # ---- mirror
        k = kind == "mirror"
        if k.any():
            ik = ia[k]
            dn = np.sum(dd[k] * nrm[k], 1)
            d[ik] = dd[k] - 2 * dn[:, None] * nrm[k]
            o[ik] = p[k] + nrm[k] * 1e-5
            T[ik] *= np.array([scene.materials[m].refl for m in mi[k]])

        # ---- satin metal (GGX lobe + optional Lambertian haze) and matte surfaces
        for kd in ("ggx", "matte"):
            k = kind == kd
            if not k.any():
                continue
            ik = ia[k]
            nk = nrm[k]
            tx = np.broadcast_to(np.array([1.0, 0.0, 0.0]), nk.shape)       # extrusion axis
            ty = np.cross(nk, tx)                                           # in-plane tangent
            wo = -dd[k]
            wol = np.stack([np.sum(wo * tx, 1), np.sum(wo * ty, 1), np.sum(wo * nk, 1)], 1)
            mats = [scene.materials[m] for m in mi[k]]
            refl = np.array([m.refl for m in mats])
            if kd == "matte":
                wil = _cosine(len(ik), rng)
                w = refl
            else:
                dif = np.array([m.diffuse for m in mats])
                pd = dif.mean(1) / np.maximum(dif.mean(1) + refl.mean(1), 1e-9)
                choose_d = rng.random(len(ik)) < pd
                ax = np.array([m.ax for m in mats]); at = np.array([m.at for m in mats])
                wil, g, cos_d = _ggx_reflect(wol, ax, at, rng)
                fres = refl + (1 - refl) * (1 - np.clip(cos_d, 0, 1))[:, None] ** 5
                w = fres * g[:, None] / np.maximum(1 - pd, 1e-9)[:, None]
                if choose_d.any():
                    wil[choose_d] = _cosine(int(choose_d.sum()), rng)
                    w[choose_d] = dif[choose_d] / np.maximum(pd[choose_d], 1e-9)[:, None]
            dead = wil[:, 2] <= 1e-6
            w[dead] = 0.0
            d[ik] = wil[:, 0:1] * tx + wil[:, 1:2] * ty + wil[:, 2:3] * nk
            o[ik] = p[k] + nk * 1e-5
            T[ik] *= w
            alive[ik[dead]] = False

        alive &= T.max(1) > 1e-5
    if collect_hits:
        out["hits"] = hits
    return out


# ----------------------------------------------------------------------------------------------- cameras
def eye_rays(eye, targets):
    """Rays from the eye (x, y, z) through target points [n, 3]."""
    targets = np.asarray(targets, float)
    o = np.broadcast_to(np.asarray(eye, float), targets.shape).copy()
    return o, targets - o


def render(scene, eye, xs, ys, z_plane=0.0, spp=64, rng=None, max_bounces=10, chunk=40000, jitter=True):
    """Image of the plane z = z_plane as seen from the eye: pixel (j, i) looks at (xs[i], ys[j], z_plane).

    Returns the same dict as `trace`, with arrays shaped [len(ys), len(xs), 3] (mean over spp)."""
    rng = rng or np.random.default_rng(1)
    xs, ys = np.asarray(xs, float), np.asarray(ys, float)
    nx, ny = len(xs), len(ys)
    dx = (xs[1] - xs[0]) if nx > 1 else 0.0
    dy = (ys[1] - ys[0]) if ny > 1 else 0.0
    gx, gy = np.meshgrid(xs, ys)
    base = np.stack([gx.ravel(), gy.ravel(), np.full(nx * ny, z_plane)], 1)
    acc = None
    for _ in range(spp):
        for c0 in range(0, len(base), chunk):
            tg = base[c0:c0 + chunk].copy()
            if jitter:
                tg[:, 0] += (rng.random(len(tg)) - 0.5) * dx
                tg[:, 1] += (rng.random(len(tg)) - 0.5) * dy
            o, d = eye_rays(eye, tg)
            r = trace(scene, o, d, rng, max_bounces)
            if acc is None:
                acc = {"band": {k: np.zeros((nx * ny, 3)) for k in r["band"]},
                       "echo": {k: np.zeros((nx * ny, 3)) for k in r["echo"]},
                       "content": np.zeros((nx * ny, 3)), "ambient": np.zeros((nx * ny, 3))}
            sl = slice(c0, c0 + len(tg))
            for k in r["band"]:
                acc["band"][k][sl] += r["band"][k]
                acc["echo"][k][sl] += r["echo"][k]
            acc["content"][sl] += r["content"]
            acc["ambient"][sl] += r["ambient"]
    shape = (ny, nx, 3)
    return {"band": {k: v.reshape(shape) / spp for k, v in acc["band"].items()},
            "echo": {k: v.reshape(shape) / spp for k, v in acc["echo"].items()},
            "content": acc["content"].reshape(shape) / spp, "ambient": acc["ambient"].reshape(shape) / spp}
