"""Lift the things that move away from their spot out of a trained splat: each gets a splat file of its own, a mesh and a collider.
  movers.py ROOM WITH   (gen_c gen_m) reads WORLD/ROOM/lifted.json and the splat trained with those things, WORLD/WITH/WITH.ply;
                        writes WORLD/ROOM/{mover_NNN.ply, mover_NNN.glb, mover_NNN_collider.glb, movers.json}
All or nothing: if any of those things gets too few splats, nothing is written and the step fails.
The splat rows are copied as they are, so all three files of a mover are in the frame of the WITH splat; movers.json gives the
way there from room metres. Also holds what blockout_mesh.py shares with this step.
"""
import sys, os, json, glob, numpy as np, trimesh
if __name__ == "__main__": args, sys.argv = sys.argv[1:], [sys.argv[0], "prep"]
import chisel_ring as C
B = C.B
S = np.diag([1.0, 1, -1])
NEAR = 0.05      # m: a splat this close to a mover's surface is part of it

def fit(name):
    """Scale, rotation and shift from the (mirrored) blockout to the frame of the splat trained in folder `name`, found
    from the two lists of the same cameras."""
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
    return s, R, t

def from_room(s, R, t):
    """The fit as 16 numbers, a 4x4 matrix row by row: room metres -> the splat file's units, mirror included."""
    M = np.eye(4); M[:3, :3] = s * R @ S; M[:3, 3] = t
    return [float(v) for v in M.ravel()]

def to_file(m, s, R, t):
    """Move a mesh in room metres into the splat file's frame."""
    m.vertices = (s * (R @ (m.vertices * [1, 1, -1]).T).T + t)
    m.invert()  # the z mirror flipped the winding
    return m

def paint(m, color):
    m.visual.vertex_colors = np.tile([*color, 255], (len(m.vertices), 1)); return m

def prim_mesh(p, faces):
    if p["shape"] == "mesh":            # a generated shape, thinned to at most `faces` triangles
        import open3d as o3d
        z = np.load(p["file"])
        g = o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(z["V"].astype(float)), o3d.utility.Vector3iVector(z["F"].astype(np.int32)))
        if len(z["F"]) > faces: g = g.simplify_quadric_decimation(faces)
        m = trimesh.Trimesh(np.asarray(g.vertices), np.asarray(g.triangles), process=False)
        if m.volume < 0: m.invert()     # faces must point outwards, like the boxes'
        return paint(m, (170, 170, 170))
    if p["shape"] == "box":
        m = trimesh.creation.box(extents=2 * np.array(p["h"], float))
        m.apply_transform(trimesh.transformations.rotation_matrix(p.get("yaw", 0.0), [0, 1, 0]))
    else:
        m = trimesh.creation.cylinder(radius=p["r"], height=2 * p["hy"], sections=24)
        m.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]))   # trimesh cylinders lie along z
    m.apply_translation(p["c"]); return paint(m, (170, 170, 170))

def obox(oi):
    """An object's bounds in room metres, turned to its own heading: {"c", "h", "yaw"}. Its shape's bounds if it has one,
    else its primitives'."""
    o = C.objs[oi]
    yaw = o.get("yaw", next((p.get("yaw", 0.0) for p in o["prims"] if p["shape"] == "box"), 0.0))
    yaw = float(yaw) if isinstance(yaw, (int, float)) and np.isfinite(yaw) else 0.0
    pts = np.load(C.SHAPES[oi])["V"].astype(float) if oi in C.SHAPES else np.concatenate([prim_mesh(p, 0).vertices for p in o["prims"]])
    cs, sn = np.cos(yaw), np.sin(yaw)
    L = np.stack([cs * pts[:, 0] - sn * pts[:, 2], pts[:, 1], sn * pts[:, 0] + cs * pts[:, 2]], 1)   # as the blockout turns a box
    lo, hi = L.min(0), L.max(0); m = (lo + hi) / 2
    return {"c": [float(cs * m[0] + sn * m[2]), float(m[1]), float(-sn * m[0] + cs * m[2])], "h": [float(v) for v in (hi - lo) / 2], "yaw": yaw}

SCENES = {}
def dist(oi, P):
    """Distance in metres from room points P (n, 3) to object oi: to the surface of its shape, or to its boxes and
    cylinders (0 inside those)."""
    d = np.full(len(P), np.inf)
    for p in C.OBJ_PRIMS[oi]:
        o = P - np.array(p["c"], float)
        if p["shape"] == "mesh":
            import open3d as o3d
            if p["file"] not in SCENES:
                z = np.load(p["file"]); SCENES[p["file"]] = o3d.t.geometry.RaycastingScene()
                SCENES[p["file"]].add_triangles(o3d.core.Tensor(z["V"].astype(np.float32)), o3d.core.Tensor(z["F"].astype(np.uint32)))
            dd = SCENES[p["file"]].compute_distance(o3d.core.Tensor(P.astype(np.float32))).numpy()
        elif p["shape"] == "box":
            cs, sn = np.cos(p.get("yaw", 0.0)), np.sin(p.get("yaw", 0.0))
            l = np.stack([cs * o[:, 0] - sn * o[:, 2], o[:, 1], sn * o[:, 0] + cs * o[:, 2]], 1)
            dd = np.linalg.norm(np.maximum(np.abs(l) - np.array(p["h"], float), 0), axis=1)
        else: dd = np.hypot(np.maximum(np.hypot(o[:, 0], o[:, 2]) - p["r"], 0), np.maximum(np.abs(o[:, 1]) - p["hy"], 0))
        d = np.minimum(d, dd)
    return d

def read_ply(path):
    """A binary splat file: its header lines, column names and table (one float32 row per splat)."""
    buf = open(path, "rb").read(); end = buf.index(b"end_header\n") + 11
    head = buf[:end].decode().splitlines()
    cols = [l.split()[2] for l in head if l.startswith("property float ")]
    if "binary_little_endian" not in head[1] or len(cols) != sum(l.startswith("property") for l in head): raise SystemExit(f"{path} is not a splat file this step can read.")
    n = int(next(l for l in head if l.startswith("element vertex")).split()[2])
    return head, cols, np.frombuffer(buf, "<f4", n * len(cols), end).reshape(n, len(cols))

def write_ply(path, head, rows):
    head = [f"element vertex {len(rows)}" if l.startswith("element vertex") else l for l in head]
    open(path, "wb").write(("\n".join(head) + "\n").encode() + np.ascontiguousarray(rows, "<f4").tobytes())

def main(room, src):
    out = f"{C.D}/{room}"
    for old in glob.glob(f"{out}/mover_*") + glob.glob(f"{out}/movers.json"): os.remove(old)   # an earlier run's
    lifted = [i for i in json.load(open(f"{out}/lifted.json")) if type(i) is int and 0 <= i < len(C.objs)]
    s, R, t = fit(src)
    head, cols, rows = read_ply(f"{C.D}/{src}/{src}.ply")
    col = lambda *names: rows[:, [cols.index(n) for n in names]].astype(float)
    P = (col("x", "y", "z") - t) @ R / s * [1, 1, -1]                # splat centres in room metres
    size = 2 * np.exp(col("scale_0", "scale_1", "scale_2").max(1)) / s   # longest axis in metres
    # off the ground (those are a coin toss between the thing and what it stands on), not a stretched stray, not see-through
    solid = (P[:, 1] > 0.02) & (size < 0.3) & (col("opacity")[:, 0] > np.log(0.05 / 0.95))
    box = [C.bounds(ps) for ps in C.OBJ_PRIMS]
    done, short = [], []
    for i in lifted:
        lo, hi = box[i]
        idx = np.nonzero(solid & np.all((P > lo - NEAR) & (P < hi + NEAR), 1))[0]
        d = dist(i, P[idx]); idx, d = idx[d < NEAR], d[d < NEAR]
        if lo[1] < 0.1:                  # it stands on the ground: the grass and shadow at its foot stay behind, or it drags a skirt of them along
            p = P[idx]; mine = (p[:, 1] > 0.06) & ((p[:, 1] > 0.15) | np.all((p[:, [0, 2]] > lo[[0, 2]]) & (p[:, [0, 2]] < hi[[0, 2]]), 1)); idx, d = idx[mine], d[mine]
        for j in range(len(C.objs)):     # a splat nearer to something else (what this stands on, a neighbour) belongs to that
            if j != i and len(idx) and np.all(box[j][0] - NEAR < hi) and np.all(box[j][1] + NEAR > lo):
                mine = dist(j, P[idx]) >= d; idx, d = idx[mine], d[mine]
        b = obox(i); hx, hy, hz = b["h"]
        need = min(300, max(30, 150 * 8 * (hx * hy + hy * hz + hx * hz)))    # a small thing has few splats; far fewer than its size gives is a failed split
        if len(idx) < need:
            print(f"{C.objs[i]['name']}: only {len(idx)} splats found, {int(np.ceil(need))} needed"); short.append(C.objs[i]["name"]); continue
        write_ply(f"{out}/mover_{i:03d}.ply", head, rows[idx])
        # the shown mesh keeps a shape's detail; the collider is a rough form the viewer can wrap a hull around
        for suffix, faces in (("", 20000), ("_collider", 500)):
            ps = C.OBJ_PRIMS[i]
            m = trimesh.util.concatenate([prim_mesh(p, max(12, faces // len(ps))) for p in ps])
            to_file(m, s, R, t).export(f"{out}/mover_{i:03d}{suffix}.glb")
        done.append({"i": i, "ply": f"mover_{i:03d}.ply", "mesh": f"mover_{i:03d}.glb", "collider": f"mover_{i:03d}_collider.glb", "fromRoom": from_room(s, R, t), "splats": int(len(idx))})
        print(f"{C.objs[i]['name']}: {len(idx)} splats lifted out")
    if short:   # the room's splat was trained without these, so a world built on it would lack them: fail, and the caller keeps the splat that has them all
        for old in glob.glob(f"{out}/mover_*"): os.remove(old)
        raise SystemExit(f"Could not lift out: {', '.join(short)}.")
    json.dump(done, open(f"{out}/movers.json", "w"))

if __name__ == "__main__": main(*args)
