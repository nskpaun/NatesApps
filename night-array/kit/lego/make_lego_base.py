#!/usr/bin/env python3
"""Night Array -- LEGO version of the "pocket section" desk tray (keyboard pocket + mouse pocket, Qi pads underneath).

Plain python3, no external dependencies.  Run from anywhere:

    python3 night-array/kit/lego/make_lego_base.py              # model + lists + checks + renders
    python3 night-array/kit/lego/make_lego_base.py --no-render  # skip the PNGs (needs node + playwright otherwise)

Writes, next to this script:
    night-array-base.ldr   LDraw model, one STEP per build step (open in BrickLink Studio / LeoCAD / LDCad)
    parts.csv              part list (LDraw/BrickLink id, name, colour, qty, est. unit price)
    bricklink-wanted.xml   BrickLink wanted-list upload (ITEMTYPE P, BrickLink colour ids)
    bricks.json            every part as a box (mm) + reference boxes (keyboard, mouse, pads, Magic Tag) for a viewer
    checks.json            the self-check results printed at the end
    steps/step-XX.png, overview.png, exploded.png   (via render_lego.mjs: headless Chromium + three.js)

Frames
    Grid / bricks.json: x to the right as you sit at the desk, y DEPTH TOWARD YOU (0 = back edge of the tray),
    z up (0 = underside).  Origin = back-left-bottom corner.  1 stud = 8.0 mm, 1 plate = 3.2 mm.
    Boxes are nominal (on the 8 mm grid); real LEGO parts are 0.1 mm smaller per side.
    LDraw: X = x * 2.5 (20 LDU per stud), Y = -z * 2.5 (-Y is up), Z = -y * 2.5 (the front of the tray faces -Z,
    i.e. the LDraw "front" view looks at the side you sit at).

Vertical stack (plate layers L0..L13, 14 x 3.2 = 44.8 mm; the printed tray is 44.0):
    L0        base plates, whole footprint (flat underside, big plates tie everything together)
    L1        plates, whole footprint, seams staggered against L0.  The pads' foam sits on L1.
    L2-L4     brick course; holes = the two pad cavities + their cable channels to the back edge
    L5        plates, same holes
    L6        THE floor layer: one 3.2 mm layer of tiles over each pad (8 x 16 tiles spanning the cavity and
              clutching the L5 studs round it), black tiles on the rest of the pocket floors, plates under the walls
    L7-L9     brick course (walls)
    L10-L12   brick course (walls)
    L13       tiles on all wall tops (Light Bluish Gray ring round the pockets, Dark Bluish Gray elsewhere)
    Pad: foam 1.6 mm on L1 (z 6.4-8.0), pad z 8.0-19.2 -> its top touches the underside of the L6 tiles.
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

# =====================================================================================================================
# PARAMETERS (mm unless noted).  Device data copied from ../poc/pocket_section.py (verified there).
# =====================================================================================================================
STUD, PLATE = 8.0, 3.2
LEGO_INSET = 0.1         # real LEGO parts are 0.1 mm smaller per side than the grid -> pockets 0.2 mm larger

KB_W, KB_D = 320.62, 126.0          # Keychron K3 Ultra 8K
KB_H_FRONT, KB_H_REAR = 20.0, 25.5
KB_PORT_FROM_REAR = 23.0            # USB-C centre (left side face) from the rear edge
TAG_STICKOUT = 10.0                 # NILLKIN Magic Tag plug + fold beyond the keyboard's left face
TAG_PAD = (48.0, 82.0, 1.0)         # receiver pad as it lies under the keyboard
TAG_COIL_FROM_LEFT, TAG_COIL_FROM_REAR = 48.0, 38.0   # ESTIMATED receiver coil centre
MOUSE_W, MOUSE_L, MOUSE_H = 59.0, 101.0, 34.0         # Lenovo X9
MOUSE_COIL_DX, MOUSE_COIL_DY = 0.0, 0.0            # coil offset from the mouse's plan centre: UNKNOWN, assumed 0
PAD_W, PAD_H = 100.0, 11.2          # Anker 313 pad (square)
PAD_CLR = 1.0                       # min. clearance round the pad in its cavity, per side
MIN_CLR = 1.5                       # min. device-to-pocket-wall clearance per side

# Layout, in studs
TRAY_W, TRAY_D = 61, 26             # 488 x 208 mm (printed tray: 487 x 205)
LEFT_WALL = 3                       # keyboard pocket starts here (x)
KB_BACK_WALL = 6                    # keyboard pocket starts here (y, from the back edge)
MID_WALL = 4                        # wall between the keyboard and mouse pockets
TAG_NOTCH_DEPTH = 1                 # Magic Tag relief into the keyboard pocket's left wall (studs)
TAG_NOTCH_LEN = 5                   # its length along y (studs), centred on the USB-C port
FINGER_NOTCH = (4, 2)               # keyboard front-wall finger notches: width x depth (studs), floor = pocket floor
FINGER_NOTCH_IN = 45.0              # notch centre from the keyboard's left / right edge (mm)

# Vertical, in plates
N_LAYERS = 14
FLOOR_L = 6                         # the tile layer the devices stand on (its top = pocket floor)
CAVITY_LAYERS = range(2, 6)         # pad cavity + cable channels
FOAM = 1.6                          # foam under each pad (e.g. 2 mm EVA squares, squeezed) -- mm

# LDraw colour, BrickLink colour id, hex, name
COLOURS = {
    72: (85, "#6c6e68", "Dark Bluish Gray"),
    0: (11, "#1b2a34", "Black"),
    71: (86, "#a0a5a9", "Light Bluish Gray"),
}
BODY, FLOORC, RIM = 72, 0, 71

# Part table: ldraw id -> (kind, w, l (studs, long side along LDraw X), name, est. USD each).  BrickLink ids are
# the same as the LDraw ids for all of these (3068b/3069b/3070b keep the 'b').  Every id was checked against the
# official LDraw library (header line of the .dat).  Prices: rough BrickLink averages (used/new mix) in the colours
# above, Nov 2026 -- treat as +/- 40 %, shipping not included.
PARTS = {
    # bricks
    "3005": ("brick", 1, 1, "Brick 1 x 1", 0.06), "3004": ("brick", 1, 2, "Brick 1 x 2", 0.06),
    "3622": ("brick", 1, 3, "Brick 1 x 3", 0.08), "3010": ("brick", 1, 4, "Brick 1 x 4", 0.09),
    "3009": ("brick", 1, 6, "Brick 1 x 6", 0.14), "3008": ("brick", 1, 8, "Brick 1 x 8", 0.20),
    "3003": ("brick", 2, 2, "Brick 2 x 2", 0.08), "3002": ("brick", 2, 3, "Brick 2 x 3", 0.10),
    "3001": ("brick", 2, 4, "Brick 2 x 4", 0.12), "2456": ("brick", 2, 6, "Brick 2 x 6", 0.22),
    "3007": ("brick", 2, 8, "Brick 2 x 8", 0.30), "3006": ("brick", 2, 10, "Brick 2 x 10", 0.55),
    # plates
    "3024": ("plate", 1, 1, "Plate 1 x 1", 0.03), "3023": ("plate", 1, 2, "Plate 1 x 2", 0.04),
    "3623": ("plate", 1, 3, "Plate 1 x 3", 0.05), "3710": ("plate", 1, 4, "Plate 1 x 4", 0.06),
    "3666": ("plate", 1, 6, "Plate 1 x 6", 0.08), "3460": ("plate", 1, 8, "Plate 1 x 8", 0.12),
    "3022": ("plate", 2, 2, "Plate 2 x 2", 0.05), "3021": ("plate", 2, 3, "Plate 2 x 3", 0.06),
    "3020": ("plate", 2, 4, "Plate 2 x 4", 0.08), "3795": ("plate", 2, 6, "Plate 2 x 6", 0.12),
    "3034": ("plate", 2, 8, "Plate 2 x 8", 0.18), "3832": ("plate", 2, 10, "Plate 2 x 10", 0.25),
    "2445": ("plate", 2, 12, "Plate 2 x 12", 0.30),
    "3031": ("plate", 4, 4, "Plate 4 x 4", 0.20), "3032": ("plate", 4, 6, "Plate 4 x 6", 0.30),
    "3035": ("plate", 4, 8, "Plate 4 x 8", 0.40), "3030": ("plate", 4, 10, "Plate 4 x 10", 0.55),
    "3029": ("plate", 4, 12, "Plate 4 x 12", 0.65),
    "3958": ("plate", 6, 6, "Plate 6 x 6", 0.45), "3036": ("plate", 6, 8, "Plate 6 x 8", 0.55),
    "3033": ("plate", 6, 10, "Plate 6 x 10", 0.70), "3028": ("plate", 6, 12, "Plate 6 x 12", 0.80),
    "3027": ("plate", 6, 16, "Plate 6 x 16", 1.30), "41539": ("plate", 8, 8, "Plate 8 x 8", 1.10),
    "92438": ("plate", 8, 16, "Plate 8 x 16", 2.20), "91405": ("plate", 16, 16, "Plate 16 x 16", 4.00),
    # tiles
    "3070b": ("tile", 1, 1, "Tile 1 x 1 with Groove", 0.04), "3069b": ("tile", 1, 2, "Tile 1 x 2 with Groove", 0.05),
    "63864": ("tile", 1, 3, "Tile 1 x 3", 0.08), "2431": ("tile", 1, 4, "Tile 1 x 4 with Groove", 0.10),
    "6636": ("tile", 1, 6, "Tile 1 x 6", 0.15), "4162": ("tile", 1, 8, "Tile 1 x 8", 0.25),
    "3068b": ("tile", 2, 2, "Tile 2 x 2 with Groove", 0.07), "26603": ("tile", 2, 3, "Tile 2 x 3", 0.15),
    "87079": ("tile", 2, 4, "Tile 2 x 4", 0.15), "69729": ("tile", 2, 6, "Tile 2 x 6", 0.30),
    "90498": ("tile", 8, 16, "Tile 8 x 16 with Bottom Tubes", 7.00),
}
HEIGHT = {"brick": 3, "plate": 1, "tile": 1}
BRICK_SET = [p for p, v in PARTS.items() if v[0] == "brick"]
PLATE_SET = [p for p, v in PARTS.items() if v[0] == "plate"]
TILE_SET = [p for p, v in PARTS.items() if v[0] == "tile" and p != "90498"]   # 8x16 tiles are placed by hand

# =====================================================================================================================
# GEOMETRY
# =====================================================================================================================
def studs_for(dev):
    return math.ceil((dev + 2 * MIN_CLR) / STUD - 1e-9)


KB_NX, KB_NY = studs_for(KB_W), studs_for(KB_D)
MS_NX, MS_NY = studs_for(MOUSE_W), studs_for(MOUSE_L)
KB_X0, KB_Y0 = LEFT_WALL, KB_BACK_WALL
MS_X0 = KB_X0 + KB_NX + MID_WALL
MS_Y0 = math.floor(KB_Y0 + KB_NY / 2 - MS_NY / 2 + 0.5)     # mouse pocket centred on the keyboard pocket (y)
RIGHT_WALL = TRAY_W - MS_X0 - MS_NX
FRONT_WALL = TRAY_D - KB_Y0 - KB_NY

# devices, centred in their pockets (mm)
KB_CLR_X, KB_CLR_Y = (KB_NX * STUD - KB_W) / 2, (KB_NY * STUD - KB_D) / 2
MS_CLR_X, MS_CLR_Y = (MS_NX * STUD - MOUSE_W) / 2, (MS_NY * STUD - MOUSE_L) / 2
KB_DEV = (KB_X0 * STUD + KB_CLR_X, KB_Y0 * STUD + KB_CLR_Y)          # keyboard back-left corner
MS_DEV = (MS_X0 * STUD + MS_CLR_X, MS_Y0 * STUD + MS_CLR_Y)
KB_COIL = (KB_DEV[0] + TAG_COIL_FROM_LEFT, KB_DEV[1] + TAG_COIL_FROM_REAR)
MS_COIL = (MS_DEV[0] + MOUSE_W / 2 + MOUSE_COIL_DX, MS_DEV[1] + MOUSE_L / 2 + MOUSE_COIL_DY)

CAV_N = math.ceil((PAD_W + 2 * PAD_CLR) / STUD)                     # 13 studs = 104 mm


def cavity_start(coil_mm):
    return math.floor(coil_mm / STUD - CAV_N / 2 + 0.5)


def make_pad(coil):
    cx, cy = cavity_start(coil[0]), cavity_start(coil[1])
    centre = ((cx + CAV_N / 2) * STUD, (cy + CAV_N / 2) * STUD)        # pad centred in its cavity
    return {"cav": (cx, cy, CAV_N, CAV_N), "centre": centre, "coil": coil,
            "offset": (centre[0] - coil[0], centre[1] - coil[1])}


KB_PADI, MS_PADI = make_pad(KB_COIL), make_pad(MS_COIL)


def rect(x0, y0, w, h):
    return {(x, y) for x in range(x0, x0 + w) for y in range(y0, y0 + h)}


FULL = rect(0, 0, TRAY_W, TRAY_D)
KB_POCKET = rect(KB_X0, KB_Y0, KB_NX, KB_NY)
MS_POCKET = rect(MS_X0, MS_Y0, MS_NX, MS_NY)
port_y = (KB_DEV[1] + KB_PORT_FROM_REAR) / STUD
TAG_NOTCH = rect(KB_X0 - TAG_NOTCH_DEPTH, math.floor(port_y - TAG_NOTCH_LEN / 2 + 0.5), TAG_NOTCH_DEPTH, TAG_NOTCH_LEN)
FINGER_NOTCHES = set()
for cx_mm in (KB_DEV[0] + FINGER_NOTCH_IN, KB_DEV[0] + KB_W - FINGER_NOTCH_IN):
    FINGER_NOTCHES |= rect(math.floor(cx_mm / STUD - FINGER_NOTCH[0] / 2 + 0.5), KB_Y0 + KB_NY, *FINGER_NOTCH)
POCKETS = KB_POCKET | MS_POCKET | TAG_NOTCH | FINGER_NOTCHES      # open above the floor layer
WALLS = FULL - POCKETS


def channel(padi):
    """Cable channel from the cavity's back edge straight to the tray's back edge (also an LED sight line)."""
    c = padi["centre"][0] / STUD
    w = 3 if abs(c - round(c)) > 0.25 else 2
    x0 = math.floor(c - w / 2 + 0.5) if w == 2 else math.floor(c - 1.5 + 0.5)
    return rect(x0, 0, w, padi["cav"][1]), (x0, w)


KB_CAV, MS_CAV = rect(*KB_PADI["cav"]), rect(*MS_PADI["cav"])
KB_CH, KB_CHX = channel(KB_PADI)
MS_CH, MS_CHX = channel(MS_PADI)
HOLES = KB_CAV | MS_CAV | KB_CH | MS_CH

# 8 x 16 tiles over the pads (placed by hand).  Keyboard: two side by side, 16 long in y; mouse: one, 8 wide = pocket.
BIG_TILES = []
kx, ky = KB_PADI["cav"][0] - 1, KB_PADI["cav"][1] - 1
BIG_TILES += [(kx, ky, 8, 16), (kx + 8, ky, 8, 16)]
BIG_TILES += [(MS_X0, MS_PADI["cav"][1] - 1, 8, 16)]


def pad_cells(padi):
    """Cells the pad's square footprint overlaps."""
    cx, cy = padi["centre"]
    x0, x1, y0, y1 = cx - PAD_W / 2, cx + PAD_W / 2, cy - PAD_W / 2, cy + PAD_W / 2
    return {(x, y) for x in range(math.floor(x0 / STUD), math.ceil(x1 / STUD))
            for y in range(math.floor(y0 / STUD), math.ceil(y1 / STUD))}


def dev_cells(dev, w, d):
    x0, y0 = dev
    return {(x, y) for x in range(math.floor(x0 / STUD), math.ceil((x0 + w) / STUD))
            for y in range(math.floor(y0 / STUD), math.ceil((y0 + d) / STUD))}


# =====================================================================================================================
# PACKER
# =====================================================================================================================
def edges_of(cells):
    """Boundary unit edges of a cell set: ('v', x, y) is the edge left of cell (x, y); ('h', x, y) above it."""
    out = set()
    for (x, y) in cells:
        if (x - 1, y) not in cells: out.add(("v", x, y))
        if (x + 1, y) not in cells: out.add(("v", x + 1, y))
        if (x, y - 1) not in cells: out.add(("h", x, y))
        if (x, y + 1) not in cells: out.add(("h", x, y + 1))
    return out


def seams(parts):
    """Internal seams of a packed course: edges shared by two different parts."""
    cnt = Counter()
    for p in parts:
        for e in edges_of(rect(p["x"], p["y"], p["w"], p["h"])):
            cnt[e] += 1
    return {e for e, n in cnt.items() if n >= 2}


def pack(region, part_ids, below_seams, prefer, colour, fixed=()):
    """Try the four scan directions (mirror x / y) and keep the packing with the fewest continued seams + parts."""
    best = None
    for fx in (False, True):
        for fy in (False, True):
            tf = lambda c, fx=fx, fy=fy: (TRAY_W - 1 - c[0] if fx else c[0], TRAY_D - 1 - c[1] if fy else c[1])
            def te(e, fx=fx, fy=fy):
                k, x, y = e
                if k == "v": return ("v", TRAY_W - x if fx else x, TRAY_D - 1 - y if fy else y)
                return ("h", TRAY_W - 1 - x if fx else x, TRAY_D - y if fy else y)
            parts = _pack({tf(c) for c in region}, part_ids, {te(e) for e in below_seams}, prefer, colour)
            for p in parts:   # back to the real frame
                if fx: p["x"] = TRAY_W - p["x"] - p["w"]
                if fy: p["y"] = TRAY_D - p["y"] - p["h"]
            hits = len(seams(list(fixed) + parts) & below_seams)
            score = hits + 2 * len(parts)
            if best is None or score < best[0]:
                best = (score, parts)
    return best[1]


def _pack(region, part_ids, below_seams, prefer, colour, fixed=()):
    """Greedy: scan the region (row- or column-major), at each first free cell place the candidate (any part, either
    orientation, anchored at that cell) with the best score = area - 1.5 * (edges that would continue a seam of the
    course below) + a small bonus for the preferred long axis.  1x1 always fits, so the region is filled exactly."""
    free = set(region)
    placed = []
    for f in fixed:
        placed.append(f)
        free -= rect(f["x"], f["y"], f["w"], f["h"])
    cands = []
    for pid in part_ids:
        _, w, l, _, _ = PARTS[pid]
        cands.append((pid, l, w, False))          # long side along x (no rotation)
        if w != l:
            cands.append((pid, w, l, True))       # long side along y (rotated 90 deg)
    order = sorted(free, key=(lambda c: (c[1], c[0])) if prefer == "x" else (lambda c: (c[0], c[1])))
    for c in order:
        if c not in free:
            continue
        best, bscore = None, -1e9
        for pid, cw, ch, rot in cands:
            cells = rect(c[0], c[1], cw, ch)
            if not cells <= free:
                continue
            hits = len(edges_of(cells) & below_seams)
            score = cw * ch - 1.5 * hits + (0.6 if (cw > ch) == (prefer == "x") and cw != ch else 0)
            if score > bscore:
                best, bscore = (pid, cw, ch, rot, cells), score
        pid, cw, ch, rot, cells = best
        placed.append({"part": pid, "x": c[0], "y": c[1], "w": cw, "h": ch, "rot": rot, "color": colour})
        free -= cells
    return placed


# =====================================================================================================================
# BUILD
# =====================================================================================================================
def build():
    courses = []   # each: dict(name, z (plates), kind, step, parts)

    def add(name, z, kind, step, parts):
        for p in parts:
            p["z"], p["kind"], p["step"] = z, PARTS[p["part"]][0], step
        courses.append({"name": name, "z": z, "kind": kind, "step": step, "parts": parts})
        return parts

    prev = set()
    c = add("L0 base plates", 0, "plate", 1, pack(FULL, PLATE_SET, prev, "x", BODY)); prev = seams(c)
    c = add("L1 plates", 1, "plate", 2, pack(FULL, PLATE_SET, prev, "y", BODY)); prev = seams(c)
    c = add("L2-L4 bricks round the pad cavities", 2, "brick", 3, pack(FULL - HOLES, BRICK_SET, prev, "x", BODY)); prev = seams(c)
    c = add("L5 plates", 5, "plate", 4, pack(FULL - HOLES, PLATE_SET, prev, "y", BODY)); prev = seams(c)
    big = [{"part": "90498", "x": x, "y": y, "w": w, "h": h, "rot": h > w, "color": FLOORC} for (x, y, w, h) in BIG_TILES]
    bigcells = set().union(*(rect(b["x"], b["y"], b["w"], b["h"]) for b in big))
    add("L6 8x16 tiles over the pads", FLOOR_L, "tile", 6, big)
    floor_tiles = pack(POCKETS - bigcells, TILE_SET, prev, "x", FLOORC)
    floor_plates = pack(FULL - POCKETS - bigcells, PLATE_SET, prev, "x", BODY)
    add("L6 pocket floor tiles + plates under the walls", FLOOR_L, "mixed", 7, floor_tiles + floor_plates)
    prev = seams(big + floor_tiles + floor_plates)
    c = add("L7-L9 wall bricks", 7, "brick", 8, pack(WALLS, BRICK_SET, prev, "y", BODY)); prev = seams(c)
    c = add("L10-L12 wall bricks", 10, "brick", 9, pack(WALLS, BRICK_SET, prev, "x", BODY)); prev = seams(c)
    ring = {(x, y) for (x, y) in WALLS if any((x + dx, y + dy) in POCKETS for dx in (-1, 0, 1) for dy in (-1, 0, 1))}
    top = pack(ring, TILE_SET, prev, "y", RIM) + pack(WALLS - ring, TILE_SET, prev, "y", BODY)
    add("L13 top tiles (rim)", 13, "tile", 10, top)
    return courses


STEP_NOTES = {
    1: "Base: big plates over the whole footprint (studs up). This is what rests on the desk.",
    2: "Second plate layer over the whole footprint; its seams cross the base's seams.",
    3: "Brick course (3 plates) leaving the two 13x13-stud pad cavities and the cable channels to the back edge.",
    4: "Plate layer on the bricks, same holes. Its studs round each cavity are what the 8x16 floor tiles grip.",
    5: "Fit the pads: foam on the cavity floor, pad on the foam (micro-USB edge toward the channel), cable out the back.",
    6: "Charging floor: 8x16 tiles over each pad (2 for the keyboard, 1 for the mouse), gripping the studs round the cavity.",
    7: "Rest of the floor layer: black tiles in the pockets, plates under the walls (they tie the floor tiles in).",
    8: "First wall course (bricks) round the pockets.",
    9: "Second wall course, joints crossing the first.",
    10: "Top tiles: Light Bluish Gray ring round the pockets, Dark Bluish Gray elsewhere.",
}


# =====================================================================================================================
# OUTPUTS
# =====================================================================================================================
def all_parts(courses):
    return [p for c in courses for p in c["parts"]]


def write_ldr(courses, path):
    L = ["0 Night Array pocket section base (LEGO)", "0 Name: night-array-base.ldr",
         "0 Author: make_lego_base.py (Night Array)", "0 !LDRAW_ORG Unofficial_Model",
         f"0 // {TRAY_W} x {TRAY_D} studs, {N_LAYERS} plates high ({TRAY_W*STUD:.0f} x {TRAY_D*STUD:.0f} x {N_LAYERS*PLATE:.1f} mm)",
         "0 // Front of the tray (the side you sit at) faces -Z. Pads, foam and cables are not LEGO and are not in the file."]
    steps = defaultdict(list)
    for p in all_parts(courses):
        steps[p["step"]].append(p)
    for s in range(1, max(STEP_NOTES) + 1):
        L.append(f"0 // Step {s}: {STEP_NOTES[s]}")
        for p in sorted(steps.get(s, []), key=lambda p: (p["y"], p["x"])):
            X = (p["x"] + p["w"] / 2) * 20
            Z = -(p["y"] + p["h"] / 2) * 20
            Y = -(p["z"] + HEIGHT[p["kind"]]) * 8
            m = "0 0 1 0 1 0 -1 0 0" if p["rot"] else "1 0 0 0 1 0 0 0 1"
            L.append(f"1 {p['color']} {X:g} {Y:g} {Z:g} {m} {p['part']}.dat")
        L.append("0 STEP")
    path.write_text("\n".join(L) + "\n")


def bom(courses):
    cnt = Counter((p["part"], p["color"]) for p in all_parts(courses))
    rows = []
    for (pid, col), n in sorted(cnt.items(), key=lambda kv: (PARTS[kv[0][0]][0], kv[0][1], kv[0][0])):
        kind, w, l, name, price = PARTS[pid]
        rows.append({"part": pid, "bricklink_id": pid, "name": name, "kind": kind, "colour": COLOURS[col][2],
                     "ldraw_colour": col, "bricklink_colour": COLOURS[col][0], "qty": n, "unit_usd": price,
                     "total_usd": round(n * price, 2)})
    return rows


def write_lists(rows):
    with open(HERE / "parts.csv", "w", newline="") as f:
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
    (HERE / "bricklink-wanted.xml").write_text("\n".join(x) + "\n")


def reference_boxes():
    z_floor = (FLOOR_L + 1) * PLATE
    z_pad = (FLOOR_L) * PLATE - PAD_H
    refs = []
    refs.append({"name": "Keychron K3 Ultra (keyboard)", "color_hex": "#3a3f47", "x": KB_DEV[0], "y": KB_DEV[1],
                 "z": z_floor, "sx": KB_W, "sy": KB_D, "sz": (KB_H_FRONT + KB_H_REAR) / 2, "kind": "device"})
    refs.append({"name": "Lenovo X9 (mouse)", "color_hex": "#2d3138", "x": MS_DEV[0], "y": MS_DEV[1], "z": z_floor,
                 "sx": MOUSE_W, "sy": MOUSE_L, "sz": MOUSE_H, "kind": "device"})
    for nm, pi in (("Anker 313 pad (keyboard)", KB_PADI), ("Anker 313 pad (mouse)", MS_PADI)):
        cx, cy = pi["centre"]
        refs.append({"name": nm, "color_hex": "#f2f2f2", "x": cx - PAD_W / 2, "y": cy - PAD_W / 2, "z": z_pad,
                     "sx": PAD_W, "sy": PAD_W, "sz": PAD_H, "kind": "pad", "step": 5})
        for dx in (-25, 25):
            for dy in (-25, 25):
                refs.append({"name": "foam square 20x20", "color_hex": "#e0b040", "x": cx + dx - 10, "y": cy + dy - 10,
                             "z": z_pad - FOAM, "sx": 20, "sy": 20, "sz": FOAM, "kind": "foam", "step": 5})
        refs.append({"name": "micro-USB plug", "color_hex": "#202020", "x": cx - 6, "y": cy - PAD_W / 2 - 30,
                     "z": z_pad + 2, "sx": 12, "sy": 30, "sz": 7, "kind": "cable", "step": 5})
    tx, ty, tz = TAG_PAD
    refs.append({"name": "Magic Tag receiver (under keyboard)", "color_hex": "#c03030", "x": KB_COIL[0] - tx / 2,
                 "y": KB_COIL[1] - ty / 2, "z": z_floor, "sx": tx, "sy": ty, "sz": tz, "kind": "tag"})
    refs.append({"name": "Magic Tag plug + fold", "color_hex": "#c03030", "x": KB_DEV[0] - TAG_STICKOUT,
                 "y": KB_DEV[1] + KB_PORT_FROM_REAR - 6, "z": z_floor, "sx": TAG_STICKOUT, "sy": 12, "sz": 9, "kind": "tag"})
    return refs


def write_json(courses, refs):
    out = []
    for p in all_parts(courses):
        kind, w, l, name, _ = PARTS[p["part"]]
        out.append({"part": p["part"], "name": name, "kind": kind, "color": COLOURS[p["color"]][2],
                    "color_hex": COLOURS[p["color"]][1], "x": p["x"] * STUD, "y": p["y"] * STUD,
                    "z": round(p["z"] * PLATE, 2), "sx": p["w"] * STUD, "sy": p["h"] * STUD,
                    "sz": round(HEIGHT[kind] * PLATE, 2), "step": p["step"]})
    doc = {"units": "mm", "frame": "x right, y depth toward the user (0 = back edge), z up (0 = underside); origin "
                                   "back-left-bottom; boxes on the nominal 8 mm grid (real parts 0.1 mm smaller/side); "
                                   "studs (dia 4.8, 1.7 tall) on top of every non-tile part",
           "size_mm": [TRAY_W * STUD, TRAY_D * STUD, N_LAYERS * PLATE], "size_studs": [TRAY_W, TRAY_D],
           "steps": {str(k): v for k, v in STEP_NOTES.items()}, "bricks": out, "reference": refs}
    (HERE / "bricks.json").write_text(json.dumps(doc, indent=1))


# =====================================================================================================================
# CHECKS
# =====================================================================================================================
def run_checks(courses, rows):
    res = []

    def chk(name, ok, detail):
        res.append({"check": name, "ok": bool(ok), "detail": detail})

    # 1. every course packed exactly (per plate layer: no holes, no overlaps)
    want = {}
    for L in range(N_LAYERS):
        if L <= 1: want[L] = FULL
        elif L in CAVITY_LAYERS: want[L] = FULL - HOLES
        elif L == FLOOR_L: want[L] = FULL
        else: want[L] = WALLS
    occ = defaultdict(Counter)
    for p in all_parts(courses):
        for L in range(p["z"], p["z"] + HEIGHT[p["kind"]]):
            for cell in rect(p["x"], p["y"], p["w"], p["h"]):
                occ[L][cell] += 1
    bad = []
    for L in range(N_LAYERS):
        got = set(occ[L])
        over = [c for c, n in occ[L].items() if n > 1]
        if got != want[L] or over:
            bad.append(f"L{L}: missing {len(want[L] - got)}, extra {len(got - want[L])}, overlaps {len(over)}")
    chk("every layer packed exactly (no holes, no overlaps)", not bad, "; ".join(bad) or f"{N_LAYERS} plate layers OK")

    # 2. parts exist in the table, in an allowed colour
    unknown = [p["part"] for p in all_parts(courses) if p["part"] not in PARTS or p["color"] not in COLOURS]
    chk("every part is in the part table / colour table", not unknown, f"unknown: {sorted(set(unknown))}" if unknown else
        f"{len(rows)} distinct part/colour lines")

    # 3. pocket clearances
    cl = {"keyboard x": KB_CLR_X, "keyboard y": KB_CLR_Y, "mouse x": MS_CLR_X, "mouse y": MS_CLR_Y}
    chk(f"pocket clearance >= {MIN_CLR} mm per side", min(cl.values()) >= MIN_CLR - 1e-9,
        ", ".join(f"{k} {v:.2f}" for k, v in cl.items()) + f" (nominal; real +{LEGO_INSET} from the LEGO inset)")

    # 4. exactly one tile layer above each pad footprint where the device sits; pad top touches it
    floor = {}
    for p in all_parts(courses):
        if p["z"] <= FLOOR_L < p["z"] + HEIGHT[p["kind"]]:
            for cell in rect(p["x"], p["y"], p["w"], p["h"]):
                floor[cell] = p
    det = []
    ok4 = True
    for nm, pi, dev, dw, dd, pocket in (("keyboard", KB_PADI, KB_DEV, KB_W, KB_D, KB_POCKET | TAG_NOTCH),
                                        ("mouse", MS_PADI, MS_DEV, MOUSE_W, MOUSE_L, MS_POCKET)):
        pc = pad_cells(pi)
        under = pc & pocket
        tiles_ok = all(floor[c]["kind"] == "tile" for c in under)
        # nothing else between the pad top (L6 bottom) and the floor top: L6 is a single 1-plate layer
        cavity_empty = all(c not in occ[L] for L in CAVITY_LAYERS for c in pc)
        base_ok = all(c in occ[1] for c in pc)
        pad_top = (CAVITY_LAYERS.start * PLATE) + FOAM + PAD_H
        gap = FLOOR_L * PLATE - pad_top
        sup = [p for p in all_parts(courses) if p["part"] == "90498" and rect(p["x"], p["y"], p["w"], p["h"]) & pc]
        sup_ok = all(len(rect(s["x"], s["y"], s["w"], s["h"]) & set(occ[FLOOR_L - 1])) >= 8 for s in sup)
        ok = tiles_ok and cavity_empty and base_ok and abs(gap) <= 0.5 and sup_ok
        ok4 &= ok
        det.append(f"{nm}: {len(under)} pad cells under the device all tile={tiles_ok}, cavity clear={cavity_empty}, "
                   f"pad top {pad_top:.1f} vs tile underside {FLOOR_L*PLATE:.1f} (gap {gap:+.1f}), "
                   f"8x16 tiles gripped by >=8 studs each={sup_ok}, pad centre off the coil estimate "
                   f"({pi['offset'][0]:+.1f}, {pi['offset'][1]:+.1f}) mm, pad-to-cavity clearance "
                   f"{(CAV_N*STUD-PAD_W)/2:.1f} mm/side")
    chk("one 3.2 mm tile layer between each pad and its device; pad top touches it", ok4, "; ".join(det))

    # 5. everything connected (stud contact graph); tiles only connect downward
    allp = all_parts(courses)
    cellmap = defaultdict(dict)   # (layer of bottom) -> cell -> idx ; (layer of top) ...
    bottoms, tops = defaultdict(dict), defaultdict(dict)
    for i, p in enumerate(allp):
        for cell in rect(p["x"], p["y"], p["w"], p["h"]):
            bottoms[p["z"]][cell] = i
            tops[p["z"] + HEIGHT[p["kind"]]][cell] = i
    adj = defaultdict(set)
    for zt, cells in tops.items():
        for cell, i in cells.items():
            if allp[i]["kind"] == "tile":
                continue
            j = bottoms.get(zt, {}).get(cell)
            if j is not None:
                adj[i].add(j); adj[j].add(i)
    seen, stack = {0}, [0]
    while stack:
        for j in adj[stack.pop()]:
            if j not in seen:
                seen.add(j); stack.append(j)
    chk("all parts connected by studs (one rigid assembly)", len(seen) == len(allp),
        f"{len(seen)}/{len(allp)} parts reachable from the base")
    no_below = sum(1 for i, p in enumerate(allp) if p["z"] > 0 and not any(
        allp[j]["z"] < p["z"] for j in adj[i]))
    chk("parts not gripped from below (held from above only)", True,
        f"{no_below} parts (plates bridging the cable channels / mouse cavity edges; held by the bricks above)")

    # 6. seam stagger
    lines, tot_n, tot_d = [], 0, 0
    seq = []
    for c in courses:
        if c["z"] == FLOOR_L and seq and seq[-1]["z"] == FLOOR_L:
            seq[-1] = {"name": "L6 floor layer", "z": FLOOR_L, "parts": seq[-1]["parts"] + c["parts"]}
        else:
            seq.append(c)
    for a, b in zip(seq, seq[1:]):
        sa, sb = seams(a["parts"]), seams(b["parts"])
        n, d = len(sb & sa), len(sb)
        tot_n += n; tot_d += d
        lines.append(f"{b['name'].split()[0]} on {a['name'].split()[0]}: {100*n/max(d,1):.0f}%")
    pct = 100 * tot_n / max(tot_d, 1)
    chk("seams staggered (% of seam edges continuing the course below)", pct <= 30, f"overall {pct:.1f}%; " + ", ".join(lines))

    # 7. height and keycaps
    H = N_LAYERS * PLATE
    zf = (FLOOR_L + 1) * PLATE
    chk("overall height close to 44 mm", abs(H - 44.0) <= 1.6,
        f"{H:.1f} mm ({N_LAYERS} plates); pocket floor at {zf:.1f} mm, pocket depth {H - zf:.1f} mm; keyboard top "
        f"{zf + KB_H_FRONT - H:+.1f} mm vs rim at the front, {zf + KB_H_REAR - H:+.1f} at the back; mouse "
        f"{zf + MOUSE_H - H:+.1f} mm proud")
    chk("Magic Tag relief", TAG_NOTCH_DEPTH * STUD + KB_CLR_X >= TAG_STICKOUT,
        f"{TAG_NOTCH_DEPTH * STUD + KB_CLR_X:.1f} mm of room left of the keyboard over {TAG_NOTCH_LEN} studs "
        f"(needs {TAG_STICKOUT})")
    return res


def main():
    courses = build()
    rows = bom(courses)
    write_ldr(courses, HERE / "night-array-base.ldr")
    write_lists(rows)
    refs = reference_boxes()
    write_json(courses, refs)
    checks = run_checks(courses, rows)
    n = sum(r["qty"] for r in rows)
    cost = sum(r["total_usd"] for r in rows)
    by_kind = Counter()
    for r in rows:
        by_kind[r["kind"]] += r["qty"]
    summary = {"size_studs": [TRAY_W, TRAY_D, N_LAYERS], "size_mm": [TRAY_W * STUD, TRAY_D * STUD, N_LAYERS * PLATE],
               "keyboard_pocket_studs": [KB_NX, KB_NY], "mouse_pocket_studs": [MS_NX, MS_NY],
               "walls_studs": {"left": LEFT_WALL, "middle": MID_WALL, "right": RIGHT_WALL, "back": KB_BACK_WALL,
                               "front": FRONT_WALL},
               "pad_cavities": {"keyboard": KB_PADI["cav"], "mouse": MS_PADI["cav"]},
               "channels_x": {"keyboard": KB_CHX, "mouse": MS_CHX},
               "parts_total": n, "parts_by_kind": dict(by_kind), "distinct_lines": len(rows),
               "est_cost_usd": round(cost, 2), "checks": checks}
    (HERE / "checks.json").write_text(json.dumps(summary, indent=1))
    print(f"Night Array LEGO base: {TRAY_W} x {TRAY_D} studs x {N_LAYERS} plates = "
          f"{TRAY_W*STUD:.0f} x {TRAY_D*STUD:.0f} x {N_LAYERS*PLATE:.1f} mm")
    print(f"  keyboard pocket {KB_NX} x {KB_NY} studs at ({KB_X0},{KB_Y0}); mouse pocket {MS_NX} x {MS_NY} at "
          f"({MS_X0},{MS_Y0}); pad cavities kb {KB_PADI['cav']} mouse {MS_PADI['cav']}")
    print(f"  {n} parts ({dict(by_kind)}), {len(rows)} lines, est. ${cost:.0f}")
    for c in checks:
        print(f"  [{'OK ' if c['ok'] else 'FAIL'}] {c['check']}: {c['detail']}")
    if "--no-render" not in sys.argv:
        subprocess.run(["node", str(HERE / "render_lego.mjs")], check=True)
    return 0 if all(c["ok"] for c in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
