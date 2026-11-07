"""Night Array kit -- envelope models of every purchased part, from the verified research (kit/research).

FROZEN INTERFACE (owner: CAD architect).  Each function returns a solid in the part's OWN local frame (documented
per function); electronics.py / dock.py / display.py place them.  Dimensions are the research values, with the
verifier's corrections applied where they exist (noted inline as 'verifier:').  Envelopes are deliberately
honest about uncertainty: where a value is only known from photos or a 3D model, ENV notes it and the printed
pocket around it uses TOL['purchased_loose'].
"""

from __future__ import annotations

import math
from functools import lru_cache

import cadquery as cq
from cadquery import Vector

from .common import (LAYOUT, box, chamfer, compound, cut, cyl_x, cyl_y, cyl_z, edges_where, fillet, fuse, near,
                     on_plane, poly_x, prism_x, prism_y, prism_z, single, stadium_y, tight_bbox, vertical_edges)

# =============================================================================
# research data (mm, kg).  'src' = where the number comes from.
# =============================================================================

S60UD = {  # Samsung ViewFinity S6 S60UD 27" QHD, LS27D606UANXGO.  verifier parsed Samsung's GLB.
    "face_w": 612.9, "face_h": 362.6,                  # flat housing face (spec 367.7 incl. the logo nub)
    "edge_band": 15.4,                                 # verifier: 15.4 (research 16)
    "box_w": 449.0, "box_h": 211.0, "box_back": 39.6,  # rear box, back face 39.6 behind the screen face
    "box_bottom": 76.0,                                # rear box underside above the face bottom
    "box_r": 12.0,                                     # rear-box plan edge radius (estimate from photos)
    "vesa": 100.0, "vesa_y": 181.2,                    # VESA centre above face bottom, centred left-right
    "vesa_pocket": [120.2, 120.2, 8.2],                # verifier: stand pocket, floor 31.4 behind the screen
    "vesa_floor": 31.4,
    "active": [596.736, 335.664], "bezel_side": 8.08,
    "active_above_vesa": 6.0,                          # verifier: 5.3-6.8
    "bezel_top_min_nocover": 6.5, "chin_min_nocover": 18.5,   # verifier: never cover more than this
    "chin_lip": {"proud": 2.0, "y": [0.4, 16.7], "half_w": 305.7},
    "nub": {"w": 40.0, "drop": 5.2, "depth": 8.0},     # logo/LED nub below the face bottom (depth estimated)
    "joystick": {"y": [39.0, 62.0], "proud": 7.0, "d": 12.0},  # behind the edge band, centred
    "ports_down": {"x": [91.0, 192.0], "w": [-32.2, -17.6], "mouth_y": 83.0},   # verifier: connector shells
    "plug_zone_below": 30.0,                           # right-angle plugs below the box underside
    "ac_inlet": {"x": [-168.5, -137.5], "body": [31.0, 21.5], "type": "IEC C14 (verifier, from pin geometry)"},
    "side_io": {"x": 224.5, "y": [179.0, 268.0]},      # USB-A / RJ45 / headphone on the box's +x face
    "mass_kg": 3.6, "vent_clear_mm": 100.0,            # manual p11 asks 10 cm free space (shroud can't: see docs)
}

DOCK_UD6950PDH = {"w": 225.0, "d": 85.0, "h": 24.5, "mass_kg": 0.465, "rear_clear": 70.0,
                  "host": "USB-C on the REAR face (5 Gbps, 100 W PD)", "brick": "130 W 20 V/6.5 A, IEC C13/C14"}
DOCK_BRICK = {"w": 150.0, "d": 70.0, "h": 30.0, "bay": [160.0, 80.0, 35.0], "mass_kg": 0.55,
              "note": "130 W brick dimensions unpublished: bay is a reservation, measure on arrival"}
STRIP = {"len": 609.6, "face_w": 40.9, "depth": 31.8, "clip": 6.0, "plug_zone": 30.0, "cord_bend": 51.0,
         "mass_kg": 0.89, "pitch": 144.0, "outlets": 6,
         "note": "verifier: M4 inserts for the clips; outlet layout vs 609.6 length inconsistent in the datasheet "
                 "(6 x 144 mm does not fit): the bay gives a continuous plug zone, measure on arrival"}
GAN = {"w": 98.81, "d": 76.31, "h": 23.1, "body_h": 22.1, "port_clear": 35.0, "inlet_clear": 30.0, "mass_kg": 0.30}
ANKER313 = {"w": 100.0, "d": 100.0, "h": 11.2, "r": 14.0, "mass_kg": 0.063, "max_ambient_C": 40}
K3U = {"w": 320.62, "d": 126.0, "h_front": 20.0, "h_rear": 25.5, "body_front": 16.55, "body_rear": 20.1,
       "feet": 2.0, "r": 6.0, "mass_kg": 0.566}
MAGIC_TAG = {"pad": [82.0, 48.0, 1.0], "overall": 100.0, "coil_from_tail": 50.0, "mass_kg": 0.0082}
X9 = {"w": 59.0, "l": 101.0, "h": 34.0, "mass_kg": 0.075}
LAPTOP = {"t": 15.0, "h": 304.0, "d": 212.0, "mass_kg": 1.40, "mass_kg_max": 2.14,
          "note": "generic 14-inch: the dock takes 11-20 mm laptops; 2.14 kg (MacBook Pro 16) is the stability case"}
NEWNEX = {"plug": [2.40, 6.65, 8.25], "head": [6.50, 15.51, 12.35], "len": 34.5, "plug_to_closed_end": 6.17,
          "cable_axis_from_face": 9.19, "zone2_step": 2.84, "zone2_end": 20.3, "relief": 8.4, "relief_end": 28.3,
          "cable_od": 4.8, "min_bend_r": 25.0}
LED_CHANNEL = {"w": 5.0, "h": 5.0, "inner_w": 3.0, "groove": 5.3}
DIMMER = {"l": 61.0, "w": 33.0, "h": 32.0, "knob_d": 16.0, "knob_h": 12.0, "panel_hole": 22.0}
WAGO = {"221-412": [13.2, 8.4, 18.8], "221-413": [18.8, 8.4, 18.6], "221-415": [29.9, 8.3, 18.6]}
POLOLU_D36V6F5 = [13.0, 3.0, 10.0]
HUSB238_5807 = [24.5, 4.9, 20.2]
PD_6032 = [40.0, 15.0, 20.0]
JACK_368 = [35.0, 15.0, 15.0]
OPTO_BOARD = [30.0, 8.0, 20.0]
IR_2167 = {"l": 20.0, "w": 10.0, "t": 8.0, "pocket": [20.6, 10.6, 9.6], "led_from_end": 5.0, "hole_d": 3.4}
BUMPON_SJ5023 = {"w": 20.6, "h": 7.6, "top": 12.0}
DESKMAT = {"w": 900.0, "d": 300.0, "t": 3.0, "r": 6.0}


# =============================================================================
# monitor: Samsung S60UD, in the RIGHT facet frame (u along the panel from the seam axis, y up, w toward the user)
# =============================================================================
# `side` decides which way the monitor's own front-view x runs in u: the monitor is not mirror-symmetric (ports
# right of centre), so the left panel is built with x_local -> -x_local before place_facet mirrors it.

def monitor_u0():
    return LAYOUT["display"]["seam_gap"] / 2


def monitor_uc():
    return monitor_u0() + S60UD["face_w"] / 2


def monitor_u_of(side, x_local):
    """Facet u of a point at the monitor's own front-view x (right positive) -- side +1 right panel, -1 left."""
    return monitor_uc() + side * x_local


def monitor_y0():
    return LAYOUT["display"]["face_bottom_y"]


def s60ud_local(side=1):
    """Housing envelope in the facet frame (screen face at w = 0).  Edge band, rear box with the VESA pocket,
    chin lip, logo nub, joystick.  Port and inlet zones are returned by s60ud_zones() (keep-clear, not solids)."""
    M = S60UD
    u0, y0 = monitor_u0(), monitor_y0()
    u1, y1 = u0 + M["face_w"], y0 + M["face_h"]
    uc = monitor_uc()
    band = box(u0, u1, y0, y1, -M["edge_band"], 0.0)
    band = fillet(band, 4.0, edges_where(band, lambda c, bb, e: (bb.zmax - bb.zmin) > 5), "monitor corners")
    by0 = y0 + M["box_bottom"]
    bx = box(uc - M["box_w"] / 2, uc + M["box_w"] / 2, by0, by0 + M["box_h"], -M["box_back"], -M["edge_band"] + 0.5)
    bx = fillet(bx, M["box_r"], edges_where(bx, lambda c, bb, e: (bb.zmax - bb.zmin) > 5), "box corners")
    bx = fillet(bx, 6.0, edges_where(bx, on_plane("z", -M["box_back"])), "box back edge")
    s = fuse(band, bx)
    # VESA pocket (the stand's push-in pocket) and M4 holes
    vy = y0 + M["vesa_y"]
    pw, ph, pd = M["vesa_pocket"]
    s = cut(s, box(uc - pw / 2, uc + pw / 2, vy - ph / 2, vy + ph / 2, -M["box_back"] - 1, -M["vesa_floor"]))
    s = cut(s, *[cyl_z(uc + a, vy + b, 2.0, -M["vesa_floor"] - 1, -M["vesa_floor"] + 10)
                 for a in (-50, 50) for b in (-50, 50)])
    # chin lip, 2 mm proud of the screen plane over the bottom 16.7 mm
    cl = M["chin_lip"]
    s = fuse(s, box(uc - cl["half_w"], uc + cl["half_w"], y0 + cl["y"][0], y0 + cl["y"][1], -0.5, cl["proud"]))
    # logo / power-LED nub below the face bottom, centred
    nb = M["nub"]
    s = fuse(s, box(uc - nb["w"] / 2, uc + nb["w"] / 2, y0 - nb["drop"], y0 + 1.0, -nb["depth"], 0.0))
    # joystick behind the chin, centred
    js = M["joystick"]
    s = fuse(s, cyl_z(uc, y0 + sum(js["y"]) / 2, js["d"] / 2, -M["edge_band"] - js["proud"], -M["edge_band"] + 0.5))
    return s


def s60ud_zones(side=1):
    """Keep-clear zones (facet frame boxes (u0,u1,y0,y1,w0,w1)) the display shroud must leave open:
    'ports' (down-facing video/USB-C/DP-out + right-angle plug room), 'ac' (C14 inlet + right-angle C13),
    'side_io' (+x face of the rear box), 'joystick' (finger room), 'vesa' (pocket), 'vent_box' (10 mm air)."""
    M = S60UD
    y0 = monitor_y0()
    by0 = y0 + M["box_bottom"]
    ua, ub = sorted((monitor_u_of(side, M["ports_down"]["x"][0]), monitor_u_of(side, M["ports_down"]["x"][1])))
    ca, cb = sorted((monitor_u_of(side, M["ac_inlet"]["x"][0]), monitor_u_of(side, M["ac_inlet"]["x"][1])))
    si = monitor_u_of(side, M["side_io"]["x"])
    uc = monitor_uc()
    js = M["joystick"]
    return {
        "ports": (ua - 5, ub + 5, by0 - M["plug_zone_below"], by0 + 8, -36.0, -13.0),
        "ac": (ca - 5, cb + 5, by0 - 45.0, by0 + 2, -40.0, -14.0),
        "side_io": ((si, si + side * 50.0) if side > 0 else (si - 50.0, si)) + (y0 + M["side_io"]["y"][0],
                                                                               y0 + M["side_io"]["y"][1], -40.0, -16.0),
        "joystick": (uc - 20, uc + 20, y0 + js["y"][0] - 8, y0 + js["y"][1] + 8, -M["edge_band"] - 30, -M["edge_band"]),
        "vent_box": (uc - M["box_w"] / 2 - 10, uc + M["box_w"] / 2 + 10, by0 - 10, by0 + M["box_h"] + 10,
                     -M["box_back"] - 10, -M["edge_band"]),
    }


def screen_local():
    """Active area skin (0.3 mm, for the app's screen texture) in the facet frame: active centre 6 mm above VESA."""
    M = S60UD
    uc = monitor_uc()
    vy = monitor_y0() + M["vesa_y"]
    aw, ah = M["active"]
    yc = vy + M["active_above_vesa"]
    return box(uc - aw / 2, uc + aw / 2, yc - ah / 2, yc + ah / 2, 0.0, 0.3)


def active_area():
    """(u0, u1, y0, y1) of the right panel's active area in the facet frame."""
    M = S60UD
    uc = monitor_uc()
    yc = monitor_y0() + M["vesa_y"] + M["active_above_vesa"]
    aw, ah = M["active"]
    return uc - aw / 2, uc + aw / 2, yc - ah / 2, yc + ah / 2


# =============================================================================
# laptop (generic 14-inch), standing closed on its left side, hinge toward -z; local = world placement by dock.py
# =============================================================================

def laptop_body(x0, y0, z0, port_z):
    """Laptop standing on its side: x [x0, x0+t], y [y0, y0+h], z [z0, z0+d].  USB-C port on the bottom edge."""
    t, h, d = LAPTOP["t"], LAPTOP["h"], LAPTOP["d"]
    x1, y1, z1 = x0 + t, y0 + h, z0 + d
    s = box(x0, x1, y0, y1, z0, z1)
    s = fillet(s, 6.0, edges_where(s, lambda c, bb, e: (bb.xmax - bb.xmin) > 5), "laptop corners")
    s = fillet(s, 2.5, edges_where(s, lambda c, bb, e: near(bb.xmin, x0) and near(bb.xmax, x0)
                                   or near(bb.xmin, x1) and near(bb.xmax, x1)), "laptop faces")
    xs = x1 - 5.0
    slab = box(xs - 0.6, xs, y0 - 5, y1 + 5, z0 - 5, z1 + 5)
    keep = prism_x(z0 + 0.6, z1 - 0.6, y0 + 0.6, y1 - 0.6, xs - 1.6, xs + 1, 5.4)
    s = cut(s, cut(slab, keep))
    xc = (x0 + x1) / 2
    port = stadium_y(xc, port_z, 8.9, 3.2, y0 - 1, y0 + 7.5, along="z")
    return cut(s, port)


# =============================================================================
# keyboard: Keychron K3 Ultra 8K + NILLKIN Magic Tag.  Local frame: left-rear-bottom corner at the origin,
# x right (320.62), z toward the user (126), y up (feet at y 0..2).
# =============================================================================

K3U_ROWS = [
    [1] * 16,
    [1] * 13 + [2, 1],
    [1.5] + [1] * 12 + [1.5, 1],
    [1.75] + [1] * 11 + [2.25, 1],
    [2.25] + [1] * 10 + [1.75, 1, 1],
    [1.25, 1.25, 1.25, 6.25, 1, 1, 1, 1, 1, 1],
]
K3U_UNIT = 18.8


def _k3u_top(z, front, rear):
    """Height at depth z (0 = rear edge, d = front) on a plane from `rear` to `front`."""
    d = K3U["d"]
    return rear + (front - rear) * z / d


def _below_plane(front, rear, sign=1):
    """Half-space solid below (sign=1) / above (sign=-1) the sloped plane through (z=0, y=rear), (z=d, y=front)."""
    d = K3U["d"]
    big = 2000
    pts = [(-big, _k3u_top(-big, front, rear)), (d + big, _k3u_top(d + big, front, rear))]
    if sign > 0:
        pts += [(d + big, -big), (-big, -big)]
    else:
        pts += [(d + big, big), (-big, big)]
    return poly_x(pts, -big, big)


@lru_cache(None)
def k3u_body_local():
    W, D = K3U["w"], K3U["d"]
    s = prism_y(0, W, 0, D, K3U["feet"], K3U["body_rear"] + 1, K3U["r"])
    s = single(s.intersect(_below_plane(K3U["body_front"], K3U["body_rear"])))
    s = fillet(s, 1.5, edges_where(s, lambda c, bb, e: bb.ymin > K3U["body_front"] - 0.5), "k3u top")
    feet = [prism_y(x - 12, x + 12, z - 5, z + 5, 0, K3U["feet"] + 0.5, 2) for x in (20, W - 20) for z in (15, D - 14)]
    return fuse(s, *feet)


@lru_cache(None)
def k3u_keys_local():
    """84 keycaps on an 18.8 mm pitch (K3 Ultra key field ~ 301 x 113), top on the 20 -> 25.5 mm plane."""
    W, D = K3U["w"], K3U["d"]
    u = K3U_UNIT
    x0 = (W - 16 * u) / 2
    z0 = 6.5
    caps = []
    for r, row in enumerate(K3U_ROWS):
        zc = z0 + (r + 0.5) * u
        x = x0
        for wu in row:
            w = wu * u
            caps.append(prism_y(x + 0.9, x + w - 0.9, zc - u / 2 + 0.9, zc + u / 2 - 0.9, K3U["body_front"] - 2,
                                K3U["h_rear"] + 2, 2.0))
            x += w
    keys = compound(caps)
    keys = keys.intersect(_below_plane(K3U["h_front"], K3U["h_rear"]))
    keys = keys.cut(_below_plane(K3U["body_front"] + 0.02, K3U["body_rear"] + 0.02))
    return keys


def magic_tag_local():
    """Magic Tag folded round the left edge with a 45-degree flex fold: pad under the left-rear, coil ~47 mm in from
    the left edge and ~45 mm forward of the rear edge (verifier); plug in the left-side USB-C ~23 mm from the rear."""
    px, pz, pt = MAGIC_TAG["pad"]
    cx, cz = 47.5, 45.0
    pad = box(cx - pz / 2, cx + pz / 2, 0.5, 0.5 + pt, cz - px / 2, cz + px / 2)
    flex = box(-1.2, cx - pz / 2 + 0.5, 0.5, 0.5 + 0.3, 16, 30)
    up = box(-1.2, -0.9, 0.5, 6.5, 16, 30)
    plug = box(-6.0, 0.0, 4.0, 9.0, 18.5, 27.5)
    return compound([pad, flex, up, plug])


# =============================================================================
# mouse: Lenovo Multi-Device Wireless Mouse (X9 Edition) 4Y51R29290, 59 x 101 x 34.  Local: centred on x/z, y up.
# =============================================================================

def _mouse_section(z, a, h):
    pts = [(a, 0.0), (a * 1.0, 0.24 * h), (a * 0.94, 0.55 * h), (a * 0.74, 0.83 * h), (a * 0.40, 0.975 * h), (0.0, h),
           (-a * 0.40, 0.975 * h), (-a * 0.74, 0.83 * h), (-a * 0.94, 0.55 * h), (-a * 1.0, 0.24 * h), (-a, 0.0)]
    vs = [Vector(x, y, z) for x, y in pts]
    sp = cq.Edge.makeSpline(vs, tangents=[Vector(0, 1, 0), Vector(0, -1, 0)])
    ln = cq.Edge.makeLine(Vector(-a, 0, z), Vector(a, 0, z))
    return cq.Wire.assembleEdges([sp, ln])


def _mouse_dims(t):
    A = 30.0 + 1.5 * t - 4.0 * t * t
    H = 34.0 - 11.0 * (t - 0.18) ** 2
    ea = (1 - abs(t) ** 2.4) ** (1 / 2.4)
    eh = (1 - abs(t) ** 3.0) ** (1 / 3.0)
    return A * ea, H * eh


MOUSE_TS = [-0.996, -0.975, -0.92, -0.8, -0.55, -0.25, 0.05, 0.3, 0.55, 0.75, 0.88, 0.96, 0.99, 0.998]


def _mouse_loft(sx, sy, sz):
    Lh = X9["l"] / 2
    wires = [_mouse_section(t * Lh * sz, *[v * s for v, s in zip(_mouse_dims(t), (sx, sy))]) for t in MOUSE_TS]
    return cq.Solid.makeLoft(wires, False)


@lru_cache(None)
def x9_local():
    """Lofted ambidextrous shell sized exactly to 59 x 101 x 34 (section scale iterated, no geometry scaling)."""
    W, L, H = X9["w"], X9["l"], X9["h"]
    sx = sy = sz = 1.0
    for _ in range(4):
        x0, y0, z0, x1, y1, z1 = tight_bbox(_mouse_loft(sx, sy, sz))
        sx *= W / (x1 - x0)
        sy *= H / (y1 - y0)
        sz *= L / (z1 - z0)
    s = _mouse_loft(sx, sy, sz)
    x0, y0, z0, x1, y1, z1 = tight_bbox(s)
    s = single(s.translate(Vector(-(x0 + x1) / 2, -y0, -(z0 + z1) / 2)))
    # scroll wheel slot + wheel
    slot = prism_y(-4.0, 4.0, -36, -14, 18, 60, 1.5)
    s = cut(s, slot)
    return s


def x9_wheel_local():
    w = cyl_x(27.0, -25.0, 8.5, -3.0, 3.0)
    return fillet(w, 1.0, w.Edges(), "wheel")


# =============================================================================
# small purchased bodies (local: min corner at the origin unless noted; x = length, y = height, z = depth)
# =============================================================================

def anker313_local():
    """Anker 313 pad A2503, centred on x/z, y 0..11.2; micro-USB on the -x side."""
    a = ANKER313
    s = prism_y(-a["w"] / 2, a["w"] / 2, -a["d"] / 2, a["d"] / 2, 0, a["h"], a["r"])
    s = fillet(s, 3.0, edges_where(s, on_plane("y", a["h"])), "anker top")
    return s


def ud6950pdh_local():
    """Plugable UD-6950PDH, x 225 (length), z 85 (rear face at z = 0, front at +85), y 24.5."""
    d = DOCK_UD6950PDH
    s = prism_y(0, d["w"], 0, d["d"], 0, d["h"], 4.0)
    ports = [box(20 + i * 22, 33 + i * 22, 6, 18, -0.01, 1.5) for i in range(6)]   # rear row (host, video, DC)
    front = [box(30 + i * 20, 43 + i * 20, 8, 15, d["d"] - 1.5, d["d"] + 0.01) for i in range(6)]
    return cut(s, *ports, *front)


def brick_local():
    b = DOCK_BRICK
    s = prism_y(0, b["w"], 0, b["d"], 0, b["h"], 6.0)
    return fillet(s, 3.0, edges_where(s, on_plane("y", b["h"])), "brick top")


def strip_local():
    """Tripp Lite PS2406RA08B lying on edge: x 609.6 long, y 40.9 tall (outlet face vertical), z 31.8 deep.
    Outlet face at z = 0 (outlets point -z), back (clip side) at z = 31.8."""
    S = STRIP
    s = box(0, S["len"], 0, S["face_w"], 0, S["depth"])
    s = fillet(s, 3.0, edges_where(s, lambda c, bb, e: (bb.xmax - bb.xmin) > 100), "strip edges")
    n = S["outlets"]
    pitch = (S["len"] - 80) / (n - 1)
    outs = [box(40 + i * pitch - 14, 40 + i * pitch + 14, 8, 33, -0.01, 1.2) for i in range(n)]
    s = cut(s, *outs)
    sw = box(S["len"] - 30, S["len"] - 12, 12, 29, -3.0, 0.5)       # lighted switch + clear cover
    cord = cyl_x(S["face_w"] / 2, S["depth"] / 2, 5.25, S["len"], S["len"] + 30)
    return fuse(s, sw, cord)


def gan_local():
    """Monoprice 46820, x 98.81, z 76.31, y 23.1 (incl. 1 mm feet).  Ports on the +x face (rotated in the bay)."""
    g = GAN
    s = prism_y(0, g["w"], 0, g["d"], 1.0, g["h"], 5.0)
    feet = [cyl_y(x, z, 4.0, 0, 1.2) for x in (17.1, g["w"] - 17.1) for z in (25.1, g["d"] - 25.1)]
    return fuse(s, *feet)


def newnex_head_local():
    """Newnex U4T1C01CR5P010 side-exit head.  Origin: plug centre on the overmold face; plug points +y;
    cable leaves along -z.  Overmold face y = 0; head down to y = -15.51."""
    N = NEWNEX
    pt, pl, pw = N["plug"]
    ht, hd, hw = N["head"]
    plug = stadium_y(0, 0, pw, pt, 0.0, pl, along="z")
    z1 = N["head"][2] / 2
    head = box(-ht / 2, ht / 2, -hd, 0.0, -z1, z1)
    z2a, z2b = -6.2, -N["zone2_end"]
    zone2 = box(-ht / 2, ht / 2, -hd, -N["zone2_step"], z2b, z2a)
    ca = -N["cable_axis_from_face"]
    relief = box(-N["relief"] / 2, N["relief"] / 2, ca - N["relief"] / 2, ca + N["relief"] / 2, -N["relief_end"], z2b + 0.5)
    cable = cyl_z(0, ca, N["cable_od"] / 2, -N["relief_end"] - 25, -N["relief_end"] + 0.5)   # first 25 mm only
    return fuse(head, zone2, relief, plug, cable)


def led_channel_local(length):
    """SuperLightingLED QSG-0505: 5 x 5 aluminium profile, x = length, centred on y/z, opal face +y."""
    return box(0, length, -2.5, 2.5, -2.5, 2.5)


def dimmer_local():
    """CONSC-DIM-03 inline knob dimmer, x 61 (knob at +x end), y 32 (incl. knob boss), z 33."""
    d = DIMMER
    s = prism_x(0, d["w"], 0, d["h"] - 6, 0, d["l"], 4.0)
    knob = cyl_x((d["h"] - 6) / 2, d["w"] / 2, d["knob_d"] / 2, d["l"], d["l"] + d["knob_h"])
    return fuse(s, knob)


def bumpon_local():
    """3M SJ5023, centred, y 0..7.6 (tapered square, 20.6 at the base)."""
    b = BUMPON_SJ5023
    return cq.Solid.makeLoft([
        cq.Wire.makePolygon([Vector(-b["w"] / 2, 0, -b["w"] / 2), Vector(b["w"] / 2, 0, -b["w"] / 2),
                             Vector(b["w"] / 2, 0, b["w"] / 2), Vector(-b["w"] / 2, 0, b["w"] / 2)], close=True),
        cq.Wire.makePolygon([Vector(-b["top"] / 2, b["h"], -b["top"] / 2), Vector(b["top"] / 2, b["h"], -b["top"] / 2),
                             Vector(b["top"] / 2, b["h"], b["top"] / 2), Vector(-b["top"] / 2, b["h"], b["top"] / 2)],
                            close=True)], True)


def ir_2167_local():
    """Adafruit 2167 half (emitter or receiver): 20 (z) x 10 (y) x 8 (x); LED axis normal to the 20 x 10 face (+x),
    5 mm from one end.  Origin at the face centre."""
    I = IR_2167
    s = box(-I["t"], 0, -I["w"] / 2, I["w"] / 2, -I["l"] / 2, I["l"] / 2)
    led = cyl_x(0, -I["l"] / 2 + I["led_from_end"], 1.5, -0.01, 1.5)
    return fuse(s, led)
