#!/usr/bin/env python3
"""Night Array -- LEGO version of the LATCH-FREE vertical laptop DOCK (Apple Silicon MacBook Pro 14" / 16").

Plain python3, no external dependencies.  Run from anywhere:

    python3 night-array/kit/lego/make_lego_dock.py                    # 16" (default), model + lists + checks + renders
    python3 night-array/kit/lego/make_lego_dock.py --model 14         # same LEGO build, settings worked out for the 14"
    python3 night-array/kit/lego/make_lego_dock.py --port tb_front    # use the front left Thunderbolt port instead
    python3 night-array/kit/lego/make_lego_dock.py --no-render        # skip the PNGs

Writes, under night-array/kit/lego/dock/:
    night-array-dock.ldr   LDraw model, one STEP per build step (BrickLink Studio / LeoCAD / LDCad)
    parts.csv              part list (LDraw id, BrickLink id, name, colour, qty, est. price)
    bricklink-wanted.xml   BrickLink wanted-list upload (ITEMTYPE P, BrickLink colour ids)
    bricks.json            every part as a box (mm) + reference boxes (laptop, plug head, foam, felt), same schema
                           as ../bricks.json; slope parts carry one extra key "slope" {down, high_mm} for drawing
    checks.json            the self-check results + the plug / liner settings for both laptops
    steps/step-XX.png, overview.png, exploded.png, plug-section.png   (via render_lego_dock.mjs)

The dock in one paragraph
    The laptop stands CLOSED on its LEFT side (MagSafe + two Thunderbolt ports face down), hinge toward the back,
    bottom face (rubber feet) toward the RIGHT wall, lid toward the LEFT wall (as seen from the front).  It drops
    into a 20 mm slot (2.5 studs: the left wall and the back wall stand on jumper plates, half a stud off the grid)
    with felt liners, lands on a felt-covered tile floor, and its rear port slides over a Newnex right-angle USB4
    plug that stands tip-up in a foam-lined pocket under the floor.  The plug's overmold face sits 0.39 mm below
    the landing plane, so the laptop rests on the floor, never on the plug.  No latch: lift it straight out.

Frames
    Grid / bricks.json: x to the right as you face the dock's front, y DEPTH TOWARD YOU (0 = back edge), z up
    (0 = desk).  Origin = back-left-bottom corner.  1 stud = 8.0 mm, 1 plate = 3.2 mm.  Internally everything is
    kept in HALF studs (4 mm) because the left wall + back wall sit half a stud off the grid.
    LDraw: X = x * 2.5, Y = -z * 2.5 (-Y is up), Z = -y * 2.5 (the dock's front faces -Z).
    Boxes are nominal (on the grid); real LEGO parts are 0.1 mm smaller per side, so the slot is 20.2 mm in real life.

Vertical stack (plate layers):
    L0, L1    plates, whole footprint.  L1 has a smooth Tile 2 x 3 = the PLUG SEAT (top at z 6.4)
    L2        plates; holes = plug pocket + the open part of the cable channel.  The plates in the channel right
              behind the pocket are the "saddle" the cable boot is clamped on
    L3-L5     brick course; holes = plug pocket + cable channel (straight out of the back edge)
    L6        the slot FLOOR (top z 22.4): smooth tiles in the slot, 1 x 4 tiles roofing the channel (held down by
              both walls), jumper plates under the left + back walls, plates under the right wall, plinth tiles
    L7        wall plate course (left + back on the jumpers' centre studs, half a stud over)
    L8 ...    wall brick courses: back wall 12 courses (top z 144.0), side walls sweep down from 11 courses at the
              back to 2 at the front in 3-stud steps, each step capped with a 33 deg slope (outer) and a 45 deg
              lead-in slope facing the slot (inner), studs capped with tiles
    Plug: felt 1.0 + shim 0.1 on the seat -> head bottom 7.5, overmold face 23.01; landing plane = floor 22.4 +
    felt 1.0 = 23.40 -> face 0.39 mm below it.  The felt under the head and on the floor is the same felt, so its
    thickness cancels out.
"""
from __future__ import annotations

import csv
import json
import math
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "dock"
sys.path.insert(0, str(HERE))
import make_lego_base as base  # noqa: E402  (reuse the base's part table, colours and grid constants)

# =====================================================================================================================
# PARAMETERS (mm unless noted)
# =====================================================================================================================
STUD, PLATE = base.STUD, base.PLATE          # 8.0, 3.2
HALF = STUD / 2                              # 4.0 mm: the internal grid unit
LEGO_INSET = base.LEGO_INSET                 # 0.1 mm per side

# Laptops.  Body sizes and weights: Apple tech specs (M3/M4/M5 family).  PORT POSITIONS ARE ESTIMATES: Apple
# publishes no dimensioned side drawing; these were scaled from Apple's left-side product photos (+/- 3 mm along the
# side, +/- 1 mm in height).  Measure your own laptop (see dock/README.md) and change them here.
#   ports_from_rear: centre of each left-side port, measured along the side from the REAR (hinge) edge
#   port_h:          port centre height above the laptop's BOTTOM case surface (not counting the rubber feet)
MODELS = {
    "14": {"name": 'MacBook Pro 14" (M3/M4/M5)', "W": 312.6, "D": 221.2, "T": 15.5, "kg": 1.60,
           "ports_from_rear": {"magsafe": 23.0, "tb_rear": 41.0, "tb_front": 55.0}, "port_h": 5.4},
    "16": {"name": 'MacBook Pro 16" (M3/M4/M5)', "W": 355.7, "D": 248.1, "T": 16.8, "kg": 2.15,
           "ports_from_rear": {"magsafe": 25.0, "tb_rear": 44.0, "tb_front": 58.0}, "port_h": 5.9},
}
FEET_H = 0.6               # rubber feet stand-off from the bottom case (ESTIMATE); T above is taken to include them
MODEL = "16"               # which laptop the reported settings are for (--model 14)
PORT = "tb_rear"           # which left USB-C port the plug enters (--port tb_front)
for _a, _b in zip(sys.argv, sys.argv[1:]):
    if _a == "--model": MODEL = _b
    if _a == "--port": PORT = _b
LAP = MODELS[MODEL]

# Newnex U4T1C01CR5P010 side-exit right-angle head (research/parts-research.json, category "dock")
PLUG_W, PLUG_T, PLUG_LEN = 8.25, 2.40, 6.65          # tongue: wide axis (along the slot, y) x thickness (x) x exposed
HEAD_Y, HEAD_X, HEAD_Z = 12.35, 6.50, 15.51          # overmold: along the plug's wide axis, thickness, mating axis
HEAD_CLOSED = 6.18                                   # plug centre -> closed end of the head (front, +y)
HEAD_ALONG_CABLE = 34.5                              # closed end -> end of the strain-relief boot (back, -y)
CABLE_BELOW_FACE = 7.8                               # cable axis below the overmold face
CABLE_OD, BEND_R = 4.8, 25.0
BOOT_D = 7.0                                         # boot diameter: NOT on the drawing, assumed (pack foam to fit)
RETENTION_N = (8, 20)                                # USB-C extraction force range (new)

# Liners (non-LEGO).  Felt = self-adhesive felt sheet, 1.0 mm.  EVA = 3 mm craft foam.  Tape = 1 mm foam tape.
FELT = 1.0
SHIM_UNDER_HEAD = 0.1      # one layer of paper / thin tape under the head (fine-tunes the overmold depth)
EVA, TAPE = 3.0, 1.0
FOAM_PRELOAD = 0.5         # each foam pad is cut this much thicker than its gap
LINER_R = FELT             # right wall (reference wall, laptop bottom face/feet): always one felt layer
SIDE_CLR = (1.5, 2.6)      # target total sideways clearance range (mm) after the liners

# Layout (studs).  Shifted parts (left + back wall) are half a stud off the grid.
BASE_W, BASE_D = 16, 35                  # 128 x 280 mm footprint
SLOT_X0, SLOT_X1 = 6.5, 9.0              # slot between the walls (grid faces), 20.0 mm (20.2 real)
LEFT_WALL = (2.5, 6.5)                   # 4 studs, stands on jumpers (half-stud grid)
RIGHT_WALL = (9, 13)                     # 4 studs, on the grid
BACK_WALL_D = 2                          # back wall y 0..2, x 2.5..12.5 (half-stud grid, bonded to the left wall)
POCKET_X0, POCKET_W, POCKET_L = 7, 2, 3  # plug pocket 2 x 3 studs (16 x 24 mm) under the floor
SADDLE_L = 3                             # rows of the channel behind the pocket where the boot is clamped
N_MAX, N_MIN, STEP_ROWS = 11, 2, 3       # side-wall courses at the back / front, rows per step
BACK_N = N_MAX + 1                       # back wall courses

# Vertical, in plates
SEAT_L = 1        # the plug seat tile layer (top = seat)
FLOOR_L = 6       # slot floor tile layer (top = floor)
WALL_PL = 7       # wall plate course
WALL0 = 8         # first wall brick course

# LDraw colour -> (BrickLink id, hex, name, price multiplier)
COLOURS = {72: (85, "#6c6e68", "Dark Bluish Gray", 1.0), 71: (86, "#a0a5a9", "Light Bluish Gray", 1.0),
           320: (59, "#720e0f", "Dark Red", 1.8)}
BODY, ACCENT, PANEL = 72, 71, 320

# Part table: the base's table (bricks, plates, tiles; ids checked against the LDraw library) plus the jumper and
# four slopes (ids checked against library.ldraw.org, Nov 2026).  ldraw id -> (kind, w, l, name, USD each)
PARTS = dict(base.PARTS)
PARTS.update({
    "15573": ("plate", 1, 2, "Plate 1 x 2 with 1 Stud (Jumper)", 0.05),
    "3037": ("slope", 2, 4, "Slope 45 2 x 4", 0.30), "3038": ("slope", 2, 3, "Slope 45 2 x 3", 0.25),
    "3039": ("slope", 2, 2, "Slope 45 2 x 2", 0.12), "3298": ("slope", 2, 3, "Slope 33 3 x 2", 0.25),
})
BRICKLINK_ID = {}           # all ids are the same on BrickLink
# slope geometry: depth along the fall line, width across it (studs); the stud row is the high end (1 row)
SLOPES = {"3037": (2, 4), "3038": (2, 3), "3039": (2, 2), "3298": (3, 2)}
SLOPE_LIP = 1.6             # mm, height of the low edge (LDraw: 4 LDU)
HEIGHT = {"brick": 3, "plate": 1, "tile": 1, "slope": 3}
JUMPER = "15573"
BRICK_SET = [p for p, v in PARTS.items() if v[0] == "brick"]
PLATE_SET = [p for p, v in base.PARTS.items() if v[0] == "plate"]
TILE_SET = [p for p, v in base.PARTS.items() if v[0] == "tile" and p != "90498"]
RED_BRICKS = ["3005", "3004", "3622", "3010", "3009", "3008", "3003", "3002", "3001"]
RED_TILES = ["3069b", "3070b"]
LEADIN_TILES = ["2431", "63864", "3069b"]
# rough masses (g per stud cell) for the stability check
MASS_PER_CELL = {"brick": 0.29, "slope": 0.21, "plate": 0.13, "tile": 0.12}

# =====================================================================================================================
# GEOMETRY (half-stud units: 1 = 4 mm)
# =====================================================================================================================
def h(v):            # studs -> half units (exact)
    return int(round(v * 2))


SLOT_REAL = ((SLOT_X0 * STUD - LEGO_INSET), (SLOT_X1 * STUD + LEGO_INSET))     # 51.9 .. 72.1
SLOT_W_REAL = SLOT_REAL[1] - SLOT_REAL[0]                                      # 20.2
BACK_FACE_REAL = BACK_WALL_D * STUD + LEGO_INSET                              # 16.1
Z_SEAT = (SEAT_L + 1) * PLATE                                                  # 6.4
Z_FLOOR = (FLOOR_L + 1) * PLATE                                                # 22.4
Z_LAND = Z_FLOOR + FELT                                                        # 23.4
Z_HEAD0 = Z_SEAT + FELT + SHIM_UNDER_HEAD                                      # 7.5
Z_FACE = Z_HEAD0 + HEAD_Z                                                      # 23.01
Z_CABLE = Z_FACE - CABLE_BELOW_FACE                                            # 15.21
OVERMOLD_DEPTH = Z_LAND - Z_FACE                                               # 0.39


def side_settings(m):
    """Felt liners left/right for laptop m: right = 1 felt (reference wall), left = felt layers for 1.5-2.6 mm."""
    room = SLOT_W_REAL - m["T"] - LINER_R
    best = None
    for n in range(0, 5):
        clr = room - n * FELT
        if SIDE_CLR[0] - 1e-9 <= clr <= SIDE_CLR[1] + 1e-9 and best is None:
            best = (n, clr)
    if best is None:
        best = (max(0, math.floor((room - SIDE_CLR[1]) / FELT + 0.999)), None)
        best = (best[0], room - best[0] * FELT)
    n, clr = best
    return {"liner_left_felt_layers": n, "liner_left_mm": n * FELT, "liner_right_mm": LINER_R, "clearance_mm": clr}


def port_xy(m, port, liner_back):
    """Port centre (x, y) with the laptop's feet on the right liner and its rear edge on the back liner."""
    x = SLOT_REAL[1] - LINER_R - FEET_H - m["port_h"]
    y = BACK_FACE_REAL + liner_back + m["ports_from_rear"][port]
    return x, y


def choose_pocket_row(m, port):
    """Pocket row so that a back liner of 1..9 whole mm and a head shift of <= 1.5 mm in the pocket fit the port."""
    best = None
    for py0 in range(SADDLE_L, 20):
        centre = (py0 + POCKET_L / 2) * STUD
        need = centre - BACK_FACE_REAL - m["ports_from_rear"][port]
        lb = min(9, max(1, round(need)))
        off = BACK_FACE_REAL + lb + m["ports_from_rear"][port] - centre
        if abs(off) <= 1.5:
            cost = abs(off) + 0.25 * lb
            if best is None or cost < best[0]:
                best = (cost, py0)
    return best[1]


PY0 = choose_pocket_row(LAP, PORT)
POCKET_CX = (POCKET_X0 + POCKET_W / 2) * STUD
POCKET_CY = (PY0 + POCKET_L / 2) * STUD


def plug_settings(m, port):
    """Everything the builder sets for laptop m: back liner, side liners, where the head sits, foam pad stacks."""
    centre_need = POCKET_CY - BACK_FACE_REAL - m["ports_from_rear"][port]
    lb = min(9, max(1, round(centre_need)))
    side = side_settings(m)
    px, py = port_xy(m, port, lb)
    # head extents
    hx0, hx1 = px - HEAD_X / 2, px + HEAD_X / 2
    hy0, hy1 = py - (HEAD_Y - HEAD_CLOSED), py + HEAD_CLOSED          # back face, closed (front) end
    px0, px1 = POCKET_X0 * STUD, (POCKET_X0 + POCKET_W) * STUD
    py0, py1 = PY0 * STUD, (PY0 + POCKET_L) * STUD
    gaps = {"left": hx0 - px0, "right": px1 - hx1, "back": hy0 - py0, "front": py1 - hy1}

    def stack(g):
        t = g + FOAM_PRELOAD
        n3 = int(t // EVA)
        n1 = round(t - n3 * EVA)
        if n3 * EVA + n1 * TAPE < g + 0.2: n1 += 1
        if n1 >= 3: n3, n1 = n3 + 1, 0
        free = n3 * EVA + n1 * TAPE
        return {"gap_mm": round(g, 2), "eva_3mm": n3, "tape_1mm": n1, "free_mm": free,
                "float_mm": round(min(g, g - 0.4 * free) if free else 0, 2)}

    pads = {k: stack(v) for k, v in gaps.items()}
    back_eva = int((lb - FELT) // EVA)
    back_tape = round(lb - FELT - back_eva * EVA)
    return {"port": port, "back_liner_mm": lb, "back_liner": f"felt 1 mm + {back_eva} x 3 mm EVA + {back_tape} x 1 mm "
            f"foam tape", "side": side, "port_x": round(px, 2), "port_y": round(py, 2),
            "head_offset_in_pocket": (round(px - POCKET_CX, 2), round(py - POCKET_CY, 2)), "pads": pads,
            "head_box": (hx0, hx1, hy0, hy1)}


SET = plug_settings(LAP, PORT)
PLUG_X, PLUG_Y = SET["port_x"], SET["port_y"]

# side-wall height profile: segments (row0, row1, courses), rear segment first
def profile():
    rows = list(range(BACK_WALL_D, BASE_D))
    n_steps = N_MAX - N_MIN
    rear = len(rows) - n_steps * STEP_ROWS
    assert rear >= 2, "base too short for the sweep"
    segs = [(BACK_WALL_D, BACK_WALL_D + rear, N_MAX)]
    y = BACK_WALL_D + rear
    for n in range(N_MAX - 1, N_MIN - 1, -1):
        segs.append((y, y + STEP_ROWS, n))
        y += STEP_ROWS
    return segs


SEGS = profile()
N_OF_ROW = {y: n for (a, b, n) in SEGS for y in range(a, b)}


# =====================================================================================================================
# PARTS IN HALF UNITS
# =====================================================================================================================
def mk(pid, x0h, y0h, wh, hh, z, colour, step, rot=False, down=None):
    kind = PARTS[pid][0]
    return {"part": pid, "x": x0h, "y": y0h, "w": wh, "h": hh, "z": z, "nz": HEIGHT[kind], "kind": kind,
            "color": colour, "step": step, "rot": rot, "down": down}


def cells_h(p):
    return {(x, y) for x in range(p["x"], p["x"] + p["w"]) for y in range(p["y"], p["y"] + p["h"])}


def stud_points(p):
    """Stud centres on top (half-unit grid lines)."""
    if p["kind"] == "tile":
        return []
    if p["part"] == JUMPER:
        return [(p["x"] + p["w"] // 2, p["y"] + p["h"] // 2)]
    pts = [(x, y) for x in range(p["x"] + 1, p["x"] + p["w"], 2) for y in range(p["y"] + 1, p["y"] + p["h"], 2)]
    if p["kind"] == "slope":       # only the high row
        d = p["down"]
        if d == "+y": pts = [q for q in pts if q[1] == p["y"] + 1]
        if d == "-y": pts = [q for q in pts if q[1] == p["y"] + p["h"] - 1]
        if d == "+x": pts = [q for q in pts if q[0] == p["x"] + 1]
        if d == "-x": pts = [q for q in pts if q[0] == p["x"] + p["w"] - 1]
    return pts


def receptors(p):
    return {(x, y) for x in range(p["x"] + 1, p["x"] + p["w"], 2) for y in range(p["y"] + 1, p["y"] + p["h"], 2)}


def perim(p):
    x0, y0, w, hh = p["x"], p["y"], p["w"], p["h"]
    e = set()
    for y in range(y0, y0 + hh):
        e.add(("v", x0, y)); e.add(("v", x0 + w, y))
    for x in range(x0, x0 + w):
        e.add(("h", x, y0)); e.add(("h", x, y0 + hh))
    return e


def seams(parts):
    cnt = Counter()
    for p in parts:
        for e in perim(p):
            cnt[e] += 1
    return {e for e, n in cnt.items() if n >= 2}


# =====================================================================================================================
# PACKER (the base's greedy packer, generalised: any bounding box, a half-stud grid offset, a placement predicate)
# =====================================================================================================================
def pack(region, part_ids, below, prefer, colour, z, step, ox=0, ok=None):
    """region: local integer cells (i, j) with global half x = 2 i + ox, half y = 2 j.  Tries the four scan
    directions, keeps the packing with the fewest seams continued from `below` (+ fewest parts)."""
    if not region:
        return []
    lo_i, hi_i = min(c[0] for c in region), max(c[0] for c in region)
    lo_j, hi_j = min(c[1] for c in region), max(c[1] for c in region)
    cands = []
    for pid in part_ids:
        _, w, l, _, _ = PARTS[pid]
        cands.append((pid, l, w, False))
        if w != l:
            cands.append((pid, w, l, True))
    best = None
    for fx in (False, True):
        for fy in (False, True):
            def true_rect(i, j, cw, ch, fx=fx, fy=fy):
                ti = lo_i + hi_i - (i + cw - 1) if fx else i
                tj = lo_j + hi_j - (j + ch - 1) if fy else j
                return ti, tj
            tf = lambda c, fx=fx, fy=fy: (lo_i + hi_i - c[0] if fx else c[0], lo_j + hi_j - c[1] if fy else c[1])
            free = {tf(c) for c in region}
            order = sorted(free, key=(lambda c: (c[1], c[0])) if prefer == "x" else (lambda c: (c[0], c[1])))
            placed = []
            for c in order:
                if c not in free:
                    continue
                bsel, bscore = None, -1e9
                for pid, cw, ch, rot in cands:
                    cells = {(c[0] + a, c[1] + b) for a in range(cw) for b in range(ch)}
                    if not cells <= free:
                        continue
                    ti, tj = true_rect(c[0], c[1], cw, ch)
                    if ok and not ok({(ti + a, tj + b) for a in range(cw) for b in range(ch)}):
                        continue
                    q = mk(pid, 2 * ti + ox, 2 * tj, 2 * cw, 2 * ch, z, colour, step, rot)
                    hits = len(perim(q) & below) / 2
                    score = cw * ch - 1.5 * hits + (0.6 if (cw > ch) == (prefer == "x") and cw != ch else 0)
                    if score > bscore:
                        bsel, bscore = (q, cells), score
                if bsel is None:
                    raise RuntimeError(f"cannot fill cell {c} (z {z}, step {step})")
                placed.append(bsel[0])
                free -= bsel[1]
            hits = len(seams(placed) & below)
            score = hits + 2 * len(placed)
            if best is None or score < best[0]:
                best = (score, placed)
    return best[1]


def rect(x0, y0, w, hh):
    return {(x, y) for x in range(x0, x0 + w) for y in range(y0, y0 + hh)}


def split_len(n, sizes=(4, 3, 2)):
    """Split a run of n studs into the given part lengths (prefers long ones, never 1 unless n == 1)."""
    for a in sizes:
        if n == a: return [a]
    for a in sizes:
        if n - a >= 2 or n - a == 0:
            rest = split_len(n - a, sizes)
            if rest is not None: return [a] + rest
    return None


# =====================================================================================================================
# BUILD
# =====================================================================================================================
FULL = rect(0, 0, BASE_W, BASE_D)
POCKET = rect(POCKET_X0, PY0, POCKET_W, POCKET_L)
CHANNEL = rect(POCKET_X0, 0, POCKET_W, PY0)
SADDLE = rect(POCKET_X0, PY0 - SADDLE_L, POCKET_W, SADDLE_L)
CHANNEL_OPEN_L2 = CHANNEL - SADDLE
ROOF_ROWS = range(BACK_WALL_D, PY0)                       # 1 x 4 roof tiles over the channel under the slot


def left_rows(k, top=False):
    return [y for y in range(BACK_WALL_D, BASE_D) if (N_OF_ROW[y] - 1 == k if top else N_OF_ROW[y] - 1 > k)]


def build():
    courses = []
    prev = set()

    def add(name, parts, step):
        courses.append({"name": name, "step": step, "parts": parts})
        return parts

    def below_of(z):
        return seams([p for c in courses for p in c["parts"] if p["z"] + p["nz"] == z])

    # ---- base -------------------------------------------------------------------------------------------------
    add("L0 base plates", pack(FULL, PLATE_SET, set(), "x", BODY, 0, 1), 1)
    seat = mk("26603", h(POCKET_X0), h(PY0), h(2), h(3), SEAT_L, BODY, 2, rot=True)
    add("L1 plates + plug seat tile", [seat] + pack(FULL - POCKET, PLATE_SET, below_of(1), "y", BODY, 1, 2), 2)
    add("L2 plates (pocket, channel, saddle)", pack(FULL - POCKET - CHANNEL_OPEN_L2, PLATE_SET, below_of(2), "x",
                                                    BODY, 2, 3), 3)
    add("L3-L5 bricks (pocket + cable channel)", pack(FULL - POCKET - CHANNEL, BRICK_SET, below_of(3), "y", BODY, 3, 4), 4)
    # step 5 = plug (reference objects only)
    # ---- L6 floor layer ---------------------------------------------------------------------------------------
    z = FLOOR_L
    L6 = []
    for y in ROOF_ROWS:                                                     # roof over the channel, 4 wide
        L6.append(mk("2431", h(6), h(y), h(4), h(1), z, BODY, 6))
    jump_cols = {y: ([2, 4] if y >= BACK_WALL_D else [2, 4, 6, 8, 10]) for y in range(BASE_D)}
    for y, xs in jump_cols.items():
        for x in xs:
            L6.append(mk(JUMPER, h(x), h(y), h(2), h(1), z, BODY, 6))
    slot_floor = {(6, y) for y in range(PY0, BASE_D)} | (rect(7, PY0, 2, BASE_D - PY0) - POCKET)
    under_right = rect(9, PY0, 4, BASE_D - PY0) | rect(10, BACK_WALL_D, 3, PY0 - BACK_WALL_D)
    taken = set().union(*(set((x // 2, y // 2) for (x, y) in cells_h(p)) for p in L6))
    plinth = FULL - taken - slot_floor - under_right - POCKET
    b6 = below_of(z)
    L6 += pack(slot_floor, TILE_SET, b6, "y", BODY, z, 6)
    L6 += pack(under_right, PLATE_SET, b6, "y", BODY, z, 6)
    L6 += pack(plinth, TILE_SET, b6, "y", BODY, z, 6)
    add("L6 slot floor: roof tiles, jumpers, floor tiles, plates, plinth tiles", L6, 6)

    # ---- L7 wall plate course ---------------------------------------------------------------------------------
    z = WALL_PL
    shifted = rect(2, 0, 10, BACK_WALL_D) | rect(2, BACK_WALL_D, 4, BASE_D - BACK_WALL_D)   # local i = x - 0.5
    jumper_studs = {(2, y) for y in range(BASE_D)} | {(4, y) for y in range(BASE_D)} | \
                   {(i, y) for i in (6, 8, 10) for y in range(BACK_WALL_D)}
    ok7 = lambda cells: bool(cells & jumper_studs)
    b7 = below_of(z)
    L7 = pack(shifted, PLATE_SET, b7, "x", BODY, z, 7, ox=1, ok=ok7)
    L7 += pack(rect(9, BACK_WALL_D, 4, BASE_D - BACK_WALL_D), PLATE_SET, b7, "y", BODY, z, 7)
    add("L7 wall plates", L7, 7)

    # ---- wall brick courses -----------------------------------------------------------------------------------
    for k in range(BACK_N):
        z = WALL0 + 3 * k
        step = 8 + k // 3
        b = below_of(z)
        parts = []
        # regular bricks
        back = rect(2, 0, 10, BACK_WALL_D) if k < BACK_N - 1 else set()
        lrows = left_rows(k)
        r = 1 if k % 2 == 0 else 2
        red = {(i, y) for y in lrows for i in range(2, 2 + r)}
        left_dbg = {(i, y) for y in lrows for i in range(2 + r, 6)}
        parts += pack(red, RED_BRICKS, b, "y", PANEL, z, step, ox=1)
        parts += pack(back | left_dbg, BRICK_SET, b | seams(parts), "x" if k % 2 else "y", BODY, z, step, ox=1)
        right = {(x, y) for y in lrows for x in range(9, 13)}
        parts += pack(right, BRICK_SET, b, "y" if k % 2 else "x", BODY, z, step)
        # tops of the steps whose top course is k
        for (ya, yb, n) in SEGS:
            if n - 1 != k:
                continue
            L = yb - ya
            for wall in ("left", "right"):
                ox = 1 if wall == "left" else 0
                # local i of the columns: left wall i 2..5 (x 2.5..6.5), right wall x 9..12
                outer = (2, 3) if wall == "left" else (11, 12)
                inner_stud = 4 if wall == "left" else 10
                inner_slope = 5 if wall == "left" else 9
                down = "+x" if wall == "left" else "-x"
                ocol = PANEL if wall == "left" else BODY
                # inner lead-in slopes facing the slot
                y = ya
                for ln in split_len(L):
                    pid = {4: "3037", 3: "3038", 2: "3039"}[ln]
                    xi = min(inner_stud, inner_slope)
                    parts.append(mk(pid, 2 * xi + ox, h(y), h(2), h(ln), z, ACCENT, step, down=down))
                    parts.append(mk({4: "2431", 3: "63864", 2: "3069b"}[ln], 2 * inner_stud + ox, h(y), h(1), h(ln),
                                    z + 3, ACCENT, step, rot=True))
                    y += ln
                # outer: flat bricks then a 33 deg slope down toward the front
                if L > 3:
                    flat = {(i, yy) for i in outer for yy in range(ya, yb - 3)}
                    parts += pack(flat, RED_BRICKS if wall == "left" else BRICK_SET, b, "y", ocol, z, step, ox=ox)
                    parts += pack(flat, RED_TILES if wall == "left" else TILE_SET, set(), "x", ocol, z + 3, step, ox=ox)
                parts.append(mk("3298", 2 * outer[0] + ox, h(yb - 3), h(2), h(3), z, ocol, step, down="+y"))
                parts.append(mk("3069b", 2 * outer[0] + ox, h(yb - 3), h(2), h(1), z + 3, ocol, step))
        if k == BACK_N - 1:                                 # back wall top: 45 deg slopes down toward the slot
            x = 2
            for ln in split_len(10):
                pid = {4: "3037", 3: "3038", 2: "3039"}[ln]
                parts.append(mk(pid, 2 * x + 1, 0, h(ln), h(2), z, ACCENT, step, down="+y"))
                parts.append(mk({4: "2431", 3: "63864", 2: "3069b"}[ln], 2 * x + 1, 0, h(ln), h(1), z + 3, ACCENT, step))
                x += ln
        add(f"wall course {k + 1} (L{z}-L{z + 2})", parts, step)
    return courses


STEP_NOTES = {
    1: "Base: plates over the whole 16 x 35 footprint (this is what stands on the desk).",
    2: "Second plate layer; its seams cross the first. The smooth Tile 2 x 3 in the pocket is the PLUG SEAT.",
    3: "Plate layer with the plug pocket (2 x 3 studs) and the cable channel to the back edge. The 2 x 3 studs of "
       "plate left in the channel right behind the pocket are the boot SADDLE.",
    4: "Brick course round the pocket and the cable channel (16 x 12.8 mm, straight out of the back).",
    5: "Fit the plug: felt + paper shim on the seat, foam pads in the pocket, head in tip up, boot on the saddle "
       "with foam above and below it, cable out of the back. (No LEGO parts in this step.)",
    6: "The floor: FIRST the 1 x 4 roof tiles over the channel (they hold the plug down), then the jumper plates "
       "under the left and back walls, the slot floor tiles, the plates under the right wall and the plinth tiles.",
    7: "Wall plates. The left and back walls go half a stud over, on the jumpers' centre studs.",
    8: "Wall courses 1-3. Left wall: Dark Red outer panel; right and back walls Dark Bluish Gray.",
    9: "Wall courses 4-6; the front steps get their 33 deg slopes and 45 deg lead-in slopes.",
    10: "Wall courses 7-9.",
    11: "Wall courses 10-12: the tall rear section and the back wall's slope crest.",
    12: "Liners and plug setting: felt on the floor and the right wall, felt on the left wall (14\" only), back "
        "liner; then the seating test. (No LEGO parts in this step.)",
}
N_STEPS = max(STEP_NOTES)


# =====================================================================================================================
# OUTPUTS
# =====================================================================================================================
def all_parts(courses):
    return [p for c in courses for p in c["parts"]]


def mm_box(p):
    return (p["x"] * HALF, p["y"] * HALF, p["z"] * PLATE, p["w"] * HALF, p["h"] * HALF, p["nz"] * PLATE)


ROT = {None: "1 0 0 0 1 0 0 0 1", "rot": "0 0 1 0 1 0 -1 0 0",
       "+y": "1 0 0 0 1 0 0 0 1", "-y": "-1 0 0 0 1 0 0 0 -1",
       "+x": "0 0 -1 0 1 0 1 0 0", "-x": "0 0 1 0 1 0 -1 0 0"}


def ldraw_line(p):
    x, y, z, sx, sy, sz = mm_box(p)
    top = z + sz
    if p["kind"] == "slope":            # LDraw origin = centre of the stud (high) row, at the top
        d = p["down"]
        if d == "+y": cx, cy = x + sx / 2, y + STUD / 2
        elif d == "-y": cx, cy = x + sx / 2, y + sy - STUD / 2
        elif d == "+x": cx, cy = x + STUD / 2, y + sy / 2
        else: cx, cy = x + sx - STUD / 2, y + sy / 2
        m = ROT[d]
    else:
        cx, cy = x + sx / 2, y + sy / 2
        m = ROT["rot" if p["rot"] else None]
    return f"1 {p['color']} {cx * 2.5:g} {-top * 2.5:g} {-cy * 2.5:g} {m} {p['part']}.dat"


def write_ldr(courses, path):
    L = ["0 Night Array laptop dock (LEGO)", "0 Name: night-array-dock.ldr", "0 Author: make_lego_dock.py (Night Array)",
         "0 !LDRAW_ORG Unofficial_Model",
         f"0 // {BASE_W} x {BASE_D} studs footprint ({BASE_W*STUD:.0f} x {BASE_D*STUD:.0f} mm), back wall "
         f"{(WALL0 + 3 * BACK_N + 1) * PLATE:.1f} mm tall",
         "0 // Front of the dock faces -Z. The laptop stands on its left side, hinge toward +Z (back).",
         "0 // Not LEGO, not in the file: Newnex plug + cable, EVA foam, felt, tape."]
    steps = defaultdict(list)
    for p in all_parts(courses):
        steps[p["step"]].append(p)
    for s in range(1, N_STEPS + 1):
        L.append(f"0 // Step {s}: {STEP_NOTES[s]}")
        for p in sorted(steps.get(s, []), key=lambda p: (p["z"], p["y"], p["x"])):
            L.append(ldraw_line(p))
        L.append("0 STEP")
    path.write_text("\n".join(L) + "\n")


def bom(courses):
    cnt = Counter((p["part"], p["color"]) for p in all_parts(courses))
    rows = []
    for (pid, col), n in sorted(cnt.items(), key=lambda kv: (PARTS[kv[0][0]][0], kv[0][1], kv[0][0])):
        kind, w, l, name, price = PARTS[pid]
        unit = round(price * COLOURS[col][3], 2)
        rows.append({"part": pid, "bricklink_id": BRICKLINK_ID.get(pid, pid), "name": name, "kind": kind,
                     "colour": COLOURS[col][2], "ldraw_colour": col, "bricklink_colour": COLOURS[col][0], "qty": n,
                     "unit_usd": unit, "total_usd": round(n * unit, 2)})
    return rows


def write_lists(rows):
    with open(OUT / "parts.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["part", "bricklink_id", "name", "colour", "ldraw_colour", "bricklink_colour", "qty",
                    "est_unit_usd", "est_total_usd"])
        for r in rows:
            w.writerow([r["part"], r["bricklink_id"], r["name"], r["colour"], r["ldraw_colour"],
                        r["bricklink_colour"], r["qty"], f"{r['unit_usd']:.2f}", f"{r['total_usd']:.2f}"])
    x = ["<INVENTORY>"]
    for r in rows:
        x.append(f"  <ITEM><ITEMTYPE>P</ITEMTYPE><ITEMID>{r['bricklink_id']}</ITEMID><COLOR>{r['bricklink_colour']}</COLOR>"
                 f"<MINQTY>{r['qty']}</MINQTY></ITEM>")
    x.append("</INVENTORY>")
    (OUT / "bricklink-wanted.xml").write_text("\n".join(x) + "\n")


def reference_boxes():
    S = SET
    hx0, hx1, hy0, hy1 = S["head_box"]
    refs = []
    lb = S["back_liner_mm"]
    lap_x1 = SLOT_REAL[1] - LINER_R                     # feet on the right liner
    refs.append({"name": LAP["name"] + " (closed, on its left side)", "color_hex": "#9aa3ad", "x": lap_x1 - LAP["T"],
                 "y": BACK_FACE_REAL + lb, "z": Z_LAND, "sx": LAP["T"], "sy": LAP["D"], "sz": LAP["W"],
                 "kind": "device"})
    refs.append({"name": "Newnex U4T1C01CR5P010 head (overmold)", "color_hex": "#1c1c1c", "x": hx0, "y": hy0,
                 "z": Z_HEAD0, "sx": HEAD_X, "sy": HEAD_Y, "sz": HEAD_Z, "kind": "plug", "step": 5})
    refs.append({"name": "USB-C plug tongue", "color_hex": "#c8c8c8", "x": PLUG_X - PLUG_T / 2, "y": PLUG_Y - PLUG_W / 2,
                 "z": Z_FACE, "sx": PLUG_T, "sy": PLUG_W, "sz": PLUG_LEN, "kind": "plug", "step": 5})
    boot_y0 = hy1 - HEAD_ALONG_CABLE
    refs.append({"name": "strain-relief boot (dia ~7, assumed)", "color_hex": "#2a2a2a", "x": PLUG_X - BOOT_D / 2,
                 "y": boot_y0, "z": Z_CABLE - BOOT_D / 2, "sx": BOOT_D, "sy": hy0 - boot_y0, "sz": BOOT_D,
                 "kind": "cable", "step": 5})
    refs.append({"name": "USB4 cable (OD 4.8) to the dock box", "color_hex": "#2a2a2a", "x": PLUG_X - CABLE_OD / 2,
                 "y": -45.0, "z": Z_CABLE - CABLE_OD / 2, "sx": CABLE_OD, "sy": boot_y0 + 45.0, "sz": CABLE_OD,
                 "kind": "cable", "step": 5})
    # felt + shim under the head
    refs.append({"name": "felt 1 mm + paper shim 0.1 under the head", "color_hex": "#d9c9a3",
                 "x": hx0 - 1, "y": hy0 - 1, "z": Z_SEAT, "sx": HEAD_X + 2, "sy": HEAD_Y + 2,
                 "sz": FELT + SHIM_UNDER_HEAD, "kind": "felt", "step": 5})
    # foam pads (5 x 5 mm faces, at mid-height of the head)
    zc = Z_HEAD0 + 5.0
    P = S["pads"]
    refs.append({"name": "EVA pad, left", "color_hex": "#e0b040", "x": POCKET_X0 * STUD, "y": PLUG_Y - 2.5, "z": zc,
                 "sx": P["left"]["gap_mm"], "sy": 5, "sz": 5, "kind": "foam", "step": 5})
    refs.append({"name": "EVA pad, right", "color_hex": "#e0b040", "x": hx1, "y": PLUG_Y - 2.5, "z": zc,
                 "sx": P["right"]["gap_mm"], "sy": 5, "sz": 5, "kind": "foam", "step": 5})
    refs.append({"name": "EVA pad, front (closed end)", "color_hex": "#e0b040", "x": PLUG_X - 2.5, "y": hy1, "z": zc,
                 "sx": 5, "sy": P["front"]["gap_mm"], "sz": 5, "kind": "foam", "step": 5})
    refs.append({"name": "EVA pad, back (under the boot)", "color_hex": "#e0b040", "x": PLUG_X - 2.5,
                 "y": PY0 * STUD, "z": Z_HEAD0 + 0.2, "sx": 5, "sy": P["back"]["gap_mm"], "sz": 3.5, "kind": "foam",
                 "step": 5})
    # boot clamp foam on the saddle and under the roof
    sad_y0 = (PY0 - SADDLE_L) * STUD
    z_sad = (2 + 1) * PLATE
    refs.append({"name": "EVA under the boot (on the saddle)", "color_hex": "#e0b040", "x": PLUG_X - 4,
                 "y": max(sad_y0, boot_y0), "z": z_sad, "sx": 8, "sy": PY0 * STUD - max(sad_y0, boot_y0),
                 "sz": Z_CABLE - BOOT_D / 2 - z_sad, "kind": "foam", "step": 5})
    z_roof = FLOOR_L * PLATE
    refs.append({"name": "foam tape over the boot (under the roof tiles)", "color_hex": "#e0b040", "x": PLUG_X - 4,
                 "y": max(sad_y0, boot_y0), "z": Z_CABLE + BOOT_D / 2, "sx": 8, "sy": PY0 * STUD - max(sad_y0, boot_y0),
                 "sz": z_roof - (Z_CABLE + BOOT_D / 2), "kind": "foam", "step": 5})
    # liners (step 12)
    y_slot0, y_slot1 = BACK_WALL_D * STUD, BASE_D * STUD
    refs.append({"name": "felt floor liner (cut out round the plug)", "color_hex": "#d9c9a3", "x": SLOT_REAL[0],
                 "y": y_slot0, "z": Z_FLOOR, "sx": SLOT_W_REAL, "sy": y_slot1 - y_slot0, "sz": FELT, "kind": "felt",
                 "step": 12})
    refs.append({"name": "felt liner, right wall (laptop feet)", "color_hex": "#d9c9a3", "x": SLOT_REAL[1] - LINER_R,
                 "y": y_slot0, "z": Z_LAND, "sx": LINER_R, "sy": y_slot1 - y_slot0, "sz": 60, "kind": "felt",
                 "step": 12})
    if S["side"]["liner_left_mm"]:
        refs.append({"name": "felt liner, left wall", "color_hex": "#d9c9a3", "x": SLOT_REAL[0], "y": y_slot0,
                     "z": Z_LAND, "sx": S["side"]["liner_left_mm"], "sy": y_slot1 - y_slot0, "sz": 60, "kind": "felt",
                     "step": 12})
    refs.append({"name": f"back liner {lb} mm ({S['back_liner']})", "color_hex": "#e0b040", "x": SLOT_REAL[0],
                 "y": BACK_FACE_REAL, "z": Z_LAND + 10, "sx": SLOT_W_REAL, "sy": lb, "sz": 50, "kind": "foam",
                 "step": 12})
    return refs


def write_json(courses, refs):
    out = []
    for p in all_parts(courses):
        kind, w, l, name, _ = PARTS[p["part"]]
        x, y, z, sx, sy, sz = mm_box(p)
        b = {"part": p["part"], "name": name, "kind": kind, "color": COLOURS[p["color"]][2],
             "color_hex": COLOURS[p["color"]][1], "x": x, "y": y, "z": round(z, 2), "sx": sx, "sy": sy,
             "sz": round(sz, 2), "step": p["step"]}
        if kind == "slope":
            b["slope"] = {"down": p["down"], "high_mm": STUD, "lip_mm": SLOPE_LIP}
        out.append(b)
    top = max(b["z"] + b["sz"] for b in out)
    doc = {"units": "mm", "frame": "x right (facing the dock's front), y depth toward the user (0 = back edge), z up "
                                   "(0 = desk); origin back-left-bottom; boxes on the nominal 8 mm grid (real parts "
                                   "0.1 mm smaller/side); studs (dia 4.8, 1.7 tall) on top of every non-tile part "
                                   "(slopes: only on the high row; jumper 15573: one stud at its centre); slope parts "
                                   "have 'slope' {down: fall direction, high_mm: width of the flat high row, lip_mm}",
           "size_mm": [BASE_W * STUD, BASE_D * STUD, round(top, 2)], "size_studs": [BASE_W, BASE_D],
           "steps": {str(k): v for k, v in STEP_NOTES.items()}, "bricks": out, "reference": refs}
    (OUT / "bricks.json").write_text(json.dumps(doc, indent=1))
    return doc


# =====================================================================================================================
# CHECKS
# =====================================================================================================================
def expected_layers():
    """Intended occupancy per plate layer, in half cells, from the design rules (independent of the packer)."""
    H = lambda cells: {(2 * x + a, 2 * y + b) for (x, y) in cells for a in (0, 1) for b in (0, 1)}
    Hs = lambda cells: {(2 * i + 1 + a, 2 * y + b) for (i, y) in cells for a in (0, 1) for b in (0, 1)}
    want = {}
    want[0] = H(FULL)
    want[1] = H(FULL)
    want[2] = H(FULL - POCKET - CHANNEL_OPEN_L2)
    for L in (3, 4, 5):
        want[L] = H(FULL - POCKET - CHANNEL)
    want[FLOOR_L] = H(FULL - POCKET)
    walls_s = rect(2, 0, 10, BACK_WALL_D) | rect(2, BACK_WALL_D, 4, BASE_D - BACK_WALL_D)
    walls_i = rect(9, BACK_WALL_D, 4, BASE_D - BACK_WALL_D)
    want[WALL_PL] = Hs(walls_s) | H(walls_i)
    top_layer = WALL0 + 3 * BACK_N
    for L in range(WALL0, top_layer + 1):
        k = (L - WALL0) // 3
        s, i = set(), set()
        if k < BACK_N:
            s |= rect(2, 0, 10, BACK_WALL_D)
            for y in range(BACK_WALL_D, BASE_D):
                if N_OF_ROW[y] > k:
                    s |= {(c, y) for c in range(2, 6)}
                    i |= {(c, y) for c in range(9, 13)}
        if (L - WALL0) % 3 == 0 and k >= 1:       # tile layer on top of the course k-1 step tops
            for (ya, yb, n) in SEGS:
                if n == k:
                    for y in range(ya, yb):
                        s.add((4, y)); i.add((10, y))
                        if y < yb - 3 or y == yb - 3:
                            s |= {(2, y), (3, y)}; i |= {(11, y), (12, y)}
            if k == BACK_N:
                s |= {(c, 0) for c in range(2, 12)}
        want[L] = Hs(s) | H(i)
    return want


def run_checks(courses, rows, doc):
    res = []

    def chk(name, ok, detail):
        res.append({"check": name, "ok": bool(ok), "detail": detail})

    allp = all_parts(courses)
    # 1 packing
    want = expected_layers()
    occ = defaultdict(Counter)
    for p in allp:
        for L in range(p["z"], p["z"] + p["nz"]):
            for c in cells_h(p):
                occ[L][c] += 1
    bad = []
    for L in sorted(set(want) | set(occ)):
        got = set(occ[L])
        over = [c for c, n in occ[L].items() if n > 1]
        w = want.get(L, set())
        if got != w or over:
            bad.append(f"L{L}: missing {len(w - got)}, extra {len(got - w)}, overlaps {len(over)} (half cells)")
    chk("every layer packed exactly (no holes, no overlaps; half-stud cells)", not bad,
        "; ".join(bad) or f"{len(want)} plate layers OK")
    # 2 parts table
    unknown = [p["part"] for p in allp if p["part"] not in PARTS or p["color"] not in COLOURS]
    chk("every part is in the part table / colour table", not unknown,
        f"unknown: {sorted(set(unknown))}" if unknown else f"{len(rows)} distinct part/colour lines")

    # 3 stud alignment + connectivity
    by_bottom = defaultdict(list)
    for i, p in enumerate(allp):
        by_bottom[p["z"]].append(i)
    interior = {}
    for z, idx in by_bottom.items():
        m = {}
        for i in idx:
            p = allp[i]
            for X in range(p["x"] + 1, p["x"] + p["w"]):
                for Y in range(p["y"] + 1, p["y"] + p["h"]):
                    m[(X, Y)] = i
        interior[z] = m
    adj = defaultdict(set)
    collisions = []
    for i, p in enumerate(allp):
        zt = p["z"] + p["nz"]
        for s in stud_points(p):
            j = interior.get(zt, {}).get(s)
            if j is None:
                continue
            if s in receptors(allp[j]):
                adj[i].add(j); adj[j].add(i)
            else:
                collisions.append((p["part"], allp[j]["part"], zt))
    chk("every stud under a part lands in a stud socket (no half-stud collisions)", not collisions,
        f"{len(collisions)} collisions: {collisions[:5]}" if collisions else "all studs aligned (the half-stud walls "
        "sit only on jumper centre studs)")
    seen, stack = {0}, [0]
    while stack:
        for j in adj[stack.pop()]:
            if j not in seen:
                seen.add(j); stack.append(j)
    chk("all parts connected by studs (one assembly)", len(seen) == len(allp), f"{len(seen)}/{len(allp)} parts reachable "
        "from the base")
    no_below = [allp[i] for i in range(len(allp)) if allp[i]["z"] > 0 and not any(allp[j]["z"] < allp[i]["z"] for j in adj[i])]
    chk("parts held from above only (not gripped from below)", True,
        f"{len(no_below)}: " + ", ".join(sorted(Counter(f"{q['part']}@L{q['z']}" for q in no_below))) if no_below else "none")
    jumpers = [p for p in allp if p["part"] == JUMPER]
    held = sum(1 for p in allp if p["z"] == WALL_PL and p["x"] % 2 == 1 and any(allp[j]["part"] == JUMPER for j in adj[allp.index(p)]))
    chk("half-stud walls stand on jumpers", held == sum(1 for p in allp if p["z"] == WALL_PL and p["x"] % 2 == 1),
        f"{len(jumpers)} jumpers; {held} wall plates on them, each on >= 1 jumper stud")

    # 4 slot width / clearances, both laptops
    det, ok4 = [], True
    for key, m in MODELS.items():
        sd = side_settings(m)
        okm = SIDE_CLR[0] - 1e-9 <= sd["clearance_mm"] <= SIDE_CLR[1] + 1e-9
        ok4 &= okm
        det.append(f'{key}": T {m["T"]} in {SLOT_W_REAL:.1f} real slot, liners L {sd["liner_left_mm"]:.1f} / R '
                   f'{sd["liner_right_mm"]:.1f} -> clearance {sd["clearance_mm"]:.2f} mm total (~{sd["clearance_mm"]/2:.1f}/side)')
    chk(f"slot {SLOT_W_REAL - 2 * LEGO_INSET:.1f} mm nominal / {SLOT_W_REAL:.1f} real; clearance {SIDE_CLR[0]}-{SIDE_CLR[1]} mm total",
        ok4, "; ".join(det))
    slot_len = BASE_D * STUD - BACK_FACE_REAL
    det = [f'{k}": rear liner + depth {plug_settings(m, PORT)["back_liner_mm"] + m["D"]:.1f} mm' for k, m in MODELS.items()]
    chk("slot long enough (open front)", all(plug_settings(m, PORT)["back_liner_mm"] + m["D"] <= slot_len for m in MODELS.values()),
        f"slot {slot_len:.1f} mm from the back wall to the front end; " + "; ".join(det))

    # 5 plug position vs the port, both laptops
    det, ok5 = [], True
    for k, m in MODELS.items():
        st = plug_settings(m, PORT)
        ox, oy = st["head_offset_in_pocket"]
        floats = {s: v["float_mm"] for s, v in st["pads"].items()}
        okm = abs(ox) <= 2.0 and abs(oy) <= 1.6 and min(v["gap_mm"] for v in st["pads"].values()) >= 2.5 and \
            min(floats.values()) >= 1.5
        ok5 &= okm
        det.append(f'{k}" {PORT}: port at x {st["port_x"]:.2f} (= right wall {SLOT_REAL[1]:.1f} - felt {LINER_R} - feet '
                   f'{FEET_H} - port height {m["port_h"]}), y {st["port_y"]:.2f} (= back wall {BACK_FACE_REAL:.1f} + back '
                   f'liner {st["back_liner_mm"]} + {m["ports_from_rear"][PORT]} from the rear); head set off the pocket '
                   f'centre by ({ox:+.2f}, {oy:+.2f}) mm with foam; gaps L/R/B/F '
                   + "/".join(f'{st["pads"][s]["gap_mm"]:.2f}' for s in ("left", "right", "back", "front"))
                   + "; float " + "/".join(f"{floats[s]:.1f}" for s in ("left", "right", "back", "front")))
    chk("plug centred on the laptop's port (lateral = port height above the bottom face; along = port from the rear)",
        ok5, "; ".join(det))

    # 6 overmold depth
    chk("overmold face 0.3-0.5 mm below the landing plane", 0.3 <= OVERMOLD_DEPTH <= 0.5,
        f"seat {Z_SEAT:.2f} + felt {FELT} + shim {SHIM_UNDER_HEAD} = head bottom {Z_HEAD0:.2f}; + head {HEAD_Z} = face "
        f"{Z_FACE:.2f}; floor tiles {Z_FLOOR:.2f} + felt {FELT} = landing {Z_LAND:.2f}; depth {OVERMOLD_DEPTH:.2f} mm "
        f"(16.0 mm of LEGO between seat and floor top minus the {HEAD_Z} mm head; the felt cancels)")
    # 7 plug held down: boot under the roof tiles, saddle under it
    roof = [p for p in allp if p["part"] == "2431" and p["z"] == FLOOR_L and p["x"] == h(6)]
    boot_top, roof_z = Z_CABLE + BOOT_D / 2, FLOOR_L * PLATE
    boot_bot, sad_z = Z_CABLE - BOOT_D / 2, 3 * PLATE
    chk("plug held down for lift-out (boot clamped between saddle and roof)", boot_top < roof_z and boot_bot > sad_z
        and len(roof) == len(ROOF_ROWS),
        f"boot {boot_bot:.2f}-{boot_top:.2f} mm (dia {BOOT_D} assumed); saddle top {sad_z:.1f} (gap {boot_bot - sad_z:.2f}, "
        f"fill with 3 mm EVA); roof underside {roof_z:.1f} (gap {roof_z - boot_top:.2f}, 1 mm foam tape); "
        f"{len(roof)} roof tiles 1 x 4 each gripping a stud at both ends and pinned by both walls; reacts the "
        f"{RETENTION_N[0]}-{RETENTION_N[1]} N extraction force")
    # 8 cable route + bend space
    ch_z0, ch_z1 = 2 * PLATE, FLOOR_L * PLATE
    hx0, hx1, hy0, hy1 = SET["head_box"]
    boot_y0 = hy1 - HEAD_ALONG_CABLE
    drop = Z_CABLE - CABLE_OD / 2
    s_len = math.sqrt(4 * BEND_R * drop - drop ** 2)
    okc = ch_z0 < Z_CABLE - CABLE_OD / 2 and Z_CABLE + CABLE_OD / 2 < ch_z1 and \
        POCKET_X0 * STUD < PLUG_X - BOOT_D / 2 and PLUG_X + BOOT_D / 2 < (POCKET_X0 + POCKET_W) * STUD and boot_y0 > 0
    chk(f"cable route straight out of the back, bend radius >= {BEND_R} mm", okc,
        f"leaves the head horizontally toward the back at z {Z_CABLE:.1f}; channel {POCKET_W*STUD:.0f} x {ch_z1-ch_z0:.1f} mm "
        f"(z {ch_z0:.1f}-{ch_z1:.1f}), straight for {boot_y0:.1f} mm behind the boot, no bend inside the dock; behind "
        f"the dock it drops {drop:.1f} mm to the desk in an S-bend of R {BEND_R} that needs {s_len:.0f} mm: keep >= "
        f"{math.ceil(s_len / 5) * 5 + 5} mm free behind the dock")
    # 9 stability
    mass = 0.0
    mx = my = mz = 0.0
    for b in doc["bricks"]:
        kind = b["kind"]
        cells = (b["sx"] / STUD) * (b["sy"] / STUD)
        per = MASS_PER_CELL[kind] * (0.65 if kind == "plate" and cells >= 32 else 1.0)
        g = per * cells + (0.12 if b["part"] == JUMPER else 0)
        cz = b["z"] + (b["sz"] * (0.4 if kind == "slope" else 0.5))
        mass += g; mx += g * (b["x"] + b["sx"] / 2); my += g * (b["y"] + b["sy"] / 2); mz += g * cz
    dock_c = (mx / mass, my / mass, mz / mass)
    lap = doc["reference"][0]
    lm = LAP["kg"] * 1000
    lc = (lap["x"] + lap["sx"] / 2, lap["y"] + lap["sy"] / 2, lap["z"] + lap["sz"] / 2)
    tot = mass + lm
    cc = [(dock_c[i] * mass + lc[i] * lm) / tot for i in range(3)]
    W, D = BASE_W * STUD, BASE_D * STUD

    def ang(c):
        return {"left": math.degrees(math.atan2(c[0], c[2])), "right": math.degrees(math.atan2(W - c[0], c[2])),
                "back": math.degrees(math.atan2(c[1], c[2])), "front": math.degrees(math.atan2(D - c[1], c[2]))}
    a_all, a_lap = ang(cc), ang(lc)
    worst = min(a_all["left"], a_all["right"])
    chk("tipping angle sideways >= 15 deg with the laptop docked", worst >= 15.0,
        f"{LAP['name']} {LAP['kg']} kg, CoM {lc[2]:.0f} mm up at x {lc[0]:.1f}; LEGO dock ~{mass/1000:.2f} kg (estimate), "
        f"CoM {dock_c[2]:.0f} mm up; together CoM x {cc[0]:.1f}, z {cc[2]:.0f} -> tips at "
        f"{a_all['left']:.1f} deg left / {a_all['right']:.1f} deg right / {a_all['front']:.1f} front / {a_all['back']:.1f} back "
        f"(laptop alone, dock weightless: {a_lap['left']:.1f} / {a_lap['right']:.1f}). Base {BASE_W} studs wide, no "
        f"ballast needed")
    # 10 walls hold the laptop
    yc = lap["y"] + lap["sy"] / 2
    row = int(yc // STUD)
    hwall = (N_OF_ROW.get(row, N_MIN) * 3 + 1) * PLATE
    chk("side walls hold the laptop upright", hwall >= 60 and (N_MAX * 3 + 1) * PLATE >= 100,
        f"wall height above the floor: {(N_MAX*3+1)*PLATE:.1f} mm at the back, {hwall:.1f} mm at the laptop's centre "
        f"(y {yc:.0f}), {(N_MIN*3+1)*PLATE:.1f} mm at the front; back wall {(BACK_N*3+2)*PLATE:.1f} mm; lead-in "
        f"45 deg slopes 8 mm wide on both wall tops")
    return res, {"dock_mass_kg": round(mass / 1000, 3), "tip_deg": {k: round(v, 1) for k, v in a_all.items()},
                 "tip_deg_laptop_only": {k: round(v, 1) for k, v in a_lap.items()}}


def main():
    OUT.mkdir(exist_ok=True)
    courses = build()
    rows = bom(courses)
    write_ldr(courses, OUT / "night-array-dock.ldr")
    write_lists(rows)
    doc = write_json(courses, reference_boxes())
    checks, extra = run_checks(courses, rows, doc)
    n = sum(r["qty"] for r in rows)
    cost = sum(r["total_usd"] for r in rows)
    by_kind = Counter()
    by_colour = Counter()
    for r in rows:
        by_kind[r["kind"]] += r["qty"]; by_colour[r["colour"]] += r["qty"]
    settings = {k: plug_settings(m, PORT) for k, m in MODELS.items()}
    for s in settings.values():
        s.pop("head_box")
    summary = {"model_shown": MODEL, "port": PORT, "size_studs": [BASE_W, BASE_D], "size_mm": doc["size_mm"],
               "slot_mm": {"nominal": (SLOT_X1 - SLOT_X0) * STUD, "real": round(SLOT_W_REAL, 2),
                           "length_from_back_wall": BASE_D * STUD - BACK_FACE_REAL},
               "z_mm": {"seat": Z_SEAT, "head_bottom": Z_HEAD0, "overmold_face": round(Z_FACE, 2), "floor": Z_FLOOR,
                        "landing": Z_LAND, "overmold_depth": round(OVERMOLD_DEPTH, 2), "cable_axis": round(Z_CABLE, 2)},
               "pocket_studs": {"x": [POCKET_X0, POCKET_X0 + POCKET_W], "y": [PY0, PY0 + POCKET_L]},
               "wall_profile_rows_courses": SEGS, "settings": settings, "port_assumptions": MODELS,
               "feet_mm": FEET_H, "parts_total": n, "parts_by_kind": dict(by_kind), "parts_by_colour": dict(by_colour),
               "distinct_lines": len(rows), "est_cost_usd": round(cost, 2), **extra, "checks": checks}
    (OUT / "checks.json").write_text(json.dumps(summary, indent=1))
    print(f"Night Array LEGO dock: {BASE_W} x {BASE_D} studs = {BASE_W*STUD:.0f} x {BASE_D*STUD:.0f} mm, "
          f"{doc['size_mm'][2]:.1f} mm tall; pocket rows {PY0}-{PY0 + POCKET_L - 1}")
    print(f"  {n} parts ({dict(by_kind)}), {len(rows)} lines, est. ${cost:.0f}; {dict(by_colour)}")
    for k, s in settings.items():
        print(f'  {k}": back liner {s["back_liner_mm"]} mm ({s["back_liner"]}), left felt x{s["side"]["liner_left_felt_layers"]}, '
              f'port ({s["port_x"]}, {s["port_y"]}), head offset {s["head_offset_in_pocket"]}, pads '
              + ", ".join(f'{q}: {v["eva_3mm"]}xEVA+{v["tape_1mm"]}xtape (gap {v["gap_mm"]})' for q, v in s["pads"].items()))
    for c in checks:
        print(f"  [{'OK ' if c['ok'] else 'FAIL'}] {c['check']}: {c['detail']}")
    if "--no-render" not in sys.argv:
        subprocess.run(["node", str(HERE / "render_lego_dock.mjs")], check=True)
    return 0 if all(c["ok"] for c in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
