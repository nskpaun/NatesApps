"""Office mesh from photo depth: Depth Pro maps aligned to COLMAP's 3D points, fused into a volume, coloured by the photos.
  mesh_photos.py SCENE_DIR(office) OUT_PREFIX
"""
import sys, json, numpy as np, open3d as o3d, trimesh
from PIL import Image
from scipy import ndimage
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
RES = 400; voxel = extent / RES
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
vis = mesh.simplify_quadric_decimation(300000) if len(mesh.triangles) > 300000 else mesh
colm = mesh.filter_smooth_taubin(5).simplify_quadric_decimation(50000)
def to_tm(mm):
    c = (np.asarray(mm.vertex_colors) * 255).astype(np.uint8)
    return trimesh.Trimesh(np.asarray(mm.vertices), np.asarray(mm.triangles), vertex_colors=c, process=False)
to_tm(vis).export(out + ".glb"); to_tm(colm).export(out + "_collider.glb")
print("visual", len(vis.triangles), "collider", len(colm.triangles))
