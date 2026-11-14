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
    src.append((t, np.asarray(im, np.float32), np.bincount(sid.ravel(), minlength=NS), sid, edge))
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
for k, cam in enumerate(tgt):
    t, P, sid = trace(cam)
    best = np.full((H, W), 1e5); col = np.zeros((H, W, 3), np.float32)
    for v in range(C.N):
        st, simg, _, ssid, sedge = src[v]
        score = rank[sid, v]; want = score < best                    # only where this view would become the source
        px, py, dist, z = B.project(src_cams[str(v)], P)
        xi, yi = np.round(px).astype(int), np.round(py).astype(int)
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
                m = miss & (ssid[ey + dy, ex_x + dx] == s)
                ey[m] += dy; ex_x[m] += dx; miss &= ~m
            ok[ex] = vis & ~miss; yi[ex] = ey; xi[ex] = ex_x
        best = np.where(ok, score, best); col[ok] = simg[yi[ok], xi[ok]]
    have = best < 1e5
    np.add.at(sums, sid[have], col[have]); np.add.at(ns, sid[have], 1); tot += np.bincount(sid.ravel(), minlength=NS)
    for j, m in enumerate((have & wall[sid], have & wall[sid] & (P[..., 1] > C.RH * 2 / 3))):
        wsum[j] += col[m].sum(0); wn[j] += m.sum()
    pending.append((k, cam, P, sid, col, have))
mean = sums / np.maximum(ns, 1)[:, None]
# surfaces no picture covers must not be black: use the overall painted colour. A ceiling that is unpainted, or painted
# only as a far dark sliver, becomes one flat lightened upper-wall colour
overall = sums.sum(0) / ns.sum() if ns.sum() else np.full(3, 128.0)
mean[ns == 0] = overall
if ns[4] < 0.5 * tot[4]:
    j = 1 if wn[1] else 0
    mean[4] = 0.6 * (wsum[j] / wn[j] if wn[j] else overall) + 0.4 * 255
    for p in pending: p[5][p[3] == 4] = False
for k, cam, P, sid, col, have in pending:
    col = np.where(have[..., None], col, mean[sid])
    Image.fromarray(col.astype(np.uint8)).save(f"{out}/images/{k:02d}.png")
    eye, r, u, fw = B.basis(cam)
    R = np.stack([S @ -r, S @ -u, S @ fw]); tv = -R @ (S @ eye)
    qx, qy, qz, qw = Rotation.from_matrix(R).as_quat()
    im_lines.append(f"{k+1} {qw} {qx} {qy} {qz} {tv[0]} {tv[1]} {tv[2]} 1 {k:02d}.png\n\n")
    idx = rng.choice(W * H, 2500, replace=False)
    pts += [(S @ P.reshape(-1, 3)[j], col.reshape(-1, 3)[j]) for j in idx]
open(f"{out}/sparse/0/cameras.txt", "w").write(f"1 PINHOLE {W} {H} {f} {f} {W/2} {H/2}\n")
open(f"{out}/sparse/0/images.txt", "w").write("".join(im_lines))
open(f"{out}/sparse/0/points3D.txt", "w").write("".join(f"{i+1} {p[0]} {p[1]} {p[2]} {int(c[0])} {int(c[1])} {int(c[2])} 0.5\n" for i, (p, c) in enumerate(pts)))
r = subprocess.run(["colmap", "model_converter", "--input_path", f"{out}/sparse/0", "--output_path", f"{out}/sparse/0", "--output_type", "BIN"], capture_output=True, text=True)
if r.returncode or not os.path.exists(f"{out}/sparse/0/images.bin"): sys.exit("colmap model_converter failed:\n" + (r.stdout + r.stderr)[-2000:])
json.dump([[list(map(float, e)), list(map(float, l))] for e, l in tgt], open(f"{out}/cams.json", "w"))
fill = [1 - p[5].mean() for p in pending]; nl = len(tgt) - n_up
print("wrote", len(tgt), "views (%d looking up); filled by flat colour: %.1f%%" % (n_up, 100 * np.mean(fill)), "(level views %.1f%%, upward views %.1f%%)" % (100 * np.mean(fill[:nl]), 100 * np.mean(fill[nl:] or [0])))
