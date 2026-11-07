"""Night Array kit -- structure: the metal load path.  FROZEN INTERFACE (owner: CAD architect).

    monitors -> 4x M4 x 22 + 10 mm spacers -> wing channels (3/16 in A36, 25 mm return flanges) -> 4x M5 per side
    -> centre bracket (3/16 in, 10-degree ears) -> 6x M5 + hammer nuts -> 2x 2040 posts (strong axis fore-aft)
    -> 4x M6 ISO 10642 -> spine plate (1/4 in A36, U-shaped) -> 3M SJ5023 feet -> desk.
    Front: front bar (1/4 in) laps onto the spine plate's legs (2x M5 csk per side) and carries the front 2020 rail.
    Middle 2020 rail hangs from the printed tiles at the row joint (ties the two rows; carries no monitor load).

Every printed part hangs from this frame; only steel / aluminium touches the feet.  SendCutSend constraints used:
1/4 in (HRP-250, 6.35 +-0.38) and 3/16 in (HRP-188, 4.78 +-0.15) A36/1008, inside bend R 3.18, k 0.32,
min flange 15.7, hole centre to bend line >= 12.4 (tapped / hardware), max part 1117 x 762, cut +-0.127.
"""

from __future__ import annotations

import math
from functools import lru_cache

import cadquery as cq
from cadquery import Vector

from .common import (COS_T, LAYOUT, SIN_T, TAN_T, PartDef, box, compound, cut, cyl_x, cyl_y, cyl_z, edges_where,
                     facet_point, fillet, fuse, place_facet, poly_y, prism_y, seam_z, single, stadium_y)
from .purchased import S60UD, bumpon_local, monitor_uc

S = LAYOUT["structure"]
T_PLATE = S["plate_t"]
T_BRK = S["bracket_t"]
FOOT_H = S["foot_h"]
Y_PLATE = (FOOT_H, FOOT_H + T_PLATE)                  # 7.6 .. 13.95

SCS = {"bend_r": 3.18, "k": 0.32, "min_flange": 15.7, "hole_to_bend": 12.4, "max_part": (1117.0, 762.0),
       "powder_max": (787.0, 940.0)}

# ---------------------------------------------------------------- spine plate (U)
SPINE = {
    "x": [-415.0, 415.0],
    "rear_z": [-161.0, -118.0],
    "leg_x": 80.0,                     # legs x +-[335, 415]
    "leg_z1": 155.0,
    "corner_r": 5.0, "inner_r": 12.0,
}
# ---------------------------------------------------------------- front bar
FRONT_BAR = {"x": [-550.0, 550.0], "z": [133.0, 159.0]}
# ---------------------------------------------------------------- posts / rails (ZYLtech)
POST = {"w": 20.0, "d": 40.0, "len": S["post_len"], "centre_hole": 5.2, "mass_kg_m": 0.88}
RAIL = {"w": 20.0, "len": 1200.0, "centre_hole": 5.0, "mass_kg_m": 0.50}
# ---------------------------------------------------------------- wing bracket
WING = {
    "u": [56.0, 375.0],                # channel length along the facet
    "h": 160.0,                        # outer height (y), centred on the VESA centre
    "flange": 25.0,                    # outer flange length (w), from the web's front face
    "vesa_slot": [4.6, 10.0],          # vertical slots for seam / height alignment
}
CENTRE = {"half_w": 60.0,              # bend lines at x = +-60 (holes at +-45: 15 mm >= 12.4)
          "h": 120.0, "ear_u1": 128.0,  # ears end at u = 128 along the facet
          "post_bolts_y": [-40.0, 0.0, 40.0], "ear_bolts_u": [72.0, 112.0], "ear_bolts_y": [-40.0, 40.0]}

FEET_XZ = [(-395.0, -150.0), (-150.0, -150.0), (150.0, -150.0), (395.0, -150.0), (-375.0, 144.0), (375.0, 144.0)]


def vesa_y():
    return LAYOUT["display"]["vesa_y"]


def web_w():
    """Facet w of the wing web's FRONT face: VESA pocket floor + spacer."""
    return -(S60UD["vesa_floor"] + LAYOUT["display"]["vesa_spacer"])


def post_front_z():
    return S["posts_z"][1]


# =============================================================================
# spine plate
# =============================================================================

def spine_outline_pts():
    """Closed plan polygon (x, z) of the U plate (sharp; corners rounded after extrusion)."""
    x0, x1 = SPINE["x"]
    z0, z1r = SPINE["rear_z"]
    lx = SPINE["leg_x"]
    zl = SPINE["leg_z1"]
    return [(x0, z0), (x1, z0), (x1, zl), (x1 - lx, zl), (x1 - lx, z1r), (x0 + lx, z1r), (x0 + lx, zl), (x0, zl)]


def spine_holes():
    """[(kind, x, z, d)] -- every hole in the spine plate (also used for the DXF)."""
    out = []
    for px in S["posts_x"]:
        for dz in (-10.0, 10.0):
            out.append(("M6 csk ISO 10642 (post)", px, sum(S["posts_z"]) / 2 + dz, 6.6))
    for sx in (-1, 1):
        for x in (350.0, 400.0):
            out.append(("M5 csk ISO 10642 (front bar lap)", sx * x, 144.0, 5.5))
    # tile anchors (M4 from below into inserts in the printed tiles' bosses)
    for x in (-385.0, -300.0, -215.0, -120.0, 120.0, 215.0, 300.0, 385.0):
        out.append(("M4 tile anchor", x, -128.0, 4.5))
    for sx in (-1, 1):
        for z in (-70.0, 10.0, 90.0):
            out.append(("M4 tile anchor", sx * 375.0, z, 4.5))
    return out


@lru_cache(None)
def spine_plate():
    y0, y1 = Y_PLATE
    s = poly_y(spine_outline_pts(), y0, y1)
    vert = edges_where(s, lambda c, bb, e: (bb.ymax - bb.ymin) > 1)
    x0, x1 = SPINE["x"]
    lx = SPINE["leg_x"]
    inner = [e for e in vert if abs(abs(e.Center().x) - (x1 - lx)) < 0.1 and e.Center().z < 0]
    outer = [e for e in vert if e not in inner]
    s = fillet(s, SPINE["inner_r"], inner, "spine inner corners")
    s = fillet(s, SPINE["corner_r"], [e for e in edges_where(s, lambda c, bb, e: (bb.ymax - bb.ymin) > 1)
                                      if any(abs(e.Center().x - o.Center().x) < 0.1 and abs(e.Center().z - o.Center().z) < 0.1
                                             for o in outer)], "spine outer corners")
    holes = []
    for kind, x, z, d in spine_holes():
        holes.append(cyl_y(x, z, d / 2, y0 - 1, y1 + 1))
        if "csk" in kind:   # countersink from below, 90 deg
            dh = 12.0 if "M6" in kind else 10.0
            holes.append(cq.Solid.makeCone(dh / 2, d / 2, (dh - d) / 2, Vector(x, y0 - 0.001, z), Vector(0, 1, 0)))
    return cut(s, *holes)


# =============================================================================
# front bar
# =============================================================================

def front_bar_holes():
    out = []
    for sx in (-1, 1):
        for x in (350.0, 400.0):
            out.append(("M5 tapped (lap screw from below)", sx * x, 144.0, 4.2))
    for x in (-500.0, -250.0, -100.0, 100.0, 250.0, 500.0):
        out.append(("M5 clear (front rail, hammer nut)", x, sum(LAYOUT["structure"]["rail_front"]["z"]) / 2, 5.5))
    return out


@lru_cache(None)
def front_bar():
    y0 = Y_PLATE[1]
    x0, x1 = FRONT_BAR["x"]
    z0, z1 = FRONT_BAR["z"]
    s = prism_y(x0, x1, z0, z1, y0, y0 + T_PLATE, 4.0)
    return cut(s, *[cyl_y(x, z, d / 2, y0 - 1, y0 + T_PLATE + 1) for _, x, z, d in front_bar_holes()])


# =============================================================================
# extrusions
# =============================================================================

def _tslot_profile_cut(axis_len_dir, c0, c1, faces):
    """Not used for booleans in bulk: see _extrusion()."""


def _extrusion(x0, x1, y0, y1, z0, z1, along):
    """Coarse 20-series T-slot extrusion: box with 6 mm x 6.1 mm slots on each 20 mm module of each face and a
    centre hole per 20 x 20 cell."""
    s = box(x0, x1, y0, y1, z0, z1)
    cuts = []
    sw, sd = 6.0, 6.1
    if along == "y":
        L0, L1 = y0 - 1, y1 + 1
        nx, nz = round((x1 - x0) / 20), round((z1 - z0) / 20)
        for i in range(nx):
            xc = x0 + 10 + 20 * i
            cuts.append(box(xc - sw / 2, xc + sw / 2, L0, L1, z0 - 1, z0 + sd))
            cuts.append(box(xc - sw / 2, xc + sw / 2, L0, L1, z1 - sd, z1 + 1))
            for k in range(nz):
                cuts.append(cyl_y(xc, z0 + 10 + 20 * k, 2.6, L0, L1))
        for k in range(nz):
            zc = z0 + 10 + 20 * k
            cuts.append(box(x0 - 1, x0 + sd, L0, L1, zc - sw / 2, zc + sw / 2))
            cuts.append(box(x1 - sd, x1 + 1, L0, L1, zc - sw / 2, zc + sw / 2))
    else:  # along x
        L0, L1 = x0 - 1, x1 + 1
        yc, zc = (y0 + y1) / 2, (z0 + z1) / 2
        cuts += [box(L0, L1, y0 - 1, y0 + sd, zc - sw / 2, zc + sw / 2), box(L0, L1, y1 - sd, y1 + 1, zc - sw / 2, zc + sw / 2),
                 box(L0, L1, yc - sw / 2, yc + sw / 2, z0 - 1, z0 + sd), box(L0, L1, yc - sw / 2, yc + sw / 2, z1 - sd, z1 + 1),
                 cyl_x(yc, zc, 2.5, L0, L1)]
    return cut(s, *cuts)


def post_box(i):
    px = S["posts_x"][i]
    z0, z1 = S["posts_z"]
    y0 = Y_PLATE[1]
    return px - POST["w"] / 2, px + POST["w"] / 2, y0, y0 + POST["len"], z0, z1


@lru_cache(None)
def posts():
    return compound([_extrusion(*post_box(i), along="y") for i in range(2)])


def rail_box(which):
    r = S["rail_front"] if which == "front" else S["rail_mid"]
    y0 = r["y0"]
    return -RAIL["len"] / 2, RAIL["len"] / 2, y0, y0 + RAIL["w"], r["z"][0], r["z"][1]


@lru_cache(None)
def rail_front():
    return _extrusion(*rail_box("front"), along="x")


@lru_cache(None)
def rail_mid():
    return _extrusion(*rail_box("mid"), along="x")


# =============================================================================
# wing bracket: centre bracket (flat panel + two 10-degree ears) and two wing channels
# =============================================================================
# Plan geometry.  Centre panel back face on the posts' front faces (z = post front).  Its front face continues,
# through a 10-degree bend at x = +-60, into the ear's front face, which is the plane w = web_w - t (the wing web's
# back face): the ears sit BEHIND the wing webs, between their flanges.  That plane is what fixes the seam axis z
# (common.LAYOUT display.seam_axis_xz), so the posts, the bracket and the monitors close up exactly.

def _ear_front_w():
    return web_w() - T_BRK


def check_closure():
    """Return the z mismatch (mm) between the centre panel front face and the ear plane at the bend line."""
    w = _ear_front_w()
    xb = CENTRE["half_w"]
    u = (xb + w * SIN_T) / COS_T
    z_plane = seam_z() + u * SIN_T + w * COS_T
    return z_plane - (post_front_z() + T_BRK)


def _ear_u0():
    w = _ear_front_w()
    return (CENTRE["half_w"] + w * SIN_T) / COS_T


@lru_cache(None)
def bracket_centre():
    """Centre panel + ears, one 3/16 in part (NA-WING-C).  10-degree bends modelled sharp (arc length 0.55 mm)."""
    yc = vesa_y()
    h = CENTRE["h"]
    y0, y1 = yc - h / 2, yc + h / 2
    zf = post_front_z()
    xb = CENTRE["half_w"]
    panel = box(-xb, xb, y0, y1, zf, zf + T_BRK)
    # ear: facet-frame slab u [u0, u1], w [front - t, front], placed per side (no trim)
    wf = _ear_front_w()
    u0 = _ear_u0()
    ear_local = box(u0 - 0.5, CENTRE["ear_u1"], y0, y1, wf - T_BRK, wf)
    holes_local = [cyl_z(u, yc + dy, 2.75, wf - T_BRK - 1, wf + 1)
                   for u in CENTRE["ear_bolts_u"] for dy in CENTRE["ear_bolts_y"]]
    ear_local = cut(ear_local, *holes_local)
    er, el = place_facet(ear_local, 1), place_facet(ear_local, -1)
    s = fuse(panel, er, el)
    # trim the sharp-bend overlap behind the panel (keep the panel's back plane clean)
    s = cut(s, box(-xb - 30, xb + 30, y0 - 1, y1 + 1, zf - 30, zf))
    holes = [cyl_z(px, yc + dy, 2.75, zf - 1, zf + T_BRK + 1) for px in S["posts_x"] for dy in CENTRE["post_bolts_y"]]
    s = cut(s, *holes)
    return s


def _wing_local():
    """One wing channel in the RIGHT facet frame: web (front face at web_w) + top/bottom 90-degree return
    flanges pointing back (-w), inside R 3.18.  Symmetric about the VESA centre line, so the same part serves
    both sides (turn it over)."""
    u0, u1 = WING["u"]
    yc = vesa_y()
    H = WING["h"]
    t = T_BRK
    R = SCS["bend_r"]
    wf = web_w()
    wb = wf - WING["flange"]
    # profile in the (y, w) plane, extruded along u (facet x): outer C with rounded outside corners
    wp = cq.Workplane("YZ", origin=(u0, 0, 0))
    outer = (wp.moveTo(yc - H / 2, wb).lineTo(yc - H / 2, wf - (R + t))
             .threePointArc((yc - H / 2 + (R + t) * (1 - math.cos(math.pi / 4)), wf - (R + t) * (1 - math.sin(math.pi / 4))),
                            (yc - H / 2 + (R + t), wf))
             .lineTo(yc + H / 2 - (R + t), wf)
             .threePointArc((yc + H / 2 - (R + t) * (1 - math.cos(math.pi / 4)), wf - (R + t) * (1 - math.sin(math.pi / 4))),
                            (yc + H / 2, wf - (R + t)))
             .lineTo(yc + H / 2, wb).lineTo(yc + H / 2 - t, wb).lineTo(yc + H / 2 - t, wf - t - R)
             .threePointArc((yc + H / 2 - t - R * (1 - math.cos(math.pi / 4)), wf - t - R * (1 - math.sin(math.pi / 4))),
                            (yc + H / 2 - t - R, wf - t))
             .lineTo(yc - H / 2 + t + R, wf - t)
             .threePointArc((yc - H / 2 + t + R * (1 - math.cos(math.pi / 4)), wf - t - R * (1 - math.sin(math.pi / 4))),
                            (yc - H / 2 + t, wf - t - R))
             .lineTo(yc - H / 2 + t, wb).close())
    s = outer.extrude(u1 - u0).val()
    uc = monitor_uc()
    sw, sl = WING["vesa_slot"]
    cuts = []
    for a in (-50.0, 50.0):
        for b in (-50.0, 50.0):
            cuts.append(stadium_y(0, 0, sl, sw, 0, 1).rotate(Vector(0, 0, 0), Vector(1, 0, 0), 90)
                        .translate(Vector(uc + a, yc + b, 0)))
    # the stadium above was built in XZ and rotated to stand in XY; extrude through the web
    cuts = [cq.Workplane("XY", origin=(0, 0, wf - t - 1)).center(uc + a, yc + b).slot2D(sl, sw, 90).extrude(t + 2).val()
            for a in (-50.0, 50.0) for b in (-50.0, 50.0)]
    cuts += [cyl_z(u, yc + dy, 2.75, wf - t - 1, wf + 1) for u in CENTRE["ear_bolts_u"] for dy in CENTRE["ear_bolts_y"]]
    # shroud mounting holes in the flanges (M4 into inserts in the shroud's bosses), 3 per flange
    for u in (110.0, 230.0, 350.0):
        for yy in (yc - H / 2 - 1, yc + H / 2 - t - 1):
            cuts.append(cyl_y(u, wb + 10.0, 2.25, yy, yy + t + 2))
    return cut(s, *cuts)


@lru_cache(None)
def wings():
    loc = _wing_local()
    return compound([place_facet(loc, -1), place_facet(loc, 1)])


@lru_cache(None)
def vesa_spacers():
    """8 x Al round spacers 8 OD x 10, M4 clearance, between the VESA pocket floors and the wing webs."""
    uc = monitor_uc()
    yc = vesa_y()
    w0, w1 = -S60UD["vesa_floor"] - LAYOUT["display"]["vesa_spacer"], -S60UD["vesa_floor"]
    sp = cut(cyl_z(0, 0, 4.0, w0, w1), cyl_z(0, 0, 2.2, w0 - 1, w1 + 1))
    loc = compound([sp.translate(Vector(uc + a, yc + b, 0)) for a in (-50, 50) for b in (-50, 50)])
    return compound([place_facet(loc, -1), place_facet(loc, 1)])


@lru_cache(None)
def feet():
    b = bumpon_local()
    return compound([b.translate(Vector(x, 0, z)) for x, z in FEET_XZ])


# =============================================================================
# fasteners (heads + clearance shanks only: threads into inserts / nuts are not modelled)
# =============================================================================

@lru_cache(None)
def fasteners():
    out = []
    y0, y1 = Y_PLATE
    # posts: M6 x 20 ISO 10642 from below, heads flush in the plate countersinks (shank inside the post's hole)
    for kind, x, z, d in spine_holes():
        if "post" in kind:
            out.append(cyl_y(x, z, 2.5, y0 + 0.2, y1 + 12))
    # bracket centre panel -> post front slots: M5 x 10 ISO 7380, heads in front of the panel
    zf = post_front_z() + T_BRK
    for px in S["posts_x"]:
        for dy in CENTRE["post_bolts_y"]:
            out.append(cyl_z(px, vesa_y() + dy, 4.75, zf, zf + 2.75))
    # ear -> wing web: M5 x 16 ISO 7380 heads on the web front (in the gap to the monitor box: 1.8 mm, so heads go
    # on the BACK: head behind the ear, nut on the web front is not possible either) -> use ISO 10642 csk from the
    # web front into a nylock nut behind the ear.  Model: nut (8 AF ~ 9.2 dia) behind the ear.
    wf = _ear_front_w()
    loc = []
    for u in CENTRE["ear_bolts_u"]:
        for dy in CENTRE["ear_bolts_y"]:
            loc.append(cyl_z(u, vesa_y() + dy, 4.6, wf - T_BRK - 5.0, wf - T_BRK))
    # VESA: M4 x 22 ISO 4762, heads behind the web
    uc = monitor_uc()
    for a in (-50, 50):
        for b in (-50, 50):
            loc.append(cyl_z(uc + a, vesa_y() + b, 3.5, web_w() - T_BRK - 4.0, web_w() - T_BRK))
    lc = compound(loc)
    out += [place_facet(lc, -1), place_facet(lc, 1)]
    # front rail: M5 x 10 ISO 7380 from below the front bar into hammer nuts (heads under the bar)
    for kind, x, z, d in front_bar_holes():
        if "rail" in kind:
            out.append(cyl_y(x, z, 4.75, Y_PLATE[1] - 2.75, Y_PLATE[1]))
    return compound(out)


# =============================================================================
# flat patterns (SendCutSend DXF): outline + holes + bend lines
# =============================================================================

def bend_allowance(angle_deg, t=T_BRK, R=SCS["bend_r"], k=SCS["k"]):
    return math.radians(angle_deg) * (R + k * t)


def flat_patterns():
    """{part_id: {'outline': [(x, y)], 'holes': [(x, y, d)], 'slots': [(x, y, w, l, angle)], 'bends': [((x0, y0),
    (x1, y1), angle_deg, direction)], 't': mm, 'material': str, 'qty': n}} -- 2D in the plate's own plane."""
    out = {}
    # spine plate: plan (x, -z)
    out["NA-SPINE-01"] = {
        "outline": [(x, -z) for x, z in spine_outline_pts()],
        "holes": [(x, -z, d) for kind, x, z, d in spine_holes()],
        "csk": [(x, -z, 12.0 if "M6" in kind else 10.0) for kind, x, z, d in spine_holes() if "csk" in kind],
        "slots": [], "bends": [], "t": T_PLATE, "material": "A36/1008 HRP-250 (1/4 in)", "qty": 1,
        "fillet": {"outer": SPINE["corner_r"], "inner": SPINE["inner_r"]},
    }
    x0, x1 = FRONT_BAR["x"]
    z0, z1 = FRONT_BAR["z"]
    out["NA-FRONTBAR-01"] = {
        "outline": [(x0, -z0), (x1, -z0), (x1, -z1), (x0, -z1)],
        "holes": [(x, -z, d) for kind, x, z, d in front_bar_holes()],
        "tapped": [(x, -z, "M5x0.8") for kind, x, z, d in front_bar_holes() if "tapped" in kind],
        "slots": [], "bends": [], "t": T_PLATE, "material": "A36/1008 HRP-250 (1/4 in)", "qty": 1,
    }
    # centre bracket: flat length = panel + 2 ears (+ bend allowance for 10 deg), height 120
    ba10 = bend_allowance(10)
    xb = CENTRE["half_w"]
    u0 = _ear_u0()
    ear = CENTRE["ear_u1"] - u0
    half = xb + ba10 / 2 + ear
    h = CENTRE["h"]
    holes = [(px, dy, 5.5) for px in S["posts_x"] for dy in CENTRE["post_bolts_y"]]
    for sx in (-1, 1):
        for u in CENTRE["ear_bolts_u"]:
            for dy in CENTRE["ear_bolts_y"]:
                holes.append((sx * (xb + ba10 / 2 + (u - u0)), dy, 5.5))
    out["NA-WING-C"] = {
        "outline": [(-half, -h / 2), (half, -h / 2), (half, h / 2), (-half, h / 2)],
        "holes": holes, "slots": [],
        "bends": [((sx * xb, -h / 2), (sx * xb, h / 2), 10.0, "ears toward the monitors (front)") for sx in (-1, 1)],
        "t": T_BRK, "material": "A36/1008 HRP-188 (3/16 in)", "qty": 1,
    }
    # wing channel: web height between bend lines + two flanges
    ba90 = bend_allowance(90)
    H = WING["h"]
    t = T_BRK
    R = SCS["bend_r"]
    web_flat = H - 2 * (R + t)               # flat between the bends (outside mould line minus setbacks)
    fl_flat = WING["flange"] - (R + t)
    total = web_flat + 2 * ba90 + 2 * fl_flat
    L = WING["u"][1] - WING["u"][0]
    ua = WING["u"][0]
    uc = monitor_uc()
    holes, slots = [], []
    for a in (-50.0, 50.0):
        for b in (-50.0, 50.0):
            slots.append((uc + a - ua, b, WING["vesa_slot"][0], WING["vesa_slot"][1], 90.0))
    for u in CENTRE["ear_bolts_u"]:
        for dy in CENTRE["ear_bolts_y"]:
            holes.append((u - ua, dy, 5.5))
    yb = web_flat / 2 + ba90
    for u in (110.0, 230.0, 350.0):
        for sy in (-1, 1):
            holes.append((u - ua, sy * (yb + (WING["flange"] - 10.0) - (R + t)), 4.5))
    out["NA-WING-01"] = {
        "outline": [(0, -total / 2), (L, -total / 2), (L, total / 2), (0, total / 2)],
        "holes": holes, "slots": slots,
        "bends": [((0, sy * web_flat / 2), (L, sy * web_flat / 2), 90.0, "flange back (away from monitor)") for sy in (-1, 1)],
        "t": T_BRK, "material": "A36/1008 HRP-188 (3/16 in)", "qty": 2,
        "note": "same part both sides: the left wing is the right one turned over about its long axis",
    }
    return out


def check_flat_patterns():
    """[(part, problem)] against the SendCutSend rules (part size, min flange, hole-to-bend)."""
    probs = []
    for pid, fp in flat_patterns().items():
        xs = [p[0] for p in fp["outline"]]
        ys = [p[1] for p in fp["outline"]]
        w, h = max(xs) - min(xs), max(ys) - min(ys)
        a, b = sorted((w, h), reverse=True)
        if a > SCS["max_part"][0] or b > SCS["max_part"][1]:
            probs.append((pid, f"part {w:.0f} x {h:.0f} exceeds 1117 x 762"))
        for (p0, p1, ang, _) in fp["bends"]:
            horiz = abs(p0[1] - p1[1]) < 1e-6
            for hx, hy, d in fp["holes"]:
                dist = abs(hy - p0[1]) if horiz else abs(hx - p0[0])
                along = (min(p0[0], p1[0]) - 1 <= hx <= max(p0[0], p1[0]) + 1) if horiz else \
                        (min(p0[1], p1[1]) - 1 <= hy <= max(p0[1], p1[1]) + 1)
                if along and dist < SCS["hole_to_bend"] - 1e-6:
                    probs.append((pid, f"hole ({hx:.1f}, {hy:.1f}) {dist:.1f} mm from a bend line (< 12.4)"))
            for sx, sy, sw, sl, sa in fp["slots"]:
                ext = sl / 2 if horiz else sw / 2
                dist = (abs(sy - p0[1]) - ext) if horiz else (abs(sx - p0[0]) - ext)
                if dist < SCS["hole_to_bend"] - 1e-6:
                    probs.append((pid, f"slot ({sx:.1f}, {sy:.1f}) {dist:.1f} mm from a bend line (< 12.4)"))
        if pid == "NA-WING-01":
            fl = WING["flange"]
            if fl < SCS["min_flange"]:
                probs.append((pid, f"flange {fl} < {SCS['min_flange']}"))
    return probs


def write_metal(outdir):
    """DXF flat patterns (layers CUT, HOLES, BEND, NOTE) for SendCutSend, one file per part, mm."""
    import os
    import ezdxf
    os.makedirs(outdir, exist_ok=True)
    written = []
    for pid, fp in flat_patterns().items():
        doc = ezdxf.new("R2010", setup=False)
        doc.units = 4   # mm
        doc.header["$INSUNITS"] = 4
        for nm, col in (("CUT", 7), ("BEND", 1), ("NOTE", 3)):
            doc.layers.add(nm, color=col)
        msp = doc.modelspace()
        msp.add_lwpolyline(fp["outline"] + [fp["outline"][0]], dxfattribs={"layer": "CUT"})
        for x, y, d in fp["holes"]:
            msp.add_circle((x, y), d / 2, dxfattribs={"layer": "CUT"})
        for x, y, w, l, ang in fp["slots"]:
            # vertical stadium w x l centred (x, y)
            r = w / 2
            hl = (l - w) / 2
            msp.add_line((x - r, y - hl), (x - r, y + hl), dxfattribs={"layer": "CUT"})
            msp.add_line((x + r, y - hl), (x + r, y + hl), dxfattribs={"layer": "CUT"})
            msp.add_arc((x, y + hl), r, 0, 180, dxfattribs={"layer": "CUT"})
            msp.add_arc((x, y - hl), r, 180, 360, dxfattribs={"layer": "CUT"})
        for p0, p1, ang, note in fp["bends"]:
            msp.add_line(p0, p1, dxfattribs={"layer": "BEND"})
            msp.add_text(f"BEND {ang:.0f} deg {note}; R 3.18 inside, k 0.32",
                         dxfattribs={"layer": "NOTE", "height": 3.0}).set_placement(((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2 + 2))
        msp.add_text(f"{pid}  {fp['material']}  t={fp['t']} mm  qty {fp['qty']}",
                     dxfattribs={"layer": "NOTE", "height": 5.0}).set_placement((min(p[0] for p in fp["outline"]),
                                                                                 max(p[1] for p in fp["outline"]) + 8))
        p = os.path.join(outdir, pid + ".dxf")
        doc.saveas(p)
        written.append(p)
    return written


# =============================================================================
# registry
# =============================================================================

_STEEL = "steel"
PARTS = [
    PartDef("spine_plate", "structure", "Spine / ballast plate (1/4 in A36, U)", _STEEL, "metal", spine_plate,
            internal=True, bom="steel-spine-plate"),
    PartDef("front_bar", "structure", "Front ballast bar (1/4 in A36)", _STEEL, "metal", front_bar, internal=True,
            bom="steel-front-bar"),
    PartDef("posts", "structure", "2040 posts (2 x 400 mm)", "aluminium", "metal", posts, internal=True,
            bom="extrusion-2040-400"),
    PartDef("rail_front", "structure", "Front 2020 rail (1200 mm)", "aluminium", "metal", rail_front, internal=True,
            bom="extrusion-2020-1200"),
    PartDef("rail_mid", "structure", "Middle 2020 rail (1200 mm)", "aluminium", "metal", rail_mid, internal=True,
            bom="extrusion-2020-1200"),
    PartDef("bracket_centre", "structure", "Centre bracket (3/16 in, 10-degree ears)", _STEEL, "metal",
            bracket_centre, internal=True, bom="steel-wing-centre"),
    PartDef("wings", "structure", "Wing channels (2 x 3/16 in, return flanges)", _STEEL, "metal", wings,
            internal=True, bom="steel-wing-channel"),
    PartDef("vesa_spacers", "structure", "VESA spacers (8 x 10 mm Al)", "aluminium", "hardware", vesa_spacers,
            internal=True, bom="spacer-m4-10"),
    PartDef("feet", "structure", "3M Bumpon SJ5023 feet (6)", "rubber", "hardware", feet, internal=False,
            bom="bumpon-sj5023", mass_g=6 * 2.0),
    PartDef("fasteners", "structure", "Structural fasteners (heads)", _STEEL, "hardware", fasteners, internal=True,
            bom="screws-structure"),
]
