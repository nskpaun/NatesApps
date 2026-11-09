"""Cross-section ray diagram (2D, x = 0 plane): geometry plus a fan of band rays."""
from __future__ import annotations

import math

import numpy as np

from .scene import MATERIALS, MAT_IDS, Scene, SCREEN_Z
from .tracer import intersect, ESCAPE, CAP, _KIND

COLORS = {
    "band": "#ff9a3c", "screen": "#8aa0c8", "mirror": "#7fd3ff", "black_glass": "#333",
    "graphite": "#555", "black_matte": "#222", "desk": "#8b7355",
}


def ray_fan(scene: Scene, n_rows=5, angles=np.linspace(-70, 70, 29), max_bounce=4):
    """Deterministic 2D rays: specular at the mirror, specular (mirror-like) at the ribbon
    surface so the diagram shows the designed glint direction, absorbed elsewhere."""
    paths = []
    ys = np.linspace(scene.band_y0 + 0.5, scene.band_y1 - 0.5, n_rows)
    rib = MAT_IDS[scene.design.ramp_finish]
    n2 = scene.normals
    for y in ys:
        for a in angles:
            r = math.radians(a)
            o = np.array([[0.0, y, SCREEN_Z + 1e-3]])
            d = np.array([[0.0, math.sin(r), math.cos(r)]])
            pts = [(o[0, 2], o[0, 1])]
            kinds = []
            for _ in range(max_bounce):
                t, seg, front = intersect(scene, o, d)
                if seg[0] == ESCAPE:
                    p = o[0] + 400 * d[0]
                    pts.append((p[2], p[1])); kinds.append("escape")
                    break
                p = o[0] + t[0] * d[0]
                pts.append((p[2], p[1]))
                if seg[0] == CAP:
                    kinds.append("absorbed"); break
                mat = scene.mat_front[seg[0]] if front[0] else scene.mat_back[seg[0]]
                n = np.array([0, n2[seg[0], 1], n2[seg[0], 0]])
                if not front[0]:
                    n = -n
                if _KIND[mat] == 1 or mat == rib:
                    kinds.append("mirror" if _KIND[mat] == 1 else "ribbon")
                    d = d - 2 * np.sum(d * n) * n
                    o = (p + n * 1e-3)[None]
                    continue
                kinds.append("absorbed")
                break
            paths.append((a, y, pts, kinds))
    return paths


def draw(ax, scene: Scene, title=None, fan=True, eye=True):
    for i, lab in enumerate(scene.labels):
        if lab == "desk":
            ax.plot([scene.p0[i, 0], 700], [0, 0], color=COLORS["desk"], lw=2)
            continue
        names = {list(MATERIALS)[scene.mat_front[i]], list(MATERIALS)[scene.mat_back[i]]}
        if "mirror" in names:
            col, lw = COLORS["mirror"], 3
        elif "band" in names:
            col, lw = COLORS["band"], 4
        elif scene.design.ramp_finish in names:
            col, lw = "#c9b8a6", 3
        else:
            col = COLORS.get(sorted(names)[0], "#666"); lw = 2
        ax.plot([scene.p0[i, 0], scene.p1[i, 0]], [scene.p0[i, 1], scene.p1[i, 1]], color=col, lw=lw,
                solid_capstyle="round")
    if fan:
        for a, y, pts, kinds in ray_fan(scene):
            pts = np.array(pts)
            good = "ribbon" in kinds
            col = "#ff9a3c" if good else ("#d04a7a" if kinds[-1] == "escape" else "#999")
            ax.plot(pts[:, 0], pts[:, 1], color=col, lw=0.6, alpha=0.8 if good else 0.35)
    if eye:
        ex, ey, ez = scene.design.eye
        ax.annotate("to eye", xy=(60, 40 + (ey - 40) * 120 / (ez - 60)), xytext=(60, 40), fontsize=7,
                    color="#2a7", arrowprops=dict(arrowstyle="->", color="#2a7"))
    ax.set_aspect("equal")
    ax.set_xlim(-170, 160); ax.set_ylim(-5, 260)
    ax.set_xlabel("z (mm, + toward you)"); ax.set_ylabel("y (mm above desk)")
    if title:
        ax.set_title(title, fontsize=10)
