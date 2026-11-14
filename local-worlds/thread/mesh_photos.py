"""Office mesh from photo depth: Depth Pro maps aligned to COLMAP's 3D points, fused into a volume, coloured by the photos.
  mesh_photos.py SCENE_DIR(office) OUT_PREFIX
Writes OUT_PREFIX.glb (visual, with smoothed normals), OUT_PREFIX_collider.glb and OUT_PREFIX_meta.json with whichever of
{"metre", "floor", "up"} could be estimated (raw trainer frame; the viewer falls back to its own guesses for missing ones).
"""
import sys, json, numpy as np, open3d as o3d, trimesh
from PIL import Image
from scipy import ndimage, sparse
from scipy.spatial.transform import Rotation
d, out = sys.argv[1:3]
cams = {}
for l in open(f"{d}/txt/cameras.txt"):
    if l[0] != "#": v = l.split(); cams[int(v[0])] = (int(v[2]), int(v[3]), float(v[4]), float(v[5]), float(v[6]), float(v[7]))
X = {}
for l in open(f"{d}/txt/points3D.txt"):
    if l[0] != "#": v = l.split(); X[int(v[0])] = [float(x) for x in v[1:4]]
L = [l for l in open(f"{d}/txt/images.txt") if l[0] != "#"]
imgs = []
for a, b in zip(L[::2], L[1::2]):
    v = a.split(); R = Rotation.from_quat([float(v[2]), float(v[3]), float(v[4]), float(v[1])]).as_matrix(); t = np.array([float(x) for x in v[5:8]])
    p = np.array(b.split(), float).reshape(-1, 3); p = p[p[:, 2] >= 0]
    imgs.append(dict(name=v[9], cam=int(v[8]), R=R, t=t, xy=p[:, :2], X=np.array([X[int(i)] for i in p[:, 2]])))
# COLMAP frame -> trainer frame (the trainer re-centres and re-scales): match camera centres, trying plausible orderings
P = np.array(json.load(open(f"{d}/scene.json"))["poses"])[:, :3, 3]
def fit(src, dst):
    ms, md = src.mean(0), dst.mean(0); U, sv, Vt = np.linalg.svd((dst - md).T @ (src - ms)); D = np.diag([1, 1, np.sign(np.linalg.det(U @ Vt))])
    R = U @ D @ Vt; s = (sv * np.diag(D)).sum() / ((src - ms) ** 2).sum(); t = md - s * R @ ms
    return s, R, t, np.abs(s * (R @ src.T).T + t - dst).max()
best = None
for label, order in (("file", imgs), ("name", sorted(imgs, key=lambda i: i["name"]))):
    C = np.array([-i["R"].T @ i["t"] for i in order]); r = fit(C, P)
    if best is None or r[3] < best[3]: best = (*r, label)
s, Rs, ts, err, label = best
print("frame fit: order by", label, "max error", float(err), "scale", float(s))
assert err < 1e-3
allX = np.array(list(X.values())); Xm = s * (Rs @ allX.T).T + ts
lo, hi = np.percentile(Xm, [2, 98], axis=0); ctr, extent = (lo + hi) / 2, float((hi - lo).max()) * 1.25
RES = 400; voxel = extent / RES; metres = []
vol = o3d.pipelines.integration.UniformTSDFVolume(length=extent, resolution=RES, sdf_trunc=5 * voxel,
        color_type=o3d.pipelines.integration.TSDFVolumeColorType.RGB8, origin=ctr - extent / 2)
for im in imgs:
    w, h, fx, fy, cx, cy = cams[im["cam"]]
    mono = np.load(f"{d}/mono/{im['name'].rsplit('.', 1)[0]}.npy")
    mono = np.asarray(Image.fromarray(mono).resize((w // 2, h // 2), Image.BILINEAR))
    z = (im["X"] @ im["R"].T + im["t"])[:, 2] * s                       # true depth at the solved points, trainer units
    u, v = np.clip((im["xy"] / 2).astype(int).T, 0, [[w // 2 - 1], [h // 2 - 1]])
    m = mono[v, u]; ok = z > 0
    A = np.stack([m, np.ones_like(m)], 1); keep = ok.copy()
    for _ in range(4):                                                    # robust fit of 1/z = a*mono + b
        coef = np.linalg.lstsq(A[keep], 1 / z[keep], rcond=None)[0]; res = np.abs(A @ coef - 1 / z) * z
        keep = ok & (res < max(0.05, 2.5 * np.median(res[keep])))
    inv = np.maximum(coef[0] * mono + coef[1], 1e-6); depth = 1 / inv
    # Depth Pro's raw output is canonical inverse depth: metres = fx / (w * mono). A scale-only fit 1/z = k*mono gives trainer units per metre.
    if keep.sum() >= 20 and (m[keep] > 0).all(): metres.append((w / fx) / np.median(1 / (z[keep] * m[keep])))
    grad = ndimage.maximum_filter(depth, 5) / ndimage.minimum_filter(depth, 5)
    depth[(grad > 1.12) | (depth > extent * 1.2)] = 0                    # drop flying pixels at depth edges
    col = np.asarray(Image.open(f"{d}/dense/images/{im['name']}").convert("RGB").resize((w // 2, h // 2)))
    rgbd = o3d.geometry.RGBDImage.create_from_color_and_depth(o3d.geometry.Image(np.ascontiguousarray(col)), o3d.geometry.Image(depth.astype(np.float32)),
        depth_scale=1.0, depth_trunc=extent * 1.2, convert_rgb_to_intensity=False)
    E = np.eye(4); E[:3, :3] = im["R"] @ Rs.T; E[:3, 3] = s * im["t"] - im["R"] @ Rs.T @ ts
    vol.integrate(rgbd, o3d.camera.PinholeCameraIntrinsic(w // 2, h // 2, fx / 2, fy / 2, cx / 2, cy / 2), E)
    print(im["name"], "points", int(keep.sum()), "of", len(z), "median error %.1f%%" % (100 * np.median(res[keep])))
mesh = vol.extract_triangle_mesh()
tri, n_tri, _ = mesh.cluster_connected_triangles(); tri, n_tri = np.asarray(tri), np.asarray(n_tri)
mesh.remove_triangles_by_mask(n_tri[tri] < n_tri.max() * 0.01); mesh.remove_unreferenced_vertices()
print("raw tris", len(mesh.triangles))

def edges(T): return np.unique(np.sort(T[:, [0, 1, 1, 2, 2, 0]].reshape(-1, 2), 1), axis=0, return_inverse=True, return_counts=True)[1:]
def stats(mm):                                                            # (boundary edges, connected components, edges whose two faces are wound against each other)
    T = np.asarray(mm.triangles); flip = np.unique(T.astype(np.int64) * len(mm.vertices) + T[:, [1, 2, 0]], return_counts=True)[1]
    return int((edges(T)[1] == 1).sum()), len(mm.cluster_connected_triangles()[1]), int((flip > 1).sum())
STATS = "boundary edges %d, components %d, inconsistently wound edges %d"
def orient(mm, first):                                                    # fill_holes winds its patch triangles at random: wind each one (from index `first` on) like the face
    T = np.asarray(mm.triangles).copy(); n = len(mm.vertices)             # across a shared edge, spreading inwards through the patch; drop the few that cannot agree with all neighbours
    near = np.zeros(n, bool); near[T[first:]] = True; old = T[:first][near[T[:first]].any(1)].astype(np.int64)
    D = set((old * n + old[:, [1, 2, 0]]).reshape(-1).tolist()); todo = list(range(first, len(T))); drop = np.zeros(len(T), bool); flipped = 0
    while todo:
        later = []
        for i in todo:
            a, b, c = T[i].tolist(); fw = [a * n + b, b * n + c, c * n + a]; bw = [b * n + a, c * n + b, a * n + c]
            same = sum(k in D for k in fw); opp = sum(k in D for k in bw)  # a neighbour must run the shared edge the other way
            if not same and not opp: later.append(i); continue             # no oriented neighbour yet
            if same and opp: drop[i] = True; continue
            if same: T[i] = [a, c, b]; fw = bw; flipped += 1
            D.update(fw)
        if len(later) == len(todo): break
        todo = later
    print("  patch triangles %d, rewound %d, dropped %d" % (len(T) - first, flipped, int(drop.sum())))
    mm.triangles = o3d.utility.Vector3iVector(T); mm.remove_triangles_by_mask(drop); return mm
def manifold(mm, first=0):                                                # drop triangles (from index `first` on) that sit on an edge with three or more faces
    T = np.asarray(mm.triangles); inv, cnt = edges(T); bad = (cnt[inv.reshape(-1)] > 2).reshape(-1, 3).any(1); bad[:first] = False
    mm.remove_triangles_by_mask(bad); return mm                           # (Open3D's remove_non_manifold_edges is not used: it gave different results run to run)
def fill(mm, radius):                                                     # close holes up to `radius` (trainer units); bigger openings (doorways, the capture's edge) stay open
    try: f = o3d.t.geometry.TriangleMesh.from_legacy(mm).fill_holes(hole_size=radius).to_legacy()
    except Exception as e: print("fill_holes skipped:", e); return mm
    k = len(mm.triangles)                                                 # it should only append triangles between existing vertices; anything else is not trusted
    if len(f.vertices) != len(mm.vertices) or len(f.triangles) < k or (np.asarray(f.triangles)[:k] != np.asarray(mm.triangles)).any(): return mm
    f.vertices, f.vertex_colors = mm.vertices, mm.vertex_colors           # same vertices in the same order (checked above), but the tensor round trip sometimes returns garbage colours
    return orient(manifold(f, k), k)                                      # some patches share an edge with existing faces, and decimation can spin for minutes on those
def tidy(mm, min_size):                                                   # after decimation: manifold again, and no loose pieces with a bounding box under min_size
    mm.remove_degenerate_triangles(); mm.remove_duplicated_triangles(); manifold(mm)
    tri, n_tri, _ = mm.cluster_connected_triangles(); tri = np.asarray(tri); V, T = np.asarray(mm.vertices), np.asarray(mm.triangles)
    lo = np.full((len(n_tri), 3), np.inf); hi = -lo
    for k in range(3): np.minimum.at(lo, tri, V[T[:, k]]); np.maximum.at(hi, tri, V[T[:, k]])
    small = np.linalg.norm(hi - lo, axis=1) < min_size; small[np.argmax(n_tri)] = False   # by size, not triangle count, so free-standing objects stay
    mm.remove_triangles_by_mask(small[tri]); mm.remove_unreferenced_vertices(); return mm

# ---- scale, up and floor. A key is only written when it could be estimated; a missing key means the viewer keeps its own guess.
S = json.load(open(f"{d}/scene.json"))
up0 = np.array(S["up"]) if "up" in S else np.array(S["poses"])[:, :3, 1].mean(0); up0 = up0 / np.linalg.norm(up0)
meta = {}
if len(metres) >= 3: meta["metre"] = float(np.median(metres))
hv = np.asarray(mesh.vertices) @ up0; h_lo, h_hi = np.percentile(hv, [4, 96])
unit = meta.get("metre", (h_hi - h_lo) / 2.4)                             # trainer units per metre; without Depth Pro's, the viewer's old guess (a 2.4 m tall capture)
print("metre: Depth Pro %s over %d photos (spread %.2f); height-span guess %.3f" % ("%.3f" % meta["metre"] if "metre" in meta else "none", len(metres), np.std(metres) if metres else 0, (h_hi - h_lo) / 2.4))
# Floor: planes among upward-facing points near the bottom (35% of the height range, at most 0.8 m so table tops stay out). Its normal is a better up than the mean camera up.
o3d.utility.random.seed(0); mesh.compute_vertex_normals(); pc = mesh.sample_points_uniformly(200000); pts, nrm = np.asarray(pc.points), np.asarray(pc.normals)
cand = pts[(pts @ up0 < h_lo + min(0.35 * (h_hi - h_lo), 0.8 * unit)) & (nrm @ up0 > np.cos(np.radians(25)))]; rest, planes = cand, []
while len(rest) >= 1000 and len(planes) < 3:                              # peel up to three planes: the biggest may be a bed or a platform, not the floor
    idx = np.array(o3d.geometry.PointCloud(o3d.utility.Vector3dVector(rest)).segment_plane(0.05 * unit, 3, 10000)[1])   # 5 cm: fused monocular depth is wavy
    for _ in range(5):                                                    # least-squares refit on the inliers: the 3-point plane differs from run to run
        c = rest[idx].mean(0); n = np.linalg.svd(rest[idx] - c, full_matrices=False)[2][2]; idx = np.where(np.abs((rest - c) @ n) < 0.05 * unit)[0]
        if len(idx) < 3: break
    if len(idx) < 3: break
    n = n * np.sign(n @ up0); planes.append((len(idx), n, float(np.median(rest[idx] @ up0)), float(np.median(rest[idx] @ n)))); rest = np.delete(rest, idx, 0)
    print("floor plane %d: %d of %d low upward points, height %.3f, tilt from camera up %.1f deg" % (len(planes), len(idx), len(cand), planes[-1][2], np.degrees(np.arccos(min(1, n @ up0)))))
if planes:
    big = max(planes, key=lambda q: q[0]); pick = big
    for q in planes:                                                      # a clearly lower plane (not the same wavy floor) of comparable size and tilt is the real floor
        if q[2] < pick[2] - 0.3 * unit and q[0] >= 0.5 * big[0] and q[1] @ big[1] > np.cos(np.radians(10)): pick = q
    cnt, n, h, fl = pick; tilt = np.degrees(np.arccos(min(1, n @ up0)))
    if big[0] >= max(1000, 0.25 * len(cand)) and tilt < 25 and abs(h - h_lo) < 0.3 * unit:   # and it must agree with the lowest heights of the mesh
        meta["up"] = n.tolist(); meta["floor"] = fl                       # floor = height along meta["up"]; use the two together
    else: print("floor plane rejected: %d points, tilt %.1f deg, %.3f against lowest heights %.3f" % (cnt, tilt, h, h_lo))
if "floor" not in meta: print("floor plane: not found, the viewer keeps its percentile guess (%.3f along camera up)" % h_lo)
json.dump(meta, open(out + "_meta.json", "w")); print("meta", json.dumps(meta))
mesh.vertex_normals = mesh.triangle_normals = o3d.utility.Vector3dVector()

# ---- visual mesh: pinholes closed (a bigger patch would smear colour), crumbs dropped
print("fused: " + STATS % stats(mesh), flush=True)
mesh = fill(mesh, 0.06 * unit)
vis = tidy(mesh.simplify_quadric_decimation(300000) if len(mesh.triangles) > 300000 else mesh, 0.1 * unit)
def soft_normals(mm, rounds=3):                                           # normals for lighting only: from a Taubin-smoothed copy, then averaged with the neighbours.
    sm = mm.filter_smooth_taubin(10); sm.compute_vertex_normals(); N = np.asarray(sm.vertex_normals).copy(); T = np.asarray(mm.triangles)   # The geometry's own normals
    e = np.concatenate([T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]]); n = len(N)                                                           # differ by about 19 degrees from
    A = sparse.coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(n, n)).tocsr(); A = A + A.T + sparse.identity(n)                  # one vertex to the next, which
    for _ in range(rounds): N = A @ N; N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-9)                                    # shows as speckle under the lamp.
    N[np.linalg.norm(N, axis=1) < 0.5] = up0; return N
# ---- collider: smoothed, holes up to 0.3 m radius closed before and after decimation (decimation tears new ones), loose bits dropped
colm = tidy(fill(mesh.filter_smooth_taubin(5), 0.3 * unit).simplify_quadric_decimation(50000), 0.25 * unit)
print("collider before closing: tris %d, " % len(colm.triangles) + STATS % stats(colm))
colm = fill(colm, 0.3 * unit)
def to_tm(mm):
    c = np.asarray(mm.vertex_colors)
    if len(c) and (not np.isfinite(c).all() or c.min() < -0.05 or c.max() > 1.05): print("WARNING: vertex colours out of range (%g to %g), the mesh colours are wrong" % (c.min(), c.max()))
    c = (np.clip(np.nan_to_num(c), 0, 1) * 255).astype(np.uint8)
    return trimesh.Trimesh(np.asarray(mm.vertices), np.asarray(mm.triangles), vertex_colors=c, vertex_normals=soft_normals(mm), process=False)
to_tm(vis).export(out + ".glb"); to_tm(colm).export(out + "_collider.glb")
print("visual: tris %d, " % len(vis.triangles) + STATS % stats(vis))
print("collider: tris %d, " % len(colm.triangles) + STATS % stats(colm))
