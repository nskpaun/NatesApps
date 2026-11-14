import sys, numpy as np, trimesh, open3d as o3d
from PIL import Image
m = trimesh.load(sys.argv[1], force="mesh")
print("bounds", m.bounds.round(3), "extent", m.extents.round(3), "watertight", m.is_watertight)
sc = o3d.t.geometry.RaycastingScene()
sc.add_triangles(o3d.core.Tensor(np.asarray(m.vertices, np.float32)), o3d.core.Tensor(np.asarray(m.faces, np.uint32)))
c = m.bounds.mean(0); r = np.linalg.norm(m.extents) * 1.15
tiles = []
for az, el in [(0, 15), (45, 20), (90, 15), (135, 20), (180, 15), (225, 20), (270, 15), (0, 89)]:
    a, e = np.radians(az), np.radians(el)
    eye = c + r * np.array([np.sin(a) * np.cos(e), np.sin(e), np.cos(a) * np.cos(e)])
    rays = o3d.t.geometry.RaycastingScene.create_rays_pinhole(fov_deg=40, center=c.tolist(), eye=eye.tolist(), up=[0, 1, 0] if el < 80 else [0, 0, -1], width_px=384, height_px=384)
    h = sc.cast_rays(rays)
    n = h["primitive_normals"].numpy(); hit = np.isfinite(h["t_hit"].numpy())
    d = rays.numpy()[..., 3:]; d /= np.linalg.norm(d, axis=-1, keepdims=True)
    sh = np.abs((n * d).sum(-1)) * 0.8 + 0.2
    tiles.append(np.where(hit, sh * 255, 255).astype(np.uint8))
Image.fromarray(np.vstack([np.hstack(tiles[:4]), np.hstack(tiles[4:])])).save(sys.argv[2])
