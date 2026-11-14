"""Reading-room blockout as boxes: render depth maps and reproject images between cameras.

Usage:
  blockout.py depth                      -> out/depth_{1,2,3}.png (+ .npy world points)
  blockout.py warp SRC_IMG SRC_CAM DST_CAM OUT_PREFIX [BASE_IMG BASE_MASK]
"""
import sys
import numpy as np
from PIL import Image

W, H, FOV = 1024, 768, 65.0
ROOM = ((0, 0, 0), (4.0, 2.6, 4.0))
BOXES = [
    # sofa on the back wall
    ((1.0, 0.0, 3.1), (3.0, 0.45, 4.0)), ((1.0, 0.45, 3.7), (3.0, 0.95, 4.0)),
    ((1.0, 0.0, 3.1), (1.2, 0.65, 4.0)), ((2.8, 0.0, 3.1), (3.0, 0.65, 4.0)),
    # armchair by the window (left wall)
    ((0.25, 0.0, 1.6), (1.05, 0.45, 2.4)), ((0.25, 0.45, 1.6), (0.45, 0.95, 2.4)),
    ((0.25, 0.0, 1.6), (1.05, 0.62, 1.72)), ((0.25, 0.0, 2.28), (1.05, 0.62, 2.4)),
    # coffee table in the middle
    ((1.5, 0.36, 1.9), (2.5, 0.42, 2.5)),
    ((1.52, 0, 1.92), (1.58, 0.36, 1.98)), ((2.42, 0, 1.92), (2.48, 0.36, 1.98)),
    ((1.52, 0, 2.42), (1.58, 0.36, 2.48)), ((2.42, 0, 2.42), (2.48, 0.36, 2.48)),
    # window frame on the left wall
    ((0.0, 0.9, 1.2), (0.06, 2.1, 2.8)),
    # floor lamp
    ((3.42, 0, 3.32), (3.47, 1.5, 3.37)), ((3.27, 1.5, 3.17), (3.62, 1.82, 3.52)),
]
CAMS = {
    "1": ((2.0, 1.5, 0.25), (2.0, 0.7, 3.2)),
    "2": ((3.4, 1.5, 0.6), (1.6, 0.7, 3.0)),
    "3": ((0.7, 1.5, 0.5), (2.5, 0.7, 3.1)),
}


def basis(cam):
    eye, tgt = np.array(cam[0], float), np.array(cam[1], float)
    f = tgt - eye
    f /= np.linalg.norm(f)
    r = np.cross(f, [0, 1, 0])  # z-forward, x-right with y up (left-handed view)
    r /= np.linalg.norm(r)
    u = np.cross(r, f)
    return eye, r, u, f


def rays(cam):
    eye, r, u, f = basis(cam)
    t = np.tan(np.radians(FOV) / 2)
    xs = (np.arange(W) + 0.5) / W * 2 - 1
    ys = 1 - (np.arange(H) + 0.5) / H * 2
    X, Y = np.meshgrid(xs * t, ys * t * H / W)
    # mirror x so the left wall (x=0) appears on screen-left when looking down +z
    d = -X[..., None] * r + Y[..., None] * u + f
    return eye, d / np.linalg.norm(d, axis=-1, keepdims=True)


def slab(eye, d, lo, hi):
    with np.errstate(divide="ignore", invalid="ignore"):
        t1 = (np.array(lo) - eye) / d
        t2 = (np.array(hi) - eye) / d
    return np.minimum(t1, t2).max(-1), np.maximum(t1, t2).min(-1)


def trace(cam):
    eye, d = rays(cam)
    _, t = slab(eye, d, *ROOM)  # camera is inside the room: exit distance
    for lo, hi in BOXES:
        tn, tf = slab(eye, d, lo, hi)
        hit = (tn < tf) & (tn > 0)
        t = np.where(hit & (tn < t), tn, t)
    return t, eye + d * t[..., None]


def project(cam, P):
    eye, r, u, f = basis(cam)
    v = P - eye
    z = v @ f
    t = np.tan(np.radians(FOV) / 2)
    x = -(v @ r) / z / t
    y = (v @ u) / z / (t * H / W)
    px = (x + 1) / 2 * W - 0.5
    py = (1 - y) / 2 * H - 0.5
    return px, py, np.linalg.norm(v, axis=-1), z


def depth_cmd():
    for k, cam in CAMS.items():
        t, P = trace(cam)
        inv = 1.0 / t
        img = (inv - inv.min()) / (inv.max() - inv.min())  # near = white
        Image.fromarray((img * 255).astype(np.uint8)).convert("RGB").save(f"out/depth_{k}.png")
        np.save(f"out/points_{k}.npy", P.astype(np.float32))
        print("depth", k, "range m", round(float(t.min()), 2), round(float(t.max()), 2))


def warp_cmd(src_img, src_k, dst_k, out, base_img=None, base_mask=None):
    """Colour every dst pixel from src image where its surface point is visible from src."""
    src = np.asarray(Image.open(src_img).convert("RGB").resize((W, H)), float)
    P = np.load(f"out/points_{dst_k}.npy").astype(float)
    t_src, _ = trace(CAMS[src_k])
    px, py, dist, z = project(CAMS[src_k], P)
    xi, yi = np.round(px).astype(int), np.round(py).astype(int)
    ok = (z > 0.05) & (xi >= 0) & (xi < W) & (yi >= 0) & (yi < H)
    xi, yi = np.clip(xi, 0, W - 1), np.clip(yi, 0, H - 1)
    ok &= np.abs(t_src[yi, xi] - dist) < 0.04  # occlusion test
    x0, y0 = np.clip(np.floor(px).astype(int), 0, W - 2), np.clip(np.floor(py).astype(int), 0, H - 2)
    fx, fy = np.clip(px - x0, 0, 1)[..., None], np.clip(py - y0, 0, 1)[..., None]
    col = (src[y0, x0] * (1 - fx) * (1 - fy) + src[y0, x0 + 1] * fx * (1 - fy)
           + src[y0 + 1, x0] * (1 - fx) * fy + src[y0 + 1, x0 + 1] * fx * fy)
    if base_img:  # keep what an earlier view already painted
        base = np.asarray(Image.open(base_img).convert("RGB"), float)
        bm = np.asarray(Image.open(base_mask).convert("L")) > 127
        col = np.where(bm[..., None], base, col)
        ok = ok | bm
    out_img = np.where(ok[..., None], col, np.array([255.0, 0, 255.0]))
    Image.fromarray(out_img.astype(np.uint8)).save(f"{out}_warp.png")
    Image.fromarray((ok * 255).astype(np.uint8)).save(f"{out}_known.png")
    print(f"{out}: {ok.mean() * 100:.1f}% of pixels covered")


if __name__ == "__main__":
    if sys.argv[1] == "depth":
        depth_cmd()
    else:
        warp_cmd(*sys.argv[2:])
