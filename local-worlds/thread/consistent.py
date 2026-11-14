"""Make the generated views agree before training: every surface (each wall, the floor, each furniture piece)
takes its appearance from ONE source picture, projected onto the blockout, then re-rendered from many cameras.
(Masking objects that spill past their blocks, using depth estimates of the pictures, was tried and fragmented surfaces more.)
  consistent.py NAME   reads chisel/NAME/images, writes chisel/NAME_c/{images,sparse/0}
"""
import sys, os, json, numpy as np
from PIL import Image
from scipy.spatial.transform import Rotation
name = sys.argv[1]; sys.argv = [sys.argv[0], "prep"]
import chisel_ring as C
B = C.B; W, H = B.W, B.H
objs = C.objs
NS = 6 + len(objs)

def trace(cam):
    return B.trace(cam, C.PRIM_OBJ)

src_cams = dict(B.CAMS)
src = []
for i in range(C.N):
    t, P, sid = trace(src_cams[str(i)])
    src.append((t, np.asarray(Image.open(f"{C.D}/{name}/images/{i:02d}.png").convert("RGB"), np.float32), np.bincount(sid.ravel(), minlength=NS)))
count = np.stack([s[2] for s in src], 1).astype(float)          # surface x view: pixels of that surface seen
rank = np.argsort(np.argsort(-count, axis=1), axis=1).astype(float)  # 0 = best view for the surface
rank[count < 400] = 1e6
print("owner view per surface:", {(["x0","floor","z0","x1","ceil","z1"] + [o["name"] for o in objs])[s]: int(count[s].argmax()) for s in range(NS)})

# target cameras: the original ring plus an inner ring looking outward at two heights
tgt = [src_cams[str(i)] for i in range(C.N)]
c = C.c
for h, r, look, n in ((C.EYE - 0.25, 0.14, 0.55, 12), (C.EYE + 0.2, 0.225, 0.5, 12)):
    for i in range(n):
        a = 2 * np.pi * (i + 0.5) / n; off = np.array([np.cos(a) * C.RW, 0, np.sin(a) * C.RD])
        tgt.append((tuple(C.free(c + off * r + [0, h, 0])), tuple(c + off * 0.55 + [0, look, 0])))

out = f"{C.D}/{name}_c"; os.makedirs(f"{out}/images", exist_ok=True); os.makedirs(f"{out}/sparse/0", exist_ok=True)
S = np.diag([1.0, 1, -1]); f = W / 2 / np.tan(np.radians(B.FOV) / 2)
im_lines, pts = [], []; rng = np.random.default_rng(0); sums = np.zeros((NS, 3)); ns = np.zeros(NS); pending = []
for k, cam in enumerate(tgt):
    t, P, sid = trace(cam)
    best = np.full((H, W), 1e9); col = np.zeros((H, W, 3), np.float32)
    for v in range(C.N):
        px, py, dist, z = B.project(src_cams[str(v)], P)
        xi, yi = np.round(px).astype(int), np.round(py).astype(int)
        ok = (z > 0.05) & (xi >= 1) & (xi < W - 1) & (yi >= 1) & (yi < H - 1)
        xi, yi = np.clip(xi, 0, W - 1), np.clip(yi, 0, H - 1)
        ok &= np.abs(src[v][0][yi, xi] - dist) < 0.05
        score = np.where(ok, rank[sid, v], 1e9)
        take = score < best
        best = np.where(take, score, best); col[take] = src[v][1][yi[take], xi[take]]
    have = best < 1e5
    np.add.at(sums, sid[have], col[have]); np.add.at(ns, sid[have], 1)
    pending.append((k, cam, P, sid, col, have))
mean = sums / np.maximum(ns, 1)[:, None]
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
os.system(f"colmap model_converter --input_path {out}/sparse/0 --output_path {out}/sparse/0 --output_type BIN 2>&1 | grep -i error")
json.dump([[list(map(float, e)), list(map(float, l))] for e, l in tgt], open(f"{out}/cams.json", "w"))
print("wrote", len(tgt), "views; filled by flat colour: %.1f%%" % (100 * np.mean([1 - p[5].mean() for p in pending])))
