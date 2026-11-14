"""Blockout geometry: a box room holding boxes (optionally turned about the vertical axis) and upright cylinders.
Renders depth from any camera by ray casting, and projects points into cameras. Used by the world pipeline in ../thread.

Coordinates: x right, y up, z towards the back wall; the room spans (0,0,0) to (width, height, depth).
A primitive is {"shape": "box", "c": centre, "h": half sizes, "yaw": radians}, {"shape": "cyl", "c": centre, "r": radius, "hy": half height}
or {"shape": "mesh", "file": npz with V (n,3) and F (m,3) in room coordinates, "c": centre and "h": half sizes of its bounding box}.
"""
import os
import numpy as np

W, H, FOV = 1024, 768, 65.0
ROOM = ((0, 0, 0), (4.0, 2.6, 4.0))
PRIMS = []   # list of primitives
CAMS = {}    # name -> (eye, target)


def basis(cam):
    eye, tgt = np.array(cam[0], float), np.array(cam[1], float)
    f = tgt - eye
    f /= np.linalg.norm(f)
    r = np.cross(f, [0, 1, 0])
    r /= np.linalg.norm(r)
    return eye, r, np.cross(r, f), f


def rays(cam):
    eye, r, u, f = basis(cam)
    t = np.tan(np.radians(FOV) / 2)
    xs = (np.arange(W) + 0.5) / W * 2 - 1
    ys = 1 - (np.arange(H) + 0.5) / H * 2
    X, Y = np.meshgrid(xs * t, ys * t * H / W)
    d = -X[..., None] * r + Y[..., None] * u + f   # x mirrored so the left wall appears on screen-left
    return eye, d / np.linalg.norm(d, axis=-1, keepdims=True)


def slab(eye, d, lo, hi):
    with np.errstate(divide="ignore", invalid="ignore"):
        t1 = (np.array(lo) - eye) / d
        t2 = (np.array(hi) - eye) / d
    return np.minimum(t1, t2).max(-1), np.maximum(t1, t2).min(-1)


SCENES = {}   # (process id, mesh file) -> ray-casting scene


def mesh_cast(eye, d, p):
    """Distance along each ray to a mesh primitive (inf where missed) and the unit surface normal there, turned to face
    the ray's origin (zero where missed)."""
    try: import open3d as o3d            # only here: the painting environment has no Open3D and never ray-casts a mesh
    except ImportError: raise SystemExit("Generated shapes can only be rendered in the thread environment: run this step with thread/.venv/bin/python.")
    key = (os.getpid(), p["file"])       # a scene built before a fork must not be used in the child: one per process
    if key not in SCENES:
        z = np.load(p["file"])
        SCENES[key] = o3d.t.geometry.RaycastingScene()
        SCENES[key].add_triangles(o3d.core.Tensor(z["V"].astype(np.float32)), o3d.core.Tensor(z["F"].astype(np.uint32)))
    eye = np.asarray(eye, float); dd = d.reshape(-1, 3)
    t = np.full(len(dd), np.inf); n = np.zeros((len(dd), 3), np.float32)
    h = np.array(p["h"], float) + 1e-3
    tn, tf = slab(eye - np.array(p["c"], float), dd, -h, h)
    m = (tn < tf) & (tf > 0)             # only rays that cross the bounding box are cast
    if m.any():
        r = np.concatenate([np.broadcast_to(eye, (int(m.sum()), 3)), dd[m]], 1).astype(np.float32)
        got = SCENES[key].cast_rays(o3d.core.Tensor(r), nthreads=1)   # one thread: callers already run one process per core
        nn = got["primitive_normals"].numpy()
        nn[(nn * dd[m]).sum(1) > 0] *= -1
        t[m] = got["t_hit"].numpy(); n[m] = nn
    return t.reshape(d.shape[:-1]), n.reshape(d.shape)


def hit(eye, d, p):
    """Distance along each ray to the primitive's surface (inf where missed or, for boxes and cylinders, where the ray
    starts inside it)."""
    if p["shape"] == "mesh": return mesh_cast(eye, d, p)[0]
    c = np.array(p["c"], float)
    if p["shape"] == "box":
        cs, sn = np.cos(p.get("yaw", 0.0)), np.sin(p.get("yaw", 0.0))
        o = eye - c
        ol = np.array([cs * o[0] - sn * o[2], o[1], sn * o[0] + cs * o[2]])
        dl = np.stack([cs * d[..., 0] - sn * d[..., 2], d[..., 1], sn * d[..., 0] + cs * d[..., 2]], -1)
        h = np.array(p["h"], float)
        tn, tf = slab(ol, dl, -h, h)
        return np.where((tn < tf) & (tn > 0), tn, np.inf)
    # upright cylinder: side wall, then caps
    o = eye - c
    a = d[..., 0] ** 2 + d[..., 2] ** 2
    b = 2 * (o[0] * d[..., 0] + o[2] * d[..., 2])
    cc = o[0] ** 2 + o[2] ** 2 - p["r"] ** 2
    with np.errstate(divide="ignore", invalid="ignore"):
        disc = b * b - 4 * a * cc
        t = (-b - np.sqrt(np.maximum(disc, 0))) / (2 * a)
        y = o[1] + t * d[..., 1]
        side = np.where((disc > 0) & (t > 0) & (np.abs(y) <= p["hy"]), t, np.inf)
        best = side
        for cap in (p["hy"], -p["hy"]):
            tc = (cap - o[1]) / d[..., 1]
            x, z = o[0] + tc * d[..., 0], o[2] + tc * d[..., 2]
            best = np.minimum(best, np.where((tc > 0) & (x * x + z * z <= p["r"] ** 2), tc, np.inf))
    return best


def inside(pt, p, margin=0.0):
    c = np.array(p["c"], float); o = np.array(pt, float) - c
    if p["shape"] != "cyl":             # a mesh counts as its bounding box
        cs, sn = np.cos(p.get("yaw", 0.0)), np.sin(p.get("yaw", 0.0))
        l = np.array([cs * o[0] - sn * o[2], o[1], sn * o[0] + cs * o[2]])
        return bool(np.all(np.abs(l) <= np.array(p["h"]) + margin))
    return bool(o[0] ** 2 + o[2] ** 2 <= (p["r"] + margin) ** 2 and abs(o[1]) <= p["hy"] + margin)


def trace(cam, ids=None, normals=False):
    """Depth and world point per pixel. With ids (one id per primitive), also returns a surface id per pixel:
    0..5 for the room's faces, otherwise 6 + the primitive's id. With normals, also the surface normal per pixel where
    a mesh is seen (facing the camera; zero elsewhere)."""
    eye, d = rays(cam)
    _, t = slab(eye, d, *ROOM)   # the camera is inside the room: distance to the far wall
    sid = None
    if ids is not None:
        P = eye + d * t[..., None]
        lo, hi = np.array(ROOM[0]), np.array(ROOM[1])
        sid = np.argmin(np.concatenate([np.abs(P - lo), np.abs(P - hi)], -1), -1)
    nrm = np.zeros(d.shape, np.float32) if normals else None
    for i, p in enumerate(PRIMS):
        tn, n = mesh_cast(eye, d, p) if normals and p["shape"] == "mesh" else (hit(eye, d, p), 0.0)
        closer = tn < t
        t = np.where(closer, tn, t)
        if ids is not None:
            sid = np.where(closer, 6 + ids[i], sid)
        if normals:
            nrm = np.where(closer[..., None], n, nrm)
    P = eye + d * t[..., None]
    return (t, P) + (() if ids is None else (sid,)) + ((nrm,) if normals else ())


def visible(eye, P, eps=1e-3):
    """Exact shadow test for points P (n, 3): True where no primitive lies between the eye and the point."""
    eye = np.array(eye, float)
    d = P - eye
    dist = np.linalg.norm(d, axis=-1)
    d = d / np.maximum(dist, 1e-9)[:, None]
    t = np.full(len(P), np.inf)
    for p in PRIMS:
        t = np.minimum(t, hit(eye, d, p))
    return t > dist - eps * (1 + dist)


def project(cam, P):
    eye, r, u, f = basis(cam)
    v = P - eye
    z = v @ f
    t = np.tan(np.radians(FOV) / 2)
    x = -(v @ r) / z / t
    y = (v @ u) / z / (t * H / W)
    return (x + 1) / 2 * W - 0.5, (1 - y) / 2 * H - 0.5, np.linalg.norm(v, axis=-1), z
