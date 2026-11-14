"""Blockout geometry: a box room holding boxes (optionally turned about the vertical axis) and upright cylinders.
Renders depth from any camera by ray casting, and projects points into cameras. Used by the world pipeline in ../thread.

Coordinates: x right, y up, z towards the back wall; the room spans (0,0,0) to (width, height, depth).
A primitive is {"shape": "box", "c": centre, "h": half sizes, "yaw": radians} or {"shape": "cyl", "c": centre, "r": radius, "hy": half height}.
"""
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


def hit(eye, d, p):
    """Distance along each ray to the primitive's surface (inf where missed or where the ray starts inside it)."""
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
    if p["shape"] == "box":
        cs, sn = np.cos(p.get("yaw", 0.0)), np.sin(p.get("yaw", 0.0))
        l = np.array([cs * o[0] - sn * o[2], o[1], sn * o[0] + cs * o[2]])
        return bool(np.all(np.abs(l) <= np.array(p["h"]) + margin))
    return bool(o[0] ** 2 + o[2] ** 2 <= (p["r"] + margin) ** 2 and abs(o[1]) <= p["hy"] + margin)


def trace(cam, ids=None):
    """Depth and world point per pixel. With ids (one id per primitive), also returns a surface id per pixel:
    0..5 for the room's faces, otherwise 6 + the primitive's id."""
    eye, d = rays(cam)
    _, t = slab(eye, d, *ROOM)   # the camera is inside the room: distance to the far wall
    sid = None
    if ids is not None:
        P = eye + d * t[..., None]
        lo, hi = np.array(ROOM[0]), np.array(ROOM[1])
        sid = np.argmin(np.concatenate([np.abs(P - lo), np.abs(P - hi)], -1), -1)
    for i, p in enumerate(PRIMS):
        tn = hit(eye, d, p)
        closer = tn < t
        t = np.where(closer, tn, t)
        if ids is not None:
            sid = np.where(closer, 6 + ids[i], sid)
    P = eye + d * t[..., None]
    return (t, P) if ids is None else (t, P, sid)


def project(cam, P):
    eye, r, u, f = basis(cam)
    v = P - eye
    z = v @ f
    t = np.tan(np.radians(FOV) / 2)
    x = -(v @ r) / z / t
    y = (v @ u) / z / (t * H / W)
    return (x + 1) / 2 * W - 0.5, (1 - y) / 2 * H - 0.5, np.linalg.norm(v, axis=-1), z
