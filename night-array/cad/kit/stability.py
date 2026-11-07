"""Night Array kit -- stability (KIT_SPEC 'Stability').  Owner: CAD architect.

    cad/.venv/bin/python -m kit.stability          (from cad/)  prints the table; exit 1 if a case fails

Criteria, both with the monitors fitted, laptop docked (worst-case 2.14 kg, MacBook Pro 16) and with no laptop:
  1. 10-degree tilt in every direction: for every edge of the support polygon the critical tilt atan(d / h) must
     exceed 10 deg (d = horizontal distance from the CoM to the edge, h = CoM height).
  2. 50 N horizontal push at the top of the screen, any direction: restoring W*d about each edge must exceed the
     overturning F*h_top.  Reported as a safety factor SF = W d / (F h_top); target >= 1.5.
The support polygon is the convex hull of the steel feet only (printed parts never carry monitor load), taken at
the foot CENTRES (conservative: the 20.6 mm Bumpons add ~10 mm of lever at every edge).  Keyboard, mouse and the
desk mat are left OUT (they may be on the mat or in a bag), which is the worse case for a push from the front.
Masses: monitors 3.6 kg each (Samsung), purchased parts from the research weights, steel / aluminium from
volume x density, prints from the shell + infill model (registry.part_mass).
"""

from __future__ import annotations

import math
import sys

import numpy as np

from . import registry as R
from .common import LAYOUT, centroid, tight_bbox
from . import purchased as P
from . import structure as ST

G = 9.81
PUSH_N = 50.0
TILT_DEG = 10.0
SF_TARGET = 1.5
EXCLUDE = {"deskmat", "keyboard_body", "keyboard_keys", "keyboard_tag", "mouse_shell", "mouse_wheel"}


def mass_table(parts):
    """[(pid, kg, (x, y, z) mm)] for every part that stays on the station."""
    out = []
    for pid, s in parts.items():
        if pid in EXCLUDE:
            continue
        g, _, _ = R.part_mass(pid, s)
        c, _ = centroid(s)
        out.append((pid, g / 1000.0, c))
    return out


def combine(rows):
    m = sum(r[1] for r in rows)
    c = np.sum([np.array(r[2]) * r[1] for r in rows], axis=0) / m
    return m, c


def hull(points):
    """Convex hull (x, z) counter-clockwise (Andrew's monotone chain)."""
    pts = sorted(set(points))
    if len(pts) < 3:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, hi = [], []
    for p in pts:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(hi) >= 2 and cross(hi[-2], hi[-1], p) <= 0:
            hi.pop()
        hi.append(p)
    return lo[:-1] + hi[:-1]


def edge_distances(poly, c):
    """[(edge, perpendicular distance from c (x, z) to the edge line, inside positive)]."""
    out = []
    n = len(poly)
    for i in range(n):
        a, b = np.array(poly[i]), np.array(poly[(i + 1) % n])
        e = b - a
        nrm = np.array([e[1], -e[0]]) / np.linalg.norm(e)      # outward for a CCW polygon in (x, z)?
        d = np.dot(np.array(c) - a, -nrm)
        out.append(((tuple(a), tuple(b)), d))
    # make 'inside positive' robust to orientation
    if sum(d for _, d in out) < 0:
        out = [(e, -d) for e, d in out]
    return out


def screen_top_y(parts):
    return tight_bbox(parts["display_frame"])[4]


def analyse(parts, laptop="max"):
    rows = mass_table(parts)
    if laptop == "none":
        rows = [r for r in rows if r[0] != "laptop_body"]
    elif laptop == "max":
        rows = [(r[0], P.LAPTOP["mass_kg_max"], r[2]) if r[0] == "laptop_body" else r for r in rows]
    m, c = combine(rows)
    W = m * G
    poly = hull([(x, z) for x, z in ST.FEET_XZ])
    h = c[1]
    htop = screen_top_y(parts)
    res = []
    for (a, b), d in edge_distances(poly, (c[0], c[2])):
        tilt = math.degrees(math.atan2(d, h))
        sf = W * d / (PUSH_N * htop)
        res.append({"edge": (a, b), "d_mm": d, "tilt_deg": tilt, "push_sf": sf})
    return {"laptop": laptop, "mass_kg": m, "com": c.tolist(), "h_top": htop, "edges": res,
            "min_tilt": min(r["tilt_deg"] for r in res), "min_sf": min(r["push_sf"] for r in res), "rows": rows}


def edge_name(edge):
    (ax, az), (bx, bz) = edge
    if abs(az - bz) < 1 and az < 0:
        return "rear"
    if abs(az - bz) < 50 and az > 0:
        return "front"
    return "right" if ax + bx > 0 else "left"


def report(parts, out=print):
    ok = True
    results = []
    for lp in ("max", "none"):
        r = analyse(parts, lp)
        results.append(r)
        label = {"max": "laptop docked (2.14 kg worst case)", "none": "no laptop"}[lp]
        out(f"\n{label}: {r['mass_kg']:.2f} kg, CoM x {r['com'][0]:.0f} y {r['com'][1]:.0f} z {r['com'][2]:.0f} mm; "
            f"push at the screen top y {r['h_top']:.0f}")
        for e in sorted(r["edges"], key=lambda e: e["push_sf"]):
            out(f"  {edge_name(e['edge']):5s} edge  d {e['d_mm']:6.1f} mm   tilt {e['tilt_deg']:5.1f} deg "
                f"(need {TILT_DEG})   50 N push SF {e['push_sf']:4.2f} (target {SF_TARGET})")
        if r["min_tilt"] < TILT_DEG or r["min_sf"] < 1.0:
            ok = False
    return ok, results


def sizing_note(parts):
    """Extra front ballast (kg at the front bar) needed to bring the worst push SF to SF_TARGET."""
    r = min((analyse(parts, lp) for lp in ("max", "none")), key=lambda r: r["min_sf"])
    worst = min(r["edges"], key=lambda e: e["push_sf"])
    if worst["push_sf"] >= SF_TARGET:
        return 0.0, worst
    # rear edge governs: adding m at the front bar (z ~ 146) adds m g (146 - z_rear) to the restoring moment
    (ax, az), (bx, bz) = worst["edge"]
    need = (SF_TARGET - worst["push_sf"]) * PUSH_N * r["h_top"]          # N mm
    lever = abs(146.0 - az)
    return need / (G * lever), worst


def main():
    sys.path.insert(0, ".")
    parts = R.build_parts(verbose=False)
    rows = mass_table(parts)
    tot = sum(r[1] for r in rows)
    print("mass budget (kg):")
    for pid, kg, c in sorted(rows, key=lambda r: -r[1])[:14]:
        print(f"  {pid:18s} {kg:6.2f}   CoM ({c[0]:6.0f}, {c[1]:5.0f}, {c[2]:6.0f})")
    print(f"  {'total on station':18s} {tot:6.2f}")
    ok, res = report(parts)
    extra, worst = sizing_note(parts)
    print(f"\nworst push SF {min(r['min_sf'] for r in res):.2f}; extra front ballast for SF {SF_TARGET}: {extra:.2f} kg")
    print("PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
