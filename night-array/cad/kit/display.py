"""Night Array kit -- display group: the two S60UD monitors (placed), the screen skin, the printed front frame,
the seam strip and the printed rear shroud + keel.

OWNER (next phase): DISPLAY engineer.  This is the architect's COARSE starting point: dimensionally right envelopes,
clearances and split planes; the details (bosses, inserts into the wing flanges, vents, finger opening, port
openings, paint allowances) are the display engineer's.  Interfaces used (do not change here): common.LAYOUT
['display'], purchased.S60UD / s60ud_zones(), structure.WING / web_w() (shroud must clear the wing flanges).
"""

from __future__ import annotations

from functools import lru_cache

import cadquery as cq
from cadquery import Vector

from .common import (COS_T, LAYOUT, SIN_T, TAN_T, Joint, PartDef, PrintSpec, box, chamfer, compound, cut, cyl_z,
                     edges_where, facet_point, fillet, fuse, on_plane, place_facet, poly_x, prism_z, seam_z, single,
                     split_solid)
from . import purchased as P
from . import structure as ST

D = LAYOUT["display"]
M = P.S60UD

DISPLAY = {
    "frame": {"lip": 1.7, "wrap": 2.2, "depth": 5.0, "cover_top": 5.0, "cover_side": 5.0, "cover_bottom": 15.0,
              "clear": 0.3, "corner_r": 6.0, "split_u": [205.0, 410.0], "split_y": 337.2},
    "seam": {"w": 4.0, "proud": 1.4, "split_y": 337.2},
    "shroud": {"wall": 3.0, "clear_band": 1.0, "inner_w": -69.0,      # clears the wing flanges (-66.4) by 2.6
               "bump_u": [52.0, 545.0], "bump_y": [218.0, 457.0], "chamfer": 22.0,
               "thin_back_w": -16.4, "front_w": -5.0,
               "split_u": [215.0, 395.0], "split_y": 337.2, "vent_pitch": 14.0, "vent": [4.0, 40.0]},
    "keel": {"x": 78.0, "z": [-166.0, -96.0], "y": [156.0, 428.0], "wall": 3.0, "split_y": 290.0},
}
F = DISPLAY["frame"]
SH = DISPLAY["shroud"]


def _housing_box(grow=0.0):
    u0 = P.monitor_u0()
    y0 = P.monitor_y0()
    return box(u0 - grow, u0 + M["face_w"] + grow, y0 - grow, y0 + M["face_h"] + grow, -M["edge_band"] - grow, grow)


# ----------------------------------------------------------------------------- monitors + screen

@lru_cache(None)
def monitor_housings():
    return compound([place_facet(P.s60ud_local(-1), -1), place_facet(P.s60ud_local(1), 1)])


@lru_cache(None)
def display_screen():
    loc = P.screen_local()
    return compound([place_facet(loc, -1), place_facet(loc, 1)])


# ----------------------------------------------------------------------------- front frame

def _frame_local():
    u0 = P.monitor_u0()
    y0 = P.monitor_y0()
    u1, y1 = u0 + M["face_w"], y0 + M["face_h"]
    c, wr = F["clear"], F["wrap"]
    ui = 3.2                                           # frame stops short of the seam strip (x >= 2.3 at w = 4.3)
    outer = box(ui, u1 + c + wr, y0 - c - wr, y1 + c + wr, -F["depth"], c + F["lip"])
    outer = fillet(outer, F["corner_r"], edges_where(outer, lambda cc, bb, e: (bb.zmax - bb.zmin) > 1 and cc.x > u0 + 1),
                   "frame corners")
    # bottom rail steps over the 2 mm chin lip
    lip = M["chin_lip"]
    rail = box(ui, u1 + c + wr, y0 - c - wr, y0 + F["cover_bottom"], -F["depth"], lip["proud"] + c + F["lip"])
    s = fuse(outer, rail)
    hous = P.s60ud_local(1)
    hous_g = fuse(_housing_box(c), box(P.monitor_uc() - lip["half_w"] - c, P.monitor_uc() + lip["half_w"] + c,
                                       y0 + lip["y"][0] - c, y0 + lip["y"][1] + c, -1, lip["proud"] + c))
    s = cut(s, hous_g)
    window = box(u0 - 10, u1 - F["cover_side"], y0 + F["cover_bottom"], y1 - F["cover_top"], -50, 50)
    nb = M["nub"]
    notch = box(P.monitor_uc() - nb["w"] / 2 - 1.0, P.monitor_uc() + nb["w"] / 2 + 1.0, y0 - 20, y0 + 1, -20, 10)
    return cut(s, window, notch)


@lru_cache(None)
def display_frame():
    loc = _frame_local()
    pieces = []
    joints = [Joint("x", u, []) for u in F["split_u"]] + [Joint("y", F["split_y"], [])]
    for side in (-1, 1):
        for nm, p in split_solid(loc, joints, "frame", dowels=False):
            pieces.append(place_facet(p, side))
    return compound(pieces)


# ----------------------------------------------------------------------------- seam strip

@lru_cache(None)
def display_seam():
    sw = DISPLAY["seam"]["w"] / 2
    zs = seam_z()
    zb = zs + sw * TAN_T + 0.05
    zf = zs + DISPLAY["seam"]["proud"] + sw * TAN_T
    y0, y1 = P.monitor_y0() + 0.5, P.monitor_y0() + M["face_h"] - 0.5
    wp = cq.Workplane("XZ", origin=(0, y1, 0))
    s = wp.polyline([(-sw, zb), (0, zs + 0.05), (sw, zb), (sw, zf), (-sw, zf)]).close().extrude(y1 - y0).val()
    # over the chins the strip steps forward onto the 2 mm chin lips
    lip = M["chin_lip"]
    yl = P.monitor_y0() + lip["y"][1] + 0.3
    s = cut(s, box(-10, 10, y0 - 1, yl, -500, 500))
    wl = lip["proud"] + 0.05
    zlx = lambda x: zs + ((x + wl * SIN_T) / COS_T) * SIN_T + wl * COS_T      # chin-lip front plane at |x|
    zlf = zlx(sw) + DISPLAY["seam"]["proud"]
    low = (cq.Workplane("XZ", origin=(0, yl, 0)).polyline([(-sw, zlx(sw)), (0, zlx(0)), (sw, zlx(sw)), (sw, zlf),
                                                          (-sw, zlf)]).close().extrude(yl - y0).val())
    s = compound([s, low])
    s = fillet(s, 0.5, edges_where(s, lambda c, bb, e: abs(c.z - zf) < 0.01 and (bb.ymax - bb.ymin) > 100), "seam")
    lo = s.cut(box(-10, 10, DISPLAY["seam"]["split_y"], 2000, -500, 500))
    hi = s.cut(box(-10, 10, -10, DISPLAY["seam"]["split_y"], -500, 500))
    return compound(lo.Solids() + hi.Solids())


# ----------------------------------------------------------------------------- rear shroud

def _shroud_outer_local():
    u0 = P.monitor_u0()
    y0 = P.monitor_y0()
    u1, y1 = u0 + M["face_w"], y0 + M["face_h"]
    c, wr = F["clear"], F["wrap"]
    wall = SH["wall"]
    # thin zone: from the frame's back edge (w = -5) to behind the edge band, the frame's outline
    thin = box(-40.0, u1 + c + wr, y0 - c - wr, y1 + c + wr, SH["thin_back_w"] - wall, SH["front_w"])
    thin = fillet(thin, F["corner_r"], edges_where(thin, lambda cc, bb, e: (bb.zmax - bb.zmin) > 1 and cc.x > 0),
                  "shroud corners")
    bu0, bu1 = SH["bump_u"]
    by0, by1 = SH["bump_y"]
    bump = box(bu0 - wall - 60, bu1 + wall, by0 - wall, by1 + wall, SH["inner_w"] - wall, SH["thin_back_w"] - 1)
    ch = SH["chamfer"]
    bump = chamfer(bump, ch, edges_where(bump, lambda cc, bb, e: abs(bb.zmin - (SH["inner_w"] - wall)) < 0.01
                                         and abs(bb.zmax - (SH["inner_w"] - wall)) < 0.01 and cc.x > bu0), "bump chamfer")
    return fuse(thin, bump)


def _shroud_cavity_local():
    u0 = P.monitor_u0()
    y0 = P.monitor_y0()
    c = SH["clear_band"]
    hous = box(-50.0, u0 + M["face_w"] + c, y0 - c, y0 + M["face_h"] + c, SH["thin_back_w"], 10.0)
    bu0, bu1 = SH["bump_u"]
    by0, by1 = SH["bump_y"]
    bump = box(bu0 - 70, bu1, by0, by1, SH["inner_w"], SH["thin_back_w"] + 0.5)
    ch = SH["chamfer"] - 1.8
    bump = chamfer(bump, ch, edges_where(bump, lambda cc, bb, e: abs(bb.zmin - SH["inner_w"]) < 0.01
                                         and abs(bb.zmax - SH["inner_w"]) < 0.01 and cc.x > bu0), "bump cavity chamfer")
    return fuse(hous, bump)


def _shroud_openings_local(side):
    """Port / AC openings in the bottom (plugs drop out of the shroud), joystick finger hole, top exhaust slots."""
    z = P.s60ud_zones(side)
    cuts = []
    for k in ("ports", "ac"):
        u0, u1, y0, y1, w0, w1 = z[k]
        cuts.append(box(u0, u1, 100.0, y1, w0 - 5, w1))
    nb = M["nub"]
    cuts.append(box(P.monitor_uc() - nb["w"] / 2 - 1.5, P.monitor_uc() + nb["w"] / 2 + 1.5, 100.0, P.monitor_y0() + 1.5,
                    -12.0, 5.0))
    u0, u1, y0, y1, w0, w1 = z["joystick"]
    cuts.append(box(u0, u1, y0, y1, -60, w1))
    # exhaust slots on the bump's top face, intake slots on its bottom face (between the port openings)
    by0, by1 = SH["bump_y"]
    vw, vl = SH["vent"]
    u = SH["bump_u"][0] + 40
    while u < SH["bump_u"][1] - 40:
        cuts.append(box(u - vw / 2, u + vw / 2, by1 - 2, by1 + SH["wall"] + 2, SH["inner_w"] + 6, SH["inner_w"] + 6 + vl))
        cuts.append(box(u - vw / 2, u + vw / 2, by0 - SH["wall"] - 2, by0 + 2, SH["inner_w"] + 6, SH["inner_w"] + 6 + vl))
        u += SH["vent_pitch"]
    return cuts


def _keel_outer():
    k = DISPLAY["keel"]
    o = box(-k["x"], k["x"], k["y"][0], k["y"][1], k["z"][0], k["z"][1])
    return chamfer(o, 16.0, edges_where(o, lambda c, bb, e: abs(bb.zmin - k["z"][0]) < 0.01
                                        and abs(bb.zmax - k["z"][0]) < 0.01 and (bb.ymax - bb.ymin) > 100), "keel rear")


def _keel_cavity():
    k = DISPLAY["keel"]
    w = k["wall"]
    i = box(-k["x"] + w, k["x"] - w, k["y"][0] - 1, k["y"][1] - w, k["z"][0] + w, k["z"][1] + 1)
    return chamfer(i, 14.0, edges_where(i, lambda c, bb, e: abs(bb.zmin - (k["z"][0] + w)) < 0.01
                                        and abs(bb.zmax - (k["z"][0] + w)) < 0.01 and (bb.ymax - bb.ymin) > 100),
                   "keel cavity rear")


def _unplace_right(shape):
    """World (x >= 0 half) -> right facet frame (inverse of place_facet without mirroring)."""
    return shape.translate(Vector(0, 0, -seam_z())).rotate(Vector(0, 0, 0), Vector(0, 1, 0), 10.0)


@lru_cache(None)
def _shroud_world():
    """One continuous rear shroud: both facet shells + the centre keel over the posts and the centre bracket."""
    outer = fuse(place_facet(_shroud_outer_local(), 1, trim=True), place_facet(_shroud_outer_local(), -1, trim=True),
                 _keel_outer())
    cav = fuse(place_facet(_shroud_cavity_local(), 1, trim=True), place_facet(_shroud_cavity_local(), -1, trim=True),
               _keel_cavity())
    s = cut(outer, cav)
    ops = []
    for side in (-1, 1):
        ops += [place_facet(c, side) for c in _shroud_openings_local(side)]
    return cut(s, *ops)


@lru_cache(None)
def display_back():
    """Rear shroud + keel, split per side in the facet frame (u 215 / 395, y 337): 12 tiles."""
    s = _shroud_world()
    joints = [Joint("x", u, []) for u in SH["split_u"]] + [Joint("y", SH["split_y"], [])]
    right = single(s.intersect(box(0, 2000, -10, 2000, -2000, 2000)))
    loc = _unplace_right(right)
    pieces = []
    for nm, p in split_solid(loc, joints, "shroud", dowels=False):
        pr = place_facet(p, 1)
        pieces += [pr, pr.mirror("YZ")]
    return compound(pieces)


# ----------------------------------------------------------------------------- registry

PARTS = [
    PartDef("display_screen", "display", "Active areas (2 x 27 in, screen skin)", "screen", "purchased", display_screen,
            bom="monitor-s60ud", mass_g=0.0, mass_note="visual skin; the monitor mass is on monitor_housings",
            owner="display"),
    PartDef("monitor_housings", "display", "Samsung S60UD monitors (2)", "plastic_black", "purchased",
            monitor_housings, bom="monitor-s60ud", mass_g=2 * M["mass_kg"] * 1000, owner="display",
            mass_note="2 x 3.6 kg (Samsung spec, no stand)"),
    PartDef("display_frame", "display", "Front frame (12 pieces)", "titanium", "printed", display_frame,
            print=PrintSpec("petg_titanium", down="+z", supports="none", infill=0.25,
                            note="front lip face down; painted titanium"), owner="display",
            split="6 pieces per side (u 205 / 410, y 337)"),
    PartDef("display_seam", "display", "Seam strip (3 pieces)", "titanium", "printed", display_seam,
            print=PrintSpec("petg_titanium", down="-z", infill=1.0, note="VHB to the bezels"), owner="display",
            split="2 pieces (y 337) + the chin step piece"),
    PartDef("display_back", "display", "Rear shroud + keel (12 tiles)", "graphite", "printed", display_back,
            print=PrintSpec("petg_cf_graphite", down="+z", supports="tree, bump chamfers", infill=0.15),
            owner="display", split="per side: u 215 / 395 x y 337"),
]
