"""Night Array kit -- dock group: the printed latch-free cradle on the right wing (split for the bed), the oxblood
panels, the seated light, the Newnex side-exit head on a floating printed carriage, the universal slot insert and the
IR break-beam; plus the docked laptop.

OWNER (next phase): DOCK engineer (with kit/insert/).  COARSE starting point: the concept's swept cradle stretched to
z +-150 so 16-inch laptops fit (slot 288 long), a 26 mm raw slot that the insert narrows to laptop + 1.5 mm,
the plug overmold face 0.4 mm below the landing plane, the carriage and its flange under the slot floor, the
break-beam at y 28.5 / z +60.  Interfaces: common.LAYOUT['dock'], purchased.NEWNEX / IR_2167 / LAPTOP.
"""

from __future__ import annotations

from functools import lru_cache

import cadquery as cq
from cadquery import Vector

from .common import (LAYOUT, PartDef, PrintSpec, box, chamfer, compound, cut, cyl_x, cyl_y, edges_where, fillet,
                     fuse, near, on_plane, prism_y, prism_z, single)
from . import purchased as P

K = {
    "x": LAYOUT["dock"]["x"], "z": LAYOUT["dock"]["z"],
    "h_back": 120.0, "h_front": 60.0,
    "profile_pts": [[-150.0, 120.0], [-110.8, 120.0], [-66.9, 104.0], [-13.8, 80.0], [46.2, 64.5], [90.0, 60.0],
                    [150.0, 60.0]],
    "plan_r": 12.0, "edge_fillet": 4.0,
    "slot": {"x": [709.0, 735.0], "z": [-144.0, 144.0], "floor_y": 24.0, "r": 3.0, "lead_in": 4.0},
    "landing_y": 24.0, "overmold_below": 0.4,          # overmold face 0.4 below the landing plane (USB-C Fig 3-80)
    "wall": 3.0, "cavity_y": [2.5, 21.0],
    "panel_t": 2.0, "panel_inset": 7.0,
    "front_panel": {"x": [657.0, 756.0], "y": [7.0, 53.0]},
    "led": {"x": 722.0, "w": 21.0, "h": 2.0, "y": 46.0, "depth": 1.0},
    "plug_z": -60.0,
    "carriage": {"wall": 1.6, "y0": 6.5, "flange": [40.0, 50.0, 2.2], "float": 1.5},
    "insert": {"z": [-120.0, 120.0], "h": 36.0, "clear": 0.75},
    "ir": {"y": 28.5, "z": 60.0},
    "split_z": 0.0,
}
SL = K["slot"]
AXIS_X = LAYOUT["dock"]["slot_axis_x"]


def _profile_wp(x1, inset=0.0):
    pts = K["profile_pts"]
    z0, z1 = K["z"]
    wp = cq.Workplane("ZY", origin=(x1, 0, 0))
    pf = list(reversed(pts))
    w = (wp.moveTo(z0, 0).lineTo(z1, 0).lineTo(z1, K["h_front"]).lineTo(pf[1][0], pf[1][1])
         .spline([tuple(p) for p in pf[2:-1]], tangents=[(-1, 0), (-1, 0)], includeCurrent=True)
         .lineTo(z0, K["h_back"]).close())
    if inset:
        w = w.offset2D(-inset, "arc")
    return w


def _prism(x0, x1, inset=0.0):
    w = _profile_wp(x1, inset)
    if not inset:
        return w.extrude(x1 - x0).val()
    from OCP.BRepBuilderAPI import BRepBuilderAPI_NurbsConvert
    nurbs = cq.Wire(BRepBuilderAPI_NurbsConvert(w.val().wrapped, True).Shape())
    return cq.Solid.extrudeLinear(cq.Face.makeFromWires(nurbs), Vector(-(x1 - x0), 0, 0))


def plug_origin():
    """Plug centre on the overmold face."""
    return (AXIS_X, K["landing_y"] - K["overmold_below"], K["plug_z"])


@lru_cache(None)
def _cradle_solid():
    x0, x1 = K["x"]
    z0, z1 = K["z"]
    s = _prism(x0, x1)
    es = edges_where(s, lambda c, bb, e: near(c.x, x1, 0.01) and (bb.ymax - bb.ymin) > 30 and (bb.zmax - bb.zmin) < 0.01)
    s = fillet(s, K["plan_r"], es, "dock plan corners")
    es = edges_where(s, lambda c, bb, e: bb.ymin > 1.0 and not (near(c.x, x0, 0.01) and c.y < 40))
    s = fillet(s, K["edge_fillet"], es, "dock edges")
    slot = prism_y(SL["x"][0], SL["x"][1], SL["z"][0], SL["z"][1], SL["floor_y"], 200, SL["r"])
    s = cut(s, slot)
    sx0, sx1 = SL["x"]
    lead = edges_where(s, lambda c, bb, e: bb.ymin > SL["floor_y"] + 20 and sx0 - 0.1 <= bb.xmin and bb.xmax <= sx1 + 0.1
                       and (bb.xmax - bb.xmin > 0.5 or bb.zmax - bb.zmin > 0.5 or near(c.x, sx0, 0.1) or near(c.x, sx1, 0.1))
                       and (bb.ymax - bb.ymin) < 70)
    s = chamfer(s, SL["lead_in"], lead, "slot lead-in")
    cy0, cy1 = K["cavity_y"]
    wl = K["wall"]
    cav = [box(x0 + wl, x1 - wl - 3, cy0, cy1, z0 + wl, z1 - 6)]
    cav.append(single(_prism(x0 + wl, sx0 - 6, 4.0).intersect(box(0, 2000, cy0, 500, z0 + wl, z1 - 6))))
    cav.append(single(_prism(sx1 + 6, x1 - 6, 4.0).intersect(box(0, 2000, cy0, 500, z0 + wl, z1 - 6))))
    s = cut(s, fuse(*cav))
    # floor hole for the carriage boss (+- float), chamfered on top
    px, py, pz = plug_origin()
    fl = K["carriage"]["float"]
    s = cut(s, prism_y(px - 6.65, px + 6.65, pz - 9.6, pz + 9.6, cy1 - 1, SL["floor_y"] + 1, 2.0))
    # relief under the floor over the head's zone 2 + strain relief (verifier: >= 1.5 mm, or the carriage rock jams)
    N = P.NEWNEX
    s = cut(s, box(px - N["relief"] / 2 - fl - 1.0, px + N["relief"] / 2 + fl + 1.0, cy1 - 1, cy1 + 1.5,
                   pz - N["relief_end"] - fl - 2.0, pz - 6.0))
    # break-beam pockets in both cheeks (IR-opaque lining: black PETG / foil)
    ir = K["ir"]
    I = P.IR_2167
    for xa, xb in ((sx0 - 3 - I["pocket"][2], sx0 - 3), (sx1 + 3, sx1 + 3 + I["pocket"][2])):
        s = cut(s, box(xa, xb, ir["y"] - I["pocket"][1] / 2, ir["y"] + I["pocket"][1] / 2, ir["z"] - I["pocket"][0] / 2,
                       ir["z"] + I["pocket"][0] / 2))
    s = cut(s, cyl_x(ir["y"], ir["z"] - 5.0, I["hole_d"] / 2, sx0 - 4, sx1 + 4))
    # oxblood panel recesses + seated-light pocket
    s = cut(s, _side_panel(x1 - K["panel_t"], x1 + 1), _front_panel(z1 - K["panel_t"], z1 + 1))
    return s


@lru_cache(None)
def dock_cradle():
    s = _cradle_solid()
    sz = K["split_z"]
    return compound([single(s.intersect(box(0, 2000, -10, 500, -500, sz))),
                     single(s.intersect(box(0, 2000, -10, 500, sz, 500)))])


def _side_panel(xa, xb):
    return single(_prism(xa, xb, K["panel_inset"]).intersect(box(0, 2000, K["panel_inset"], 500, -500, 500)))


def _front_panel(za, zb):
    fp = K["front_panel"]
    return prism_z(fp["x"][0], fp["x"][1], fp["y"][0], fp["y"][1], za, zb, 3.0)


def _led_box(za, zb):
    L = K["led"]
    return prism_z(L["x"] - L["w"] / 2, L["x"] + L["w"] / 2, L["y"], L["y"] + L["h"], za, zb, 0.9)


@lru_cache(None)
def dock_panels():
    x1, z1 = K["x"][1], K["z"][1]
    side = single(_side_panel(x1 - K["panel_t"], x1))
    lo = single(side.intersect(box(0, 2000, -10, 500, -500, K["split_z"])))
    hi = single(side.intersect(box(0, 2000, -10, 500, K["split_z"], 500)))
    front = cut(_front_panel(z1 - K["panel_t"], z1), _led_box(z1 - K["led"]["depth"], z1 + 1))
    return compound([lo, hi, front])


@lru_cache(None)
def dock_led():
    z1 = K["z"][1]
    return _led_box(z1 - K["led"]["depth"], z1)


@lru_cache(None)
def dock_connector():
    px, py, pz = plug_origin()
    return P.newnex_head_local().translate(Vector(px, py, pz))


@lru_cache(None)
def dock_carriage():
    """Floating carriage: block gripping the Newnex head below the slot floor + flange under the floor (retains it
    against the 8-20 N extraction pull).  Springs (4 x 9657K614 at 45 deg) are the dock engineer's."""
    px, py, pz = plug_origin()
    c = K["carriage"]
    N = P.NEWNEX
    wl = c["wall"]
    ht = N["head"][0]
    cy1 = K["cavity_y"][1]
    blk = box(px - ht / 2 - wl, px + ht / 2 + wl, c["y0"], cy1 - 0.3, pz - N["zone2_end"] - wl, pz + N["head"][2] / 2 + wl)
    fx, fz, ft = c["flange"]
    fl = box(px - fx / 2, px + fx / 2, cy1 - 0.3 - ft, cy1 - 0.3, pz - fz / 2 - 6.0, pz + fz / 2 - 6.0)
    s = fuse(blk, fl)
    return cut(s, dock_connector(), box(px - 4.3, px + 4.3, py - N["cable_axis_from_face"] - 4.3,
                                        py - N["cable_axis_from_face"] + 4.3, pz - 60, pz - N["zone2_end"] + 0.5))


@lru_cache(None)
def dock_insert():
    """Universal slot insert for the 15 mm generic laptop: two walls (laptop + 0.75 per side) joined at the hinge end;
    IR beam holes coaxial with the cradle's; open over the plug."""
    t = P.LAPTOP["t"]
    ins = K["insert"]
    sx0, sx1 = SL["x"]
    y0 = SL["floor_y"]
    y1 = y0 + ins["h"]
    z0, z1 = ins["z"]
    gap0, gap1 = AXIS_X - t / 2 - ins["clear"], AXIS_X + t / 2 + ins["clear"]
    w0 = box(sx0 + 0.2, gap0, y0, y1, z0, z1)
    w1 = box(gap1, sx1 - 0.2, y0, y1, z0, z1)
    bridge = box(sx0 + 0.2, sx1 - 0.2, y0, y0 + 4.0, z0, z0 + 6.0)
    s = fuse(w0, w1, bridge)
    ir = K["ir"]
    s = cut(s, cyl_x(ir["y"], ir["z"] - 5.0, 1.75, sx0 - 1, sx1 + 1))
    return s


@lru_cache(None)
def ir_beam():
    I = P.IR_2167
    sx0, sx1 = SL["x"]
    ir = K["ir"]
    emit = P.ir_2167_local().translate(Vector(sx0 - 3.3, ir["y"], ir["z"]))
    recv = P.ir_2167_local().mirror("YZ").translate(Vector(sx1 + 3.3, ir["y"], ir["z"]))
    return compound([emit, recv])


@lru_cache(None)
def laptop_body():
    t = P.LAPTOP["t"]
    return P.laptop_body(AXIS_X - t / 2, K["landing_y"], -106.0, K["plug_z"])


PARTS = [
    PartDef("dock_cradle", "dock", "Dock cradle (2 pieces)", "titanium", "printed", dock_cradle,
            print=PrintSpec("petg_titanium", down="-x", supports="tree, slot lead-in", infill=0.2,
                            note="inner (-x) face down"), owner="dock", split="z 0"),
    PartDef("dock_panels", "dock", "Oxblood panels (3)", "oxblood", "printed", dock_panels,
            print=PrintSpec("pla_oxblood", down="-x", infill=1.0), owner="dock", split="side panel at z 0"),
    PartDef("dock_led", "dock", "Seated light (light pipe)", "amber_led", "printed", dock_led,
            print=PrintSpec("petg_clear", down="+z", infill=1.0), owner="dock"),
    PartDef("dock_connector", "dock", "Newnex USB4 side-exit head", "plastic_black", "purchased", dock_connector,
            bom="cable-newnex-u4-cr5", mass_g=45.0, mass_note="1 m cable; head + cradle-side length", owner="dock"),
    PartDef("dock_carriage", "dock", "Floating plug carriage", "graphite", "printed", dock_carriage, internal=True,
            print=PrintSpec("petg_cf_graphite", down="-y", infill=1.0), owner="dock"),
    PartDef("dock_insert", "dock", "Universal slot insert (15 mm laptop)", "graphite", "printed", dock_insert,
            print=PrintSpec("petg_black", down="-x", infill=0.4, note="IR-opaque black"), owner="dock"),
    PartDef("ir_beam", "dock", "IR break-beam (Adafruit 2167)", "plastic_black", "purchased", ir_beam, internal=True,
            bom="ir-beam-2167", mass_g=6.0, owner="dock"),
    PartDef("laptop_body", "laptop", "Laptop (generic 14 in, 15 mm)", "laptop_alu", "purchased", laptop_body,
            mass_g=P.LAPTOP["mass_kg"] * 1000, mass_note="owner's laptop, not in the BOM", owner="dock"),
]
