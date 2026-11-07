"""Night Array kit -- base group: the printed base (14 tiles on the steel), the keyboard and mouse locator
inserts, the bottom hatches, the under-glow and charge indicators; plus the stowed keyboard, mouse and the desk mat.

OWNER (next phase): BASE engineer.  This is the architect's COARSE starting point: the outer form (rim 50, deck 46,
rear plinth over the strip), the pockets at their real floors, the open-bottom cavity that leaves every bay and the
steel clear, and the tiling with dowel holes.  The base engineer adds: tile-to-tile bosses (M3 inserts), anchors
onto the spine plate / rails, hatch bosses and magnets, ribs, vents (Anker 40 C max ambient), the pad carriers,
reveals, the K3 insert's Magic Tag relief, cable channels.  Interfaces: common.LAYOUT['base'|'qi'|'keyboard'|
'mouse'], electronics.BAYS / KEEPOUTS, structure (plate, bar, rails, posts).
"""

from __future__ import annotations

from functools import lru_cache

import cadquery as cq
from cadquery import Vector

from .common import (DOWEL, LAYOUT, Joint, PartDef, PrintSpec, TOL, box, compound, cut, edges_where, fillet, fuse,
                     near, on_plane, prism_y, single, split_solid)
from . import electronics as EL
from . import purchased as P
from . import structure as ST

B = LAYOUT["base"]
Q = LAYOUT["qi"]

BASE = {
    "top_fillet": 5.0,
    "pocket_wall": 2.0,
    "kb_insert": {"clear": 1.0, "wall": 2.0, "h": 13.0, "split_x": -90.0},     # device clearance, frame wall, height
    "mouse_insert": {"opening": [61.0, 103.0], "wall": 2.0, "h": 12.0},
    "undercut": {"x": [-565.0, 565.0], "y": [2.0, 10.0], "depth": 8.0},
    "glow": {"x": [-560.0, 560.0], "y": [4.0, 9.0], "z": [158.0, 163.0]},
    "indicator": {"seg": 20.83, "w": 2.0, "z": [132.4, 134.4], "depth": 1.0},   # on the pocket front lip
    "hatch_t": 2.0,
}


def kb_pocket():
    """(x0, x1, z0, z1) of the keyboard pocket (insert outer + print clearance)."""
    kx, kz = LAYOUT["keyboard"]["x"], LAYOUT["keyboard"]["z"]
    i = BASE["kb_insert"]
    g = i["clear"] + i["wall"] + TOL["print_clear"]
    return kx[0] - g, kx[1] + g, kz[0] - g, kz[1] + g


def mouse_pocket():
    mi = BASE["mouse_insert"]
    cx, cz = LAYOUT["mouse"]["c"]
    hw = mi["opening"][0] / 2 + mi["wall"] + TOL["print_clear"]
    hd = mi["opening"][1] / 2 + mi["wall"] + TOL["print_clear"]
    return cx - hw, cx + hw, cz - hd, cz + hd


# ----------------------------------------------------------------------------- the shell

def _deck_region(y0, y1):
    """Recessed deck: inside the rim, minus the rear plinth."""
    x0, x1 = B["x"]
    z0, z1 = B["z"]
    r = B["rim_w"]
    dk = prism_y(x0 + r, x1 - r, z0 + r, z1 - r, y0, y1, B["corner_r"] - r)
    px0, px1 = B["plinth_x"]
    return cut(dk, prism_y(px0, px1, z0 - 1, B["row_joint_z"], y0 - 1, y1 + 1, 10.0))


@lru_cache(None)
def _shell():
    x0, x1 = B["x"]
    z0, z1 = B["z"]
    H, sk = B["height"], B["skirt_y"]
    s = prism_y(x0, x1, z0, z1, sk, H, B["corner_r"])
    s = fillet(s, BASE["top_fillet"], edges_where(s, on_plane("y", H)), "base top")
    dk = _deck_region(B["deck_y"], H + 5)
    dk = fillet(dk, 2.0, edges_where(dk, on_plane("y", B["deck_y"])), "deck fillet")
    s = cut(s, dk)
    # pockets
    pk = []
    for (a, b, c, d), fy in ((kb_pocket(), Q["kb_floor_y"]), (mouse_pocket(), Q["mouse_floor_y"])):
        pk.append(prism_y(a, b, c, d, fy, H + 5, 6.0))
    s = cut(s, *pk)
    # Magic Tag plug relief on the keyboard pocket's left wall (the plug sits proud of the K3's left face)
    ka = kb_pocket()
    kz = LAYOUT["keyboard"]["z"]
    s = cut(s, prism_y(ka[0] - 4.5, ka[0] + 1.0, kz[0] + 12.0, kz[0] + 34.0, Q["kb_floor_y"], H + 5, 1.5))
    # open-bottom cavity: everything under the deck / plinth / rim skins, except the pocket walls and floors
    w, dt = B["wall"], B["deck_t"]
    cav = prism_y(x0 + w, x1 - w, z0 + w, z1 - w, sk - 1, H - dt, B["corner_r"] - w)
    cav = cut(cav, _deck_region(B["deck_y"] - dt, H + 5))     # deck skin stays
    keep = []
    pw = BASE["pocket_wall"]
    for (a, b, c, d), fy in ((kb_pocket(), Q["kb_floor_y"]), (mouse_pocket(), Q["mouse_floor_y"])):
        keep.append(prism_y(a - pw, b + pw, c - pw, d + pw, fy - Q["floor_over_coil"], H + 5, 6.0 + pw))
    keep.append(prism_y(ka[0] - 4.5 - pw, ka[0], kz[0] + 12.0 - pw, kz[0] + 34.0 + pw, Q["kb_floor_y"] - 1.0, H + 5, 1.5))
    cav = cut(cav, *keep)
    s = cut(s, cav)
    # under-glow undercut along the front bottom edge
    u = BASE["undercut"]
    s = cut(s, prism_y(u["x"][0], u["x"][1], z1 - u["depth"], z1 + 20, u["y"][0] - 1, u["y"][1], 3.0))
    # charge indicator windows (light pipes) in the deck in front of each pocket
    ind = BASE["indicator"]
    for cx in ((kb_pocket()[0] + kb_pocket()[1]) / 2, LAYOUT["mouse"]["c"][0]):
        s = cut(s, box(cx - ind["seg"] / 2, cx + ind["seg"] / 2, B["deck_y"] - ind["depth"] - 5, B["deck_y"] + 1,
                       ind["z"][0], ind["z"][1]))
    # cable chase into the neck through the plinth
    cx0, cx1, cy0, cy1, cz0, cz1 = EL.BAYS["chase_neck"][0]
    s = cut(s, box(cx0, cx1, cy0, H + 1, cz0, cz1))
    # recess for the graphite deck liner (flush with the deck)
    s = cut(s, _liner_fp(B["deck_y"] - 1.0, B["deck_y"] + 1.0))
    return s


def tile_joints():
    """The tiling grid: column cuts (both rows) + the row joint, with dowel points on each cut plane."""
    js = []
    zr = B["row_joint_z"]
    for x in B["tile_joints_x"]:
        js.append(Joint("x", x, [(B["height"] - 12.0, B["z"][0] + 20.0), (B["height"] - 12.0, B["z"][1] - 20.0)]))
    js.append(Joint("z", zr, [(x, B["height"] - 12.0) for x in (-560.0, -370.0, -200.0, 0.0, 235.0, 430.0, 575.0)]))
    return js


@lru_cache(None)
def base_tiles():
    return [s for nm, s in split_solid(_shell(), tile_joints(), "base", dowels=True)]


@lru_cache(None)
def base_shell():
    return compound(base_tiles())


def _liner_fp(y0, y1):
    """Deck liner footprint (inside the rim with a 3 mm titanium reveal, around the plinth, pockets, indicators)."""
    r = B["rim_w"] + 3.0
    x0, x1 = B["x"]
    z0, z1 = B["z"]
    f = prism_y(x0 + r, x1 - r, z0 + r, z1 - r, y0, y1, B["corner_r"] - r)
    px0, px1 = B["plinth_x"]
    holes = [prism_y(px0 - 3, px1 + 3, z0 - 1, B["row_joint_z"] + 3, y0 - 1, y1 + 1, 12.0)]
    for a, b, c, d in (kb_pocket(), mouse_pocket()):
        holes.append(prism_y(a - 3, b + 3, c - 3, d + 3, y0 - 1, y1 + 1, 9.0))
    ind = BASE["indicator"]
    holes.append(box(-2000, 2000, y0 - 1, y1 + 1, ind["z"][0] - 2.5, ind["z"][1] + 2.5))
    cx0, cx1, _, _, cz0, cz1 = EL.BAYS["chase_neck"][0]
    holes.append(box(cx0 - 3, cx1 + 3, y0 - 1, y1 + 1, cz0 - 3, cz1 + 3))
    return cut(f, *holes)


@lru_cache(None)
def deck_liner():
    """Graphite deck inlay, 1 mm, flush in a recess of the shell; split at the base tile joints."""
    f = _liner_fp(B["deck_y"] - 1.0, B["deck_y"])
    js = [Joint("x", x, []) for x in B["tile_joints_x"]] + [Joint("z", B["row_joint_z"], [])]
    return compound([p for nm, p in split_solid(f, js, "liner", dowels=False)])


# ----------------------------------------------------------------------------- inserts, hatches, lights

@lru_cache(None)
def kb_insert():
    """K3 Ultra locator frame: opening = keyboard + 1 mm, 2 mm walls, 13 tall; split at x = -90 (330 > 245)."""
    kx, kz = LAYOUT["keyboard"]["x"], LAYOUT["keyboard"]["z"]
    i = BASE["kb_insert"]
    fy = Q["kb_floor_y"]
    c, w = i["clear"], i["wall"]
    o = prism_y(kx[0] - c - w, kx[1] + c + w, kz[0] - c - w, kz[1] + c + w, fy, fy + i["h"], 6.0)
    o = cut(o, prism_y(kx[0] - c, kx[1] + c, kz[0] - c, kz[1] + c, fy - 1, fy + i["h"] + 1, 4.0))
    # Magic Tag relief at the left-rear (plug + folded flex)
    o = cut(o, box(kx[0] - c - w - 1, kx[0] + 1, fy - 1, fy + i["h"] + 1, kz[0] + 12, kz[0] + 34))
    sx = i["split_x"]
    return compound([single(o.intersect(box(-2000, sx, -10, 200, -500, 500))),
                     single(o.intersect(box(sx, 2000, -10, 200, -500, 500)))])


@lru_cache(None)
def mouse_insert():
    mi = BASE["mouse_insert"]
    cx, cz = LAYOUT["mouse"]["c"]
    fy = Q["mouse_floor_y"]
    hw, hd = mi["opening"][0] / 2, mi["opening"][1] / 2
    w = mi["wall"]
    o = prism_y(cx - hw - w, cx + hw + w, cz - hd - w, cz + hd + w, fy, fy + mi["h"], 8.0)
    return cut(o, prism_y(cx - hw, cx + hw, cz - hd, cz + hd, fy - 1, fy + mi["h"] + 1, 6.0))


@lru_cache(None)
def base_hatches():
    """Removable bottom hatches (M3 into inserts in the tiles; magnets optional), y 2..4: one per bay group."""
    t = BASE["hatch_t"]
    y0 = B["skirt_y"]
    out = []
    for name in ("strip", "gan", "lv_hub", "dock_box", "dock_brick", "kb_pad", "mouse_pad"):
        x0, x1, _, _, z0, z1 = EL.BAYS[name][0]
        if name == "strip":
            z0 = EL.BAYS["strip_plug_zone"][0][4]
        if name == "dock_box":
            z0 = EL.BAYS["dock_cables"][0][4]
        out.append(prism_y(x0 - 3, x1 + 3, z0 - 3, z1 + 3, y0, y0 + t, 4.0))
    # stay inside the shell walls and clear of the feet
    x0, x1 = B["x"]
    z0, z1 = B["z"]
    w = B["wall"] + TOL["print_clear"]
    inside = prism_y(x0 + w, x1 - w, z0 + w, z1 - w, 0, 50, B["corner_r"] - w)
    feet = [prism_y(x - 13, x + 13, z - 13, z + 13, -1, 20, 3.0) for x, z in ST.FEET_XZ]
    js = [Joint("x", x, []) for x in B["tile_joints_x"]]
    res = []
    for h in out:
        h = cut(single(h.intersect(inside)), *feet)
        x0_, _, _, x1_, _, _ = h.BoundingBox().xmin, 0, 0, h.BoundingBox().xmax, 0, 0
        if x1_ - x0_ > 245.0:
            res += [p for nm, p in split_solid(h, js, "hatch", dowels=False)]
        else:
            res.append(h)
    return compound(res)


@lru_cache(None)
def base_glow():
    g = BASE["glow"]
    return box(g["x"][0], g["x"][1], g["y"][0], g["y"][1], g["z"][0], g["z"][1])


def _indicator(cx):
    ind = BASE["indicator"]
    return box(cx - ind["seg"] / 2, cx + ind["seg"] / 2, B["deck_y"] - ind["depth"] - 5, B["deck_y"], ind["z"][0],
               ind["z"][1])


def kb_charge_led():
    a, b, _, _ = kb_pocket()
    return _indicator((a + b) / 2)


def mouse_charge_led():
    return _indicator(LAYOUT["mouse"]["c"][0])


# ----------------------------------------------------------------------------- devices (stow) + desk mat

def kb_origin():
    kx, kz = LAYOUT["keyboard"]["x"], LAYOUT["keyboard"]["z"]
    return Vector(kx[0], Q["kb_floor_y"], kz[0])


@lru_cache(None)
def keyboard_body():
    return P.k3u_body_local().translate(kb_origin())


@lru_cache(None)
def keyboard_keys():
    return P.k3u_keys_local().translate(kb_origin())


@lru_cache(None)
def keyboard_tag():
    return P.magic_tag_local().translate(kb_origin())


def mouse_origin():
    cx, cz = LAYOUT["mouse"]["c"]
    return Vector(cx, Q["mouse_floor_y"], cz)


@lru_cache(None)
def mouse_shell():
    return P.x9_local().translate(mouse_origin())


@lru_cache(None)
def mouse_wheel():
    return P.x9_wheel_local().translate(mouse_origin())


DESKMAT_C = (60.0, 390.0)


@lru_cache(None)
def deskmat():
    d = P.DESKMAT
    cx, cz = DESKMAT_C
    s = prism_y(cx - d["w"] / 2, cx + d["w"] / 2, cz - d["d"] / 2, cz + d["d"] / 2, 0, d["t"], d["r"])
    return fillet(s, 1.0, edges_where(s, on_plane("y", d["t"])), "deskmat")


# ----------------------------------------------------------------------------- registry

_TI = PrintSpec("petg_titanium", down="+y", supports="none", infill=0.15,
                note="printed upside down: the deck / rim face on the plate, open bottom up")
PARTS = [
    PartDef("base_shell", "base", "Base shell (14 tiles)", "titanium", "printed", base_shell, print=_TI, owner="base",
            split="2 rows (z -37) x 7 columns (x -455 / -280 / -125 / 115 / 355 / 500), dowels 6 x 16"),
    PartDef("deck_liner", "base", "Graphite deck liner", "graphite", "printed", deck_liner,
            print=PrintSpec("petg_cf_graphite", down="-y", infill=1.0), owner="base",
            split="split at the base tile joints"),
    PartDef("kb_insert", "base", "K3 Ultra locator insert (2 pieces)", "graphite", "printed", kb_insert,
            print=PrintSpec("petg_cf_graphite", down="-y", infill=0.3), owner="base", split="x -90"),
    PartDef("mouse_insert", "base", "X9 locator insert", "graphite", "printed", mouse_insert,
            print=PrintSpec("petg_cf_graphite", down="-y", infill=0.3), owner="base"),
    PartDef("base_hatches", "base", "Bottom hatches (7)", "graphite", "printed", base_hatches, internal=True,
            print=PrintSpec("petg_black", down="-y", infill=0.2), owner="base"),
    PartDef("base_glow", "base", "Under-glow (2 x QSG-0505 + 1800 K COB)", "amber_led", "purchased", base_glow,
            bom="led-channel-qsg0505", owner="electrical"),
    PartDef("kb_charge_led", "base", "Keyboard charge indicator", "amber_led", "printed", kb_charge_led,
            print=PrintSpec("petg_clear", down="-y", infill=1.0, note="light pipe over one COB segment"),
            owner="electrical"),
    PartDef("mouse_charge_led", "base", "Mouse charge indicator", "amber_led", "printed", mouse_charge_led,
            print=PrintSpec("petg_clear", down="-y", infill=1.0), owner="electrical"),
    PartDef("keyboard_body", "keyboard", "Keychron K3 Ultra 8K (chassis)", "graphite", "purchased", keyboard_body,
            bom="kb-k3-ultra", mass_g=P.K3U["mass_kg"] * 1000 * 0.7, mass_note="566 g split 70/30 chassis/keycaps",
            owner="base"),
    PartDef("keyboard_keys", "keyboard", "K3 Ultra keycaps (84)", "keycap", "purchased", keyboard_keys,
            bom="kb-k3-ultra", mass_g=P.K3U["mass_kg"] * 1000 * 0.3, owner="base"),
    PartDef("keyboard_tag", "keyboard", "NILLKIN Magic Tag (Qi receiver)", "plastic_black", "purchased", keyboard_tag,
            internal=True, bom="kb-magic-tag", mass_g=8.2, owner="base"),
    PartDef("mouse_shell", "mouse", "Lenovo Multi-Device Mouse X9", "graphite", "purchased", mouse_shell,
            bom="mouse-lenovo-x9", mass_g=P.X9["mass_kg"] * 1000 - 3, owner="base"),
    PartDef("mouse_wheel", "mouse", "Scroll wheel", "rubber", "purchased", mouse_wheel, bom="mouse-lenovo-x9",
            mass_g=3.0, owner="base"),
    PartDef("deskmat", "deskmat", "Felt desk mat (Oakywood 90 x 30)", "felt", "purchased", deskmat,
            bom="deskmat-oakywood", mass_g=420.0, mass_note="estimate (felt + cork, 900 x 300 x 3)", owner="base"),
]
