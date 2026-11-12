#!/usr/bin/env python3
"""Night Array -- the FULL desk station in LEGO: hollow base with the keyboard + mouse charging pockets, two necks,
one brick-built frame round two (different) 27" monitors, and the latch-free laptop dock at the right end.

Plain python3, no external dependencies.  Run from anywhere:

    python3 night-array/kit/lego/make_lego_station.py                  # model + lists + checks + renders
    python3 night-array/kit/lego/make_lego_station.py --no-render      # skip the PNGs (needs node + playwright)
    python3 night-array/kit/lego/make_lego_station.py --lite           # cheaper variant, written to station/lite/
    python3 night-array/kit/lego/make_lego_station.py --left acer_kb272_ebi --right sceptre_e275w_fpt
    python3 night-array/kit/lego/make_lego_station.py --model 14       # passed on to the dock generator (MacBook 14")

Writes, under night-array/kit/lego/station/ (station/lite/ with --lite):
    night-array-station.ldr   LDraw (MPD inside one .ldr): main model + one submodel per section (base, pockets,
                              necks, frame, dock), STEPs inside each
    parts.csv, bricklink-wanted.xml   part list / BrickLink wanted-list upload (same formats as ../parts.csv)
    bricks.json               every part as a box (mm) + reference boxes; same schema as ../bricks.json and
                              ../dock/bricks.json (optional "slope"), plus an optional "section" on every brick
    non-lego-parts.md/json    stands, bars, hardware, foam/felt + pointers into ../../parts.json
    checks.json               self-check results, sizes, part count and cost by section
    overview.png, back.png, exploded-sections.png, section-neck.png, steps/step-XX.png  (render_lego_station.mjs)

THE RULE THIS DESIGN IS BUILT ROUND: LEGO never carries a monitor.  Each monitor hangs on a steel VESA pole mount
(VIVO STAND-V001C) that is clamped to the desk; the LEGO necks and the LEGO frame are cladding that stands on the
LEGO base and is kept from falling forward by a lip that hooks behind the monitors' top edge (2 mm air, felt).

Reuse: the pocket block is make_lego_base.py's tray (same cell sets, same pad/tile arrangement, same checks) dropped
into the base; the dock is make_lego_dock.py's build() (plug pocket, seat, saddle, roof, liners unchanged), repacked
with parts that exist in Sand Blue and recoloured; packer, part table, LDraw writer and stud logic come from those.

Frames (same as the other two generators)
    x to the right as you sit at the desk, y DEPTH TOWARD YOU (0 = back edge of the base = back edge of the desk),
    z up (0 = desk).  1 stud = 8 mm, 1 plate = 3.2 mm.  Parts are kept in HALF studs (4 mm) like the dock.
    LDraw: X = x * 2.5, Y = -z * 2.5, Z = -y * 2.5 (front of the station faces -Z).

Plate layers (L0 = on the desk):
    L0          floor plates (Tan), whole footprint except the two clamp cut-outs
    L1-L11      pocket block: exactly the tray of make_lego_base.py (L1 plates, L2-4 bricks with the pad cavities,
                L5 plates, L6 floor tiles, L7-9 and L10-12 wall bricks)
                hollow part: outer wall 2 studs + ribs: L1-3 brick, L4 plate, L5-7 brick, L8-10 brick, L11 plate
    L12         deck plates on the wall/rib tops (hidden colour), Sand Blue plate round the outside
    L13         deck tiles (Sand Blue), pocket rim tiles, gold charge marks, pastel accents.  Top = 44.8 mm
    L13-L34     necks (two cheeks + a striped pedestal under the frame)
    L35-L42     frame bottom beam (aluminium flat bar in a slot), then the columns / mullion / bezel lips, top beam
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
sys.path.insert(0, str(HERE))
import make_lego_base as base   # noqa: E402
import make_lego_dock as dock   # noqa: E402  (also parses --model / --port)

LITE = "--lite" in sys.argv
OUT = HERE / "station" / ("lite" if LITE else "")
DATA = HERE / "station"
STUD, PLATE, HALF = base.STUD, base.PLATE, 4.0


def _arg(flag, default):
    for a, b in zip(sys.argv, sys.argv[1:]):
        if a == flag:
            return b
    return default


# =====================================================================================================================
# MONITORS  (mm, kg).  CHANGE THESE TO WHAT YOU MEASURE, then re-run the script: every opening, the frame width,
# the base width, the necks and the checks follow from this block.
#   W, H            housing width / height without the stand
#   D               deepest point of the housing without the stand
#   vesa_to_front   VESA mounting face (where the plate bolts on) to the front glass.  Assumed = D until measured
#   top_edge_depth  how thick the housing is along its TOP edge (the frame's retaining lip goes behind it)
#   bezel           housing edge -> first lit pixel: side / top / bottom
#   vesa            hole pattern (mm); 0 = no VESA holes at all (see README "if a monitor has no VESA holes")
#   buttons         "rear" or "bottom" (bottom = the frame gets a finger notch under that corner)
# Active area of every 27" 1920 x 1080 panel: 597.9 x 336.3 mm (0.3114 mm pixel pitch).
# =====================================================================================================================
ACTIVE_W, ACTIVE_H = 597.9, 336.3
MONITORS = {
    # --- Acer KB272 family (owner: label says "KB272", suffix unknown) ------------------------------------------
    "acer_kb272_ebi": {
        "name": 'Acer KB272 EBI 27" FHD IPS 100 Hz (UM.HK2AA.E02)', "W": 614.7, "H": 367.1, "D": 66.7,
        "vesa_to_front": 66.7, "top_edge_depth": 12.0, "kg": 4.73, "vesa": 100,
        "bezel": {"side": 8.4, "top": 8.4, "bottom": 22.4}, "psu": "internal (AC cord in the box) -- CONFIRM",
        "ports": "1 x HDMI 1.4 + 1 x VGA + audio out, in the rear bulge, plugs point down", "buttons": "rear",
        "confidence": "medium: W/D from Acer US (24.2 x 14.5 x 2.7 in) + reseller sheet (61.47 x 6.67 cm); H from the "
                      "same chassis KA272 H (367.1); another database says 612.4 x 366.5; weight 10.43 lb is Acer's "
                      "figure (may include the stand: then the panel is ~3.4 kg). displayninja says VESA 75, Acer "
                      "says 100 -- the stand takes both. Bezels and top_edge_depth are ESTIMATES.",
        "sources": ["https://www.acer.com/us-en/monitors/essential/kb2/pdp/UM.HK2AA.E02",
                    "https://store.acer.com/en-us/27-acer-kb2-essential-monitor-kb272-ebi",
                    "https://devicebeast.com/display/acer-kb272-ebi-27",
                    "https://www.displayninja.com/acer-kb272-ebi-review/"]},
    "acer_kb272_e0bi": {
        "name": 'Acer KB272 E0bi / G0bi (newer slim chassis; numbers are the KA272 E0bi sheet, same panel family)',
        "W": 611.5, "H": 361.3, "D": 45.2, "vesa_to_front": 45.2, "top_edge_depth": 10.0, "kg": 3.0, "vesa": 100,
        "bezel": {"side": 6.8, "top": 6.8, "bottom": 18.2}, "psu": "external adapter", "ports": "HDMI + VGA, rear, down",
        "buttons": "rear",
        "confidence": "low for a KB272: this is Acer's EU sheet for the KA272 E0bi (UM.HX2EE.034); the KB272 E0bi/G0bi "
                      "are sold as the same generation but were not verified",
        "sources": ["https://shop.datacom.bg/images/products/originals/Acer/add/168.pdf",
                    "https://www.displayninja.com/acer-kb272-g0bi-review/"]},
    # --- Sceptre 27" FHD (owner: label says "F27"; no Sceptre page uses that name) ------------------------------
    "sceptre_e275w_fpt": {
        "name": 'Sceptre E275W-FPT 27" FHD IPS 75 Hz (most likely "F27": edgeless IPS, HDMI x2 + VGA)',
        "W": 612.6, "H": 359.2, "D": 45.0, "vesa_to_front": 45.0, "top_edge_depth": 10.0, "kg": 3.00, "vesa": 100,
        "bezel": {"side": 7.3, "top": 7.3, "bottom": 15.6}, "psu": "external 12 V 3 A adapter (26 W typ.)",
        "ports": "2 x HDMI + VGA + audio in/out, rear", "buttons": "rear",
        "confidence": "medium-low that this is the owner's model; for the E275W-FPT itself W/H/weight/VESA are "
                      "Sceptre's own figures (24.12 x 14.14 x 1.12 in, 6.61 lb, VESA 100 M4 x 10). The 1.12 in is "
                      "the thin edge; D (45) and vesa_to_front are ESTIMATES -- measure.",
        "sources": ["https://www.sceptre.com/support/688/E275W-FPT",
                    "https://www.sceptre.com/Monitors/IPS-Series/E275W-FPT-27-LED-Monitor-product1314category12category99.html"]},
    "sceptre_e275w_fpt1": {
        "name": 'Sceptre E275W-FPT1 27" FHD IPS', "W": 612.6, "H": 359.2, "D": 45.0, "vesa_to_front": 45.0,
        "top_edge_depth": 10.0, "kg": 3.15, "vesa": 100, "bezel": {"side": 7.3, "top": 7.3, "bottom": 15.6},
        "psu": "external 12 V 3 A adapter", "ports": "rear", "buttons": "rear",
        "confidence": "figures from Sceptre (24.12 x 14.14 x 1.12 in, 6.94 lb, VESA 100)",
        "sources": ["https://sceptre.com/support/908/E275W-FPT1"]},
    "sceptre_e275w_19203rs": {
        "name": 'Sceptre E275W-19203RS 27" FHD TN (older, thicker)', "W": 615.2, "H": 360.4, "D": 45.0,
        "vesa_to_front": 45.0, "top_edge_depth": 15.0, "kg": 4.30, "vesa": 75,
        "bezel": {"side": 8.6, "top": 8.6, "bottom": 15.5}, "psu": "internal (AC cord)", "ports": "rear",
        "buttons": "rear", "confidence": "figures from Sceptre (24.22 x 14.19 x 1.77 in, 9.47 lb, VESA 75)",
        "sources": ["https://www.sceptre.com/support/578/E275W-19203RS"]},
    "sceptre_e275w_19203rd": {
        "name": 'Sceptre E275W-19203RD 27" FHD (metal back, thick bezels)', "W": 623.8, "H": 367.0, "D": 43.2,
        "vesa_to_front": 43.2, "top_edge_depth": 12.0, "kg": 3.27, "vesa": 100,
        "bezel": {"side": 11.7, "top": 11.7, "bottom": 17.0}, "psu": "external 12 V 3 A adapter", "ports": "rear",
        "buttons": "rear", "confidence": "figures from Sceptre (24.56 x 14.45 x 1.7 in, 7.2 lb, VESA 100, bezels "
                                         "11.7/11.7/11.7/17)",
        "sources": ["https://www.sceptre.com/Monitors/Flat-Series/E275W-19203RD-27-LED-Monitor-product1170category12category16.html"]},
}
LEFT = _arg("--left", "acer_kb272_ebi")          # monitor on the left as you sit
RIGHT = _arg("--right", "sceptre_e275w_fpt")     # monitor on the right (next to the laptop dock)
MON = [dict(MONITORS[LEFT], key=LEFT), dict(MONITORS[RIGHT], key=RIGHT)]

# =====================================================================================================================
# STRUCTURE (not LEGO).  One VIVO STAND-V001C per monitor: 35 mm steel pole + fixed tilt bracket + C-clamp (or
# grommet bolt).  Verified on vivo-us.com 2026-11-11: US$34.99, pole 17.7 in, 17.6 lb (8 kg), VESA 75 + 100,
# desk 10-88 mm (clamp).  Dimensions marked EST are not published: measure and change.
# =====================================================================================================================
STAND = {"product": "VIVO Single Monitor Desk Mount STAND-V001C (black) / STAND-V001CW (white)", "mpn": "STAND-V001C",
         "usd": 34.99, "url": "https://vivo-us.com/products/stand-v001c", "max_kg": 8.0, "ship_kg": 3.18,
         "pole_len": 450.0, "pole_d": 35.0,           # pole_d EST (VIVO poles are 1.38 in)
         "bracket": 65.0,                             # EST: pole centre -> VESA mounting face
         "clamp_w": 100.0, "clamp_d": 90.0, "clamp_h": 12.0,   # EST: clamp top plate on the desk (w x d x thickness)
         "pole_y": 40.0,                              # EST: pole centre in from the desk's back edge when clamped
         "clamp_lever": 45.0, "clamp_screw_n": 5000.0,  # EST: jaw lever arm; working load of the clamp screw (M10)
         "desk_mm": (10, 88)}
BAR = {"product": "Aluminium flat bar 1/8 in x 3/4 in (3.2 x 19 mm), 6063: one 48 in (1219 mm) for the bottom beam, "
                  "one 36 in (914 mm) for the top beam, e.g. Everbilt / Hillman",
       "t": 3.2, "h": 19.05, "len": 1219.0, "len_top": 914.0, "usd": 9.0, "usd_top": 7.0, "E": 69000.0}
PLUGABLE = (225.0, 85.0, 24.5)                       # UD-6950PDH dock box
SCREEN_GAP = (1.5, 4.0)                              # allowed clearance monitor housing -> LEGO opening, per side
FACE_GAP = (1.5, 8.0)                                # allowed air gap front glass -> back of the bezel bricks

# =====================================================================================================================
# COLOURS  LDraw id -> (BrickLink id, hex, name, price multiplier)
# =====================================================================================================================
SB, TAN, LBG, BLK, BLO, LN, LAV, GOLD = 379, 19, 71, 0, 191, 78, 31, 297
COLOURS = {SB: (55, "#70819a", "Sand Blue", 2.2), TAN: (2, "#d7ba8c", "Tan", 1.1),
           LBG: (86, "#a0a5a9", "Light Bluish Gray", 1.0), BLK: (11, "#1b2a34", "Black", 1.0),
           BLO: (110, "#fcac00", "Bright Light Orange", 1.5), LN: (90, "#ffc995", "Light Nougat", 2.0),
           LAV: (154, "#cda4de", "Lavender", 1.6), GOLD: (115, "#aa7f2e", "Pearl Gold", 1.5)}
MIN_SETS = 5      # a part/colour counts as "exists and is findable" if >= this many sets contain it (Rebrickable)
AVAIL = json.loads((DATA / "part-colour-availability.json").read_text())["sets"]


def avail(pid, col):
    return AVAIL.get(pid, {}).get(str(col), 0)


# Part table = the dock's (which is the base's + jumper + 45/33 deg slopes) + a few long parts and three corner
# parts.  ids checked against library.ldraw.org on 2026-11-11 (header + bounding box of every .dat).
PARTS = dock.PARTS
PARTS.update({
    "2465": ("brick", 1, 16, "Brick 1 x 16", 0.45), "6112": ("brick", 1, 12, "Brick 1 x 12", 0.35),
    "4282": ("plate", 2, 16, "Plate 2 x 16", 0.45),
    "4477": ("plate", 1, 10, "Plate 1 x 10", 0.15), "60479": ("plate", 1, 12, "Plate 1 x 12", 0.20),
    "3040b": ("slope", 1, 2, "Slope 45 2 x 1", 0.08),
    "11477": ("cslope", 1, 2, "Slope, Curved 2 x 1 x 2/3", 0.06), "15068": ("cslope", 2, 2, "Slope, Curved 2 x 2 x 2/3", 0.08),
    "3665": ("islope", 1, 2, "Slope, Inverted 45 2 x 1", 0.08),
})
HEIGHT = dock.HEIGHT
HEIGHT.update({"cslope": 2, "islope": 3})
dock.MASS_PER_CELL.update({"cslope": 0.12, "islope": 0.2})
BRICKS = [p for p, v in PARTS.items() if v[0] == "brick"]
PLATES = [p for p, v in PARTS.items() if v[0] == "plate" and p != dock.JUMPER]
TILES = [p for p, v in PARTS.items() if v[0] == "tile" and p != "90498"]


def pset(ids, col):
    return [p for p in ids if avail(p, col) >= MIN_SETS]


S_BRICK = {c: pset(BRICKS, c) for c in (SB, TAN, LBG)}
S_PLATE = {c: pset(PLATES, c) for c in (SB, TAN, LBG, BLO, LN, LAV)}
S_TILE = {c: pset(TILES, c) for c in (SB, TAN, LBG, BLK)}

# =====================================================================================================================
# GEOMETRY (studs / plates unless it says mm)
# =====================================================================================================================
def R(x0, y0, w, h):
    return {(x, y) for x in range(x0, x0 + w) for y in range(y0, y0 + h)}


def opening(m):
    """Opening for one monitor: studs wide, plates high, clearances, felt liner if a whole stud is too much."""
    n = math.ceil((m["W"] + 2 * SCREEN_GAP[0]) / STUD - 1e-9)
    cx = (n * STUD - m["W"]) / 2
    liner = 0.0
    if cx > SCREEN_GAP[1]:                        # stud grid too coarse: line the two side faces with felt
        liner = math.ceil(cx - (SCREEN_GAP[0] + SCREEN_GAP[1]) / 2)
    nz = math.ceil((m["H"] + 2 * SCREEN_GAP[0]) / PLATE - 1e-9)
    cz = (nz * PLATE - m["H"]) / 2
    return {"n": n, "nz": nz, "clr_x": cx - liner, "liner_x": liner, "clr_z": cz}


OPEN = [opening(m) for m in MON]
COL_W, WEB_W = 2, 1                                # frame side columns, web between the two housings
FRAME_W = COL_W + OPEN[0]["n"] + WEB_W + OPEN[1]["n"] + COL_W
OPEN_X = [COL_W, COL_W + OPEN[0]["n"] + WEB_W]     # left stud of each opening
WEB_X = COL_W + OPEN[0]["n"]
MON_CX = [(OPEN_X[i] + OPEN[i]["n"] / 2) * STUD for i in (0, 1)]          # monitor centre x (mm)

BASE_W, BASE_D = FRAME_W, 40                       # base = frame width; 14 studs rear zone + the 26-stud tray
REAR = BASE_D - base.TRAY_D                        # 14
PB0 = round(FRAME_W / 2 - (base.KB_X0 + (base.MS_X0 + base.MS_NX - base.KB_X0) / 2))   # pockets centred on the seam
PY0 = REAR
DOCK_X0, DOCK_Y0 = BASE_W, BASE_D - dock.BASE_D    # dock: right end, flush with the front (5 studs filler behind)
TOTAL_W = BASE_W + dock.BASE_W
N_BASE = base.N_LAYERS                             # 14 plates = 44.8 mm

# depth: both screens' front glass in one plane
Y_FACE = STAND["pole_y"] + STAND["bracket"] + max(m["vesa_to_front"] for m in MON)       # mm
SPACER = [round(max(m["vesa_to_front"] for m in MON) - m["vesa_to_front"]) for m in MON]  # VESA stand-offs (mm)
FYB = math.ceil((Y_FACE + FACE_GAP[0]) / STUD - 1e-9)       # stud row of the bezel bricks (in front of the glass)
FRAME_D = 5
FY0 = FYB - (FRAME_D - 1)                          # frame occupies rows FY0 .. FYB
SLOT_Y = FY0 + 2                                   # row of the aluminium bar slot in both beams
FACE_AIR = FYB * STUD - Y_FACE

# necks
POLE_C = [(MON_CX[i] / STUD, STAND["pole_y"] / STUD) for i in (0, 1)]     # pole centre, studs (may be x.5)
NECK = []
for i in (0, 1):
    cw = 6 if abs(POLE_C[i][0] - round(POLE_C[i][0])) < 0.01 else 7       # channel width (centred on the pole)
    c0 = int(round(POLE_C[i][0] - cw / 2))
    NECK.append({"c0": c0, "c1": c0 + cw, "x0": c0 - 2, "x1": c0 + cw + 2,
                 "hole": R(c0, int(round(POLE_C[i][1])) - 3, cw, 6)})
NECK_Z0, NECK_COURSES = 13, 7                      # base plate at L13, then 7 courses (21 plates)
ZB = NECK_Z0 + 1 + 3 * NECK_COURSES                # 35: frame bottom beam starts
ZO = ZB + 8                                        # 43: bottom of the openings
HMAX = max(o["nz"] for o in OPEN)
ZT = ZO + HMAX                                     # top beam starts
Z_TOP = ZT + 8
SILL = [HMAX - o["nz"] for o in OPEN]              # plates of sill under the shorter monitor


def lips(i):
    m, o = MON[i], OPEN[i]
    nb = int((m["bezel"]["bottom"] - 0.5 + o["clr_z"]) // PLATE) + SILL[i]
    nt = max(1, int((m["bezel"]["top"] - 0.5 + o["clr_z"]) // PLATE))
    return nb, nt


LIP = [lips(i) for i in (0, 1)]
MON_Z0 = [(ZO + SILL[i]) * PLATE + OPEN[i]["clr_z"] for i in (0, 1)]      # housing bottom (mm)
MON_X0 = [OPEN_X[i] * STUD + (OPEN[i]["n"] * STUD - MON[i]["W"]) / 2 for i in (0, 1)]
VESA_Z = [MON_Z0[i] + MON[i]["H"] / 2 for i in (0, 1)]
# retaining lip behind the monitors' top edge
LIP_ROWS = [max(FY0 + 1, int((Y_FACE - MON[i]["top_edge_depth"] - 1.5) // STUD)) for i in (0, 1)]   # exclusive end
LIP_GAP = [Y_FACE - MON[i]["top_edge_depth"] - LIP_ROWS[i] * STUD for i in (0, 1)]
BAR_STUDS = math.ceil(BAR["len"] / STUD) + 1          # bottom beam slot
BAR_X0 = (FRAME_W - BAR_STUDS) // 2
TBAR_STUDS = math.ceil(BAR["len_top"] / STUD) + 1      # top beam slot (shorter bar: clear of the rounded corners)
TBAR_X0 = WEB_X - TBAR_STUDS // 2

# ---- plan sets -------------------------------------------------------------------------------------------------
BASE = R(0, 0, BASE_W, BASE_D)


def sh(cells):
    return {(x + PB0, y + PY0) for (x, y) in cells}


B_FULL, B_HOLES, B_POCKETS, B_WALLS = sh(base.FULL), sh(base.HOLES), sh(base.POCKETS), sh(base.WALLS)
HZ = BASE - B_FULL                                 # hollow part of the base
FILLER = R(DOCK_X0, 0, dock.BASE_W, DOCK_Y0)       # strip behind the dock (its cable channel runs through)
DOCK_RECT = R(DOCK_X0, DOCK_Y0, dock.BASE_W, dock.BASE_D)
CH_COLS = R(DOCK_X0 + dock.POCKET_X0, 0, dock.POCKET_W, DOCK_Y0)
CLAMP_HALF = math.ceil(STAND["clamp_w"] / 2 / STUD) + 0          # 7 studs each side of the pole
CLAMP_BAY = [R(int(round(POLE_C[i][0])) - CLAMP_HALF, 0, 2 * CLAMP_HALF, REAR - 2) for i in (0, 1)]
CUTOUT = CLAMP_BAY[0] | CLAMP_BAY[1]               # no floor here: the clamp plate sits on the desk itself
HOLES12 = NECK[0]["hole"] | NECK[1]["hole"]


def band(region, w, outside=None):
    """Cells of `region` within w studs (8-neighbourhood) of a cell that is not in `outside` (default: region)."""
    inside = region if outside is None else outside
    return {(x, y) for (x, y) in region
            if any((x + dx, y + dy) not in inside for dx in range(-w, w + 1) for dy in range(-w, w + 1))}


def footprint(L):
    """What counts as 'inside' on layer L when deciding which faces are visible from outside."""
    f = set(BASE)
    if L <= 6:
        f |= FILLER | DOCK_RECT                    # the dock plinth / filler top is at L6
    return f


def skin_of(region, L, w):
    return band(region, w, footprint(L)) if L > 0 else set()


def skin_colour(L):
    return TAN if L <= 4 else SB


# hollow structure ---------------------------------------------------------------------------------------------
WALL2 = band(BASE, 2) & HZ
FRONT_X = [(2, PB0), (PB0 + base.TRAY_W, BASE_W - 2)]            # x ranges of the two hollow front zones
DOCKBAY = (NECK[1]["x1"] + 3, BASE_W - 2)                         # x range of the Plugable bay (right front zone)
SPINE = R(2, REAR - 2, BASE_W - 4, 2) | set().union(*(R(a, REAR, b - a, 2) for a, b in FRONT_X))
MID_Y = 30                                                        # second support line, rows 30-31
MID = set().union(*(R(a, MID_Y, b - a, 2) for a, b in FRONT_X))
POSTS = set().union(*(R(x, MID_Y, 2, 2) for x in range(DOCKBAY[0] + 10, DOCKBAY[1] - 4, 10)))
MID_OPEN = R(DOCKBAY[0], MID_Y, DOCKBAY[1] - DOCKBAY[0], 2) - POSTS    # open under the beam (cables)
RIBS = set()
for i in (0, 1):                                                  # clamp bay side walls + piers under the necks
    xc = int(round(POLE_C[i][0]))
    RIBS |= R(xc - CLAMP_HALF - 2, 2, 2, REAR - 4) | R(xc + CLAMP_HALF, 2, 2, REAR - 4)
    RIBS |= R(NECK[i]["x0"], REAR + 2, 2, FYB + 2 - REAR - 2) | R(NECK[i]["x1"] - 2, REAR + 2, 2, FYB + 2 - REAR - 2)
for x in (14, 26, FRONT_X[1][0]):                                 # full ribs: left front zone, right zone next to the block
    RIBS |= R(x, REAR + 2, 2, BASE_D - 2 - REAR - 2)
for x in range(PB0 + 8, PB0 + base.TRAY_W - 6, 16):               # rear zone, behind the pocket block
    RIBS |= R(x, 2, 2, REAR - 4)
RIBS -= CUTOUT
HOLE_BEAM = set().union(*(R(int(round(POLE_C[i][0])) - CLAMP_HALF, 8, 2 * CLAMP_HALF, 2) for i in (0, 1)))  # L8-L11 only
STRUCT = (WALL2 | SPINE | MID | RIBS | HOLE_BEAM) & HZ
# openings in the structure
DOOR_CABLE = set()                                                # L1-L4, 4 studs wide
for a, b in ((20, 2), (PB0 - 8, 2), (PB0 + base.TRAY_W + 6, 2), (BASE_W - 16, 2)):
    DOOR_CABLE |= R(a, REAR - 2, 4, 4)                            # through the spine
for cx in (base.KB_CHX, base.MS_CHX):                             # pad cable channels through the spine
    DOOR_CABLE |= R(PB0 + cx[0], REAR - 2, cx[1], 2)
DOOR_CABLE |= {(x, y) for (x, y) in RIBS if y in range(5, 9) or y in range(REAR + 4, REAR + 8)}
DOOR_CABLE |= R(8, MID_Y, 4, 2) | R(PB0 - 12, MID_Y, 4, 2)
DOOR_CABLE |= R(BASE_W // 2 - 2, 0, 4, 2)                         # cable exit, centre of the back wall
DOOR_CABLE |= R(BASE_W - 12, 0, 4, 2)                             # cable exit behind the Plugable bay
DOOR_CLAMP = set().union(*(R(int(round(POLE_C[i][0])) - CLAMP_HALF, 0, 2 * CLAMP_HALF, 2) for i in (0, 1)))  # L1-L7
LINTEL = [int(round(POLE_C[i][0])) - 8 for i in (0, 1)]           # 1 x 16 bricks over the clamp doorways


def struct_at(L):
    s = set(STRUCT)
    if L <= 7:
        s -= DOOR_CLAMP | MID_OPEN | HOLE_BEAM
    if L <= 4:
        s -= DOOR_CABLE
    return s


SUPPORT11 = set(STRUCT)
# removable deck lids (plates + tiles packed on their own so nothing bridges out of them)
LIDS = {
    "dock bay lid (Plugable UD-6950PDH)": R(DOCKBAY[0], REAR + 1, DOCKBAY[1] - DOCKBAY[0], MID_Y - REAR),
    "left bay lid (spare bay / monitor adapter)": R(2, REAR + 1, NECK[0]["x0"] - 2 - 2, MID_Y - REAR),
    "rear lid (pad cables, USB power)": R(NECK[0]["x1"] + CLAMP_HALF, 1, NECK[1]["x0"] - CLAMP_HALF - NECK[0]["x1"] - CLAMP_HALF, REAR - 2),
}
NECK_FOOT = []
for n in NECK:
    NECK_FOOT.append(R(n["x0"] - 2, FY0, n["x1"] - n["x0"] + 4, FRAME_D) | R(n["x0"], 0, 2, FY0) | R(n["x1"] - 2, 0, 2, FY0))

# =====================================================================================================================
# PART STORE + PACKING
# =====================================================================================================================
ALL = []            # every LEGO part: dock-style dicts in half-stud units + "section"
BY_TOP = defaultdict(list)
WANT = defaultdict(set)      # layer -> half cells that are meant to be filled (for the packing check)


def _reg(p, section, step):
    p["section"], p["step"] = section, step
    ALL.append(p)
    BY_TOP[p["z"] + p["nz"]].append(p)
    for L in range(p["z"], p["z"] + p["nz"]):
        WANT[L] |= dock.cells_h(p)       # explicit parts define their own cells; fill() checks its region itself
    return p


def mk(pid, x, y, w, h, z, colour, section, step, rot=False, down=None):
    """One explicit part; x, y, w, h in studs (w along x)."""
    kind = PARTS[pid][0]
    p = {"part": pid, "x": int(round(2 * x)), "y": int(round(2 * y)), "w": int(round(2 * w)), "h": int(round(2 * h)),
         "z": z, "nz": HEIGHT[kind], "kind": kind, "color": colour, "step": step,
         "rot": rot or (down is None and h > w), "down": down}
    return _reg(p, section, step)


def seams_under(z):
    return dock.seams(BY_TOP.get(z, []))


def fill(region, pids, z, colour, prefer, section, step, ok=None):
    """Pack a stud-cell region with the given parts on layer z (the dock's greedy packer)."""
    if not region:
        return []
    parts = dock.pack(set(region), pids, seams_under(z), prefer, colour, z, step, ok=ok)
    got = set().union(*(dock.cells_h(p) for p in parts))
    want = {(2 * x + a, 2 * y + b) for (x, y) in region for a in (0, 1) for b in (0, 1)}
    assert got == want, f"packer left holes at z {z}"
    for p in parts:
        _reg(p, section, step)
    return parts


def supported(support):
    """Placement rule for parts that bridge openings: both ends of the long axis must sit on `support`."""
    def ok(cells):
        on = cells & support
        if len(on) == len(cells):
            return True
        if not on:
            return False
        xs, ys = [c[0] for c in cells], [c[1] for c in cells]
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        along_x = (x1 - x0) >= (y1 - y0)
        if along_x:
            a, b = {c for c in on if c[0] == x0}, {c for c in on if c[0] == x1}
        else:
            a, b = {c for c in on if c[1] == y0}, {c for c in on if c[1] == y1}
        if a and b:
            return True
        if (x1 - x0) == (y1 - y0):      # square: try the other axis too
            return bool({c for c in on if c[1] == y0}) and bool({c for c in on if c[1] == y1})
        return False
    return ok


def bridge(region, support, pids, z, colour, section, step):
    """Put one long part over every opening in the course below (1 stud of bearing at each end); returns its cells."""
    un = region - support
    done, seen = set(), set()
    by = defaultdict(list)
    for pid in pids:
        by[PARTS[pid][1]].append((PARTS[pid][2], pid))
    for start in sorted(un):
        if start in seen:
            continue
        comp, stack = {start}, [start]
        while stack:
            cx, cy = stack.pop()
            for q in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                if q in un and q not in comp:
                    comp.add(q); stack.append(q)
        seen |= comp
        x0, x1 = min(c[0] for c in comp), max(c[0] for c in comp)
        y0, y1 = min(c[1] for c in comp), max(c[1] for c in comp)
        good = lambda c: c in region and c in support and c not in done
        for axis in ("x", "y"):
            a0, a1, b0, b1 = (x0, x1, y0, y1) if axis == "x" else (y0, y1, x0, x1)
            cell = (lambda a, b: (a, b)) if axis == "x" else (lambda a, b: (b, a))
            if not all(good(cell(a0 - 1, b)) and good(cell(a1 + 1, b)) for b in range(b0, b1 + 1)):
                continue
            need, b, ok = a1 - a0 + 3, b0, True
            plan = []
            while b <= b1:
                wd = 2 if (b + 1 <= b1 and any(l >= need for l, _ in by[2])) else 1
                opts = sorted((l, pid) for l, pid in by[wd] if l >= need)
                if not opts:
                    ok = False; break
                l, pid = opts[0]
                for s in range(a0 - 1 - (l - need), a0):
                    cells = {cell(a, bb) for a in range(s, s + l) for bb in range(b, b + wd)}
                    if cells <= region and not (cells & done) and all(good(cell(s, bb)) and good(cell(s + l - 1, bb)) for bb in range(b, b + wd)):
                        plan.append((pid, s, b, l, wd, cells)); break
                else:
                    ok = False; break
                b += wd
            if not ok:
                continue
            for pid, s, b, l, wd, cells in plan:
                if axis == "x": mk(pid, s, b, l, wd, z, colour, section, step)
                else: mk(pid, b, s, wd, l, z, colour, section, step)
                done |= cells
            break
        else:
            raise RuntimeError(f"cannot bridge opening at {(x0, y0)}-{(x1, y1)} on L{z}")
    return done


DECK_BREAKS = {REAR - 1, REAR + 1, MID_Y + 1}     # deck strips always end on these support rows
FLOOR_BREAKS = DECK_BREAKS | {1, BASE_D - 1}


def deck_tile(zone, support, pids, z, colour, section, step, breaks=DECK_BREAKS):
    """Deck plates: strips along y that start and end on a support row, merged sideways into the widest plate."""
    dims = {}
    for pid in pids:
        a, b = PARTS[pid][1], PARTS[pid][2]
        dims[(a, b)] = pid; dims[(b, a)] = pid          # (width along x, length along y)
    lengths = sorted({l for (a, l) in dims if a <= 2}, reverse=True)
    segs = defaultdict(dict)                              # x -> {r0: L}
    for x in sorted({c[0] for c in zone}):
        rows = sorted(c[1] for c in zone if c[0] == x)
        rs = set(rows)
        memo = {}

        def plan(i):
            """Longest-first split of rows[i:] into strips whose first and last row are supported."""
            if i >= len(rows):
                return []
            if i not in memo:
                memo[i] = None
                r0 = rows[i]
                for L in lengths:
                    if (all(r in rs for r in range(r0, r0 + L)) and (x, r0) in support and (x, r0 + L - 1) in support
                            and not any(r in breaks for r in range(r0 + 1, r0 + L))):
                        rest_ = plan(i + L)
                        if rest_ is not None:
                            memo[i] = [(r0, L)] + rest_
                            break
            return memo[i]

        p = plan(0)
        if p is None:
            raise RuntimeError(f"deck column x={x} on L{z} cannot be covered by supported plates")
        segs[x] = dict(p)
    for x in sorted(segs):
        for r0 in sorted(segs[x]):
            L = segs[x].pop(r0)
            n = 1
            while segs.get(x + n, {}).get(r0) == L:
                n += 1
            widths = sorted({a for (a, l) in dims if l == L}, reverse=True)
            one = sorted((l for (a, l) in dims if a == 1), reverse=True)

            def split(xx, r, left):
                """1-wide plates for one lone column (every piece supported at both ends)."""
                if left == 0:
                    return []
                for l in one:
                    if l <= left and (xx, r) in support and (xx, r + l - 1) in support:
                        t = split(xx, r + l, left - l)
                        if t is not None:
                            return [(r, l)] + t
                return None

            memo2 = {}

            def cols(k):
                """Split the run of n equal columns into available plate widths (or a lone re-split column)."""
                if k == n:
                    return []
                if k not in memo2:
                    memo2[k] = None
                    for wd in widths:
                        if wd > 1 and k + wd <= n and cols(k + wd) is not None:
                            memo2[k] = [wd] + cols(k + wd); break
                    else:
                        if (1 in widths or split(x + k, r0, L) is not None) and cols(k + 1) is not None:
                            memo2[k] = [1] + cols(k + 1)
                return memo2[k]

            ws = cols(0)
            if ws is None:
                raise RuntimeError(f"deck strip at {(x, r0)} length {L} x {n} columns: no plate widths fit")
            xx = x
            for wd in ws:
                if wd == 1 and 1 not in widths:
                    for (r, l) in split(xx, r0, L):
                        mk(dims[(1, l)], xx, r, 1, l, z, colour, section, step)
                else:
                    mk(dims[(wd, L)], xx, r0, wd, L, z, colour, section, step)
                xx += wd
            for k in range(1, n):
                del segs[x + k][r0]


def split_skin(region, L, w):
    s = skin_of(region, L, w) if w else set()
    return s, region - s


# =====================================================================================================================
# BUILD
# =====================================================================================================================
STEPS = {
    1: ("base", "Floor: Tan plates over the whole footprint (studs up), including under the dock. The two "
                "rectangular gaps at the back are for the desk clamps."),
    2: ("pockets", "Pocket block, lower half (the tray of the pocket-base build): plates, then bricks and plates "
                   "leaving the two 13 x 13 pad cavities and their cable channels to the back."),
    3: ("base", "Hollow base: outer wall (Tan below, Sand Blue above) and the hidden ribs up to deck height; "
                "the strip behind the dock with the dock cable channel. Leave the two clamp bays open at the back."),
    4: ("non-lego", "Not LEGO: clamp the two VIVO poles to the desk through the clamp bays; foam + Anker pads into "
                    "the cavities; Plugable dock box into the right bay; run the cables."),
    5: ("pockets", "Charging floor: the three black 8 x 16 tiles over the pads, black tiles on the rest of the "
                   "pocket floors, plates under the walls."),
    6: ("pockets", "Pocket walls: two brick courses, Sand Blue wherever a face shows."),
    7: ("base", "Deck plates on the walls and ribs (the three lids are separate groups), Sand Blue plate round "
                "the outside edge."),
    8: ("base", "Top tiles: Sand Blue deck and pocket rims, two Pearl Gold marks behind each pocket, the three "
                "pastel patches at the front left."),
    9: ("dock", "Dock, lower part: plug seat, plug pocket and cable channel, then fit the Newnex plug exactly as "
                "in the dock build, and close the floor (roof tiles, jumpers, floor tiles)."),
    10: ("dock", "Dock walls: Tan outer panel on the left wall, Sand Blue elsewhere, lead-in slopes."),
    11: ("necks", "Necks: two cheeks either side of each pole and the striped pedestal under the frame."),
    12: ("non-lego", "Not LEGO: bolt the VESA plates to the monitors (stand-offs on the thinner one), hang them "
                     "on the brackets, set height and level so both sit 2-3 mm above the frame's bottom beam line."),
    13: ("frame", "Frame bottom beam on the two pedestals, with the first aluminium flat bar in its slot."),
    14: ("frame", "Frame sides, the web between the two screens and the bezel lips (they overlap the monitors' "
                  "edges by a few mm without touching)."),
    15: ("frame", "Top beam with the second flat bar, the retaining lips behind the monitors' top edge and the "
                  "rounded corners."),
    16: ("non-lego", "Liners and devices: felt in the dock, felt pads on the retaining lips and bezel corners, "
                     "laptop, keyboard, mouse."),
}
N_STEPS = max(STEPS)


def build_floor():
    # strips along y between the wall / spine / mid lines, so every floor plate is gripped by structure above it
    foot = (BASE - CUTOUT) | FILLER | DOCK_RECT
    deck_tile(foot, STRUCT | B_FULL | FILLER | DOCK_RECT, S_PLATE[TAN], 0, TAN, "base", 1, breaks=FLOOR_BREAKS)


def build_pockets():
    def two(region, L, w, kind, prefer, step, core_col=LBG):
        s, c = split_skin(region, L, w)
        sets = {"brick": S_BRICK, "plate": S_PLATE}[kind]
        fill(s, sets[skin_colour(L)], L, skin_colour(L), prefer, "pockets", step)
        fill(c, sets[core_col], L, core_col, prefer, "pockets", step)

    two(B_FULL, 1, 1, "plate", "y", 2)
    two(B_FULL - B_HOLES, 2, 2, "brick", "x", 2)
    two(B_FULL - B_HOLES, 5, 1, "plate", "y", 2)
    big = set()
    for (x, y, w, h) in base.BIG_TILES:
        mk("90498", x + PB0, y + PY0, w, h, base.FLOOR_L, BLK, "pockets", 5, rot=h > w)
        big |= R(x + PB0, y + PY0, w, h)
    fill(B_POCKETS - big, S_TILE[BLK], base.FLOOR_L, BLK, "x", "pockets", 5)
    two(B_FULL - B_POCKETS - big, base.FLOOR_L, 2, "plate", "x", 5)
    for L, w, prefer in ((7, 1, "y"), (10, 2, "x")):       # walls: Sand Blue where a face shows
        vis = (skin_of(B_WALLS, L, w) | {c for c in B_WALLS if any((c[0] + dx, c[1] + dy) in B_POCKETS
                                                                  for dx in range(-w, w + 1) for dy in range(-w, w + 1))})
        fill(vis, S_BRICK[SB], L, SB, prefer, "pockets", 6)
        fill(B_WALLS - vis, S_BRICK[LBG], L, LBG, prefer, "pockets", 6)


def build_hollow():
    for L, kind, w in ((1, "brick", 2), (4, "plate", 2), (5, "brick", 1), (8, "brick", 1), (11, "plate", 2)):
        S = struct_at(L)
        sets = {"brick": S_BRICK, "plate": S_PLATE}[kind]
        fixed = set()
        if L == 8:                                           # lintels over the clamp doorways
            for x in LINTEL:
                for y in (0, 1):
                    mk("2465", x, y, 16, 1, L, LBG, "base", 3)
                fixed |= R(x, 0, 16, 2)
        if L == 11:
            for x in LINTEL:
                mk("4282", x, 0, 16, 2, L, LBG, "base", 3)
                fixed |= R(x, 0, 16, 2)
        S -= fixed
        skin = skin_of(S & WALL2, L, w)
        col = skin_colour(L)
        if L in (5, 8):                                      # bridge the doors / open spans of the course below
            below = struct_at(L - 1)
            skin -= bridge(skin, below, sets[col], L, col, "base", 3)
            S -= bridge(S - skin_of(S & WALL2, L, w), below, sets[LBG], L, LBG, "base", 3)
        fill(skin, sets[col], L, col, "x" if L % 2 else "y", "base", 3)
        fill(S - skin_of(S & WALL2, L, w), sets[LBG], L, LBG, "y" if L % 2 else "x", "base", 3)
    # strip behind the dock
    for L, kind in ((1, "plate"), (2, "brick"), (5, "plate")):
        reg = FILLER - (CH_COLS if L >= 2 else set())
        s = band(reg, 2 if L != 5 else 1, footprint(7) | FILLER | DOCK_RECT) - R(DOCK_X0, 0, 1, DOCK_Y0)
        s &= reg
        sets = {"brick": S_BRICK, "plate": S_PLATE}[kind]
        fill(s, sets[skin_colour(L)], L, skin_colour(L), "x", "base", 3)
        fill(reg - s, sets[LBG], L, LBG, "x", "base", 3)
    fill(FILLER, S_TILE[SB], 6, SB, "x", "base", 3)          # roof (the tiles bridge the 2-stud channel)


def build_deck():
    edge = band(HZ, 1, BASE)                                 # outside row
    fill(edge, S_PLATE[SB], 12, SB, "x", "base", 7)
    deck = HZ - edge - HOLES12
    rest = set(deck)
    for name, lid in LIDS.items():
        deck_tile(lid & deck, SUPPORT11, S_PLATE[LBG], 12, LBG, "base", 7)
        rest -= lid
    deck_tile(rest, SUPPORT11, S_PLATE[LBG], 12, LBG, "base", 7)


GOLD_CELLS, ACCENTS = [], []


def build_top():
    fixed = set()
    kx = PB0 + base.KB_X0 + base.KB_NX // 2
    ky = PY0 + base.KB_Y0 - 1
    mx = PB0 + base.MS_X0 + base.MS_NX // 2
    my = PY0 + base.MS_Y0 - 1
    for (cx, cy) in ((kx, ky), (mx, my)):
        for x in (cx - 3, cx + 1):
            mk("3069b", x, cy, 2, 1, 13, GOLD, "pockets", 8)
            fixed |= R(x, cy, 2, 1)
            GOLD_CELLS.append((x, cy))
    for k, col in enumerate((BLO, LN, LAV)):
        for y in (BASE_D - 2, BASE_D - 1):
            mk("2431", 3 + 4 * k, y, 4, 1, 13, col, "base", 8)
            fixed |= R(3 + 4 * k, y, 4, 1)
        ACCENTS.append((3 + 4 * k, col))
    foot = NECK_FOOT[0] | NECK_FOOT[1]
    deck = HZ - HOLES12 - foot - fixed
    rest = set(deck)
    if not LITE:
        for name, lid in LIDS.items():
            fill(lid & deck, S_TILE[SB], 13, SB, "x", "base", 8)
            rest -= lid
        fill(rest, S_TILE[SB], 13, SB, "x", "base", 8)
    else:                                                    # lite: tiles only on the outside 2 rows of the deck
        rim = band(HZ, 2, BASE) & deck
        fill(rim, S_TILE[SB], 13, SB, "x", "base", 8)
    fill(B_WALLS - fixed, S_TILE[SB], 13, SB, "y", "pockets", 8)


DOCK_LOCAL = []


def build_dock():
    """The dock generator's build(), repacked with Sand-Blue-available parts, moved and recoloured."""
    dock.BRICK_SET = S_BRICK[SB]
    dock.PLATE_SET = S_PLATE[SB]
    dock.TILE_SET = S_TILE[SB]
    courses = dock.build()
    W2, D2 = 2 * dock.BASE_W, 2 * dock.BASE_D
    for c in courses:
        for p in c["parts"]:
            if p["z"] == 0:
                continue                                     # the dock's L0 is the station's floor (step 1)
            DOCK_LOCAL.append(dict(p))
            col = p["color"]
            outer = p["x"] + p["w"] == W2 or p["y"] + p["h"] == D2
            if col == dock.PANEL:
                col = TAN
            elif col == dock.BODY:
                if p["z"] >= 5:
                    col = SB if avail(p["part"], SB) >= MIN_SETS else LBG
                else:
                    col = TAN if (outer and avail(p["part"], TAN) >= MIN_SETS) else LBG
            q = dict(p, x=p["x"] + 2 * DOCK_X0, y=p["y"] + 2 * DOCK_Y0, color=col)
            _reg(q, "dock", 9 if p["step"] <= 7 else 10)


def build_necks():
    for n in NECK:
        x0, x1 = n["x0"], n["x1"]
        ped = R(x0, FY0, x1 - x0, FRAME_D)

        def cheeks(y0):
            return (R(x0, y0, 2, FY0 - y0) | R(x1 - 2, y0, 2, FY0 - y0)) if y0 < FY0 else set()

        flare = R(x0 - 2, FY0, 2, FRAME_D) | R(x1, FY0, 2, FRAME_D)
        fill(ped | cheeks(0) | flare, S_PLATE[SB], NECK_Z0, SB, "y", "necks", 11)
        for y in range(FY0, FY0 + FRAME_D):                  # flared foot: 45 deg slopes either side of the pedestal
            mk("3040b", x0 - 2, y, 2, 1, NECK_Z0 + 1, SB, "necks", 11, down="-x")
            mk("3040b", x1, y, 2, 1, NECK_Z0 + 1, SB, "necks", 11, down="+x")
        top_row = FY0 - 1                                    # last cheek row (high row of the top slope)
        for c in range(NECK_COURSES):
            z = NECK_Z0 + 1 + 3 * c
            yb = max(0, top_row - 2 - 3 * (NECK_COURSES - 1 - c))
            slope = c >= 1
            for xa in (x0, x1 - 2):
                if slope:
                    mk("3298", xa, yb, 2, 3, z, SB, "necks", 11, down="-y")
                    mk("3069b", xa, yb + 2, 2, 1, z + 3, SB, "necks", 11)
            ch = cheeks(yb + 3) if slope else cheeks(0)
            if c in (2, 3):                                  # the pastel stripes run through the pedestal
                fill(ch, S_BRICK[SB], z, SB, "y", "necks", 11)
            else:
                fill(ch | ped, S_BRICK[SB], z, SB, "y" if c % 2 else "x", "necks", 11)
        for k, col in enumerate((BLO, BLO, LN, LN, LAV, LAV)):
            fill(ped, S_PLATE[col], NECK_Z0 + 7 + k, col, "x" if k % 2 else "y", "necks", 11)


def build_frame():
    S = "frame"
    full = R(0, FY0, FRAME_W, FRAME_D)
    slot = R(BAR_X0, SLOT_Y, BAR_STUDS, 1)
    cornL, cornR = R(0, FY0, 2, FRAME_D), R(FRAME_W - 2, FY0, 2, FRAME_D)
    # ---- bottom beam (step 13) ----
    main = full - cornL - cornR
    fill(main, S_PLATE[SB], ZB, SB, "x", S, 13)
    fill(main - slot, S_BRICK[SB], ZB + 1, SB, "x", S, 13)
    fill(main - slot, S_BRICK[SB], ZB + 4, SB, "y", S, 13)
    for y in range(FY0, FY0 + FRAME_D):                      # chamfered bottom corners: inverted slopes
        mk("3665", 0, y, 2, 1, ZB, SB, S, 13, down="-x")
        mk("3665", FRAME_W - 2, y, 2, 1, ZB, SB, S, 13, down="+x")
    fill(cornL | cornR, S_BRICK[SB], ZB + 3, SB, "y", S, 13)
    fill(cornL | cornR, S_PLATE[SB], ZB + 6, SB, "y", S, 13)
    fill(full, S_PLATE[SB], ZB + 7, SB, "x", S, 13)
    # ---- sides, web, sills, lips (step 14) ----
    cols = cornL | cornR
    web = R(WEB_X, FY0, WEB_W, FRAME_D) | R(WEB_X - 1, FYB, WEB_W + 2, 1)
    n_c = HMAX // 3
    for c in range(n_c):
        fill(cols, S_BRICK[SB], ZO + 3 * c, SB, "y" if c % 2 else "x", S, 14)
        fill(web, S_BRICK[SB], ZO + 3 * c, SB, "x" if c % 2 else "y", S, 14)
    for L in range(ZO + 3 * n_c, ZT):
        fill(cols | web, S_PLATE[SB], L, SB, "y", S, 14)
    for i in (0, 1):
        ox0, n = OPEN_X[i], OPEN[i]["n"]
        inner0 = ox0 + (1 if i == 1 else 0)                  # the web flange already covers one stud of each opening
        inner1 = ox0 + n - (1 if i == 0 else 0)
        nb, nt = LIP[i]
        for L in range(ZO, ZO + SILL[i]):                    # sill under the shorter monitor (row behind the bezel)
            fill(R(ox0, FYB - 1, n, 1), S_PLATE[SB], L, SB, "x", S, 14)
        row = R(inner0, FYB, inner1 - inner0, 1)             # bottom lip
        L = ZO
        while L + 3 <= ZO + nb:
            fill(row, S_BRICK[SB], L, SB, "x", S, 14); L += 3
        while L < ZO + nb:
            fill(row, S_PLATE[SB], L, SB, "x", S, 14); L += 1
        side = R(ox0 if i == 0 else ox0 + n - 1, FYB, 1, 1)  # outer side lip (1 stud)
        z = ZO + nb
        while z + 3 <= ZT:
            fill(side, S_BRICK[SB], z, SB, "x", S, 14); z += 3
        while z < ZT:
            fill(side, S_PLATE[SB], z, SB, "x", S, 14); z += 1
        top = R(inner0 + (1 if i == 0 else 0), FYB, inner1 - inner0 - 1, 1)   # top lip, hangs under the top beam
        for L in range(ZT - nt, ZT):
            fill(top, S_PLATE[SB], L, SB, "x", S, 15)
        # retaining lips behind the monitor's top edge: 3 short blocks hanging under the top beam
        for f in (1 / 6, 1 / 2, 5 / 6):
            xs = ox0 + int(n * f) - 3
            fill(R(xs, FY0, 6, LIP_ROWS[i] - FY0), S_BRICK[SB], ZT - 3, SB, "x", S, 15)
    # ---- top beam (step 15) ----
    tslot = R(TBAR_X0, SLOT_Y, TBAR_STUDS, 1)

    def inset(k):
        return full - R(0, FY0, k, FRAME_D) - R(FRAME_W - k, FY0, k, FRAME_D)

    fill(inset(2) - tslot, S_BRICK[SB], ZT, SB, "x", S, 15)
    fill(inset(4) - tslot, S_BRICK[SB], ZT + 3, SB, "y", S, 15)
    fill(inset(6), S_PLATE[SB], ZT + 6, SB, "x", S, 15)
    fill(inset(6), S_TILE[SB], ZT + 7, SB, "x", S, 15)
    for (xa, z) in ((0, ZT), (2, ZT + 3), (4, ZT + 6)):      # rounded top corners: three steps of curved slopes
        for (xx, d) in ((xa, "-x"), (FRAME_W - 2 - xa, "+x")):
            mk("15068", xx, FY0, 2, 2, z, SB, S, 15, down=d)
            mk("15068", xx, FY0 + 2, 2, 2, z, SB, S, 15, down=d)
            mk("11477", xx, FY0 + 4, 2, 1, z, SB, S, 15, down=d)


def build():
    build_floor()
    build_pockets()
    build_hollow()
    build_deck()
    build_top()
    build_dock()
    build_necks()
    build_frame()


# =====================================================================================================================
# OUTPUT HELPERS
# =====================================================================================================================
def stud_points(p):
    if p["kind"] in ("tile", "cslope"):
        return []
    if p["kind"] == "islope":
        return [(x, y) for x in range(p["x"] + 1, p["x"] + p["w"], 2) for y in range(p["y"] + 1, p["y"] + p["h"], 2)]
    return dock.stud_points(p)


def receptors(p):
    pts = dock.receptors(p)
    if p["kind"] == "islope":           # only the cell away from the overhang has a bottom
        d = p["down"]
        if d == "-x": pts = {q for q in pts if q[0] == p["x"] + p["w"] - 1}
        if d == "+x": pts = {q for q in pts if q[0] == p["x"] + 1}
        if d == "-y": pts = {q for q in pts if q[1] == p["y"] + p["h"] - 1}
        if d == "+y": pts = {q for q in pts if q[1] == p["y"] + 1}
    return pts


def ldraw_line(p):
    if p["kind"] == "cslope":           # LDraw origin = centre of the footprint, at the BOTTOM; high end at +Z
        x, y, z, sx, sy, sz = dock.mm_box(p)
        return (f"1 {p['color']} {(x + sx / 2) * 2.5:g} {-z * 2.5:g} {-(y + sy / 2) * 2.5:g} "
                f"{dock.ROT[p['down']]} {p['part']}.dat")
    if p["kind"] == "islope":
        q = dict(p, kind="slope")
        return dock.ldraw_line(q)
    return dock.ldraw_line(p)


SECTIONS = ["base", "pockets", "dock", "necks", "frame"]
SECTION_NOTE = {"base": "hollow base: floor, outer wall, ribs, deck, deck tiles",
                "pockets": "keyboard + mouse pocket block (pads underneath)", "dock": "laptop dock (right end)",
                "necks": "two necks round the VESA poles", "frame": "screen frame round both monitors"}


def write_ldr(path):
    name = "night-array-station.ldr"
    L = [f"0 FILE {name}", "0 Night Array station (LEGO)", f"0 Name: {name}",
         "0 Author: make_lego_station.py (Night Array)", "0 !LDRAW_ORG Unofficial_Model",
         f"0 // {TOTAL_W} x {BASE_D} studs footprint ({TOTAL_W * STUD:.0f} x {BASE_D * STUD:.0f} mm), "
         f"{Z_TOP * PLATE:.1f} mm tall.  Front faces -Z.",
         f"0 // Monitors: left {MON[0]['name']}; right {MON[1]['name']}",
         "0 // Not LEGO, not in the file: VESA pole mounts, monitors, aluminium bars, pads, foam, felt, cables."]
    for s in SECTIONS:
        L.append(f"0 // Section: {s} -- {SECTION_NOTE[s]}")
        L.append(f"1 16 0 0 0 1 0 0 0 1 0 0 0 1 station-{s}.ldr")
        L.append("0 STEP")
    L.append("0 NOFILE")
    for s in SECTIONS:
        L += [f"0 FILE station-{s}.ldr", f"0 Night Array station: {s}", f"0 Name: station-{s}.ldr",
              "0 Author: make_lego_station.py (Night Array)", "0 !LDRAW_ORG Unofficial_Model"]
        for st in range(1, N_STEPS + 1):
            ps = [p for p in ALL if p["section"] == s and p["step"] == st]
            if not ps:
                continue
            L.append(f"0 // Step {st}: {STEPS[st][1]}")
            for p in sorted(ps, key=lambda p: (p["z"], p["y"], p["x"])):
                L.append(ldraw_line(p))
            L.append("0 STEP")
        L.append("0 NOFILE")
    path.write_text("\n".join(L) + "\n")


def price(p):
    return round(PARTS[p["part"]][4] * COLOURS[p["color"]][3], 2)


def bom(parts):
    cnt = Counter((p["part"], p["color"]) for p in parts)
    rows = []
    for (pid, col), n in sorted(cnt.items(), key=lambda kv: (PARTS[kv[0][0]][0], kv[0][1], kv[0][0])):
        kind, w, l, name, pr = PARTS[pid]
        unit = round(pr * COLOURS[col][3], 2)
        rows.append({"part": pid, "bricklink_id": pid, "name": name, "kind": kind, "colour": COLOURS[col][2],
                     "ldraw_colour": col, "bricklink_colour": COLOURS[col][0], "qty": n, "unit_usd": unit,
                     "total_usd": round(n * unit, 2), "sets_with_this_colour": avail(pid, col)})
    return rows


def write_lists(rows):
    with open(OUT / "parts.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["part", "bricklink_id", "name", "colour", "ldraw_colour", "bricklink_colour", "qty",
                    "est_unit_usd", "est_total_usd", "sets_containing_part_in_colour"])
        for r in rows:
            w.writerow([r["part"], r["bricklink_id"], r["name"], r["colour"], r["ldraw_colour"],
                        r["bricklink_colour"], r["qty"], f"{r['unit_usd']:.2f}", f"{r['total_usd']:.2f}",
                        r["sets_with_this_colour"]])
    x = ["<INVENTORY>"]
    for r in rows:
        x.append(f"  <ITEM><ITEMTYPE>P</ITEMTYPE><ITEMID>{r['bricklink_id']}</ITEMID><COLOR>{r['bricklink_colour']}</COLOR>"
                 f"<MINQTY>{r['qty']}</MINQTY></ITEM>")
    x.append("</INVENTORY>")
    (OUT / "bricklink-wanted.xml").write_text("\n".join(x) + "\n")


def reference_boxes():
    refs = []

    def add(name, kind, col, x, y, z, sx, sy, sz, step=None, **kw):
        r = {"name": name, "color_hex": col, "x": round(x, 2), "y": round(y, 2), "z": round(z, 2), "sx": round(sx, 2),
             "sy": round(sy, 2), "sz": round(sz, 2), "kind": kind}
        if step:
            r["step"] = step
        r.update(kw)
        refs.append(r)

    for i in (0, 1):
        m = MON[i]
        side = "left" if i == 0 else "right"
        t = min(m["top_edge_depth"], m["D"])
        add(f"{m['name']} ({side} monitor, housing)", "monitor", "#17181b", MON_X0[i], Y_FACE - t, MON_Z0[i], m["W"], t,
            m["H"], 12)
        bw, bh = m["W"] * 0.62, m["H"] * 0.62
        add(f"{side} monitor rear bulge (ports face down, vents)", "monitor", "#1d1e22", MON_CX[i] - bw / 2,
            Y_FACE - m["vesa_to_front"], VESA_Z[i] - bh / 2, bw, m["vesa_to_front"] - t, bh, 12)
        add(f"{side} screen (active area {ACTIVE_W} x {ACTIVE_H})", "screen", "#07080c", MON_CX[i] - ACTIVE_W / 2,
            Y_FACE - 0.2, MON_Z0[i] + m["bezel"]["bottom"], ACTIVE_W, 0.6, ACTIVE_H, 12)
        px, py = MON_CX[i], STAND["pole_y"]
        add(f"VIVO STAND-V001C pole dia {STAND['pole_d']:.0f} x {STAND['pole_len']:.0f} ({side})", "stand", "#3a3d42",
            px - STAND["pole_d"] / 2, py - STAND["pole_d"] / 2, STAND["clamp_h"], STAND["pole_d"], STAND["pole_d"],
            STAND["pole_len"], 4, shape="cyl")
        add(f"C-clamp top plate on the desk ({side}; steel)", "stand", "#2b2d31", px - STAND["clamp_w"] / 2, 0,
            0, STAND["clamp_w"], STAND["clamp_d"], STAND["clamp_h"], 4)
        add(f"C-clamp body under the desk edge ({side})", "stand", "#2b2d31", px - 30, -22, -70, 60, 22,
            70 + STAND["clamp_h"], 4)
        y_plate = Y_FACE - m["vesa_to_front"] - SPACER[i]
        add(f"tilt bracket ({side})", "stand", "#3a3d42", px - 30, py, VESA_Z[i] - 35, 60, y_plate - 4 - py, 70, 4)
        add(f"VESA plate 120 x 120 ({side})", "stand", "#3a3d42", px - 60, y_plate - 4, VESA_Z[i] - 60, 120, 4, 120, 12)
        if SPACER[i]:
            for dx in (-50, 50):
                for dz in (-50, 50):
                    add(f"M4 stand-off {SPACER[i]} mm ({side})", "hardware", "#b8a05a", px + dx - 4, y_plate,
                        VESA_Z[i] + dz - 4, 8, SPACER[i], 8, 12)
    for (z, st, nm, x0, n, ln) in ((ZB + 1, 13, "bottom beam", BAR_X0, BAR_STUDS, BAR["len"]),
                                   (ZT, 15, "top beam", TBAR_X0, TBAR_STUDS, BAR["len_top"])):
        add(f"aluminium flat bar 3.2 x 19 x {ln:.0f} in the {nm}", "bar", "#c9ccd1", x0 * STUD + (n * STUD - ln) / 2,
            SLOT_Y * STUD + (STUD - BAR["t"]) / 2, z * PLATE, ln, BAR["t"], BAR["h"], st)
    for r in base.reference_boxes():                         # keyboard, mouse, pads, foam, Magic Tag
        r = dict(r, x=r["x"] + PB0 * STUD, y=r["y"] + PY0 * STUD)
        r["step"] = 4 if r.get("step") == 5 else 16
        refs.append(r)
    for r in dock.reference_boxes():                         # laptop, plug, foam, felt
        r = dict(r, x=r["x"] + DOCK_X0 * STUD, y=r["y"] + DOCK_Y0 * STUD)
        r["step"] = 9 if r.get("step") == 5 else 16
        if r["name"].startswith("USB4 cable"):               # stop it at the back edge of the station
            end = r["y"] + r["sy"]
            r["y"], r["sy"] = -20.0, end + 20.0
        refs.append(r)
    bx = (DOCKBAY[0] + 1) * STUD
    add("Plugable UD-6950PDH dock box 225 x 85 x 24.5", "electronics", "#2f3136", bx, (REAR + 2) * STUD + 2, PLATE,
        PLUGABLE[0], PLUGABLE[1], PLUGABLE[2], 4)
    return refs


def brick_json(p):
    kind, w, l, name, _ = PARTS[p["part"]]
    x, y, z, sx, sy, sz = dock.mm_box(p)
    b = {"part": p["part"], "name": name, "kind": {"cslope": "slope", "islope": "slope"}.get(kind, kind),
         "color": COLOURS[p["color"]][2], "color_hex": COLOURS[p["color"]][1], "x": x, "y": y, "z": round(z, 2),
         "sx": sx, "sy": sy, "sz": round(sz, 2), "step": p["step"], "section": p["section"]}
    if kind == "slope":
        b["slope"] = {"down": p["down"], "high_mm": STUD, "lip_mm": dock.SLOPE_LIP}
    elif kind == "cslope":
        b["slope"] = {"down": p["down"], "high_mm": 1.0, "lip_mm": 3.0, "curved": True}
    elif kind == "islope":
        b["slope"] = {"down": p["down"], "high_mm": STUD, "lip_mm": 0.0, "inverted": True}
    return b


def write_json(refs):
    doc = {"units": "mm",
           "frame": "x right (as you sit), y depth toward the user (0 = back edge of the base / desk), z up (0 = "
                    "desk); origin back-left-bottom of the base; boxes on the nominal 8 mm grid (real parts 0.1 mm "
                    "smaller/side); studs (dia 4.8, 1.7 tall) on top of every non-tile part (slopes: high row only; "
                    "jumper 15573: one centre stud; curved slopes: none); 'slope' {down, high_mm, lip_mm} as in "
                    "dock/bricks.json, plus curved:true (2/3-high bow, no studs) or inverted:true (the overhang "
                    "points toward 'down', studs on the whole top); 'section' = base | pockets | dock | necks | frame",
           "size_mm": [TOTAL_W * STUD, BASE_D * STUD, round(Z_TOP * PLATE, 2)], "size_studs": [TOTAL_W, BASE_D],
           "sections": SECTION_NOTE, "steps": {str(k): v[1] for k, v in STEPS.items()},
           "step_section": {str(k): v[0] for k, v in STEPS.items()},
           "bricks": [brick_json(p) for p in ALL], "reference": refs}
    (OUT / "bricks.json").write_text(json.dumps(doc, indent=0))
    return doc


# =====================================================================================================================
# NON-LEGO PARTS
# =====================================================================================================================
def non_lego():
    foam = [round(max(0.0, g - 2.0)) for g in LIP_GAP]
    items = [
        {"id": "vesa_mount", "qty": 2, "unit_usd": STAND["usd"], "product": STAND["product"], "mpn": STAND["mpn"],
         "url": STAND["url"], "role": "carries one monitor each: steel pole, tilt bracket, C-clamp (or grommet bolt)",
         "dims": "pole 17.7 in (450 mm) x ~35 mm dia; 17.6 lb (8 kg); VESA 75 + 100; desk 10-88 mm (clamp)"},
        {"id": "frame_bar_bottom", "qty": 1, "unit_usd": BAR["usd"], "product": "Aluminium flat bar 1/8 in x 3/4 in x 48 in (6063), e.g. Everbilt / Hillman",
         "mpn": "generic 1/8 x 3/4 x 48", "url": "any hardware store (Home Depot / Lowe's / Ace metal rack)",
         "role": "stiffener in the frame's bottom beam (slot 8 mm wide x 19.2 mm high); no cutting",
         "dims": "3.2 x 19.05 x 1219 mm, ~0.2 kg"},
        {"id": "frame_bar_top", "qty": 1, "unit_usd": BAR["usd_top"], "product": "Aluminium flat bar 1/8 in x 3/4 in x 36 in (6063)",
         "mpn": "generic 1/8 x 3/4 x 36", "url": "same rack",
         "role": "stiffener in the frame's top beam, centred on the web between the screens; no cutting",
         "dims": "3.2 x 19.05 x 914 mm, ~0.15 kg"},
        {"id": "vesa_standoffs", "qty": 1 if any(SPACER) else 0, "unit_usd": 9.0,
         "product": f"4 x M4 male-female hex stand-off {max(SPACER)} mm (steel or brass) + 4 x M4 x 10 screws",
         "mpn": "generic", "url": "any fastener kit",
         "role": f"brings the thinner monitor's glass forward into the same plane (stand-offs: left {SPACER[0]} mm, "
                 f"right {SPACER[1]} mm)", "dims": f"M4, {max(SPACER)} mm"},
        {"id": "felt", "qty": 1, "unit_usd": 8.0, "product": "self-adhesive felt sheet 1 mm, A4, x2 (shared with the dock)",
         "mpn": "generic", "url": "craft store",
         "role": "dock liners (see ../dock/README.md); dots inside the bezel corners; side liners in an opening "
                 f"when the stud grid leaves more than 4 mm (left {OPEN[0]['liner_x']:.0f} mm, right {OPEN[1]['liner_x']:.0f} mm per side)",
         "dims": "1 mm"},
        {"id": "eva", "qty": 1, "unit_usd": 7.0, "product": "EVA craft foam 3 mm sheet + 1 mm foam tape (shared with the dock)",
         "mpn": "generic", "url": "craft store",
         "role": f"plug pocket pads (dock); pads on the retaining lips (left {foam[0]} mm, right {foam[1]} mm thick); "
                 "foam collars between pole and neck cheeks; 2 mm foam under each Qi pad", "dims": "3 mm / 1 mm"},
        {"id": "feet", "qty": 1, "unit_usd": 6.0, "product": "3M Bumpon SJ5023 (in kit/parts.json: feet) or thin felt dots",
         "mpn": "SJ5023", "url": "see ../../parts.json", "role": "optional: under the floor plates on a slippery desk",
         "dims": ""},
    ]
    pointers = ["dock (Plugable UD-6950PDH)", "cradle_cable (Newnex U4T1C01CR5P010)", "keyboard", "keyboard_qi",
                "mouse", "qi_pad (x2)", "power_strip (outside, behind/under the desk: it does not fit inside)",
                "monitor_cords (only for a monitor with an internal PSU)", "gan_charger", "ties"]
    total = sum(i["qty"] * i["unit_usd"] for i in items)
    doc = {"note": "Non-LEGO parts of the LEGO station. Electronics are NOT repeated here: they are the items with "
                   "these ids in night-array/kit/parts.json. The two monitors are the owner's own.",
           "items": items, "electronics_in_kit_parts_json": pointers, "total_usd": round(total, 2)}
    (OUT / "non-lego-parts.json").write_text(json.dumps(doc, indent=1))
    md = ["# Night Array LEGO station: parts that are not LEGO", "",
          "Generated by `make_lego_station.py`. Prices are US street prices on 2026-11-11.", "",
          "| Qty | Part | Part no. | Each | Role | Size |", "|---|---|---|---|---|---|"]
    for i in items:
        if i["qty"]:
            md.append(f"| {i['qty']} | {i['product']} | {i['mpn']} | ${i['unit_usd']:.2f} | {i['role']} | {i['dims']} |")
    md += ["", f"Total: about **${total:.0f}**.", "",
           "Electronics (already in [`../../parts.json`](../../parts.json), not counted above): "
           + "; ".join(pointers) + ".", "",
           f"Stand source: <{STAND['url']}> (price, pole height, capacity, VESA and desk thickness checked there). "
           "Pole diameter, bracket depth and clamp plate size are estimates: measure them when the stand arrives "
           "and put them in the `STAND` block of the script."]
    (OUT / "non-lego-parts.md").write_text("\n".join(md) + "\n")
    return doc


# =====================================================================================================================
# CHECKS
# =====================================================================================================================
def part_mass(p):
    kind = p["kind"]
    cells = (p["w"] / 2) * (p["h"] / 2)
    per = dock.MASS_PER_CELL[kind] * (0.65 if kind == "plate" and cells >= 32 else 1.0)
    return per * cells + (0.12 if p["part"] == dock.JUMPER else 0)


def run_checks(rows, refs):
    res = []

    def chk(name, ok, detail):
        res.append({"check": name, "ok": bool(ok), "detail": detail})

    # ---- 1 packing: no overlaps anywhere, pocket block + dock layers exactly as their generators define them ----
    occ = defaultdict(Counter)
    for p in ALL:
        for L in range(p["z"], p["z"] + p["nz"]):
            for c in dock.cells_h(p):
                occ[L][c] += 1
    over = sum(1 for L in occ for c, n in occ[L].items() if n > 1)
    H = lambda cells: {(2 * x + a, 2 * y + b) for (x, y) in cells for a in (0, 1) for b in (0, 1)}
    bad = []
    blk = H(B_FULL)
    for L in range(N_BASE):
        if L == 0: want = H((BASE - CUTOUT) | FILLER | DOCK_RECT)
        else:
            if L == 1: w = B_FULL
            elif L in base.CAVITY_LAYERS: w = B_FULL - B_HOLES
            elif L == base.FLOOR_L: w = B_FULL
            else: w = B_WALLS
            want = H(w)
        got = set(occ[L]) & (blk if L else set(occ[L]))
        if got != want:
            bad.append(f"L{L}: missing {len(want - got)}, extra {len(got - want)}")
    # hollow part: every layer equals the intended structure
    hz = H(HZ)
    for L in range(1, 12):
        want = H(struct_at(L))
        got = set(occ[L]) & hz
        if got != want:
            bad.append(f"hollow L{L}: missing {len(want - got)}, extra {len(got - want)}")
    if set(occ[12]) & hz != H(HZ - HOLES12):
        bad.append("deck L12 not exact")
    # dock: the dock generator's own expected layers (local frame)
    dwant = dock.expected_layers()
    docc = defaultdict(set)
    for p in DOCK_LOCAL:
        for L in range(p["z"], p["z"] + p["nz"]):
            docc[L] |= dock.cells_h(p)
    for L in sorted(set(dwant) | set(docc)):
        if L and docc[L] != dwant.get(L, set()):
            bad.append(f"dock L{L}: differs from make_lego_dock.expected_layers()")
    chk("layers packed exactly (no overlaps; pocket block = base generator's tray; hollow walls/ribs/deck = plan; "
        "dock = dock generator's layers)", not bad and not over,
        "; ".join(bad) or f"{len(occ)} plate layers, 0 overlapping half-cells; pocket block 14 layers, hollow "
                           f"structure 11 layers + deck, dock {len(dwant) - 1} layers all exact")

    # ---- 2 part table / LDraw ids / colour availability ----
    unknown = sorted({p["part"] for p in ALL if p["part"] not in PARTS or p["color"] not in COLOURS})
    rare = sorted({(r["part"], r["colour"], r["sets_with_this_colour"]) for r in rows if r["sets_with_this_colour"] < MIN_SETS})
    fallback = Counter()
    for p in ALL:
        if p["section"] == "dock" and p["color"] == LBG and p["z"] >= 5:
            fallback[p["part"]] += 1
    chk(f"every part is in the part table and exists in its colour (>= {MIN_SETS} sets, Rebrickable inventories)",
        not unknown and not rare,
        (f"unknown {unknown}; rare {rare}" if unknown or rare else
         f"{len(rows)} part/colour lines, all LDraw ids verified against library.ldraw.org; least common line: "
         + ", ".join(f"{r['part']} {r['colour']} ({r['sets_with_this_colour']} sets)"
                     for r in sorted(rows, key=lambda r: r["sets_with_this_colour"])[:6])))

    # ---- 3 stud alignment + connectivity ----
    by_bottom = defaultdict(dict)
    for i, p in enumerate(ALL):
        m = by_bottom[p["z"]]
        for X in range(p["x"] + 1, p["x"] + p["w"]):
            for Y in range(p["y"] + 1, p["y"] + p["h"]):
                m[(X, Y)] = i
    adj = defaultdict(set)
    collisions = []
    for i, p in enumerate(ALL):
        zt = p["z"] + p["nz"]
        for s in stud_points(p):
            j = by_bottom.get(zt, {}).get(s)
            if j is None:
                continue
            if s in receptors(ALL[j]):
                adj[i].add(j); adj[j].add(i)
            elif ALL[j]["kind"] != "islope":
                collisions.append((p["part"], ALL[j]["part"], zt))
    chk("every stud under a part lands in a stud socket", not collisions,
        f"{len(collisions)} collisions: {collisions[:5]}" if collisions else "all studs aligned")
    comp = {}
    for i in range(len(ALL)):
        if i in comp:
            continue
        comp[i] = i
        stack = [i]
        while stack:
            for j in adj[stack.pop()]:
                if j not in comp:
                    comp[j] = i; stack.append(j)
    by_sec = defaultdict(set)
    for i, p in enumerate(ALL):
        by_sec[p["section"]].add(comp[i])
    n_comp = len(set(comp.values()))
    loose = Counter(ALL[r]["section"] + ":" + ALL[r]["part"] for r in set(comp.values()))
    chk("connectivity: all sections are one stud-connected assembly", n_comp == 1,
        f"{n_comp} connected group(s); " + ("sections share one group: " + ", ".join(SECTIONS) if n_comp == 1 else
                                            f"groups rooted at {dict(loose.most_common(8))}"))
    hang = [p for i, p in enumerate(ALL) if p["z"] > 0 and not any(ALL[j]["z"] < p["z"] for j in adj[i])]
    hc = Counter(p["section"] for p in hang)
    chk("parts held from above only (not gripped from below)", True,
        f"{len(hang)} ({dict(hc)}): plates bridging cable channels / doors, the top bezel lip, the retaining lips "
        "and the bottom corner slopes hang from the course above")

    # ---- 4 pockets + pads (same rules as the base generator) ----
    cl = {"keyboard x": base.KB_CLR_X, "keyboard y": base.KB_CLR_Y, "mouse x": base.MS_CLR_X, "mouse y": base.MS_CLR_Y}
    chk(f"pocket clearance >= {base.MIN_CLR} mm per side", min(cl.values()) >= base.MIN_CLR - 1e-9,
        ", ".join(f"{k} {v:.2f}" for k, v in cl.items()))
    floor = {}
    for p in ALL:
        if p["z"] <= base.FLOOR_L < p["z"] + p["nz"]:
            for c in dock.cells_h(p):
                floor[c] = p
    det, ok4 = [], True
    for nm, pi, pocket in (("keyboard", base.KB_PADI, base.KB_POCKET | base.TAG_NOTCH), ("mouse", base.MS_PADI, base.MS_POCKET)):
        pc = sh(base.pad_cells(pi))
        under = pc & sh(pocket)
        tiles_ok = all(floor[(2 * x, 2 * y)]["kind"] == "tile" for (x, y) in under)
        cav_clear = all((2 * x, 2 * y) not in occ[L] for L in base.CAVITY_LAYERS for (x, y) in pc)
        base_ok = all((2 * x, 2 * y) in occ[1] for (x, y) in pc)
        pad_top = base.CAVITY_LAYERS.start * PLATE + base.FOAM + base.PAD_H
        gap = base.FLOOR_L * PLATE - pad_top
        sup = [p for p in ALL if p["part"] == "90498" and {(x // 2, y // 2) for (x, y) in dock.cells_h(p)} & pc]
        sup_ok = all(len({c for c in dock.cells_h(s) if c in occ[base.FLOOR_L - 1]}) >= 8 * 4 for s in sup)
        ok = tiles_ok and cav_clear and base_ok and abs(gap) <= 0.5 and sup_ok
        ok4 &= ok
        det.append(f"{nm}: {len(under)} pad cells under the device all tile={tiles_ok}, cavity clear={cav_clear}, "
                   f"pad top {pad_top:.1f} vs tile underside {base.FLOOR_L * PLATE:.1f} (gap {gap:+.1f}), 8x16 tiles "
                   f"gripped={sup_ok}, pad centre off the coil estimate ({pi['offset'][0]:+.1f}, {pi['offset'][1]:+.1f}) mm")
    chk("one 3.2 mm tile layer between each pad and its device; pad top touches it", ok4, "; ".join(det))
    # Qi keep-outs: steel >= 20 mm, any metal >= 10 mm from each pad footprint
    dmin = 1e9
    mets = [r for r in refs if r["kind"] in ("stand", "bar", "hardware")]
    pads = [r for r in refs if r["kind"] == "pad"]
    for a in pads:
        for b in mets:
            d = [max(b[k] - (a[k] + a["s" + k]), a[k] - (b[k] + b["s" + k]), 0) for k in "xyz"]
            dd = math.sqrt(sum(v * v for v in d))
            dmin = min(dmin, dd)
    chk("Qi keep-out: steel >= 20 mm and all metal >= 10 mm from each pad", dmin >= 20.0,
        f"nearest metal (clamp plate / pole / bars / stand-offs) is {dmin:.0f} mm from a pad; gold marks and all "
        f"else near the pads is ABS")

    # ---- 5 monitor openings ----
    det, ok5 = [], True
    for i in (0, 1):
        m, o = MON[i], OPEN[i]
        nb, nt = LIP[i]
        cov_b = (nb - SILL[i]) * PLATE - o["clr_z"]
        cov_t = nt * PLATE - o["clr_z"]
        cov_s = STUD - (o["clr_x"] + o["liner_x"])
        okm = (SCREEN_GAP[0] - 1e-6 <= o["clr_x"] <= SCREEN_GAP[1] and SCREEN_GAP[0] - 1e-6 <= o["clr_z"] <= SCREEN_GAP[1]
               and cov_b <= m["bezel"]["bottom"] and cov_t <= m["bezel"]["top"] and cov_s <= m["bezel"]["side"])
        ok5 &= okm
        det.append(f"{'left' if i == 0 else 'right'} {m['key']}: housing {m['W']} x {m['H']} in {o['n']} studs x "
                   f"{o['nz']} plates = {o['n'] * STUD:.0f} x {o['nz'] * PLATE:.1f} mm -> clearance {o['clr_x']:.2f} mm "
                   f"each side" + (f" after a {o['liner_x']:.0f} mm felt liner each side" if o["liner_x"] else "")
                   + f", {o['clr_z']:.2f} top and bottom; bezel lips cover {cov_s:.1f} / {cov_t:.1f} / {cov_b:.1f} mm "
                   f"of the {m['bezel']['side']} / {m['bezel']['top']} / {m['bezel']['bottom']} mm side / top / bottom "
                   f"border (never the lit area)")
    chk(f"monitor openings: {SCREEN_GAP[0]}-{SCREEN_GAP[1]} mm clearance all round, lips stay off the picture", ok5,
        "; ".join(det))
    seam = MON_X0[1] - (MON_X0[0] + MON[0]["W"])
    pic = seam + MON[0]["bezel"]["side"] + MON[1]["bezel"]["side"]
    touch = [p for p in ALL if p["section"] == "frame" and any(
        dock.mm_box(p)[0] < MON_X0[i] + MON[i]["W"] and dock.mm_box(p)[0] + dock.mm_box(p)[3] > MON_X0[i]
        and dock.mm_box(p)[2] < MON_Z0[i] + MON[i]["H"] and dock.mm_box(p)[2] + dock.mm_box(p)[5] > MON_Z0[i]
        and dock.mm_box(p)[1] < Y_FACE and dock.mm_box(p)[1] + dock.mm_box(p)[4] > Y_FACE - MON[i]["top_edge_depth"]
        for i in (0, 1))]
    chk("nothing LEGO touches a monitor (no load on the panels)", not touch and FACE_GAP[0] <= FACE_AIR <= FACE_GAP[1],
        f"{len(touch)} frame parts intersect a housing; air between the front glass (y {Y_FACE:.1f}) and the back of "
        f"the bezel bricks (y {FYB * STUD:.0f}): {FACE_AIR:.1f} mm; housings {seam:.1f} mm apart (one stud of web + "
        f"clearances) -> picture-to-picture gap about {pic:.0f} mm; glass planes aligned with stand-offs "
        f"{SPACER[0]} / {SPACER[1]} mm (left / right)")
    chk("frame cannot fall forward: retaining lips behind the monitors' top edge", all(LIP_ROWS[i] > FY0 and 1.0 <= LIP_GAP[i] <= 9.5 for i in (0, 1)),
        "; ".join(f"{'left' if i == 0 else 'right'}: 3 blocks {LIP_ROWS[i] - FY0} stud(s) deep x 6 wide hang 9.6 mm "
                  f"below the top beam, {LIP_GAP[i]:.1f} mm behind the housing's top edge (fill to ~2 mm with "
                  f"{max(0.0, LIP_GAP[i] - 2):.0f} mm foam), overlap {9.6 - OPEN[i]['clr_z']:.1f} mm" for i in (0, 1))
        + "; vents, ports and rear buttons stay open: the frame is only 40 mm deep and has no back")

    # ---- 6 stands / poles / necks ----
    det, ok6 = [], True
    for i in (0, 1):
        n, m = NECK[i], MON[i]
        r = STAND["pole_d"] / 2
        cx = min(MON_CX[i] - r - n["c0"] * STUD, n["c1"] * STUD - MON_CX[i] - r)
        hy0 = min(c[1] for c in n["hole"]) * STUD
        hy1 = (max(c[1] for c in n["hole"]) + 1) * STUD
        cy = min(STAND["pole_y"] - r - hy0, hy1 - STAND["pole_y"] - r)
        top = STAND["clamp_h"] + STAND["pole_len"]
        okm = cx >= 2.0 and cy >= 2.0 and VESA_Z[i] + 40 <= top and m["kg"] <= STAND["max_kg"] and m["vesa"] in (75, 100)
        ok6 &= okm
        det.append(f"{'left' if i == 0 else 'right'}: pole dia {STAND['pole_d']:.0f} at x {MON_CX[i]:.0f}, y "
                   f"{STAND['pole_y']:.0f}: {cx:.1f} mm to the cheeks, {cy:.1f} mm fore/aft in the deck hole; VESA "
                   f"centre {VESA_Z[i]:.0f} mm up, pole top {top:.0f}; {m['kg']} kg on a {STAND['max_kg']:.0f} kg "
                   f"mount (x{STAND['max_kg'] / m['kg']:.1f}); VESA {m['vesa']}")
    clamp_fit = all(STAND["clamp_w"] <= 2 * CLAMP_HALF * STUD and STAND["clamp_d"] <= (REAR - 2) * STUD
                    and STAND["clamp_h"] <= 7 * PLATE for _ in (0,))
    chk("VESA poles: clearance inside the necks, height, rated load, clamp bays", ok6 and clamp_fit,
        "; ".join(det) + f"; clamp plate {STAND['clamp_w']:.0f} x {STAND['clamp_d']:.0f} x {STAND['clamp_h']:.0f} in a "
        f"bay {2 * CLAMP_HALF * STUD:.0f} x {(REAR - 2) * STUD:.0f} mm with a {7 * PLATE:.1f} mm high doorway; necks "
        f"top at {ZB * PLATE:.0f} mm, monitors start at {min(MON_Z0):.0f} mm")

    # ---- 7 stability ----
    mass = defaultdict(float)
    mom = defaultdict(lambda: [0.0, 0.0, 0.0])
    for p in ALL:
        g = part_mass(p)
        x, y, z, sx, sy, sz = dock.mm_box(p)
        mass[p["section"]] += g
        for k, v in enumerate((x + sx / 2, y + sy / 2, z + sz / 2)):
            mom[p["section"]][k] += g * v
    lego_g = sum(mass.values())
    lap = next(r for r in refs if r["kind"] == "device" and "MacBook" in r["name"])
    bodies = [(lego_g / 1000, [sum(mom[s][k] for s in mass) / lego_g for k in range(3)])]
    lapm = dock.LAP["kg"]
    lapc = [lap["x"] + lap["sx"] / 2, lap["y"] + lap["sy"] / 2, lap["z"] + lap["sz"] / 2]
    Wm, Dm = TOTAL_W * STUD, BASE_D * STUD

    def tip_angles(bodies):
        M = sum(b[0] for b in bodies)
        c = [sum(b[0] * b[1][k] for b in bodies) / M for k in range(3)]
        return M, c, {"left": math.degrees(math.atan2(c[0], c[2])), "right": math.degrees(math.atan2(Wm - c[0], c[2])),
                      "back": math.degrees(math.atan2(c[1], c[2])), "front": math.degrees(math.atan2(Dm - c[1], c[2]))}

    M1, c1, a1 = tip_angles(bodies)
    M2, c2, a2 = tip_angles(bodies + [(lapm, lapc)])
    chk("LEGO station on its own (it carries no monitor): tips at >= 10 deg, laptop docked or not",
        min(min(a1.values()), min(a2.values())) >= 10.0,
        f"LEGO ~{lego_g / 1000:.1f} kg (estimate), centre of mass {c1[2]:.0f} mm up: tips at "
        + " / ".join(f"{k} {v:.0f}" for k, v in a1.items()) + f" deg; with the {lapm} kg laptop: "
        + " / ".join(f"{k} {v:.0f}" for k, v in a2.items()) + " deg")
    # frame on the pedestals
    fm = mass["frame"] / 1000 + 2 * 0.2
    fc = [mom["frame"][k] / mass["frame"] for k in range(3)]
    arm = (FYB + 1) * STUD - fc[1]                       # to the front edge of the pedestals
    tip_frame = math.degrees(math.atan2(arm, fc[2] - ZB * PLATE))
    chk("frame stands on the pedestals by itself when level (lips only work in a knock)", fc[1] > FY0 * STUD and arm > 8,
        f"frame ~{fm:.2f} kg with the two bars, centre of mass y {fc[1]:.0f} (pedestals y {FY0 * STUD}-{(FYB + 1) * STUD}), "
        f"{fc[2] - ZB * PLATE:.0f} mm above them: balanced to {tip_frame:.1f} deg without any clutch; beyond that the "
        f"stud clutch and then the retaining lips hold it (a 10 deg tilt needs {fm * 9.81 * (fc[2] - ZB * PLATE) / 1000 * math.sin(math.radians(10)) - fm * 9.81 * arm / 1000 * math.cos(math.radians(10)):.2f} N m)")
    # bars
    I = BAR["t"] * BAR["h"] ** 3 / 12
    cant = MON_CX[0] - (NECK[0]["x1"] - NECK[0]["x0"]) * STUD / 2
    P_end = 0.35 * 9.81
    d_cant = P_end * cant ** 3 / (3 * BAR["E"] * I)
    span = MON_CX[1] - MON_CX[0]
    d_mid = 0.5 * 9.81 * span ** 3 / (48 * BAR["E"] * I)
    chk("frame beams: aluminium bar deflection < 1.5 mm", d_cant < 1.5 and d_mid < 1.5,
        f"bar I = {I:.0f} mm4; bottom beam overhangs the neck by {cant:.0f} mm carrying ~0.35 kg (side column + "
        f"corner + end of the top beam) -> {d_cant:.2f} mm at the tip; the web between the screens (~0.5 kg) "
        f"mid-way between the necks ({span:.0f} mm) -> {d_mid:.2f} mm; LEGO alone would sag, hence the bars")
    # monitors on clamped poles
    det, ok7 = [], True
    for i in (0, 1):
        m = MON[i]
        w = m["kg"] * 9.81
        ecc = (STAND["bracket"] + SPACER[i] + m["vesa_to_front"] / 2) / 1000
        top = (MON_Z0[i] + m["H"]) / 1000
        M_push = 50.0 * top + w * ecc
        M_tilt = w * (math.sin(math.radians(10)) * VESA_Z[i] / 1000 + math.cos(math.radians(10)) * ecc)
        T = M_push / (STAND["clamp_lever"] / 1000)
        margin = STAND["clamp_screw_n"] / T
        z_mod = math.pi / 32 * (STAND["pole_d"] ** 4 - (STAND["pole_d"] - 3.0) ** 4) / STAND["pole_d"]
        sig = M_push * 1000 / z_mod
        ok7 &= margin >= 2.0 and sig < 235 / 2
        det.append(f"{'left' if i == 0 else 'right'} ({m['kg']} kg): 50 N at the top of the screen ({top * 1000:.0f} mm) "
                   f"+ own weight {ecc * 1000:.0f} mm in front of the pole = {M_push:.1f} N m at the clamp (10 deg "
                   f"tilt alone: {M_tilt:.1f} N m) -> clamp screw {T:.0f} N of ~{STAND['clamp_screw_n']:.0f} N "
                   f"(margin x{margin:.1f}); pole bending {sig:.0f} MPa of 235 (x{235 / sig:.1f})")
    # the same loads if the poles were NOT clamped (whole station as one rigid body on the desk) -- information
    mons = [(MON[i]["kg"], [MON_CX[i], Y_FACE - MON[i]["vesa_to_front"] / 2, VESA_Z[i]]) for i in (0, 1)]
    stands = [(2.3, [MON_CX[i], STAND["pole_y"], 200.0]) for i in (0, 1)]
    Mt, ct, _ = tip_angles(bodies + mons + stands)
    ztop = max(MON_Z0[i] + MON[i]["H"] for i in (0, 1))
    free_f = Mt * 9.81 * (Dm - ct[1]) / 1000 / (50 * ztop / 1000)
    free_b = Mt * 9.81 * ct[1] / 1000 / (50 * ztop / 1000)
    chk("monitors on the clamped poles: 10 deg tilt and a 50 N push at the top of the screen", ok7,
        "; ".join(det) + f". For comparison, NOT clamped (poles only standing in the LEGO): margin x{free_f:.2f} "
        f"against a push toward you and x{free_b:.2f} away from you, and only if LEGO held the poles -- it must "
        f"not, so the clamps (or grommet bolts) are mandatory")

    # ---- 8 size, bays ----
    bay_w = (DOCKBAY[1] - DOCKBAY[0]) * STUD
    bay_d = (BASE_D - 2 - REAR - 2) * STUD
    clear_h = 11 * PLATE
    under_beam = 7 * PLATE
    chk("Plugable dock bay", bay_w >= PLUGABLE[0] + 10 and (MID_Y - REAR - 2) * STUD >= PLUGABLE[1] + 2 and clear_h >= PLUGABLE[2] + 3
        and bay_d - PLUGABLE[1] >= 70,
        f"bay {bay_w:.0f} x {bay_d:.0f} x {clear_h:.1f} mm clear (floor to deck); box 225 x 85 x 24.5 sits against the "
        f"spine with {(MID_Y - REAR - 2) * STUD - PLUGABLE[1]:.0f} mm to the beam line and {bay_d - PLUGABLE[1]:.0f} mm of cable "
        f"space in front of it (the beam is {under_beam:.1f} mm above the floor on two 2 x 2 posts); lid = "
        f"{len([p for p in ALL if p['z'] == 12 and {(c[0] // 2, c[1] // 2) for c in dock.cells_h(p)} <= LIDS['dock bay lid (Plugable UD-6950PDH)']])} deck plates")
    chk("power strip", True, "Tripp Lite PS2406RA08B (610 mm) does NOT fit between the clamp bays (free run "
        f"{(NECK[1]['x0'] - CLAMP_HALF - NECK[0]['x1'] - CLAMP_HALF) * STUD:.0f} mm, 80 mm deep) -> keep it and both power "
        "bricks outside, behind / under the desk; only low-voltage and signal cables enter the base")
    H_mm = Z_TOP * PLATE
    chk("overall size", True, f"{TOTAL_W * STUD:.0f} x {BASE_D * STUD:.0f} x {H_mm:.0f} mm ({TOTAL_W} x {BASE_D} studs; "
        f"base {BASE_W * STUD:.0f} wide + dock {dock.BASE_W * STUD:.0f}); base {N_BASE * PLATE:.1f} mm high; frame "
        f"{FRAME_W * STUD:.0f} x {(Z_TOP - ZB) * PLATE:.0f} x {FRAME_D * STUD} mm; laptop top {lap['z'] + lap['sz']:.0f} mm")
    # dock: the dock generator's own plug checks still hold (geometry unchanged)
    chk("dock plug arrangement unchanged", abs(dock.OVERMOLD_DEPTH - 0.39) < 0.02,
        f"overmold face {dock.OVERMOLD_DEPTH:.2f} mm below the landing plane, pocket rows {dock.PY0}-{dock.PY0 + dock.POCKET_L - 1}, "
        f"slot {dock.SLOT_W_REAL:.1f} mm. Dock parts above the plinth that stay Light Bluish Gray (jumpers 15573 and "
        f"Tile 1 x 4 have no Sand Blue version; the lead-in slopes and their tiles are the dock's light liner "
        f"colour by design): " + (", ".join(f"{n} x {k}" for k, n in sorted(fallback.items())) or "none"))
    extra = {"mass_kg": {k: round(v / 1000, 2) for k, v in mass.items()}, "lego_kg": round(lego_g / 1000, 2),
             "tip_deg_lego_only": {k: round(v, 1) for k, v in a1.items()},
             "tip_deg_with_laptop": {k: round(v, 1) for k, v in a2.items()}}
    return res, extra


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    build()
    rows = bom(ALL)
    write_ldr(OUT / "night-array-station.ldr")
    write_lists(rows)
    refs = reference_boxes()
    doc = write_json(refs)
    nl = non_lego()
    checks, extra = run_checks(rows, refs)
    by_sec = {}
    for s in SECTIONS:
        ps = [p for p in ALL if p["section"] == s]
        by_sec[s] = {"parts": len(ps), "est_usd": round(sum(price(p) for p in ps), 2),
                     "colours": dict(Counter(COLOURS[p["color"]][2] for p in ps))}
    n = len(ALL)
    cost = sum(r["total_usd"] for r in rows)
    summary = {
        "variant": "lite" if LITE else "full", "monitors": {"left": MON[0], "right": MON[1]},
        "openings": OPEN, "bezel_lips_plates_bottom_top": LIP, "sill_plates": SILL, "vesa_standoffs_mm": SPACER,
        "size_studs": [TOTAL_W, BASE_D, Z_TOP], "size_mm": doc["size_mm"],
        "base_studs": [BASE_W, BASE_D, N_BASE], "frame_studs": {"x": [0, FRAME_W], "y": [FY0, FYB + 1], "z": [ZB, Z_TOP]},
        "pocket_block_origin_studs": [PB0, PY0], "necks": [{k: v for k, v in nk.items() if k != "hole"} for nk in NECK],
        "glass_plane_y_mm": Y_FACE, "monitor_bottom_z_mm": MON_Z0, "vesa_centre_z_mm": VESA_Z,
        "stand": STAND, "bar": BAR, "lids": {k: len(v) for k, v in LIDS.items()},
        "parts_total": n, "distinct_lines": len(rows), "est_lego_usd": round(cost, 2),
        "est_non_lego_usd": nl["total_usd"], "by_section": by_sec,
        "parts_by_colour": dict(Counter(COLOURS[p["color"]][2] for p in ALL)), **extra, "checks": checks}
    (OUT / "checks.json").write_text(json.dumps(summary, indent=1))
    print(f"Night Array LEGO station ({'LITE' if LITE else 'full'}): {TOTAL_W} x {BASE_D} studs = "
          f"{TOTAL_W * STUD:.0f} x {BASE_D * STUD:.0f} x {Z_TOP * PLATE:.0f} mm")
    print(f"  {n} parts, {len(rows)} lines, LEGO est. ${cost:.0f}, non-LEGO ${nl['total_usd']:.0f}")
    for s in SECTIONS:
        print(f"    {s:8s} {by_sec[s]['parts']:5d} parts  ${by_sec[s]['est_usd']:.0f}")
    for c in checks:
        print(f"  [{'OK ' if c['ok'] else 'FAIL'}] {c['check']}: {c['detail']}")
    if "--no-render" not in sys.argv:
        subprocess.run(["node", str(HERE / "render_lego_station.mjs"), str(OUT)], check=True)
    return 0 if all(c["ok"] for c in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
