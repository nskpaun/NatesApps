"""Blockout boxes -> mesh + collider GLB, placed in the trained splat's coordinate frame.  blockout_mesh.py NAME"""
import sys, json, numpy as np, trimesh
sys.argv, name = [sys.argv[0], "prep"], sys.argv[1]
import chisel_ring as C
B = C.B
S = np.diag([1.0, 1, -1])
import os
cj = f"{C.D}/{name}/cams.json"
eyes = [c[0] for c in json.load(open(cj))] if os.path.exists(cj) else [B.CAMS[str(i)][0] for i in range(C.N)]
src = np.array([S @ np.array(e) for e in eyes])          # camera centres, blockout world (mirrored)
dst = np.array(json.load(open(f"{C.D}/{name}/{name}_scene.json"))["poses"])[:, :3, 3]  # same cameras, trainer frame
if len(src) != len(dst): raise SystemExit(f"The room has {len(src)} cameras but the trained world has {len(dst)}. Rebuild this world from the start.")
mu_s, mu_d = src.mean(0), dst.mean(0)
U, sv, Vt = np.linalg.svd((dst - mu_d).T @ (src - mu_s))                      # similarity transform (Umeyama)
D = np.diag([1, 1, np.sign(np.linalg.det(U @ Vt))])
R = U @ D @ Vt; s = (sv * np.diag(D)).sum() / ((src - mu_s) ** 2).sum(); t = mu_d - s * R @ mu_s
err = float(np.abs((s * (R @ src.T).T + t) - dst).max()); print("fit error", err, "scale", float(s))
# the two camera lists describe the same rig, so the fit must be near exact; if not, the splat was trained on other cameras (a stale re-run)
if err > 1e-3 * float(np.abs(dst - mu_d).max()): raise SystemExit(f"The room shape does not line up with the trained world (fit error {err:.3g}). Rebuild this world from the start.")
def paint(m, color):
    m.visual.vertex_colors = np.tile([*color, 255], (len(m.vertices), 1)); return m
def prim_mesh(p):
    if p["shape"] == "box":
        m = trimesh.creation.box(extents=2 * np.array(p["h"], float))
        m.apply_transform(trimesh.transformations.rotation_matrix(p.get("yaw", 0.0), [0, 1, 0]))
    else:
        m = trimesh.creation.cylinder(radius=p["r"], height=2 * p["hy"], sections=24)
        m.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]))   # trimesh cylinders lie along z
    m.apply_translation(p["c"]); return paint(m, (170, 170, 170))
lo, hi = np.array(B.ROOM[0], float), np.array(B.ROOM[1], float)
room = trimesh.creation.box(extents=hi - lo); room.apply_translation((lo + hi) / 2); room.invert()
parts = [paint(room, (120, 120, 125))] + [prim_mesh(p) for p in B.PRIMS]
m = trimesh.util.concatenate(parts)
m.vertices = (s * (R @ (m.vertices * [1, 1, -1]).T).T + t)
m.invert()  # the z mirror flipped the winding
m.export(f"{C.D}/{name}/{name}_mesh.glb"); m.export(f"{C.D}/{name}/{name}_mesh_collider.glb")
mid = s * R @ (S @ [C.RW / 2, 0, C.RD / 2]) + t     # middle of the room's floor in the trained frame, so the viewer need not guess it from the mesh
json.dump({"metre": float(s), "room": [C.RW, C.RH, C.RD], "centre": [float(mid[0]), float(mid[2])], "floor": float(mid[1])}, open(f"{C.D}/{name}/{name}_metre.json", "w"))
print("tris", len(m.faces))
