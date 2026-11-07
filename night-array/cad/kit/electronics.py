"""Night Array kit -- electronics: bay envelopes, Qi keep-outs, placement of the purchased electronics and the
main cable routes.  FROZEN INTERFACE (owner: CAD architect; the ELECTRICAL engineer documents wiring against it).

BAYS are the contract with the BASE engineer: each is an axis-aligned box (x0, x1, y0, y1, z0, z1) in app mm that the
printed base must leave EMPTY (the part plus its clearances).  KEEPOUTS are volumes in which a class of material
must not appear.  The part solids are placed inside their bays.
"""

from __future__ import annotations

from functools import lru_cache

import cadquery as cq
from cadquery import Vector

from .common import (LAYOUT, PartDef, box, compound, cyl_axis, cyl_y, fuse, prism_y, single)
from . import purchased as P

Q = LAYOUT["qi"]
FLOOR_TOP = 4.5          # bay floors (printed hatch tops): electronics stand on 0.5 mm ribs above y = 4.0

# =============================================================================
# placements (app mm)
# =============================================================================

STRIP_X0 = -P.STRIP["len"] / 2                      # strip centred on the seam: x -304.8 .. 304.8
STRIP_FACE_Z = -87.0                                # outlet face (outlets point -z, toward the posts / neck)
GAN_AT = (-605.0, 8.0)                              # min-x, min-z corner (rotated: 76.31 along x, 98.81 along z)
DOCK_AT = (420.0, 20.0)                             # min-x, rear face z
BRICK_AT = (420.0, -158.0)
DIMMER_KNOB = (-640.0, 25.0, -75.0)                 # knob axis exits the left end wall here (x, y, z)

BAYS = {
    # name: (x0, x1, y0, y1, z0, z1), what, clearances included
    "strip": ((STRIP_X0 - 1.0, -STRIP_X0 + 1.0, FLOOR_TOP, FLOOR_TOP + P.STRIP["face_w"] + 1.5,
               STRIP_FACE_Z, STRIP_FACE_Z + P.STRIP["depth"] + P.STRIP["clip"] + 0.5),
              "Tripp Lite PS2406RA08B on edge + 6 mm clips (M4 inserts); outlet face toward -z"),
    "strip_plug_zone": ((STRIP_X0 - 1.0, -STRIP_X0 + 1.0, FLOOR_TOP, FLOOR_TOP + P.STRIP["face_w"] + 1.5,
                         STRIP_FACE_Z - P.STRIP["plug_zone"], STRIP_FACE_Z),
                        "30 mm right-angle plug zone in front of the outlet face (continuous: outlet layout TBC)"),
    "strip_cord_bend_l": ((STRIP_X0 - P.STRIP["cord_bend"], STRIP_X0 - 1.0, 14.5, FLOOR_TOP + P.STRIP["face_w"] + 1.5,
                           STRIP_FACE_Z - 5, STRIP_FACE_Z + P.STRIP["depth"] + 5),
                          "51 mm cord bend reserve (cord end not yet known: both ends reserved, above the steel)"),
    "strip_cord_bend_r": ((-STRIP_X0 + 1.0, -STRIP_X0 + P.STRIP["cord_bend"], 14.5, FLOOR_TOP + P.STRIP["face_w"] + 1.5,
                           STRIP_FACE_Z - 5, STRIP_FACE_Z + P.STRIP["depth"] + 5), "as left"),
    "gan": ((GAN_AT[0] - 30.0, GAN_AT[0] + P.GAN["d"] + 35.0, FLOOR_TOP, FLOOR_TOP + P.GAN["h"] + 5.0,
             GAN_AT[1], GAN_AT[1] + P.GAN["w"]),
            "Monoprice 46820, ports +x (35 mm right-angle USB-C room), C8 inlet -x (30 mm), 5 mm air above"),
    "dock_box": ((DOCK_AT[0], DOCK_AT[0] + P.DOCK_UD6950PDH["w"], FLOOR_TOP, FLOOR_TOP + P.DOCK_UD6950PDH["h"] + 4.0,
                  DOCK_AT[1], DOCK_AT[1] + P.DOCK_UD6950PDH["d"] + 22.0),
                 "Plugable UD-6950PDH; front ports +z with 22 mm for the two receiver dongles"),
    "dock_cables": ((DOCK_AT[0], DOCK_AT[0] + P.DOCK_UD6950PDH["w"], FLOOR_TOP, 23.0,
                     DOCK_AT[1] - P.DOCK_UD6950PDH["rear_clear"], DOCK_AT[1]),
                    ">= 70 mm behind the rear face (host USB-C, 2 x video, DC in); passes under the middle rail"),
    "dock_brick": ((BRICK_AT[0], BRICK_AT[0] + P.DOCK_BRICK["bay"][0], FLOOR_TOP, FLOOR_TOP + P.DOCK_BRICK["bay"][2],
                    BRICK_AT[1], BRICK_AT[1] + P.DOCK_BRICK["bay"][1]),
                   "130 W brick reservation 160 x 80 x 35 (size unpublished: measure); C13 cord to the strip"),
    "lv_hub": ((-625.0, -430.0, FLOOR_TOP, 40.0, -152.0, -56.0),
               "LV hub: WAGO 221 carrier, HUSB238 5807, 6032 + jack, Pololu 5 V, opto board, dimmer"),
    "chase_neck": ((-110.0, 110.0, 4.5, 50.0, -160.0, -88.0),
                   "cable chase from the base into the neck (between and around the posts)"),
    "kb_pad": ((Q["kb_coil"][0] - 50 - Q["kb_adjust"][0], Q["kb_coil"][0] + 50 + Q["kb_adjust"][0],
                Q["kb_floor_y"] - Q["floor_over_coil"] - P.ANKER313["h"] - 3.0, Q["kb_floor_y"] - Q["floor_over_coil"],
                Q["kb_coil"][1] - 50 - Q["kb_adjust"][1], Q["kb_coil"][1] + 50 + Q["kb_adjust"][1]),
               "Anker 313 + 3 mm slotted carrier, full travel (x 35-60 / z 35-55 mm from the keyboard's left/rear)"),
    "mouse_pad": ((Q["mouse_coil"][0] - 50 - Q["mouse_adjust"][0], Q["mouse_coil"][0] + 50 + Q["mouse_adjust"][0],
                   Q["mouse_floor_y"] - Q["floor_over_coil"] - P.ANKER313["h"] - 3.0,
                   Q["mouse_floor_y"] - Q["floor_over_coil"],
                   Q["mouse_coil"][1] - 50 - Q["mouse_adjust"][1], Q["mouse_coil"][1] + 50 + Q["mouse_adjust"][1]),
                  "Anker 313 + carrier, +-10 mm travel"),
}


def _keepout(pad, adjust, floor_y, grow):
    cx, cz = pad
    ax, az = adjust
    return (cx - 50 - ax - grow, cx + 50 + ax + grow, 0.0, floor_y + Q["keepout_above"],
            cz - 50 - az - grow, cz + 50 + az + grow)


KEEPOUTS = {
    # name: (box, classes it excludes)
    "qi_kb_metal": (_keepout(Q["kb_coil"], Q["kb_adjust"], Q["kb_floor_y"], Q["keepout_metal"]),
                    "no metal, magnets, LED PCBs or screws (except the pad itself)"),
    "qi_kb_steel": (_keepout(Q["kb_coil"], Q["kb_adjust"], Q["kb_floor_y"], Q["keepout_steel"]), "no steel"),
    "qi_mouse_metal": (_keepout(Q["mouse_coil"], Q["mouse_adjust"], Q["mouse_floor_y"], Q["keepout_metal"]),
                       "no metal, magnets, LED PCBs or screws"),
    "qi_mouse_steel": (_keepout(Q["mouse_coil"], Q["mouse_adjust"], Q["mouse_floor_y"], Q["keepout_steel"]), "no steel"),
}

# cable routes: polylines (app mm) with a nominal bundle diameter, for length estimates and the coarse model
ROUTES = {
    "mains_in": {"pts": [(330.0, 25.0, -70.0), (330.0, 25.0, -150.0), (330.0, 25.0, -168.0)], "d": 10.5,
                 "what": "strip cord -> rear wall strain relief (the only mains cord leaving the station)"},
    "monitor_ac": {"pts": [(-60.0, 25.0, -100.0), (0.0, 30.0, -100.0), (0.0, 150.0, -100.0), (0.0, 200.0, -140.0)],
                   "d": 12.0, "what": "2 x right-angle C13 cords: strip -> neck chase -> shroud -> monitor C14 inlets"},
    "video": {"pts": [(440.0, 12.0, 15.0), (440.0, 12.0, -40.0), (60.0, 30.0, -40.0), (0.0, 40.0, -100.0),
                      (0.0, 200.0, -110.0)], "d": 9.0,
              "what": "2 x HDMI/DP from the dock box rear -> under the middle rail -> neck chase -> monitors"},
    "dock_host": {"pts": [(722.0, 14.4, -60.0), (722.0, 14.4, -120.0), (660.0, 14.0, -120.0), (600.0, 12.0, 10.0)],
                  "d": 4.8, "what": "Newnex USB4 cable: cradle carriage -> base -> dock box host port (coil the spare)"},
    "lv_12v": {"pts": [(-520.0, 20.0, -90.0), (-450.0, 12.0, 120.0), (0.0, 6.0, 150.0)], "d": 5.0,
               "what": "dimmed 12 V: LV hub -> under-glow halves (front) / neck bar (via the chase)"},
}

# =============================================================================
# placed parts
# =============================================================================


@lru_cache(None)
def power_strip():
    return P.strip_local().translate(Vector(STRIP_X0, FLOOR_TOP, STRIP_FACE_Z))


@lru_cache(None)
def gan_charger():
    g = P.gan_local()   # x 98.81, z 76.31 -> rotate so the long faces run along z: ports face +x
    g = g.rotate(Vector(0, 0, 0), Vector(0, 1, 0), 90)       # x -> -z, z -> x
    x0, y0, z0, x1, y1, z1 = g.BoundingBox().xmin, 0, g.BoundingBox().zmin, 0, 0, 0
    return g.translate(Vector(GAN_AT[0] - x0, FLOOR_TOP, GAN_AT[1] - z0))


@lru_cache(None)
def dock_box():
    return P.ud6950pdh_local().translate(Vector(DOCK_AT[0], FLOOR_TOP, DOCK_AT[1]))


@lru_cache(None)
def dock_brick():
    b = P.DOCK_BRICK
    return P.brick_local().translate(Vector(BRICK_AT[0] + 5.0, FLOOR_TOP, BRICK_AT[1] + 5.0))


@lru_cache(None)
def qi_pads():
    a = P.anker313_local()
    kb = a.translate(Vector(Q["kb_coil"][0], Q["kb_floor_y"] - Q["floor_over_coil"] - P.ANKER313["h"], Q["kb_coil"][1]))
    ms = a.translate(Vector(Q["mouse_coil"][0], Q["mouse_floor_y"] - Q["floor_over_coil"] - P.ANKER313["h"],
                            Q["mouse_coil"][1]))
    return compound([kb, ms])


@lru_cache(None)
def lv_hub():
    """WAGO carrier + boards + dimmer as coarse envelopes inside the lv_hub bay (rear-left); the dimmer's knob comes
    out through the left end wall (22 mm hole) at DIMMER_KNOB."""
    y0 = FLOOR_TOP
    parts = [box(-565.0, -465.0, y0, y0 + 3, -150.0, -90.0)]                         # carrier plate 100 x 60
    for i, k in enumerate(("221-415", "221-415", "221-413", "221-413", "221-412")):
        w, h, d = P.WAGO[k]
        parts.append(box(-560.0 + i * 18, -560.0 + i * 18 + h, y0 + 3, y0 + 3 + d, -145.0, -145.0 + w))
    w, h, d = P.HUSB238_5807
    parts.append(box(-560.0, -560.0 + w, y0 + 3, y0 + 3 + h, -112.0, -112.0 + d))
    w, h, d = P.POLOLU_D36V6F5
    parts.append(box(-530.0, -530.0 + w, y0 + 3, y0 + 3 + h, -110.0, -110.0 + d))
    w, h, d = P.OPTO_BOARD
    parts.append(box(-510.0, -510.0 + w, y0 + 3, y0 + 3 + h, -112.0, -112.0 + d))
    w, h, d = P.PD_6032
    parts.append(box(-475.0, -475.0 + w, y0, y0 + h, -150.0, -150.0 + d))
    w, h, d = P.JACK_368
    parts.append(box(-475.0, -475.0 + w, y0, y0 + h, -118.0, -118.0 + d))
    dm = P.dimmer_local().mirror("YZ")          # knob now at -x
    bb = dm.BoundingBox()
    kx, ky, kz = DIMMER_KNOB
    dm = dm.translate(Vector(kx + 3.0 - bb.xmin, ky - (P.DIMMER["h"] - 6) / 2, kz - P.DIMMER["w"] / 2))
    parts.append(dm)
    return compound(parts)


def route_solid(name):
    r = ROUTES[name]
    pts = r["pts"]
    segs = [cyl_axis(a, b, r["d"] / 2) for a, b in zip(pts, pts[1:])]
    return compound(segs)


def route_length(name):
    import math
    pts = ROUTES[name]["pts"]
    return sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))


def bay_solid(name):
    x0, x1, y0, y1, z0, z1 = BAYS[name][0]
    return box(x0, x1, y0, y1, z0, z1)


def keepout_solid(name):
    x0, x1, y0, y1, z0, z1 = KEEPOUTS[name][0]
    return box(x0, x1, y0, y1, z0, z1)


# =============================================================================
# registry
# =============================================================================

PARTS = [
    PartDef("power_strip", "electronics", "Power strip (Tripp Lite PS2406RA08B)", "aluminium", "purchased", power_strip,
            internal=True, bom="strip-ps2406ra08b", mass_g=P.STRIP["mass_kg"] * 1000),
    PartDef("gan_charger", "electronics", "GaN charger (Monoprice 46820)", "plastic_black", "purchased", gan_charger,
            internal=True, bom="gan-monoprice-46820", mass_g=P.GAN["mass_kg"] * 1000),
    PartDef("dock_box", "electronics", "Dock (Plugable UD-6950PDH)", "aluminium", "purchased", dock_box,
            internal=True, bom="dock-ud6950pdh", mass_g=P.DOCK_UD6950PDH["mass_kg"] * 1000),
    PartDef("dock_brick", "electronics", "Dock power brick (130 W)", "plastic_black", "purchased", dock_brick,
            internal=True, bom="dock-ud6950pdh", mass_g=P.DOCK_BRICK["mass_kg"] * 1000,
            mass_note="included with the dock; size unpublished (bay is a reservation)"),
    PartDef("qi_pads", "electronics", "Qi pads (2 x Anker 313)", "plastic_black", "purchased", qi_pads,
            internal=True, bom="qi-anker-313", mass_g=2 * P.ANKER313["mass_kg"] * 1000),
    PartDef("lv_hub", "electronics", "LV hub (WAGO, PD triggers, 5 V, dimmer)", "pcb", "purchased", lv_hub,
            internal=True, bom="lv-hub", mass_g=120.0, mass_note="sum of the hub parts, estimated"),
]
