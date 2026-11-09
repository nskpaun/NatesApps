#!/usr/bin/env python3
"""Night Array -- printable PROOF-OF-CONCEPT "pocket section" of the desk base.

A tray (keyboard pocket + mouse pocket) that charges a Keychron K3 Ultra 8K (with a NILLKIN Magic Tag Type-C Short
receiver) and a Lenovo Multi-Device Wireless Mouse X9 Edition through 1.0 mm of PETG, from two Anker 313 (A2503)
pads mounted intact in sliding, lockable carriers.  Function over looks: plain PETG, no paint, no lights.

Run with the CadQuery venv:

    night-array/cad/.venv/bin/python night-array/kit/poc/pocket_section.py            # STLs + checks + preview
    night-array/cad/.venv/bin/python night-array/kit/poc/pocket_section.py --no-render

Writes print-ready STLs (mm, Z-up, flat face down, centred on the origin in X/Y, z min = 0) to ./print/, a
print-list.json beside them, assembly meshes for the preview to ./build/ (git-ignored) and preview PNGs to ./preview/
(via render_preview.mjs: headless Chromium + three.js from night-array/viewer/node_modules).

Frame used below (the assembled tray, NOT the app frame): x to the right as you sit at the desk (0 = tray left edge),
y away from you (0 = tray front edge), z up (0 = tray underside; the rubber feet stand ~2 mm below it).
The brief's "x and z" travel (app axes) is x and y here.

How it is built (and why it is split like this)
  * A 1.0 mm floor can only be printed accurately (and without supports) flat on the bed.  So each pad sits under a
    separate FLOOR BLOCK: the part of the tray directly above that pad's cavity, printed bottom-down, whose underside
    IS the 1.0 mm charging floor.  It drops into a tapered (45 deg) seat in the tile from below; the pad presses it up
    into the seat.  Everything else is in two TILES (left/right), joined with printed keys + 4 x M3 screws/nuts.
  * Under each block: a cavity holding a CARRIER (Anker pad in a tray, on foam) that slides +/-15 mm in x and y and is
    locked by 2 x M3 through crossed slots (carrier slot along x, hatch slot along y).  A removable HATCH closes the
    cavity from below; it has the lock slots, a finger window to push the carrier, a 5 mm tick scale and an LED
    sight slot.
"""
from __future__ import annotations

import json
import math
import struct
import subprocess
import sys
from functools import reduce
from pathlib import Path

import cadquery as cq
import numpy as np

HERE = Path(__file__).resolve().parent
OUT = HERE / "print"          # print-ready STLs
BUILD = HERE / "build"        # assembly-position meshes for the preview (git-ignored)
PREVIEW = HERE / "preview"    # rendered PNGs

# =====================================================================================================================
# PARAMETERS -- every dimension in mm.  Purchased-part data: kit/research/parts-research.json, "input-charging",
# with the verifier's corrections applied (they win over the research report).
# =====================================================================================================================

# --- Keychron K3 Ultra 8K (verified: Keychron spec table + dimensioned side view) ---------------------------------
KB_W = 320.62            # keyboard width (x)
KB_D = 126.0             # keyboard depth (y)
KB_H_FRONT = 20.0        # height at the front incl. keycaps and 2 mm feet
KB_H_REAR = 25.5         # height at the rear incl. keycaps and feet (flip-out feet FOLDED -- they must stay folded)
KB_CORNER_R = 6.0        # plan corner radius (estimate)
KB_PORT_FROM_REAR = 23.0 # USB-C centre from the rear edge, on the LEFT side face (verifier's scaled estimate)

# --- NILLKIN Magic Tag Type-C Short (corrected: pad 82 x 48, 100 mm overall; thickness unpublished, ~1 mm) ----------
TAG_STICKOUT = 10.0      # plug + 180-deg fold stick out this far beyond the keyboard's left face (user: ~8-10)
TAG_PAD = (48.0, 82.0, 1.0)   # receiver pad (x, y, z) as it lies under the keyboard, in the 2 mm foot gap
# Receiver COIL centre under the keyboard -- ESTIMATED (verifier: 45-55 mm in from the left edge; ~23 mm from the rear
# edge if the pad lies on the port line, ~45-50 mm after a 45-deg fold to clear the rear-left foot).  The carrier's
# +/-15 mm travel around these nominals covers x 33..63 and y 23..53 -- that is the reason the carriers slide.
TAG_COIL_FROM_LEFT = 48.0
TAG_COIL_FROM_REAR = 38.0

# --- Lenovo Multi-Device Wireless Mouse X9 Edition 4Y51R29290 (verifier: 59 W x 101 L x 34 H, native Qi) -----------
MOUSE_W, MOUSE_L, MOUSE_H = 59.0, 101.0, 34.0
MOUSE_COIL_DX = 0.0      # coil offset from the mouse's plan centre: UNKNOWN, assumed centred (carrier covers +/-15)
MOUSE_COIL_DY = 0.0

# --- Anker 313 Wireless Charger (Pad) A2503 (verifier: 100 x 100 x 11.2, micro-USB on one edge, FOD, <= 5 mm) ------
PAD_W = 100.0            # square pad
PAD_H = 11.2
PAD_R = 14.0             # plan corner radius (estimate)
PAD_FIT = 0.5            # pad-to-carrier-wall clearance per side (snug, drop-in)
PLUG_LEN = 30.0          # straight micro-USB plug + strain relief sticking out of the pad edge
PLUG_W = 12.0            # plug overmould width

# --- Clearances / fits ----------------------------------------------------------------------------------------------
KB_CLR = 2.5             # keyboard-to-pocket-wall clearance per side
MOUSE_CLR = 3.0          # mouse-to-pocket-wall clearance per side
FIT = 0.4                # sliding/drop-in fit per side (floor block in its seat, keys in their holes)
HATCH_FIT = 0.4         # hatch-to-recess clearance per side

# --- Vertical stack (z = 0 is the tray underside) -------------------------------------------------------------------
HATCH_T = 4.0            # hatch plate, flush in a recess in the tile underside; carrier sits on it
CARRIER_BASE_T = 3.0     # carrier base plate
FOAM_GAP = 2.0           # carrier base top -> pad underside: 3 mm EVA foam squeezed to 2 mm pushes the pad UP
FLOOR_T = 1.0            # THE charging floor: solid PETG over each pad's top face (print 100 % infill -- it's solid)
TRAY_H = 44.0            # rim height (KIT_SPEC base <= 50).  K3 Ultra keycaps then sit 2.8 below / 2.7 above it
Z_HATCH_TOP = HATCH_T
Z_PAD_BOT = HATCH_T + CARRIER_BASE_T + FOAM_GAP
Z_MB = Z_PAD_BOT + PAD_H           # pad top = underside of the 1.0 mm floor = underside of the floor blocks
Z_FLOOR = Z_MB + FLOOR_T           # pocket floor (both pockets on the same plane)

# --- Carrier travel and cavities ------------------------------------------------------------------------------------
TRAVEL = 15.0            # carrier adjustment, +/- in x and in y
SWEEP = PAD_W / 2 + TRAVEL        # half-size of the square the pad top can reach (65)
CAV_MARGIN = 3.5         # cavity wall beyond the pad sweep (carrier walls reach SWEEP + 2.4)
CH = SWEEP + CAV_MARGIN  # cavity half-size (68.5)
BAY_LEN = 34.0           # plug bay: cavity extension on the pad's micro-USB side (plug + travel + cable bend)
BAY_W = PLUG_W + 2 * TRAVEL + 6   # plug bay width (48)
SEAT_H = 2.0             # 45-deg tapered seat for the floor blocks (also the block's locating flange height)
BLOCK_INSET = 1.8        # floor-block underside = cavity outline shrunk by this (still covers the pad sweep by 1.7)

# --- Carrier (local frame: pad centre at x = y = 0, base underside at z = 0) ----------------------------------------
CAR_WALL = 2.1           # wall round the pad
CAR_HALF = PAD_W / 2 + PAD_FIT + CAR_WALL     # 52.4
CAR_WALL_H = 6.0         # wall height above the base (pad engaged 4 mm)
CAR_WALL_GAP = 24.0      # gap in the middle of each wall: micro-USB plug, LED light, finger access
EAR_Y = 63.5             # lock-screw line, +/- y from the pad centre: PAD_W/2 + 10 + washer radius 3.5 -> steel >= 10 mm off the pad
EAR_HALF_X = 20.0        # ear half-width (slot 30 + 3.4 long)
EAR_OUT = 5.0            # ear extends this far past the screw line
SLOT_D = 3.6             # M3 clearance
NUT_AF = 6.0             # M3 nut channel width (nut is 5.5 across flats -> cannot turn)
NUT_WALL_H = 2.6         # nut channel walls (M3 nut 2.4 thick)

# --- Cavity galleries for the carrier ears (cavity extension in y, roofed by the floor block) -----------------------
GAL_X = EAR_HALF_X + TRAVEL + 1.0             # 36
GAL_Y = EAR_Y + EAR_OUT + TRAVEL + 1.0        # 82

# --- Hatch ----------------------------------------------------------------------------------------------------------
HATCH_MARGIN = 10.0      # hatch beyond the main cavity (its 4 screws sit 6 mm outside the cavity corners)
HATCH_MARGIN_EXT = 3.0   # hatch beyond the galleries / plug bay
HATCH_SCREW_IN = 6.0     # hatch screws: this far outside the cavity corner, in x and in y (nut >= 10 mm off the pad)
FINGER_WIN = 50.0        # square window under the carrier centre: push the carrier with a fingertip, read the ticks
HEAD_CB_D, HEAD_CB_H = 6.4, 2.2   # counterbore for an M3 ISO 7380 button head (5.7 x 1.65)
LOCK_CB_W, LOCK_CB_H = 7.6, 2.4   # counterbored slot for button head + M3 washer (7 OD)
HEX_D = 6.7              # printed nut trap, across corners (M3 nut 6.35) -- press the nut in

# --- Layout in the tray -----------------------------------------------------------------------------------------------
WALL_MIN = 3.0           # minimum plastic between a hatch recess and the tile's outer edge
FRONT_RIM = 20.0         # keyboard pocket front wall from the tray front edge
TRAY_D = 205.0           # tray depth (y)
POCKET_GAP = 16.0       # wall between the keyboard pocket and the mouse pocket at floor level (the two coves meet ~1 mm below the rim)
MOUSE_PAD_Y = 92.0       # mouse pad (and pocket) centre, y
# Keyboard left edge: as far left as its carrier bay allows (hatch recess keeps WALL_MIN to the tile edge).
KB_X0 = WALL_MIN + HATCH_MARGIN + CH - TAG_COIL_FROM_LEFT         # 33.5
KB_Y0 = FRONT_RIM + KB_CLR                                         # keyboard front edge (21)
KB_PAD = (KB_X0 + TAG_COIL_FROM_LEFT, KB_Y0 + KB_D - TAG_COIL_FROM_REAR)   # keyboard pad nominal centre
MOUSE_X = KB_X0 + KB_W + KB_CLR + POCKET_GAP + MOUSE_W / 2 + MOUSE_CLR      # mouse pocket centre x
MOUSE_PAD = (MOUSE_X + MOUSE_COIL_DX, MOUSE_PAD_Y + MOUSE_COIL_DY)
TRAY_W = math.ceil(MOUSE_PAD[0] + CH + HATCH_MARGIN + WALL_MIN)    # 480
JOINT_X = math.floor(TRAY_W / 2)  # tile split line (x).  Passes through the keyboard pocket's THICK floor, 50 mm clear
                                  # of both hatch recesses; never through a 1.0 mm charging floor.

# --- Pocket details ---------------------------------------------------------------------------------------------------
TAG_RELIEF_DEPTH = 14.0  # Magic Tag plug/fold relief into the keyboard pocket's left wall
TAG_RELIEF_LEN = 37.0    # its length along y, centred on the USB-C port
KB_NOTCH_W = 34.0        # finger notches in the keyboard pocket's front wall (one near each end)
KB_NOTCH_IN = 45.0       # notch centre from the keyboard's left/right edge
KB_NOTCH_FRONT = 7.0     # front wall left standing in front of each notch
KB_NOTCH_DIP = 4.0       # notch dips this far below the floor so a fingertip gets under the keyboard (thick floor only)
POCKET_STRAIGHT = 6.0    # pocket walls rise straight this far above the floor, so devices still land over the chargers
POCKET_FLARE = 12.0      # above that, a soft cove widens the opening by this much per side at the rim
COVE_STEPS = 24          # ruled loft sections through the cove (fine facets, smooth to the eye)
MOUSE_POCKET_R = 18.0    # mouse pocket plan corner radius
MOUSE_NOTCH_W = 30.0     # finger notches either side of the mouse
MOUSE_NOTCH_IN = 6.0

# --- Tile joint ---------------------------------------------------------------------------------------------------
KEY = (20.0, 10.0, 6.0)  # printed alignment key (x long, y, z); 3 of them
KEY_POS = [(10.0, 30.0), (95.0, 12.0), (185.0, 30.0)]   # (y, z) of each key across the joint
JOINT_SCREW_Y = [32.0, 60.0, 125.0, 172.0]              # M3 x 20 screws across the joint, from below
JOINT_SCREW_Z = 7.0
JOINT_POCKET = (28.0, 12.0, 14.0)   # left-tile access pocket (x long, y wide, z high), open underneath, for the hex key
JOINT_WALL = 6.0         # plastic between the access pocket and the joint face
JOINT_NUT_AT = 9.0       # right tile: nut slot this far from the joint face
NUT_T_SLOT = 3.0         # nut slot thickness (M3 nut 2.4)

# --- Underside ------------------------------------------------------------------------------------------------------
FOOT_D, FOOT_DEPTH = 10.5, 1.2    # pockets for 10 mm x ~3 mm self-adhesive rubber bumpers (stand ~1.8 mm proud)
FOOT_INSET = (10.0, 8.0)          # foot centres from the tile corners (x, y); 4 per tile
CABLE_W, CABLE_H = 8.0, 7.0       # cable groove (open underneath, 45-deg peaked roof) from each plug bay to the back

# --- Coupon (test print) --------------------------------------------------------------------------------------------
COUPON = 110.0           # coupon plate size
COUPON_SKIRT_H = 3.0     # skirt that hangs down round the pad to locate the coupon
COUPON_SKIRT_T = 1.6
COUPON_GAP = 22.0        # gaps in the skirt (micro-USB plug, LED)

# --- Printer / material --------------------------------------------------------------------------------------------
BED_MAX = 245.0          # KIT_SPEC: every part fits 245 x 245 x 245 in its print orientation
PETG_DENSITY = 1.27      # g/cm3
EST_SHELL = 1.0          # estimate: walls/top/bottom ~1.0 mm of solid over the whole surface ...
EST_INFILL = 0.15        # ... plus 15 % gyroid inside
EST_RATE = 28.0          # cm3 of extruded PETG per hour (Bambu PETG standard profile, rough average)

# =====================================================================================================================
# geometry helpers
# =====================================================================================================================


def box(x0, x1, y0, y1, z0, z1):
    return cq.Workplane("XY").box(x1 - x0, y1 - y0, z1 - z0, centered=False).translate((x0, y0, z0))


def rbox(x0, x1, y0, y1, z0, z1, r):
    w, h = x1 - x0, y1 - y0
    s = cq.Workplane("XY", origin=((x0 + x1) / 2, (y0 + y1) / 2, z0)).rect(w, h).extrude(z1 - z0)
    r = min(r, w / 2 - 0.05, h / 2 - 0.05)
    return s.edges("|Z").fillet(r) if r > 0.05 else s


def cyl(x, y, z0, z1, d):
    return cq.Workplane("XY", origin=(x, y, z0)).circle(d / 2).extrude(z1 - z0)


def hexprism(x, y, z0, z1, d):
    return cq.Workplane("XY", origin=(x, y, z0)).polygon(6, d).extrude(z1 - z0)


def slot(x, y, z0, z1, length, d, along="x"):
    return cq.Workplane("XY", origin=(x, y, z0)).slot2D(length, d, 0 if along == "x" else 90).extrude(z1 - z0)


def xcyl(x0, x1, y, z, d):
    return cq.Workplane("YZ", origin=(x0, 0, 0)).center(y, z).circle(d / 2).extrude(x1 - x0)


def frustum(r, z0, h, inset):
    """Loft from rect r=(x0,x1,y0,y1) at z0 to the same rect shrunk by `inset` at z0+h (45 deg if inset == h)."""
    x0, x1, y0, y1 = r
    cx, cy, w, d = (x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0
    return (cq.Workplane("XY", origin=(cx, cy, z0)).rect(w, d).workplane(offset=h)
            .rect(w - 2 * inset, d - 2 * inset).loft(combine=True))


def gable_y(xc, y0, y1, w, h):
    """Groove running along y, open underneath, rectangular w x h then a 45-deg peaked roof (prints without support)."""
    pts = [(xc - w / 2, -0.5), (xc + w / 2, -0.5), (xc + w / 2, h), (xc, h + w / 2), (xc - w / 2, h)]
    s = cq.Workplane("XZ").polyline(pts).close().extrude(y1 - y0)
    bb = s.val().BoundingBox()
    return s.translate((0, y0 - bb.ymin, 0))


def union(items):
    items = [i for i in items if i is not None]
    return reduce(lambda a, b: a.union(b), items)


def grow(r, d):
    x0, x1, y0, y1 = r
    return (x0 - d, x1 + d, y0 - d, y1 + d)


def prism(r, z0, z1):
    return box(r[0], r[1], r[2], r[3], z0, z1)


def vol(wp):
    try:
        return sum(s.Volume() for s in wp.solids().vals())
    except Exception:
        return 0.0


def overlap(a, b):
    """Volume (mm3) shared by two workplanes; 0 for touching faces."""
    try:
        return vol(a.intersect(b))
    except Exception:
        return float("nan")


# =====================================================================================================================
# per-pocket outlines (all axis-aligned rectangles in the tray frame)
# =====================================================================================================================

POCKETS = {
    "kb": {"pad": KB_PAD, "bay": "+x"},       # keyboard pad: micro-USB toward +x (bay under the keyboard pocket floor)
    "mouse": {"pad": MOUSE_PAD, "bay": "-x"},  # mouse pad: micro-USB toward -x (bay under the keyboard pocket's right
                                               # end; toward the back the plug would hit the carrier's rear ear)
}


def cavity_rects(p):
    cx, cy = POCKETS[p]["pad"]
    main = (cx - CH, cx + CH, cy - CH, cy + CH)
    gal = (cx - GAL_X, cx + GAL_X, cy - GAL_Y, cy + GAL_Y)
    sx = 1 if POCKETS[p]["bay"] == "+x" else -1
    xa, xb = cx + sx * (CH - 4), cx + sx * (CH + BAY_LEN)
    bay = (min(xa, xb), max(xa, xb), cy - BAY_W / 2, cy + BAY_W / 2)
    return {"main": main, "gal": gal, "bay": bay}


def hatch_rects(p):
    c = cavity_rects(p)
    return [grow(c["main"], HATCH_MARGIN), grow(c["gal"], HATCH_MARGIN_EXT), grow(c["bay"], HATCH_MARGIN_EXT)]


def hatch_screws(p):
    cx, cy = POCKETS[p]["pad"]
    a = CH + HATCH_SCREW_IN
    return [(cx + sx * a, cy + sy * a) for sx in (-1, 1) for sy in (-1, 1)]


def seat_shape(p, extra):
    """Floor-block shape (extra = 0) or the hole it drops into (extra = FIT): a 45-deg flange then straight walls."""
    rs = [grow(r, -(BLOCK_INSET - extra)) for r in cavity_rects(p).values()]
    low = union([frustum(r, Z_MB - (0.05 if extra else 0), SEAT_H + (0.05 if extra else 0), SEAT_H) for r in rs])
    high = union([prism(grow(r, -SEAT_H), Z_MB + SEAT_H - 0.01, TRAY_H + 1) for r in rs])
    return low.union(high)


def feet_positions():
    fx, fy = FOOT_INSET
    pts = []
    for x0, x1 in ((0, JOINT_X), (JOINT_X, TRAY_W)):
        for x in (x0 + fx, x1 - fx):
            for y in (fy, TRAY_D - fy):
                pts.append((x, y))
    return pts


# =====================================================================================================================
# the solid tray ("monolith"): outer block with the pockets cut -- tiles and floor blocks are both cut from it
# =====================================================================================================================

def cove_pocket(x0, x1, y0, y1, r):
    """Pocket cut: straight walls for POCKET_STRAIGHT above the floor, then a concave quarter-ellipse cove (a bowl)
    that starts almost flat where it leaves the straight wall and rises to meet the rim vertically,
    POCKET_FLARE wider per side at the rim.  Built as ONE ruled loft from the floor to the rim (no internal faces),
    so the cut stays watertight."""
    zs = Z_FLOOR + POCKET_STRAIGHT
    H = TRAY_H - zs

    def section(off, z):
        a0, a1, b0, b1 = x0 - off, x1 + off, y0 - off, y1 + off
        w = cq.Wire.makePolygon([cq.Vector(a0, b0, z), cq.Vector(a1, b0, z), cq.Vector(a1, b1, z), cq.Vector(a0, b1, z)], close=True)
        return w.fillet2D(r + off, w.Vertices())

    wires = [section(0.0, Z_FLOOR)]
    for k in range(COVE_STEPS + 1):
        t = math.pi / 2 * k / COVE_STEPS
        wires.append(section(POCKET_FLARE * math.sin(t), zs + H * (1 - math.cos(t))))
    wires.append(section(POCKET_FLARE, TRAY_H + 1.0))
    out = cq.Workplane().add(cq.Solid.makeLoft(wires, True))
    assert out.val().isValid() and out.val().Volume() > 0, 'cove pocket loft failed'
    return out


def monolith():
    m = box(0, TRAY_W, 0, TRAY_D, 0, TRAY_H)
    top = TRAY_H + 1
    cuts = []
    # keyboard pocket
    kx0, kx1 = KB_X0 - KB_CLR, KB_X0 + KB_W + KB_CLR
    ky0, ky1 = KB_Y0 - KB_CLR, KB_Y0 + KB_D + KB_CLR
    cuts.append(cove_pocket(kx0, kx1, ky0, ky1, KB_CORNER_R + KB_CLR))
    # Magic Tag relief (left wall, centred on the USB-C port)
    py = KB_Y0 + KB_D - KB_PORT_FROM_REAR
    cuts.append(rbox(kx0 - TAG_RELIEF_DEPTH, kx0 + 3, py - TAG_RELIEF_LEN / 2, py + TAG_RELIEF_LEN / 2, Z_FLOOR, top, 2))
    # keyboard finger notches (front wall) + dips below the floor where the floor is thick (outside every cavity)
    cav_all = [r for p in POCKETS for r in cavity_rects(p).values()]
    for xc in (KB_X0 + KB_NOTCH_IN, KB_X0 + KB_W - KB_NOTCH_IN):
        cuts.append(rbox(xc - KB_NOTCH_W / 2, xc + KB_NOTCH_W / 2, KB_NOTCH_FRONT, ky0 + 2, Z_FLOOR, top, 3))
        dip = (xc - KB_NOTCH_W / 2, xc + KB_NOTCH_W / 2, KB_NOTCH_FRONT, ky0 + 12)
        if not any(dip[0] < r[1] + 3 and dip[1] > r[0] - 3 and dip[2] < r[3] + 3 and dip[3] > r[2] - 3 for r in cav_all):
            cuts.append(rbox(*dip, Z_FLOOR - KB_NOTCH_DIP, Z_FLOOR + 0.5, 3))
    # mouse pocket + side notches
    mx, my = MOUSE_X, MOUSE_PAD_Y
    hw, hl = MOUSE_W / 2 + MOUSE_CLR, MOUSE_L / 2 + MOUSE_CLR
    cuts.append(cove_pocket(mx - hw, mx + hw, my - hl, my + hl, MOUSE_POCKET_R))
    for s in (-1, 1):
        xa = mx + s * hw
        cuts.append(rbox(min(xa, xa + s * MOUSE_NOTCH_IN) - (2 if s > 0 else 0), max(xa, xa + s * MOUSE_NOTCH_IN) + (2 if s < 0 else 0),
                         my - MOUSE_NOTCH_W / 2, my + MOUSE_NOTCH_W / 2, Z_FLOOR, top, 2))
    for c in cuts:
        m = m.cut(c)
    return m


def tile_full(mono):
    t = mono
    cuts = []
    for p in POCKETS:
        c = cavity_rects(p)
        cuts.append(seat_shape(p, FIT))                                  # floor-block hole
        cuts += [prism(r, Z_HATCH_TOP - 0.1, Z_MB + 0.05) for r in c.values()]   # carrier cavity
        cuts += [prism(grow(r, 0), -1, Z_HATCH_TOP) for r in hatch_rects(p)]   # hatch recess
        for (x, y) in hatch_screws(p):                                   # hatch nut traps (press nut in from below)
            cuts.append(hexprism(x, y, Z_HATCH_TOP - 0.1, Z_HATCH_TOP + 2.6, HEX_D))
            cuts.append(cyl(x, y, Z_HATCH_TOP, Z_HATCH_TOP + 7.0, SLOT_D))   # M3 x 8 tip room
        # cable groove from the plug bay to the back edge
        cx, cy = POCKETS[p]["pad"]
        b = c["bay"]
        sx = 1 if POCKETS[p]["bay"] == "+x" else -1
        cuts.append(gable_y((b[0] + b[1]) / 2 + 2 * sx, cy, TRAY_D + 1, CABLE_W, CABLE_H))
    for x, y in feet_positions():
        cuts.append(cyl(x, y, -1, FOOT_DEPTH, FOOT_D))
    # joint: key holes (both sides), screw access pockets (left), clearance holes, nut slots (right)
    J = JOINT_X
    for (y, z) in KEY_POS:
        kx, ky, kz = KEY
        cuts.append(box(J - kx / 2 - 0.5, J + kx / 2 + 0.5, y - ky / 2 - FIT, y + ky / 2 + FIT, z - kz / 2 - FIT, z + kz / 2 + FIT))
    px, pw, ph = JOINT_POCKET
    for y in JOINT_SCREW_Y:
        cuts.append(box(J - JOINT_WALL - px, J - JOINT_WALL, y - pw / 2, y + pw / 2, -1, ph))
        cuts.append(xcyl(J - JOINT_WALL - 1, J + JOINT_NUT_AT + NUT_T_SLOT + 7, y, JOINT_SCREW_Z, SLOT_D))
        cuts.append(box(J + JOINT_NUT_AT, J + JOINT_NUT_AT + NUT_T_SLOT, y - NUT_AF / 2, y + NUT_AF / 2, -1, JOINT_SCREW_Z + 3.3))
    for c in cuts:
        t = t.cut(c)
    return t


def floor_block(mono, p):
    return mono.intersect(seat_shape(p, 0.0))


# =====================================================================================================================
# hatch, carrier, key, coupon
# =====================================================================================================================

def hatch(p):
    cx, cy = POCKETS[p]["pad"]
    h = union([prism(grow(r, -HATCH_FIT), 0, HATCH_T) for r in hatch_rects(p)])
    cuts = []
    for (x, y) in hatch_screws(p):
        cuts += [cyl(x, y, -1, HATCH_T + 1, SLOT_D), cyl(x, y, -1, HEAD_CB_H, HEAD_CB_D)]
    for s in (-1, 1):   # lock slots along y (carrier slots run along x -> the crossing point locks both axes)
        y = cy + s * EAR_Y
        cuts.append(slot(cx, y, -1, HATCH_T + 1, 2 * TRAVEL + SLOT_D, SLOT_D, "y"))
        cuts.append(slot(cx, y, -1, LOCK_CB_H, 2 * TRAVEL + LOCK_CB_W, LOCK_CB_W, "y"))
    f = FINGER_WIN / 2
    cuts.append(rbox(cx - f, cx + f, cy - f, cy + f, -1, HATCH_T + 1, 4))
    # tick scale engraved in the underside: every 5 mm, +/-15, longer at 0 (read the carrier's centre dimple against it)
    for i in range(-3, 4):
        L = 5.0 if i == 0 else 3.0
        cuts.append(box(cx + 5 * i - 0.35, cx + 5 * i + 0.35, cy - f - 1 - L, cy - f - 1, -1, 0.4))
        cuts.append(box(cx - f - 1 - L, cx - f - 1, cy + 5 * i - 0.35, cy + 5 * i + 0.35, -1, 0.4))
    # LED sight slot in the plug bay (the pad's blue LED lights the closed cavity; watch the glow here)
    sx = 1 if POCKETS[p]["bay"] == "+x" else -1
    xa, xb = cx + sx * (CH + 2), cx + sx * (CH + 28)
    cuts.append(rbox(min(xa, xb), max(xa, xb), cy + 17, cy + 22.5, -1, HATCH_T + 1, 2))
    for x, y in feet_positions():
        cuts.append(cyl(x, y, -1, FOOT_DEPTH, FOOT_D))
    for c in cuts:
        h = h.cut(c)
    return h


def carrier():
    """Local frame: pad centre at x=y=0, base underside z=0.  Same part for both pockets (print 2)."""
    a = CAR_HALF
    base = rbox(-a, a, -a, a, 0, CARRIER_BASE_T, PAD_R + PAD_FIT + CAR_WALL)
    ears = [rbox(-EAR_HALF_X, EAR_HALF_X, min(s * (a - 8), s * (EAR_Y + EAR_OUT)), max(s * (a - 8), s * (EAR_Y + EAR_OUT)),
                 0, CARRIER_BASE_T, 3) for s in (-1, 1)]
    c = union([base] + ears)
    zt = CARRIER_BASE_T
    # pad walls: ring, with a gap in the middle of every side
    ring = rbox(-a, a, -a, a, zt - 0.01, zt + CAR_WALL_H, PAD_R + PAD_FIT + CAR_WALL).cut(
        rbox(-(PAD_W / 2 + PAD_FIT), PAD_W / 2 + PAD_FIT, -(PAD_W / 2 + PAD_FIT), PAD_W / 2 + PAD_FIT, zt - 1, zt + CAR_WALL_H + 1, PAD_R + PAD_FIT))
    g = CAR_WALL_GAP / 2
    ring = ring.cut(box(-g, g, -a - 1, a + 1, zt - 1, zt + CAR_WALL_H + 1)).cut(box(-a - 1, a + 1, -g, g, zt - 1, zt + CAR_WALL_H + 1))
    c = c.union(ring)
    # captive nut channels on the ears: walls + 1.2 mm lips over the nut (slot left open for the screw tip), closed at
    # the -x end, open at the +x end -- slide an M3 nut in from +x.  The nut slides along x with the screw as the
    # carrier moves in x; the lips keep it in while the tray is upside down during assembly.
    for s in (-1, 1):
        y = s * EAR_Y
        x0, x1 = -EAR_HALF_X + 1, EAR_HALF_X
        for side in (-1, 1):
            y0 = y + side * NUT_AF / 2
            y1 = y0 + side * 1.6
            c = c.union(box(x0, x1, min(y0, y1), max(y0, y1), zt - 0.01, zt + NUT_WALL_H + 1.2))
            ya, yb = y + side * SLOT_D / 2, y1
            c = c.union(box(x0, x1, min(ya, yb), max(ya, yb), zt + NUT_WALL_H, zt + NUT_WALL_H + 1.2))
        c = c.union(box(x0, x0 + 1.5, y - NUT_AF / 2 - 0.1, y + NUT_AF / 2 + 0.1, zt - 0.01, zt + NUT_WALL_H + 1.2))   # end stop
        c = c.cut(slot(0, y, -1, zt + 1, 2 * TRAVEL + SLOT_D, SLOT_D, "x"))
    # centre dimple underneath (45-deg cone, prints without support): the pointer for the hatch tick scale
    cone = cq.Workplane("XY").add(cq.Solid.makeCone(6.0, 4.5, 1.5, pnt=cq.Vector(0, 0, -0.001)))
    c = c.cut(cone)
    # foam locating marks: four 0.4 mm recesses, 20 x 20, where the foam squares go
    for sx in (-1, 1):
        for sy in (-1, 1):
            c = c.cut(box(sx * 28 - 10, sx * 28 + 10, sy * 28 - 10, sy * 28 + 10, zt - 0.4, zt + 0.1))
    return c


def key():
    kx, ky, kz = KEY
    return box(0, kx, 0, ky, 0, kz).edges().chamfer(0.5)


def coupon():
    """Upright frame: membrane top at z = SKIRT_H + FLOOR_T, skirt hangs down round the pad.  Printed flipped."""
    s = COUPON / 2
    inner = PAD_W / 2 + 0.4
    plate = rbox(-s, s, -s, s, COUPON_SKIRT_H, COUPON_SKIRT_H + FLOOR_T, 18)
    skirt = rbox(-(inner + COUPON_SKIRT_T), inner + COUPON_SKIRT_T, -(inner + COUPON_SKIRT_T), inner + COUPON_SKIRT_T, 0,
                 COUPON_SKIRT_H + 0.01, PAD_R + 0.4 + COUPON_SKIRT_T).cut(
        rbox(-inner, inner, -inner, inner, -1, COUPON_SKIRT_H + 0.5, PAD_R + 0.4))
    g = COUPON_GAP / 2
    skirt = skirt.cut(box(-g, g, -s - 1, s + 1, -1, COUPON_SKIRT_H)).cut(box(-s - 1, s + 1, -g, g, -1, COUPON_SKIRT_H))
    return plate.union(skirt)


# =====================================================================================================================
# purchased-part envelopes (checks + preview only)
# =====================================================================================================================

def keyboard_env():
    y0, y1 = KB_Y0, KB_Y0 + KB_D
    pts = [(y0, Z_FLOOR), (y1, Z_FLOOR), (y1, Z_FLOOR + KB_H_REAR), (y0, Z_FLOOR + KB_H_FRONT)]
    s = cq.Workplane("YZ", origin=(KB_X0, 0, 0)).polyline(pts).close().extrude(KB_W)
    try:
        return s.edges("|Z").fillet(KB_CORNER_R)
    except Exception:
        return s


def magic_tag_env():
    py = KB_Y0 + KB_D - KB_PORT_FROM_REAR
    plug = box(KB_X0 - TAG_STICKOUT, KB_X0, py - 6, py + 6, Z_FLOOR + 0.3, Z_FLOOR + 10.5)
    cx, cy = KB_PAD
    # pad lies along x, tail edge toward the left (flex side); coil ~50 mm from the tail edge (verifier, scaled)
    pad = box(max(cx - 50, KB_X0), max(cx - 50, KB_X0) + TAG_PAD[1], cy - TAG_PAD[0] / 2, cy + TAG_PAD[0] / 2, Z_FLOOR + 0.5, Z_FLOOR + 0.5 + TAG_PAD[2])
    return plug.union(pad)


def mouse_env():
    hw, hl = MOUSE_W / 2, MOUSE_L / 2
    m = rbox(MOUSE_X - hw, MOUSE_X + hw, MOUSE_PAD_Y - hl, MOUSE_PAD_Y + hl, Z_FLOOR, Z_FLOOR + MOUSE_H, 24)
    try:
        m = m.faces(">Z").edges().fillet(12)
    except Exception:
        pass
    return m


def pad_env(x, y):
    a = PAD_W / 2
    return rbox(x - a, x + a, y - a, y + a, Z_PAD_BOT, Z_PAD_BOT + PAD_H, PAD_R)


def plug_env(p, x, y):
    a = PAD_W / 2
    zc = Z_PAD_BOT + PAD_H / 2
    sx = 1 if POCKETS[p]["bay"] == "+x" else -1
    xa, xb = x + sx * a, x + sx * (a + PLUG_LEN)
    return box(min(xa, xb), max(xa, xb), y - PLUG_W / 2, y + PLUG_W / 2, zc - 4, zc + 4)


def foam_env(x, y):
    zt = Z_HATCH_TOP + CARRIER_BASE_T
    return union([box(x + sx * 28 - 10, x + sx * 28 + 10, y + sy * 28 - 10, y + sy * 28 + 10, zt, zt + FOAM_GAP)
                  for sx in (-1, 1) for sy in (-1, 1)])


# =====================================================================================================================
# STL export + mesh checks (no trimesh needed)
# =====================================================================================================================

def to_print(wp, flip=False):
    """Print orientation: optional flip about x, then centred on the origin in x/y with z min = 0."""
    s = wp.val() if len(wp.solids().vals()) == 1 else cq.Compound.makeCompound(wp.solids().vals())
    if flip:
        s = s.rotate(cq.Vector(0, 0, 0), cq.Vector(1, 0, 0), 180)
    bb = s.BoundingBox()
    return s.translate(cq.Vector(-(bb.xmin + bb.xmax) / 2, -(bb.ymin + bb.ymax) / 2, -bb.zmin))


def export_stl(shape, path, tol=0.03):
    cq.exporters.export(cq.Workplane().add(shape), str(path), tolerance=tol, angularTolerance=0.15)


def read_stl(path):
    data = Path(path).read_bytes()
    if data[:5] == b"solid" and b"facet" in data[:400]:
        v = [list(map(float, l.split()[1:4])) for l in data.decode().splitlines() if l.strip().startswith("vertex")]
        return np.array(v, dtype=np.float64).reshape(-1, 3, 3)
    n = struct.unpack("<I", data[80:84])[0]
    a = np.frombuffer(data[84:84 + n * 50], dtype=np.dtype([("n", "<3f4"), ("v", "<9f4"), ("a", "<u2")]))
    return a["v"].astype(np.float64).reshape(-1, 3, 3)


def mesh_check(path):
    tri = read_stl(path)
    pts = tri.reshape(-1, 3)
    key_ = np.round(pts / 1e-4).astype(np.int64)
    _, idx = np.unique(key_, axis=0, return_inverse=True)
    f = idx.reshape(-1, 3)
    f = f[(f[:, 0] != f[:, 1]) & (f[:, 1] != f[:, 2]) & (f[:, 0] != f[:, 2])]
    e = np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]])
    und = np.sort(e, axis=1)
    _, cnt = np.unique(und, axis=0, return_counts=True)
    # directed-edge test: every directed edge appears once, and its reverse once
    _, dcnt = np.unique(e, axis=0, return_counts=True)
    watertight = bool(np.all(cnt == 2))
    oriented = bool(np.all(dcnt == 1))
    v0, v1, v2 = tri[:, 0], tri[:, 1], tri[:, 2]
    volume = float(np.einsum("ij,ij->i", v0, np.cross(v1, v2)).sum() / 6.0)
    ext = pts.max(0) - pts.min(0)
    return {"triangles": int(len(tri)), "watertight": watertight, "consistently_oriented": oriented,
            "volume_mm3": round(volume, 1), "size_mm": [round(float(x), 2) for x in ext],
            "fits_bed": bool(np.all(ext <= BED_MAX + 1e-6)), "z_min": round(float(pts[:, 2].min()), 3),
            "positive_volume": volume > 0}


def estimate(shape, infill_override=None):
    V = shape.Volume() / 1000.0          # cm3
    A = shape.Area() / 100.0             # cm2
    shell = min(V, A * EST_SHELL / 10.0)
    infill = EST_INFILL if infill_override is None else infill_override
    ve = shell + infill * (V - shell)
    return round(ve * PETG_DENSITY, 1), round(ve / EST_RATE + 0.1, 2)


# =====================================================================================================================
# build
# =====================================================================================================================

def build(render=True):
    OUT.mkdir(parents=True, exist_ok=True)
    BUILD.mkdir(parents=True, exist_ok=True)
    print("tray %.0f x %.0f x %.0f mm, joint at x = %.0f; keyboard pad nominal %s, mouse pad nominal %s"
          % (TRAY_W, TRAY_D, TRAY_H, JOINT_X, tuple(round(v, 1) for v in KB_PAD), tuple(round(v, 1) for v in MOUSE_PAD)))
    mono = monolith()
    tile = tile_full(mono)
    tiles = {"tile_left": tile.intersect(box(-1, JOINT_X, -1, TRAY_D + 1, -1, TRAY_H + 1)),
             "tile_right": tile.intersect(box(JOINT_X, TRAY_W + 1, -1, TRAY_D + 1, -1, TRAY_H + 1))}
    blocks = {p: floor_block(mono, p) for p in POCKETS}
    hatches = {p: hatch(p) for p in POCKETS}
    car = carrier()
    k = key()
    cp = coupon()

    # ---------------------------------------------------------------- print parts
    parts = [  # (file, workplane, qty, flip, infill, supports, orientation note, material)
        ("tile_left.stl", tiles["tile_left"], 1, False, None, "none", "underside down (as assembled)"),
        ("tile_right.stl", tiles["tile_right"], 1, False, None, "none", "underside down (as assembled)"),
        ("kb_floor_block.stl", blocks["kb"], 1, False, None, "none", "1.0 mm charging floor DOWN on the bed (as assembled)"),
        ("mouse_floor_block.stl", blocks["mouse"], 1, False, None, "none", "1.0 mm charging floor DOWN on the bed (as assembled)"),
        ("pad_carrier.stl", car, 2, False, None, "none", "base down (as assembled)"),
        ("kb_hatch.stl", hatches["kb"], 1, False, None, "none", "outside face (tick scale) down"),
        ("mouse_hatch.stl", hatches["mouse"], 1, False, None, "none", "outside face (tick scale) down"),
        ("joint_key.stl", k, 3, False, 1.0, "none", "flat"),
        ("coupon.stl", cp, 1, True, 1.0, "none", "flipped: the 1.0 mm plate on the bed, skirt up"),
    ]
    plist, checks = [], {}
    for fname, wp, qty, flip, infill, sup, orient in parts:
        s = to_print(wp, flip)
        export_stl(s, OUT / fname)
        mc = mesh_check(OUT / fname)
        g, h = estimate(s, infill)
        checks[fname] = mc
        plist.append({"file": "print/" + fname, "qty": qty, "material": "PETG (PLA works for a test)",
                      "orientation": orient, "supports": sup, "size_mm": mc["size_mm"],
                      "grams_each_est": g, "hours_each_est": h, "solid_volume_cm3": round(s.Volume() / 1000, 1)})
        print("  %-22s x%d  %-24s watertight=%s oriented=%s fits_bed=%s  ~%5.0f g  ~%.1f h"
              % (fname, qty, " x ".join("%.1f" % v for v in mc["size_mm"]), mc["watertight"], mc["consistently_oriented"],
                 mc["fits_bed"], g, h))
    (OUT / "print-list.json").write_text(json.dumps({"parts": plist, "estimate_model": {
        "shell_mm": EST_SHELL, "infill": EST_INFILL, "rate_cm3_per_h": EST_RATE, "density": PETG_DENSITY,
        "note": "rough volume-based estimate; the slicer's number wins"}}, indent=2) + "\n")

    # ---------------------------------------------------------------- assembly checks
    rep = {"tray_mm": [TRAY_W, TRAY_D, TRAY_H], "joint_x": JOINT_X}
    solid_tray = [tile] + list(blocks.values())
    kb, tag, ms = keyboard_env(), magic_tag_env(), mouse_env()
    rep["keyboard_vs_tray_mm3"] = round(sum(overlap(kb, t) for t in solid_tray), 3)
    rep["magic_tag_vs_tray_mm3"] = round(sum(overlap(tag, t) for t in solid_tray), 3)
    rep["mouse_vs_tray_mm3"] = round(sum(overlap(ms, t) for t in solid_tray), 3)
    # side clearance: grow the devices by (clearance - 0.1) in plan -- must still not touch
    kbg = rbox(KB_X0 - KB_CLR + 0.1, KB_X0 + KB_W + KB_CLR - 0.1, KB_Y0 - KB_CLR + 0.1, KB_Y0 + KB_D + KB_CLR - 0.1, Z_FLOOR + 0.5,
               Z_FLOOR + 20, KB_CORNER_R + KB_CLR - 0.1)
    rep["keyboard_grown_%.1f_vs_tray_mm3" % (KB_CLR - 0.1)] = round(sum(overlap(kbg, t) for t in solid_tray), 3)
    msg = rbox(MOUSE_X - MOUSE_W / 2 - MOUSE_CLR + 0.1, MOUSE_X + MOUSE_W / 2 + MOUSE_CLR - 0.1,
               MOUSE_PAD_Y - MOUSE_L / 2 - MOUSE_CLR + 0.1, MOUSE_PAD_Y + MOUSE_L / 2 + MOUSE_CLR - 0.1, Z_FLOOR + 0.5, Z_FLOOR + 20, 24)
    rep["mouse_grown_%.1f_vs_tray_mm3" % (MOUSE_CLR - 0.1)] = round(sum(overlap(msg, t) for t in solid_tray), 3)
    rep["keycaps_vs_rim_mm"] = {"front": round(Z_FLOOR + KB_H_FRONT - TRAY_H, 2), "rear": round(Z_FLOOR + KB_H_REAR - TRAY_H, 2)}
    rep["mouse_top_above_rim_mm"] = round(Z_FLOOR + MOUSE_H - TRAY_H, 2)
    # carriers + pads at the 9 corners/centre of their travel
    sweep = {}
    for p in POCKETS:
        cx, cy = POCKETS[p]["pad"]
        worst = {"pad_vs_tray": 0.0, "pad_vs_hatch": 0.0, "pad_vs_carrier": 0.0, "plug_vs_tray": 0.0,
                 "carrier_vs_tray": 0.0, "carrier_vs_hatch": 0.0, "pad_lifted_0.05_vs_block(contact)": 1e9}
        for dx in (-TRAVEL, 0, TRAVEL):
            for dy in (-TRAVEL, 0, TRAVEL):
                x, y = cx + dx, cy + dy
                pe = pad_env(x, y)
                ce = car.translate((x, y, Z_HATCH_TOP))
                pl = plug_env(p, x, y)
                worst["pad_vs_tray"] = max(worst["pad_vs_tray"], overlap(pe, tile) + sum(overlap(pe, b) for b in blocks.values()))
                worst["pad_vs_hatch"] = max(worst["pad_vs_hatch"], overlap(pe, hatches[p]))
                worst["pad_vs_carrier"] = max(worst["pad_vs_carrier"], overlap(pe, ce))
                worst["plug_vs_tray"] = max(worst["plug_vs_tray"], overlap(pl, tile) + sum(overlap(pl, b) for b in blocks.values()) + overlap(pl, ce))
                worst["carrier_vs_tray"] = max(worst["carrier_vs_tray"], overlap(ce, tile) + sum(overlap(ce, b) for b in blocks.values()))
                worst["carrier_vs_hatch"] = max(worst["carrier_vs_hatch"], overlap(ce, hatches[p]))
                worst["pad_lifted_0.05_vs_block(contact)"] = min(worst["pad_lifted_0.05_vs_block(contact)"],
                                                                 overlap(pe.translate((0, 0, 0.05)), blocks[p]))
        sweep[p] = {k_: round(v, 3) for k_, v in worst.items()}
        # floor stack at the nominal pad centre: solid plastic between pad top and pocket floor
        col = blocks[p].intersect(box(cx - 0.25, cx + 0.25, cy - 0.25, cy + 0.25, -5, TRAY_H + 5))
        bb = col.val().BoundingBox()
        sweep[p]["floor_stack"] = {"pad_top_z": round(Z_MB, 3), "floor_bottom_z": round(bb.zmin, 3), "floor_top_z": round(bb.zmax, 3),
                                   "floor_thickness": round(bb.zmax - bb.zmin, 3), "device_rests_at_z": round(Z_FLOOR, 3)}
        # floor stays 1.0 over the whole pad sweep: sample a 5 x 5 grid of columns
        th = []
        for gx in np.linspace(-SWEEP + 1, SWEEP - 1, 5):
            for gy in np.linspace(-SWEEP + 1, SWEEP - 1, 5):
                c2 = blocks[p].intersect(box(cx + gx - 0.2, cx + gx + 0.2, cy + gy - 0.2, cy + gy + 0.2, -5, Z_MB + FLOOR_T + 0.001))
                b2 = c2.val().BoundingBox() if c2.solids().vals() else None
                th.append(None if b2 is None else round(b2.zmax - b2.zmin, 3))
        sweep[p]["floor_thickness_over_sweep_min_max"] = [min(t for t in th if t is not None), max(t for t in th if t is not None)]
        sweep[p]["floor_bottom_flat_at_pad_top"] = all(t is not None for t in th)
    rep["sweep"] = sweep

    # metal keep-out: plan distance from every screw/nut to the pad footprint at ANY carrier position
    def dist_rect(x, y, r):
        dx = max(r[0] - x, 0, x - r[1]); dy = max(r[2] - y, 0, y - r[3])
        return math.hypot(dx, dy)
    sweeps = {p: (POCKETS[p]["pad"][0] - SWEEP, POCKETS[p]["pad"][0] + SWEEP, POCKETS[p]["pad"][1] - SWEEP, POCKETS[p]["pad"][1] + SWEEP) for p in POCKETS}
    metal = []
    for p in POCKETS:
        for (x, y) in hatch_screws(p):
            metal.append(("hatch screw+nut " + p, x, y, HEX_D / 2))
    for y in JOINT_SCREW_Y:
        for x in (JOINT_X - JOINT_WALL - 3, JOINT_X + JOINT_NUT_AT + NUT_T_SLOT + 6):
            metal.append(("joint screw/nut", x, y, HEX_D / 2))
    md = [(n, round(min(dist_rect(x, y, r) for r in sweeps.values()) - rad, 1)) for n, x, y, rad in metal]
    rep["metal_min_plan_distance_to_any_pad_position_mm"] = min(d for _, d in md)
    rep["metal_detail"] = md
    rep["lock_screws_distance_to_pad_edge_mm"] = round(EAR_Y - PAD_W / 2 - 3.5, 1)   # washer radius
    rep["lock_screw_note"] = "lock screws move with the carrier in y (always EAR_Y from the pad centre), so their gap to the pad never changes"
    rep["meshes"] = checks
    ok = (all(c["watertight"] and c["consistently_oriented"] and c["fits_bed"] and c["positive_volume"] for c in checks.values())
          and rep["keyboard_vs_tray_mm3"] < 0.01 and rep["mouse_vs_tray_mm3"] < 0.01 and rep["magic_tag_vs_tray_mm3"] < 0.01
          and all(v < 0.01 for p in sweep for k_, v in sweep[p].items() if isinstance(v, float) and "contact" not in k_)
          and all(sweep[p]["pad_lifted_0.05_vs_block(contact)"] > 1 for p in sweep)
          and all(abs(sweep[p]["floor_stack"]["floor_thickness"] - FLOOR_T) < 1e-3 for p in sweep)
          and rep["metal_min_plan_distance_to_any_pad_position_mm"] >= 10 and rep["lock_screws_distance_to_pad_edge_mm"] >= 10
          and rep["keyboard_grown_%.1f_vs_tray_mm3" % (KB_CLR - 0.1)] < 0.01 and rep["mouse_grown_%.1f_vs_tray_mm3" % (MOUSE_CLR - 0.1)] < 0.01)
    rep["ALL_CHECKS_PASS"] = bool(ok)
    (BUILD / "checks.json").write_text(json.dumps(rep, indent=2) + "\n")
    print(json.dumps({k_: v for k_, v in rep.items() if k_ not in ("meshes", "metal_detail")}, indent=1))

    # ---------------------------------------------------------------- preview meshes (assembly positions)
    scene = []

    def add(name, wp, color, explode, opacity=1.0, group="print"):
        s = wp.val() if len(wp.solids().vals()) == 1 else cq.Compound.makeCompound(wp.solids().vals())
        export_stl(s, BUILD / (name + ".stl"), tol=0.08)
        scene.append({"file": name + ".stl", "color": color, "explode": explode, "opacity": opacity, "group": group})

    add("tile_left", tiles["tile_left"], "#b9b2a4", [-25, 0, 0])
    add("tile_right", tiles["tile_right"], "#c4bdaf", [25, 0, 0])
    add("kb_block", blocks["kb"], "#e0a458", [-25, 0, -70])
    add("mouse_block", blocks["mouse"], "#e0a458", [25, 0, -70])
    for p in POCKETS:
        cx, cy = POCKETS[p]["pad"]
        ex = -25 if p == "kb" else 25
        add(p + "_pad", pad_env(cx, cy), "#2a2c30", [ex, 0, -120], group="purchased")
        add(p + "_plug", plug_env(p, cx, cy), "#555a60", [ex, 0, -120], group="purchased")
        add(p + "_foam", foam_env(cx, cy), "#5b8fd1", [ex, 0, -145], group="purchased")
        add(p + "_carrier", car.translate((cx, cy, Z_HATCH_TOP)), "#7fa37a", [ex, 0, -170])
        add(p + "_hatch", hatches[p], "#8e8a83", [ex, 0, -205])
    add("keyboard", kb, "#3b3f46", [-25, 0, 70], group="purchased")
    add("magic_tag", tag, "#d0d4da", [-25, 0, 55], group="purchased")
    add("mouse", ms, "#4a4e55", [25, 0, 70], group="purchased")
    (BUILD / "scene.json").write_text(json.dumps({"parts": scene, "bounds": [[0, 0, 0], [TRAY_W, TRAY_D, TRAY_H]],
                                                  "section_y": KB_PAD[1]}, indent=1))
    if render:
        node = subprocess.run(["node", str(HERE / "render_preview.mjs"), str(BUILD), str(PREVIEW)], text=True)
        if node.returncode != 0:
            print("preview render failed", file=sys.stderr)
    return ok


if __name__ == "__main__":
    ok = build(render="--no-render" not in sys.argv)
    sys.exit(0 if ok else 1)
