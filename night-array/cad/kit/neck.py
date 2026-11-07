"""Night Array kit -- stand group: the printed trapezoid neck shroud around the 2040 posts and the cable chase,
with the amber light bar (QSG-0505 channel) and the inlaid NIGHT ARRAY lettering.

OWNER (next phase): DISPLAY engineer.  COARSE starting point: right envelope, wall, split, light groove, badge.
Interfaces: structure posts (x +-45, z -158..-118: leave >= 2 mm), the plinth top (y 50), the keel above (y 156).
"""

from __future__ import annotations

from functools import lru_cache

import cadquery as cq
from cadquery import Vector

from .common import (LAYOUT, PartDef, PrintSpec, box, compound, cut, edges_where, fillet, frame_plane, fuse,
                     halfspace, on_plane, single, to_frame)

NECK = {
    "y": [50.0, 156.0],
    "bottom_w": 320.0, "top_w": 180.0,
    "z_back": -163.0,                     # vertical back face, 2 mm in from the base rear
    "z_front": [-86.0, -98.0],            # front face at the bottom / top (leans back 6.5 deg)
    "wall": 3.0, "edge_r": 8.0,
    "light": {"w": 150.0, "groove": 5.3, "y": [126.0, 131.3], "depth": 5.5},   # QSG-0505 in a 5.3 x 5.3 groove
    "badge": {"text": "NIGHT ARRAY", "size": 8.5, "tracking": 0.42, "y": 104.0, "depth": 0.6, "font": "Inter",
              "kind": "regular"},
    "split_x": 0.0,
}


def _front_z(y):
    (zb, zt), (y0, y1) = NECK["z_front"], NECK["y"]
    return zb + (zt - zb) * (y - y0) / (y1 - y0)


def _face_plane(y):
    y0, y1 = NECK["y"]
    dz = NECK["z_front"][1] - NECK["z_front"][0]
    import math
    L = math.hypot(y1 - y0, dz)
    return frame_plane((0.0, y, _front_z(y)), (1, 0, 0), (0.0, -dz / L, (y1 - y0) / L))


def _body(inset=0.0, ext=0.0):
    y0, y1 = NECK["y"]
    hb, ht = NECK["bottom_w"] / 2, NECK["top_w"] / 2
    zb = NECK["z_back"]
    zf0, zf1 = NECK["z_front"]
    s = box(-hb - 1, hb + 1, y0 - ext, y1 + ext, zb - 1, zf0 + 1)
    dy = y1 - y0
    cuts = [
        halfspace((0, y0, zf0 - inset * 1.0), (0, -(zf1 - zf0), dy)),      # front face (leaning back)
        halfspace((0, y0, zb + inset), (0, 0, -1)),                        # back face
        halfspace((hb - inset, y0, 0), (dy, hb - ht, 0)),                  # right side
        halfspace((-hb + inset, y0, 0), (-dy, hb - ht, 0)),                # left side
    ]
    return cut(s, *cuts)


@lru_cache(None)
def _outer():
    s = _body()
    s = fillet(s, NECK["edge_r"], edges_where(s, lambda c, bb, e: (bb.ymax - bb.ymin) > 50), "neck edges")
    return fillet(s, 1.5, edges_where(s, on_plane("y", NECK["y"][1])), "neck top edge")


def _light_box(grow=0.0):
    L = NECK["light"]
    yc = (L["y"][0] + L["y"][1]) / 2
    g = L["groove"]
    b = box(-L["w"] / 2 - grow, L["w"] / 2 + grow, -g / 2 - grow, g / 2 + grow, -L["depth"], 0.0)
    return to_frame(b, _face_plane(yc))


@lru_cache(None)
def _text():
    bd = NECK["badge"]
    size = bd["size"]
    glyphs, x = [], 0.0
    for ch in bd["text"]:
        if ch == " ":
            x += 0.62 * size
            continue
        g = cq.Workplane("XY").text(ch, size, bd["depth"], halign="left", valign="bottom", font=bd["font"],
                                    kind=bd["kind"]).val()
        bb = g.BoundingBox()
        glyphs.append(g.translate(Vector(x - bb.xmin, 0, 0)))
        x += bb.xlen + bd["tracking"] * size
    allg = compound(glyphs)
    bb = allg.BoundingBox()
    allg = allg.translate(Vector(-(bb.xmin + bb.xmax) / 2, -(bb.ymin + bb.ymax) / 2, -bd["depth"]))
    return to_frame(allg, _face_plane(bd["y"]))


@lru_cache(None)
def neck():
    s = _outer()
    w = NECK["wall"]
    inner = _body(w, 2.0)
    inner = fillet(inner, NECK["edge_r"] - w, edges_where(inner, lambda c, bb, e: (bb.ymax - bb.ymin) > 50), "neck inner")
    s = cut(s, inner, _light_box(), _text())
    lo = single(s.intersect(box(-500, NECK["split_x"], -10, 500, -500, 500)))
    hi = single(s.intersect(box(NECK["split_x"], 500, -10, 500, -500, 500)))
    return compound([lo, hi])


@lru_cache(None)
def neck_light():
    """The visible light: QSG-0505 opal diffuser face (the channel and the 7-segment COB strip sit behind it)."""
    return _light_box(-0.15)


@lru_cache(None)
def neck_badge():
    return _text()


PARTS = [
    PartDef("neck", "stand", "Neck shroud (2 halves)", "graphite", "printed", neck,
            print=PrintSpec("petg_cf_graphite", down="-z", supports="none", infill=0.15,
                            note="back face down; front face (badge, light groove) up"), owner="display",
            split="2 halves at x = 0 (through the word space of the badge)"),
    PartDef("neck_light", "stand", "Neck light bar (QSG-0505 + 1800 K COB)", "amber_led", "purchased", neck_light,
            bom="led-channel-qsg0505", owner="electrical"),
    PartDef("neck_badge", "stand", "NIGHT ARRAY inlay", "titanium", "printed", neck_badge,
            print=PrintSpec("petg_titanium", down="-z", infill=1.0, note="print the letters flat, glue in"),
            owner="display"),
]
