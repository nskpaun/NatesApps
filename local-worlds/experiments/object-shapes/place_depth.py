import sys, os, numpy as np, trimesh, open3d as o3d
from PIL import Image
sys.path.insert(0, os.getcwd())
import chisel_ring as C
B = C.B
out = sys.argv[2]
oi = [o["name"] for o in C.objs].index("car_center")
blk = C.objs[oi]["prims"][0]
B.PRIMS = [p for p, o in zip(B.PRIMS, C.PRIM_OBJ) if o != oi]
m = trimesh.load(sys.argv[1], force="mesh")
V = np.asarray(m.vertices, float) - m.bounds.mean(0)
V = V[:, [2, 1, 0]] * [1, 1, -1]                        # turn a quarter about the vertical: the car's length runs along x
ext = V.max(0) - V.min(0)
s = min(2 * np.array(blk["h"]) / ext)
V = V * s
base = max((p["c"][1] + p["h"][1] for p in B.PRIMS if p["shape"] == "box" and B.inside([blk["c"][0], p["c"][1], blk["c"][2]], p)), default=0.0)
V += [blk["c"][0], base - V[:, 1].min(), blk["c"][2]]
print("scale", round(s, 3), "size", (V.max(0) - V.min(0)).round(2), "rests at", base)
trimesh.Trimesh(V, m.faces).export(f"{out}/car_placed.glb")
sc = o3d.t.geometry.RaycastingScene()
sc.add_triangles(o3d.core.Tensor(V.astype(np.float32)), o3d.core.Tensor(np.asarray(m.faces, np.uint32)))
for k in sys.argv[3:]:
    cam = B.CAMS[k]
    t, _ = B.trace(cam)
    eye, d = B.rays(cam)
    r = np.concatenate([np.broadcast_to(eye, d.shape), d], -1).astype(np.float32)
    t = np.minimum(t, sc.cast_rays(o3d.core.Tensor(r))["t_hit"].numpy())
    inv = 1 / np.maximum(t, 0.3); lo, hi = np.percentile(inv, [1, 99])
    img = np.clip((inv - lo) / max(hi - lo, 1e-6), 0, 1) ** 0.6
    Image.fromarray((img * 255).astype(np.uint8)).convert("RGB").save(f"{out}/depth_{int(k):02d}.png")
