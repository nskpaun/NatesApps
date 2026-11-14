"""Make the generated views agree before training: every surface (each wall, the floor, each furniture piece)
takes its appearance from ONE source picture, projected onto the blockout, then re-rendered from many cameras.
(Masking objects that spill past their blocks, using depth estimates of the pictures, was tried and fragmented surfaces more.)
  consistent.py NAME   reads chisel/NAME/images, writes chisel/NAME_c/{images,sparse/0}
"""
import sys, os, json, glob, subprocess, numpy as np
from PIL import Image
from scipy.spatial.transform import Rotation
name = sys.argv[1]; sys.argv = [sys.argv[0], "prep"]
import chisel_ring as C
B = C.B; W, H = B.W, B.H
objs = C.objs
NS = 6 + len(objs)
MESH = np.isin(np.arange(NS), [6 + oi for oi in C.SHAPES])       # surfaces that are generated shapes, not boxes

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
    src.append((t, np.asarray(im, np.float32), np.bincount(sid.ravel(), minlength=NS), sid, edge, C.halo(sid)))
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
n_up = 0
for ri, (h, r, lr, look, n, ph) in enumerate(rings):
    for i in range(n):
        a = 2 * np.pi * (i + ph) / n; off = np.array([np.cos(a) * C.RW, 0, np.sin(a) * C.RD])
        eye = C.free(c + off * r + [0, h, 0])
        if eye is None: continue                                     # no usable position (inside furniture)
        tgt.append((tuple(eye), tuple(c + off * lr + [0, look, 0]))); n_up += ri >= 2

out = f"{C.D}/{name}_c"; os.makedirs(f"{out}/images", exist_ok=True); os.makedirs(f"{out}/sparse/0", exist_ok=True)
for old in glob.glob(f"{out}/images/*.png") + glob.glob(f"{out}/sparse/0/*.bin"): os.remove(old)   # an earlier run's views; COLMAP prefers old .bin over new .txt
S = np.diag([1.0, 1, -1]); f = W / 2 / np.tan(np.radians(B.FOV) / 2)
im_lines, pts = [], []; rng = np.random.default_rng(0); sums = np.zeros((NS, 3)); ns = np.zeros(NS); tot = np.zeros(NS); pending = []
wall = np.isin(np.arange(NS), (0, 2, 3, 5)); wsum = np.zeros((2, 3)); wn = np.zeros(2)   # painted wall colour: [all, top third]

def render(k):
    """One target view: for every pixel, the colour from the best painted view that truly sees that surface point."""
    cam = tgt[k]
    if MESH.any():
        t, P, sid, nrm = B.trace(cam, C.PRIM_OBJ, True)
        on = MESH[sid]; Pm, nm = P[on], nrm[on]
    else: t, P, sid = trace(cam); on = None
    best = np.full((H, W), 1e5); col = np.zeros((H, W, 3), np.float32)
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
    return k, P.astype(np.float32), sid.astype(np.int16), col.astype(np.uint8), best < 1e5

# the views are independent, so they are rendered in parallel (forked workers share the painted pictures without copying)
import multiprocessing as mp
from scipy import ndimage
workers = max(1, min(8, (os.cpu_count() or 4) - 2, len(tgt)))
if workers > 1:
    with mp.get_context("fork").Pool(workers) as pool: results = pool.map(render, range(len(tgt)), chunksize=1)
else: results = [render(k) for k in range(len(tgt))]

CELL = 0.03                                                          # texture cell on a room face, in metres
lo3, hi3 = np.array(B.ROOM[0], float), np.array(B.ROOM[1], float)
def cells(f, P):
    """Texture cell indices on room face f for world points P."""
    u, w = [a for a in range(3) if a != f % 3]
    nu, nw = int(np.ceil((hi3[u] - lo3[u]) / CELL)), int(np.ceil((hi3[w] - lo3[w]) / CELL))
    return np.clip(((P[..., u] - lo3[u]) / CELL).astype(int), 0, nu - 1), np.clip(((P[..., w] - lo3[w]) / CELL).astype(int), 0, nw - 1), nu, nw
tex = {}
for k, P, sid, col, have in results:
    cam = tgt[k]; colf = col.astype(np.float32)
    sh = sid[have]                                                   # np.bincount, not np.add.at: the latter is many times slower
    for ch in range(3): sums[:, ch] += np.bincount(sh, weights=colf[have][:, ch], minlength=NS)
    ns += np.bincount(sh, minlength=NS); tot += np.bincount(sid.ravel(), minlength=NS)
    for j, m in enumerate((have & wall[sid], have & wall[sid] & (P[..., 1] > C.RH * 2 / 3))):
        wsum[j] += colf[m].sum(0); wn[j] += m.sum()
    for fc in range(6):                                              # gather every painted pixel of a face into its texture
        m = have & (sid == fc)
        if not m.any(): continue
        iu, iw, nu, nw = cells(fc, P[m])
        if fc not in tex: tex[fc] = [np.zeros((nu, nw, 3)), np.zeros((nu, nw))]
        flat = iu * nw + iw; cm = colf[m]
        for ch in range(3): tex[fc][0][..., ch] += np.bincount(flat, weights=cm[:, ch], minlength=nu * nw).reshape(nu, nw)
        tex[fc][1] += np.bincount(flat, minlength=nu * nw).reshape(nu, nw)
    pending.append((k, cam, P, sid, colf, have))
mean = sums / np.maximum(ns, 1)[:, None]
# surfaces no picture covers must not be black: use the overall painted colour. A ceiling that is unpainted, or painted
# only as a far dark sliver, becomes one flat lightened upper-wall colour
overall = sums.sum(0) / ns.sum() if ns.sum() else np.full(3, 128.0)
mean[ns == 0] = overall
flat_ceiling = ns[4] < 0.5 * tot[4]
if flat_ceiling:
    j = 1 if wn[1] else 0
    mean[4] = 0.6 * (wsum[j] / wn[j] if wn[j] else overall) + 0.4 * 255
    for p in pending: p[5][p[3] == 4] = False
# unpainted parts of a wall or floor continue the surrounding paint instead of turning one flat colour: each empty
# texture cell takes the nearest painted cell's colour, then the borrowed area is blurred so it reads as soft floor, not shards
fill_tex = {}
for fc, (acc, cnt) in tex.items():
    if fc == 4 and flat_ceiling: continue
    painted = cnt > 0
    if painted.all() or not painted.any(): continue
    avg = acc / np.maximum(cnt, 1)[..., None]
    idx = ndimage.distance_transform_edt(~painted, return_distances=False, return_indices=True)
    near = avg[idx[0], idx[1]]
    soft = np.stack([ndimage.gaussian_filter(near[..., ch], 8) for ch in range(3)], -1)
    fill_tex[fc] = np.where(painted[..., None], avg, soft)
for k, cam, P, sid, col, have in pending:
    fillc = mean[sid]
    for fc, t_ in fill_tex.items():
        m = ~have & (sid == fc)
        if m.any():
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
print("wrote", len(tgt), "views (%d looking up); filled by flat colour: %.1f%%" % (n_up, 100 * np.mean(fill)), "(level views %.1f%%, upward views %.1f%%)" % (100 * np.mean(fill[:nl]), 100 * np.mean(fill[nl:] or [0])))
