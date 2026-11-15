"""Make the generated views agree before training: every surface (each wall, the floor, each furniture piece)
takes its appearance from ONE source picture, projected onto the blockout, then re-rendered from many cameras.
(Masking objects that spill past their blocks, using depth estimates of the pictures, was tried and fragmented surfaces more.)
  consistent.py NAME   reads chisel/NAME/images, writes chisel/NAME_c/{images,sparse/0}
A world with things that move away from their spot (C.LIFT) gets two sets from the same pictures: NAME_m as above, and
NAME_c without those things, the ground and wall behind them filled in; NAME_c/lifted.json lists them. Both sets have a
ring of views around each of those things, so every side of it is trained.
An outdoor world (C.OUT) also gets NAME_c/sky.json, the colour of its sky.
A part of an object that no picture shows takes the object's own paint: from its mirror image where it has one, else from
the nearest painted part. Where a thing was taken out, the floor and wall behind continue the paint around the gap.
"""
import sys, os, json, glob, shutil, subprocess, numpy as np
from PIL import Image, ImageFilter
from scipy.spatial.transform import Rotation
name = sys.argv[1]; sys.argv = [sys.argv[0], "prep"]
import chisel_ring as C
B = C.B; W, H = B.W, B.H
objs = C.objs
NS = 6 + len(objs)
MESH = np.isin(np.arange(NS), [6 + oi for oi in C.SHAPES])       # surfaces that are generated shapes, not boxes
OUT = bool(getattr(C, "OUT", False))                             # outdoors: B.ROOM is a far shell, its sides a backdrop, its top sky
LIFT = sorted({i for i in getattr(C, "LIFT", ()) if 0 <= i < len(objs)})   # objects that move away from their spot
if os.environ.get("WORLD_LIFT") == "0": LIFT = []                # leave them in the room, where they stay still
LIFT_HALO = 81                                                   # px, odd: the band around a lifted object that is never taken as room paint
BARE = None                                                      # set for the second pass: (primitives, their objects) without the lifted ones
# the floor under and around a lifted object that stands on or just above it holds its painted shadow: (bounds, metres around)
SHADE = [(lo, hi, float(np.clip(hi[1], 0.4, 2.0))) for lo, hi in (C.bounds(C.OBJ_PRIMS[oi]) for oi in LIFT) if lo[1] < 0.6]
def shaded(P):
    """Floor points under and around a lifted object, where the paintings show its shadow rather than the bare floor."""
    m = np.zeros(P.shape[:-1], bool)
    for lo, hi, b in SHADE:
        m |= np.hypot(np.maximum(np.maximum(lo[0] - P[..., 0], P[..., 0] - hi[0]), 0), np.maximum(np.maximum(lo[2] - P[..., 2], P[..., 2] - hi[2]), 0)) < b
    return m

def trace(cam):
    return B.trace(cam, C.PRIM_OBJ)

OFFS = [(0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1)]
src_cams = dict(B.CAMS)
src = []
for i in range(C.N):
    t, P, sid = trace(src_cams[str(i)])
    im = Image.open(f"{C.D}/{name}/images/{i:02d}.png").convert("RGB")
    if im.size != (W, H): im = im.resize((W, H), Image.LANCZOS)      # pictures may be painted smaller than the working size
    edge = np.zeros((H, W), bool)                                    # source pixels with another surface next to them
    for dy, dx in OFFS: edge |= sid != np.roll(sid, (dy, dx), (0, 1))
    src.append((t, np.asarray(im, np.float32), np.bincount(sid.ravel(), minlength=NS), sid, edge, C.halo(sid, C.SLIM if C.NEW else ())))      # layouts with "rules" 2: the band round a post is not ground paint either
src_lift = []                                                    # per painted view: the lifted objects and the band around their outlines
for s_ in src if LIFT else ():
    on_ = np.isin(s_[3], [6 + oi for oi in LIFT])
    # the objects' own pixels count too: a point just past an outline rounds onto the object, then borrows from its edge
    src_lift.append(np.asarray(Image.fromarray((on_ * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(LIFT_HALO))) > 127)
count = np.stack([s[2] for s in src], 1).astype(float)          # surface x view: pixels of that surface seen
rank = np.argsort(np.argsort(-count, axis=1), axis=1).astype(float)  # 0 = best view for the surface
rank[count < 400] = 1e6
print("owner view per surface:", {(["x0","floor","z0","x1","ceil","z1"] + [o["name"] for o in objs])[s]: int(count[s].argmax()) for s in range(NS)})

# target cameras: the original ring, an inner ring looking outward at two heights, and a ring pitched up at the
# ceiling and wall tops (plus one at the upper walls in tall rooms). Never straight up: B.basis needs a horizontal part.
tgt = [src_cams[str(i)] for i in range(C.N)]
c = C.c
up = ((C.RH, 6, 0.0), (0.6 * C.RH, 6, 0.5)) if C.RH >= 3.2 else ((C.RH, 10, 0.0),)
rings = [(C.EYE - 0.25, 0.14, 0.55, 0.55, 12, 0.5), (C.EYE + 0.2, 0.225, 0.55, 0.5, 12, 0.5)] + [(C.EYE - 0.3, 0.15, 0.5, y, n, ph) for y, n, ph in up]
# four steep views across the middle of the ceiling, which the ring above leaves unseen
rings.append((C.EYE - 0.3, 0.2, -0.03, C.RH, 4, 0.25))
# views that cost no painting but pin the splat down where people actually look while moving around: the floor from
# above, the room from a grid of standing positions, and a low ring. Without them the floor is only ever seen at a
# grazing angle from near the centre, and training stretches it into streaks.
def add(eye, look):
    e = C.free(eye)
    if e is not None and np.linalg.norm(np.array(look) - e) > 0.3: tgt.append((tuple(e), tuple(look)))
for i in range(12):                                                  # looking down across the middle of the floor
    a = 2 * np.pi * (i + 0.25) / 12; off = np.array([np.cos(a) * C.RW, 0, np.sin(a) * C.RD])
    add(c + off * 0.3 + [0, C.EYE + 0.2, 0], c - off * 0.1)
for i in range(8):                                                   # looking down at the floor along the walls
    a = 2 * np.pi * (i + 0.5) / 8; off = np.array([np.cos(a) * C.RW, 0, np.sin(a) * C.RD])
    add(c + off * 0.12 + [0, C.EYE + 0.2, 0], c + off * 0.46)
for fx in (0.2, 0.5, 0.8):                                           # standing at a grid of spots, looking four ways
    for fz in (0.2, 0.5, 0.8):
        pos = np.array([fx * C.RW, C.EYE, fz * C.RD])
        for dx, dz in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
            add(pos, pos + np.array([dx * 0.25 * C.RW, -0.45, dz * 0.25 * C.RD]))
for i in range(6):                                                   # a low ring, as if crouching
    a = 2 * np.pi * (i + 0.5) / 6; off = np.array([np.cos(a) * C.RW, 0, np.sin(a) * C.RD])
    add(c + off * 0.25 + [0, 0.9, 0], c - off * 0.3 + [0, 0.5, 0])
# a thing that moves away from its spot shows every side as it turns or as people walk round it, and the views above see it
# from inside the room only: each gets a ring of views of its own. Outdoors these may stand up to 6 m outside the walking
# area, on the ground that is built there
for oi in LIFT:
    lo, hi = C.bounds(C.OBJ_PRIMS[oi]); mid = (lo + hi) / 2; far = max(1.2, 1.1 * max(hi[1] - lo[1], np.hypot(hi[0] - lo[0], hi[2] - lo[2])))
    for i in range(8):
        for k in (1, 1.5, 2, 3):                                     # further out while a post or frame (what holds a swing's seat) would fill the picture
            a = 2 * np.pi * (i + 0.5) / 8; e = mid + [np.cos(a) * far * k, 0, np.sin(a) * far * k]; e[1] = max(0.6, mid[1] + 0.35 * far)
            if not OUT: e[1] = min(e[1], C.RH - 0.2); e = C.free(e)
            elif not (-6 < e[0] < C.RW + 6 and -6 < e[2] < C.RD + 6) or any(B.inside(e, p, 0.25) for p in C.KEEP_OUT): e = None
            if e is None or not C.crowded(e, 0.5): break         # (half a painted view's clearance: these see paint, they do not make it)
        if e is not None and not C.crowded(e, 0.5) and np.hypot(mid[0] - e[0], mid[2] - e[2]) > 0.3: tgt.append((tuple(e), tuple(mid)))
n_up = 0
for ri, (h, r, lr, look, n, ph) in enumerate(rings):
    for i in range(n):
        a = 2 * np.pi * (i + ph) / n; off = np.array([np.cos(a) * C.RW, 0, np.sin(a) * C.RD])
        eye = C.free(c + off * r + [0, h, 0])
        if eye is None: continue                                     # no usable position (inside furniture)
        tgt.append((tuple(eye), tuple(c + off * lr + [0, look, 0]))); n_up += ri >= 2

S = np.diag([1.0, 1, -1]); f = W / 2 / np.tan(np.radians(B.FOV) / 2)
wall = np.isin(np.arange(NS), (0, 2, 3, 5))

def render(k):
    """One target view: for every pixel, the colour from the best painted view that truly sees that surface point."""
    cam = tgt[k]; full, ids = B.PRIMS, C.PRIM_OBJ
    if BARE: B.PRIMS, ids = BARE                                     # the target is the room without the lifted objects...
    if MESH.any():
        t, P, sid, nrm = B.trace(cam, ids, True)
        on = MESH[sid]; Pm, nm = P[on], nrm[on]
    else: t, P, sid = B.trace(cam, ids); on = None
    B.PRIMS = full                                                   # ...but the painted views saw them: B.visible below needs them all
    best = np.full((H, W), 1e5); col = np.zeros((H, W, 3), np.float32)
    lost = np.zeros((H, W), bool) if BARE else None                  # points a painted view shows only next to or behind a lifted object
    # try the painted views most likely to own this picture's surfaces first: once a pixel has its best-ranked source,
    # lower-ranked views skip it, which is most of the work saved
    share = np.bincount(sid.ravel(), minlength=NS)
    for v in np.argsort((np.minimum(rank, C.N) * share[:, None]).sum(0)):
        st, simg, _, ssid, sedge, shalo = src[v]
        score = rank[sid, v]
        if on is not None and on.any():
            # a picture that sees a curved shape side-on smears it, and its outline rarely matches the shape to the pixel:
            # such a view is used only where no view sees the point reasonably head-on
            to = np.array(src_cams[str(v)][0]) - Pm; cos = (to * nm).sum(1) / np.maximum(np.linalg.norm(to, axis=1), 1e-9)
            score[on] += C.N * (cos < C.GRAZE)
            # a view behind the surface is no source at all: through a gap or a single-sheet part it would lend the paint of the other side
            score[on] = np.where(cos <= 0, 1e6, score[on])
        px, py, dist, z = B.project(src_cams[str(v)], P)
        xi, yi = np.round(px).astype(int), np.round(py).astype(int)
        if on is not None:
            # the band around a shape's outline in a picture often holds the shape's own paint: the wall or floor seen
            # there is taken from another view where one exists, or the car's outline ends up stamped on the wall behind it
            score = score + C.N * shalo[np.clip(yi, 0, H - 1), np.clip(xi, 0, W - 1)]
        if BARE:
            # next to a lifted object the painting holds its spill, its edge and its shadow: never a surface of the bare room
            by = src_lift[v][np.clip(yi, 0, H - 1), np.clip(xi, 0, W - 1)]; score = np.where(by, 1e6, score)
            lost |= by & (z > 0.05) & (xi >= 1) & (xi < W - 1) & (yi >= 1) & (yi < H - 1)
        want = score < best                                          # only where this view would become the source
        want &= (z > 0.05) & (xi >= 1) & (xi < W - 1) & (yi >= 1) & (yi < H - 1)
        xi, yi = np.clip(xi, 0, W - 1), np.clip(yi, 0, H - 1)
        # room faces away from any silhouette in the source: same surface, depth within a tolerance that grows with distance
        plain = want & (sid < 6) & ~sedge[yi, xi]
        ok = plain & (ssid[yi, xi] == sid) & (np.abs(st[yi, xi] - dist) < np.maximum(0.05, 0.01 * dist))
        # objects and silhouettes: exact shadow ray (comparing against the source's depth at a rounded pixel gave staircase
        # edges), then take the colour from the nearest source pixel that shows the same surface
        ex = np.nonzero(want & ~plain)
        if len(ex[0]):
            ey, ex_x, s = yi[ex], xi[ex], sid[ex]
            vis = B.visible(src_cams[str(v)][0], P[ex])
            miss = vis & (ssid[ey, ex_x] != s)
            for dy, dx in OFFS:
                if not miss.any(): break
                # clip: entries moved by an earlier offset can already sit on the picture's last row or column
                m = miss & (ssid[np.clip(ey + dy, 0, H - 1), np.clip(ex_x + dx, 0, W - 1)] == s)
                ey[m] += dy; ex_x[m] += dx; miss &= ~m
            ok[ex] = vis & ~miss; yi[ex] = ey; xi[ex] = ex_x
        best = np.where(ok, score, best); col[ok] = simg[yi[ok], xi[ok]]
    have = best < 1e5
    if BARE and SHADE: by = (sid == 1) & shaded(P); have &= ~by; lost |= by
    return k, P.astype(np.float32), sid.astype(np.int16), col.astype(np.uint8), have, lost

# the views are independent, so they are rendered in parallel (forked workers share the painted pictures without copying)
import multiprocessing as mp
from scipy import ndimage
from scipy.spatial import cKDTree
workers = max(1, min(8, (os.cpu_count() or 4) - 2, len(tgt)))
def render_all():
    if workers > 1:
        with mp.get_context("fork").Pool(workers) as pool: return pool.map(render, range(len(tgt)), chunksize=1)
    return [render(k) for k in range(len(tgt))]

BAND = 0.5                                                           # metres of height per row when looking for the sky's colour
CELL = 0.03                                                          # texture cell on a room face, in metres
lo3, hi3 = np.array(B.ROOM[0], float), np.array(B.ROOM[1], float)
def cells(f, P):
    """Texture cell indices on room face f for world points P."""
    u, w = [a for a in range(3) if a != f % 3]
    nu, nw = int(np.ceil((hi3[u] - lo3[u]) / CELL)), int(np.ceil((hi3[w] - lo3[w]) / CELL))
    return np.clip(((P[..., u] - lo3[u]) / CELL).astype(int), 0, nu - 1), np.clip(((P[..., w] - lo3[w]) / CELL).astype(int), 0, nw - 1), nu, nw
VOX = 0.02                                                           # metres: an object's painted points are gathered into cells this size
def frame(oi):
    """An object's own upright mirror planes, through the middle of its bounds along and across its heading: a point on
    both, their two normals, and how far from paint a mirrored point may land and still take it."""
    o = objs[oi]; yaw = o.get("yaw", next((p.get("yaw", 0.0) for p in o["prims"] if p["shape"] == "box"), 0.0))
    yaw = float(yaw) if isinstance(yaw, (int, float)) and np.isfinite(yaw) else 0.0
    turn = lambda a: np.array([[np.cos(a), 0, -np.sin(a)], [np.sin(a), 0, np.cos(a)]])
    ax = turn(yaw)
    if oi in C.SHAPES: pts = np.load(C.SHAPES[oi])["V"].astype(float)
    else:
        ext = lambda p: p["r"] * ax if p["shape"] == "cyl" else turn(p.get("yaw", 0.0)) * np.array(p["h"], float)[[0, 2], None]
        pts = np.array([np.array(p["c"], float) + sx * e[0] + sz * e[1] for p in o["prims"] for e in [ext(p)] for sx in (-1, 1) for sz in (-1, 1)])
    l = pts @ ax.T
    return (l.min(0) + l.max(0)) / 2 @ ax, ax, max(0.03, 0.02 * float(np.ptp(l, 0).max()))
def spread(avg, painted, q=4):
    """A smooth continuation of a face's painted cells over the whole face: every cell a mean of the paint around it,
    weighted steeply towards the nearest, so a wide gap is crossed without streaks. Worked out q times coarser."""
    nu, nw = painted.shape; pad = ((0, -nu % q), (0, -nw % q))
    blk = lambda a: np.pad(a, pad).reshape((nu + pad[0][1]) // q, q, (nw + pad[1][1]) // q, q).sum((1, 3))
    lay = [blk(painted.astype(float))] + [blk(avg[..., ch] * painted) for ch in range(3)]
    tot = [np.zeros_like(lay[0]) for _ in lay]; sg = 1.0
    while sg <= max(lay[0].shape):
        for a, b in zip(tot, lay): a += sg ** -4 * ndimage.gaussian_filter(b, sg, mode="constant")
        sg *= 2
    low = [ndimage.zoom(a / np.maximum(tot[0], 1e-300), q, order=1, mode="nearest", grid_mode=True)[:nu, :nw] for a in tot[1:]]
    return np.stack(low, -1)
def mend(avg, painted, soft, gap, level, cnt, fine):
    """Paint for the cells of a face that a lifted thing stood on or hid (gap): the colours around the gap carried
    smoothly across it, plus the fine grain of painted cells beside it. level: a wall, whose paint runs in level bands
    (skirting, fence, horizon), so every height is carried across from its own left and right; given with the level
    direction first. cnt: how many pixels painted each cell. fine: the paint's grain, what a slight blur takes away.
    Returns the paint and where it could be made."""
    nu, nw = painted.shape; gu, gw = np.mgrid[:nu, :nw]; ok = np.ones((nu, nw), bool)
    if level:
        L = np.maximum.accumulate(np.where(painted, gu, -1), 0); R = np.minimum.accumulate(np.where(painted, gu, nu)[::-1], 0)[::-1]
        ok = (L >= 0) | (R < nu)
        t = np.where((L >= 0) & (R < nu), (gu - L) / np.maximum(R - L, 1), R < nu)[..., None]
        low = soft[np.clip(L, 0, nu - 1), gw] * (1 - t) + soft[np.clip(R, 0, nu - 1), gw] * t
    else: low = spread(avg, painted)
    # the grain: each block of the gap wears that of painted cells one shift away (sideways only on a wall), the shortest
    # shift that finds paint for nearly all of it. Only solid stretches of cells that were seen well lend grain: far
    # ground seen at a low angle is painted as long streaks
    good = ndimage.uniform_filter((cnt >= 0.05 * np.percentile(cnt[painted], 90)).astype(float), 9) > 0.8
    for u0, w0 in ((u0, w0) for u0 in range(0, nu, 64) for w0 in range(0, nw, 64) if gap[u0:u0 + 64, w0:w0 + 64].any()):
        cu, cw = np.nonzero(gap[u0:u0 + 64, w0:w0 + 64]); cu += u0; cw += w0; best = (0.0, 0, 0); k = 8
        while k < max(nu, nw) and best[0] < 0.9:
            for a, b in ((1, 0), (-1, 0)) if level else ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
                u, w = cu + k * a, cw + k * b
                cov = ((u >= 0) & (u < nu) & (w >= 0) & (w < nw) & good[np.clip(u, 0, nu - 1), np.clip(w, 0, nw - 1)]).mean()
                if cov > best[0]: best = (cov, k * a, k * b)
            k = k * 3 // 2
        gu[cu, cw] += best[1]; gw[cu, cw] += best[2]
    there = (gu >= 0) & (gu < nu) & (gw >= 0) & (gw < nw); gu, gw = np.clip(gu, 0, nu - 1), np.clip(gw, 0, nw - 1); there &= good[gu, gw] & gap
    grain = np.clip(fine[gu, gw], -20, 20) * np.minimum(1, 2 * ndimage.gaussian_filter(there.astype(float), 3))[..., None] * there[..., None]
    return np.clip(low + grain, 0, 255), ok
def blend(t_, fc, P):
    """A face's texture at world points P, blended between its cells (at a close look single cells show as blocks)."""
    u, w = [a for a in range(3) if a != fc % 3]; nu, nw = t_.shape[:2]
    fu, fw = (P[..., u] - lo3[u]) / CELL - 0.5, (P[..., w] - lo3[w]) / CELL - 0.5
    iu, iw = np.clip(np.floor(fu).astype(int), 0, nu - 2), np.clip(np.floor(fw).astype(int), 0, nw - 2)
    a, b = np.clip(fu - iu, 0, 1)[..., None], np.clip(fw - iw, 0, 1)[..., None]
    return (t_[iu, iw] * (1 - a) + t_[iu + 1, iw] * a) * (1 - b) + (t_[iu, iw + 1] * (1 - a) + t_[iu + 1, iw + 1] * a) * b
TOPY = np.array([np.inf] * 6 + [C.bounds(ps)[1][1] - 0.03 for ps in C.OBJ_PRIMS])   # per surface: the height where an object's top begins
def write(results, out, bare=False):
    """Blend the rendered views into one training set in folder `out`: pictures, cameras and starting points."""
    os.makedirs(f"{out}/images", exist_ok=True); os.makedirs(f"{out}/sparse/0", exist_ok=True)
    for old in glob.glob(f"{out}/images/*.png") + glob.glob(f"{out}/sparse/0/*.bin"): os.remove(old)   # an earlier run's views; COLMAP prefers old .bin over new .txt
    im_lines, pts = [], []; rng = np.random.default_rng(0); sums = np.zeros((NS, 3)); ns = np.zeros(NS); tot = np.zeros(NS); pending = []
    wsum = np.zeros((2, 3)); wn = np.zeros(2)                        # painted wall colour: [all, top third]
    nb = int(hi3[1] / BAND) + 1; band = np.zeros((nb * 512, 4))      # outdoors: painted backdrop colour and count, by height and by coarse colour
    tex = {}; tsum = np.zeros((NS, 3)); tn = np.zeros(NS)            # bare room: the painted colour of each object's top
    cloud = []                                                       # per view: the painted points of objects, by cell
    for k, P, sid, col, have, lost in results:
        cam = tgt[k]; colf = col.astype(np.float32)
        if bare:
            m = have & (P[..., 1] > TOPY[sid])
            for ch in range(3): tsum[:, ch] += np.bincount(sid[m], weights=colf[m][:, ch], minlength=NS)
            tn += np.bincount(sid[m], minlength=NS)
        sh = sid[have]                                                   # np.bincount, not np.add.at: the latter is many times slower
        for ch in range(3): sums[:, ch] += np.bincount(sh, weights=colf[have][:, ch], minlength=NS)
        ns += np.bincount(sh, minlength=NS); tot += np.bincount(sid.ravel(), minlength=NS)
        for j, m in enumerate((have & wall[sid], have & wall[sid] & (P[..., 1] > C.RH * 2 / 3))):
            wsum[j] += colf[m].sum(0); wn[j] += m.sum()
            if OUT and j == 0:
                q = col[m].astype(int) >> 5
                row = np.clip((P[m][:, 1] / BAND).astype(int), 0, nb - 1) * 512 + q[:, 0] * 64 + q[:, 1] * 8 + q[:, 2]
                for ch in range(3): band[:, ch] += np.bincount(row, weights=colf[m][:, ch], minlength=len(band))
                band[:, 3] += np.bincount(row, minlength=len(band))
        for fc in range(6):                                              # gather every painted pixel of a face into its texture
            # ...and, in the bare room, mark the cells that are unpainted because of a lifted object
            for j, m in enumerate((have & (sid == fc),) + (() if lost is None else (lost & ~have & (sid == fc),))):
                if not m.any(): continue
                iu, iw, nu, nw = cells(fc, P[m])
                if fc not in tex: tex[fc] = [np.zeros((nu, nw, 3)), np.zeros((nu, nw)), np.zeros((nu, nw), bool)]
                flat = iu * nw + iw; cm = colf[m]
                if j: tex[fc][2] |= (np.bincount(flat, minlength=nu * nw) > 0).reshape(nu, nw); continue
                for ch in range(3): tex[fc][0][..., ch] += np.bincount(flat, weights=cm[:, ch], minlength=nu * nw).reshape(nu, nw)
                tex[fc][1] += np.bincount(flat, minlength=nu * nw).reshape(nu, nw)
        m = have & (sid >= 6)
        if m.any():
            key = (sid[m].astype(np.int64) << 54) + ((np.floor(P[m] / VOX).astype(np.int64) + (1 << 17)) << [36, 18, 0]).sum(1)
            u, inv = np.unique(key, return_inverse=True)
            cloud.append((u, np.stack([np.bincount(inv, weights=a, minlength=len(u)) for a in (*P[m].T, *colf[m].T, np.ones(len(inv)))], 1).astype(np.float32)))
        pending.append((k, cam, P, sid, colf, have))
    mean = sums / np.maximum(ns, 1)[:, None]
    # surfaces no picture covers must not be black: use the overall painted colour. A ceiling that is unpainted, or painted
    # only as a far dark sliver, becomes one flat lightened upper-wall colour
    overall = sums.sum(0) / ns.sum() if ns.sum() else np.full(3, 128.0)
    mean[ns == 0] = overall
    flat_ceiling = ns[4] < 0.5 * tot[4]
    if OUT:
        # the sky's colour is the commonest colour the pictures show in the top two metres of the painted backdrop (their
        # mean would be tinted by any treetops painted there); everything above is that colour
        band = band.reshape(nb, 512, 4); per = band[..., 3].sum(1)
        top = max([r for r in range(nb) if per[r] >= 0.002 * per.sum() and per[r]], default=0)
        rows = band[max(0, top + 1 - int(2 / BAND)):top + 1].sum(0); best = rows[rows[:, 3].argmax()]
        sky = best[:3] / best[3] if best[3] else overall
        mean[4] = sky; flat_ceiling = True
        for p in pending: p[5][p[3] == 4] = False
        json.dump([round(float(v) / 255, 4) for v in sky], open(f"{out}/sky.json", "w"))
    elif flat_ceiling:
        j = 1 if wn[1] else 0
        mean[4] = 0.6 * (wsum[j] / wn[j] if wn[j] else overall) + 0.4 * 255
        for p in pending: p[5][p[3] == 4] = False
    # unpainted parts of a wall or floor continue the surrounding paint instead of turning one flat colour: each empty
    # texture cell takes the nearest painted cell's colour, then the borrowed area is blurred so it reads as soft floor, not shards
    fill_tex = {}
    for fc, (acc, cnt, gone) in tex.items():
        if fc == 4 and flat_ceiling: continue
        painted = cnt > 0
        if painted.all() or not painted.any(): continue
        avg = acc / np.maximum(cnt, 1)[..., None]
        idx = ndimage.distance_transform_edt(~painted, return_distances=False, return_indices=True)
        near = avg[idx[0], idx[1]]
        soft = np.stack([ndimage.gaussian_filter(near[..., ch], 8) for ch in range(3)], -1)
        # ...and, in the set that keeps a lifted thing, all the ground no picture shows: its own ring of views looks at the
        # ground under and behind it, where the nearest paint is its shadow
        gap = ~painted & (ndimage.binary_dilation(gone) if bare else bool(LIFT) and fc == 1)
        if gap.any():
            # where a lifted thing stood or hid the face, the gap can be metres wide (the ground behind a car, out to the
            # backdrop): nearest-cell fill would draw the paint at its rim across it in stripes
            tr = (lambda a: a) if fc % 3 else (lambda a: a.swapaxes(0, 1))
            fine = avg - np.stack([ndimage.gaussian_filter(near[..., ch], 3) for ch in range(3)], -1)
            new, ok = mend(tr(avg), tr(painted), tr(soft), tr(gap), fc % 3 != 1, tr(cnt), tr(fine)); gap &= tr(ok); soft[gap] = tr(new)[gap]
        if OUT and fc != 1:
            # the backdrop above its paint: nearest-cell fill would draw the top row of paint upwards as streaks, so it
            # is blurred wide and fades into the sky colour over 8 m above the highest painted cell of each column
            up = painted if fc % 3 else painted.T                    # height runs along the last axis (faces 0 and 3 hold it first)
            nh = up.shape[1]; any_ = up.any(1); tops = np.where(any_, nh - 1 - up[:, ::-1].argmax(1), 0).astype(float)
            tops[~any_] = np.median(tops[any_]); tops = ndimage.uniform_filter1d(tops, 33, mode="nearest")
            a = np.clip((np.arange(nh)[None] - tops[:, None]) / (8 / CELL), 0, 1); a = a * a * (3 - 2 * a)
            a = (a if fc % 3 else a.T)[..., None]
            wide = np.stack([ndimage.gaussian_filter(near[..., ch], 40) for ch in range(3)], -1)
            b = np.minimum(a * 8, 1)                                 # the first metre goes from the narrow blur to the wide one
            soft = (soft * (1 - b) + wide * b) * (1 - a) + sky * a
        fill_tex[fc] = np.where(painted[..., None], avg, soft)
    # a part of an object that no picture shows takes the object's own paint, not one flat colour: the paint at its mirror
    # image across the object's upright planes (the far side of a car looks like the near side), else the nearest paint
    # on the object (a patch of a tree's crown continues the leaves around it)
    trees, frames, lent = {}, {}, 0
    if cloud:
        u, inv = np.unique(np.concatenate([c[0] for c in cloud]), return_inverse=True); acc = np.concatenate([c[1] for c in cloud]); del cloud
        acc = np.stack([np.bincount(inv, weights=acc[:, j], minlength=len(u)) for j in range(7)], 1); acc = acc[:, :6] / acc[:, 6:]
        for s in np.unique(u >> 54):
            a = acc[u >> 54 == s]; _, inv = np.unique(np.floor(a[:, :3] / (5 * VOX)).astype(np.int64), axis=0, return_inverse=True); inv = inv.ravel()
            b = np.stack([np.bincount(inv, weights=a[:, j]) for j in range(6)], 1) / np.bincount(inv)[:, None]     # the same paint, five times coarser
            trees[int(s)] = (cKDTree(a[:, :3]), a[:, 3:], cKDTree(b[:, :3]), b[:, 3:])
    def borrow(s, Q):
        tree, tc, wide, wc = trees[s]; Q = Q.astype(float); T = Q.copy()
        if s not in frames: frames[s] = frame(s - 6)
        mid, ax, tol = frames[s]
        far = np.nonzero(tree.query(Q, workers=-1)[0] > 2 * VOX)[0]      # a small gap in the paint just closes from its rim
        best = np.full(len(far), tol)
        for planes in ((0,), (1,), (0, 1)):                              # across one plane, the other, then both (a half turn)
            todo = np.nonzero(best >= tol)[0] if len(planes) > 1 else np.arange(len(far))    # both only where neither alone found paint
            if not len(todo): continue
            M = Q[far[todo]]
            for j in planes: M = M - 2 * ((M - mid) @ ax[j])[:, None] * ax[j]
            d = tree.query(M, workers=-1)[0]; hit = d < best[todo]
            best[todo[hit]] = d[hit]; T[far[todo[hit]]] = M[hit]
        n = min(4, tree.n); d, j = tree.query(T, k=n, workers=-1); d, j = d.reshape(-1, n), j.reshape(-1, n)
        w = 1 / (d * d + (VOX / 2) ** 2); out = (tc[j] * w[..., None]).sum(1) / w.sum(1)[:, None]
        # far from any paint the nearest few cells are all one stretch of a rim, drawn out as rays: there the colour
        # comes from more of the paint around, softly
        deep = np.nonzero(d[:, 0] > 5 * VOX)[0]
        if len(deep):
            n = min(8, wide.n); dd, j = wide.query(T[deep], k=n, workers=-1); dd, j = dd.reshape(-1, n), j.reshape(-1, n)
            w = 1 / (dd * dd + (5 * VOX) ** 2); a = np.clip((d[deep, :1] - 5 * VOX) / (10 * VOX), 0, 1)
            out[deep] = out[deep] * (1 - a) + (wc[j] * w[..., None]).sum(1) / w.sum(1)[:, None] * a
        return out
    for k, cam, P, sid, col, have in pending:
        fillc = mean[sid]
        for s in np.unique(sid[~have & (sid >= 6)]) if trees else ():
            if int(s) in trees: m = ~have & (sid == s); fillc[m] = borrow(int(s), P[m]); lent += m.sum()
        if bare:    # where a lifted thing stood on another object, that object's top is its own colour, not the darker mean with its sides
            m = ~have & (P[..., 1] > TOPY[sid]) & (tn[sid] > 0); fillc[m] = (tsum / np.maximum(tn, 1)[:, None])[sid[m]]
        for fc, t_ in fill_tex.items():
            m = ~have & (sid == fc)
            if m.any() and bare: fillc[m] = blend(t_, fc, P[m])
            elif m.any():
                iu, iw, _, _ = cells(fc, P[m]); fillc[m] = t_[iu, iw]
        col = np.where(have[..., None], col, fillc)
        Image.fromarray(col.astype(np.uint8)).save(f"{out}/images/{k:03d}.png")
        eye, r, u, fw = B.basis(cam)
        R = np.stack([S @ -r, S @ -u, S @ fw]); tv = -R @ (S @ eye)
        qx, qy, qz, qw = Rotation.from_matrix(R).as_quat()
        im_lines.append(f"{k+1} {qw} {qx} {qy} {qz} {tv[0]} {tv[1]} {tv[2]} 1 {k:03d}.png\n\n")
        idx = rng.choice(W * H, 2500, replace=False)
        pts += [(S @ P.reshape(-1, 3)[j].astype(float), col.reshape(-1, 3)[j]) for j in idx]
    open(f"{out}/sparse/0/cameras.txt", "w").write(f"1 PINHOLE {W} {H} {f} {f} {W/2} {H/2}\n")
    open(f"{out}/sparse/0/images.txt", "w").write("".join(im_lines))
    open(f"{out}/sparse/0/points3D.txt", "w").write("".join(f"{i+1} {p[0]} {p[1]} {p[2]} {int(c[0])} {int(c[1])} {int(c[2])} 0.5\n" for i, (p, c) in enumerate(pts)))
    r = subprocess.run(["colmap", "model_converter", "--input_path", f"{out}/sparse/0", "--output_path", f"{out}/sparse/0", "--output_type", "BIN"], capture_output=True, text=True)
    if r.returncode or not os.path.exists(f"{out}/sparse/0/images.bin"): sys.exit("colmap model_converter failed:\n" + (r.stdout + r.stderr)[-2000:])
    json.dump([[list(map(float, e)), list(map(float, l))] for e, l in tgt], open(f"{out}/cams.json", "w"))
    fill = [1 - p[5].mean() for p in pending]; nl = len(tgt) - n_up
    print(*(["without the moving things:"] if bare else []), "wrote", len(tgt), "views (%d looking up); filled by flat colour: %.1f%%" % (n_up, 100 * np.mean(fill)), "(level views %.1f%%, upward views %.1f%%)" % (100 * np.mean(fill[:nl]), 100 * np.mean(fill[nl:] or [0])),
          "of which objects' unseen parts painted from themselves: %.1f%%" % (100 * lent / (len(tgt) * W * H)))

out = f"{C.D}/{name}_c"
if os.path.exists(f"{out}/lifted.json"): os.remove(f"{out}/lifted.json")     # an earlier run's
if not LIFT: write(render_all(), out)
else:
    # the same pictures give two sets: one as painted, and one of the room without the things that move away, where the
    # ground and wall they hid are filled in. The trained splat of the first lends those things; the second is the room
    write(render_all(), f"{C.D}/{name}_m")
    lifted = LIFT
    try:
        keep = [j for j, oi in enumerate(C.PRIM_OBJ) if oi not in LIFT]
        BARE = ([B.PRIMS[j] for j in keep], [C.PRIM_OBJ[j] for j in keep])
        write(render_all(), out, True)
    except Exception as e:      # the moving things then stay where they are: the room is the set as painted
        print(f"Could not make the room without the moving things ({type(e).__name__}: {e}): they stay still.", flush=True)
        BARE, lifted = None, []
        shutil.rmtree(out, ignore_errors=True); shutil.copytree(f"{C.D}/{name}_m", out)
    json.dump(lifted, open(f"{out}/lifted.json", "w"))
