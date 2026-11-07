#!/usr/bin/env python3
"""Night Array -- verification of the kit CAD and its deliverables.

    cad/.venv/bin/python cad/verify.py [--fast] [--export DIR] [--geometry-only] [--no-interference]

Checks
  1. layout: KIT_SPEC envelope (base h <= 50, depth <= 330, x = 0 at the seam, 10-degree toe-in, ~17 mm seam, keycaps
     within +-3 mm of the rim, VESA height from the monitor), structure closure, SendCutSend rules on the flat patterns,
     load path (only steel / aluminium on the feet; no printed part below the steel), every B-rep valid
  2. interference (boolean volume <= 0.5 mm3) between every pair of parts, purchased envelopes included: stow, work,
     the stow <-> work paths (keyboard, mouse along their 'via' waypoints, mat shown), every dock_sequence step and the
     laptop lift part-way
  3. print fit: every printed piece fits the 245 mm cube; Qi keep-outs (metal / steel classes) and bays (no printed
     material inside a bay); stability (kit/stability.py: 10-degree tilt, 50 N push at the screen top)
  4. STEP / STL round trip in Z-up CAD axes (names, colours, boxes, volumes, normals)
  5. scene.json shape and numbers against a fresh build; GLB nodes / extras / bounds
Exit code 1 on any failure.
"""

import json
import os
import struct
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import cadquery as cq  # noqa: E402
from cadquery import Vector  # noqa: E402

from kit import common as C  # noqa: E402
from kit import registry as R  # noqa: E402
from kit.common import LAYOUT  # noqa: E402

EXPORT = os.path.join(HERE, "export")
FAIL = []
TOL = 0.6


def check(ok, msg):
    print(("  ok    " if ok else "  FAIL  ") + msg, flush=True)
    if not ok:
        FAIL.append(msg)


def tight_bbox(shape):
    return C.tight_bbox(shape)


# ----------------------------------------------------------------------------
# 1. layout
# ----------------------------------------------------------------------------

def check_layout(parts):
    print("\n[1] layout, structure, load path")
    from kit import purchased as PU, structure as ST, base as KB, dock as KD
    B = LAYOUT["base"]
    x0, y0, z0, x1, y1, z1 = tight_bbox(parts["base_shell"])
    check(y1 <= 50.0 + 1e-6, f"base height {y1:.1f} mm (<= 50)")
    check(z1 - z0 <= 330.0 + 1e-6, f"base depth {z1 - z0:.1f} mm (<= 330)")
    check(abs(x0 - B["x"][0]) < TOL and abs(x1 - B["x"][1]) < TOL, f"base x [{x0:.1f}, {x1:.1f}]")
    # display: symmetric about x = 0, toe-in, seam between the active areas
    a = tight_bbox(parts["monitor_housings"])
    check(abs(a[0] + a[3]) < 0.05, f"monitors symmetric about the seam x = 0 (x [{a[0]:.1f}, {a[3]:.1f}])")
    ua, ub, ya, yb = PU.active_area()
    check(abs(2 * ua - 17.0) < 0.5, f"seam between the active areas {2 * ua:.2f} mm (~17)")
    check(abs(C.TOE_IN_DEG - 10.0) < 1e-9, "toe-in 10 deg")
    vy = LAYOUT["display"]["vesa_y"]
    check(abs(vy - (LAYOUT["display"]["face_bottom_y"] + PU.S60UD["vesa_y"])) < 1e-6,
          f"VESA centre y {vy} = face bottom + {PU.S60UD['vesa_y']} (S60UD)")
    xr = C.facet_point(1, PU.monitor_u0() + PU.S60UD["face_w"], 0, 0)
    check(abs(xr[2] - C.seam_z() - 106.4) < 1.5, f"outer edges {xr[2] - C.seam_z():.1f} mm forward of the seam (~106.4)")
    # keycaps within +-3 mm of the rim (stowed)
    k = tight_bbox(parts["keyboard_keys"])
    from kit.purchased import K3U
    fy = LAYOUT["qi"]["kb_floor_y"]
    front, rear = fy + K3U["h_front"], fy + K3U["h_rear"]
    check(abs(front - B["height"]) <= 3.0 + 1e-6 and abs(rear - B["height"]) <= 3.0 + 1e-6,
          f"keycaps {front:.1f} (front) .. {rear:.1f} (rear) vs rim {B['height']} (+-3)")
    # structure closes: posts, centre bracket and monitors meet exactly
    check(abs(ST.check_closure()) < 0.05, f"bracket closure {ST.check_closure():+.3f} mm (ear plane = panel face)")
    probs = ST.check_flat_patterns()
    check(not probs, "SendCutSend rules (size, flanges, hole-to-bend >= 12.4)" + "".join(f"\n          {p}" for p in probs))
    # load path: only steel / aluminium / rubber touch y < 2; printed parts never under the steel
    low = []
    for p in R.PARTS:
        if p.group in ("deskmat", "dock", "laptop"):
            continue                     # the mat lies on the desk; the cradle (printed) carries only the laptop
        if tight_bbox(parts[p.id])[1] < 1.9:
            low.append(p.id)
    check(set(low) <= {"feet"}, f"only the feet reach the desk ({low})")
    feet_top = C.LAYOUT["structure"]["foot_h"]
    for fx, fz in ST.FEET_XZ:
        probe = C.box(fx - 3, fx + 3, feet_top + 0.5, feet_top + 1.0, fz - 3, fz + 3)
        ok = parts["spine_plate"].intersect(probe).Volume() > 1.0
        if not ok:
            check(False, f"foot at ({fx}, {fz}) is not under the spine plate")
    check(True, f"{len(ST.FEET_XZ)} feet, all under the spine plate (steel)")
    dock_low = tight_bbox(parts["dock_cradle"])[1]
    check(dock_low >= -1e-6, f"dock cradle stands on the desk (y {dock_low:.2f}); it carries the laptop only")


# ----------------------------------------------------------------------------
# 2. interference
# ----------------------------------------------------------------------------

def bb_overlap(a, b, pad=0.05):
    return all(a[i] - pad <= b[i + 3] and b[i] - pad <= a[i + 3] for i in range(3))


PATH_SAMPLES = 6


def interference(parts, moved=None, only=None, label="", hidden=(), quiet=False):
    moved = moved or {}
    shapes = {}
    for pid, s in parts.items():
        if pid in hidden:
            continue
        if pid in moved:
            s = s.translate(Vector(*moved[pid]))
        shapes[pid] = s
    boxes = {pid: tight_bbox(s) for pid, s in shapes.items()}
    ids = list(shapes)
    worst, n = [], 0
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            if only and a not in only and b not in only:
                continue
            if not bb_overlap(boxes[a], boxes[b]):
                continue
            n += 1
            try:
                v = shapes[a].intersect(shapes[b]).Volume()
            except Exception as ex:  # noqa: BLE001
                v = float("nan")
                print("   boolean failed", a, b, ex)
            if not (abs(v) <= 0.5):
                worst.append((v, a, b))
    worst.sort(reverse=True)
    if not (quiet and not worst):
        check(not worst, f"{label}: {n} candidate pairs, {len(worst)} interfering"
              + "".join(f"\n          {a} x {b}: {v:.2f} mm3" for v, a, b in worst[:20]))
    return worst


def group_parts(g):
    return [p.id for p in R.PARTS if p.group == g]


def check_interference(parts, fast=False):
    print("\n[2] interference (intersection volume <= 0.5 mm3), purchased envelopes included")
    import build
    pm = R.POSES_MM
    kb, ms, lp = group_parts("keyboard"), group_parts("mouse"), group_parts("laptop")
    interference(parts, hidden={"deskmat"}, label="stow pose (every part)")
    work = {p: pm["work_keyboard"] for p in kb}
    work.update({p: pm["work_mouse"] for p in ms})
    interference(parts, work, only=set(kb + ms + ["deskmat"]), label="work pose (keyboard + mouse on the mat)")
    # stow <-> work paths
    kp = path_points(build.work_path("work_keyboard"), pm["work_keyboard"])
    mp = path_points(build.work_path("work_mouse"), pm["work_mouse"])
    bad = 0
    for i, (a, b) in enumerate(zip(kp, mp)):
        mv = {p: tuple(a) for p in kb}
        mv.update({p: tuple(b) for p in ms})
        bad += len(interference(parts, mv, only=set(kb + ms), label=f"path {i}", quiet=True))
    check(bad == 0, f"stow <-> work paths: {len(kp)} samples ({PATH_SAMPLES} per segment), {bad} interfering")
    # dock sequence
    from kit import dock as KD
    seq = build.dock_sequence()
    check([s["step"] for s in seq] == ["align", "lower", "lift"], "dock_sequence: align, lower, lift")
    from kit.purchased import NEWNEX
    plug_top = KD.plug_origin()[1] + NEWNEX["plug"][1]
    for s in seq:
        d = np.array(s["laptop"]["t"]) * 1000.0
        interference(parts, {p: tuple(d) for p in lp}, only=set(lp), label=f"dock_sequence '{s['step']}' "
                                                                            f"(laptop {d[1]:+.0f} mm)")
        ly0 = tight_bbox(parts["laptop_body"].translate(Vector(*d)))[1]
        if s["step"] == "align":
            check(KD.K["h_front"] < ly0 < KD.K["h_back"] and ly0 > plug_top,
                  f"align: laptop bottom y {ly0:.1f} in the lead-in, above the plug tip ({plug_top:.1f})")
        elif s["step"] == "lower":
            check(abs(ly0 - KD.K["landing_y"]) < 0.01 and ly0 < plug_top < ly0 + 7.5,
                  f"lower: laptop on the landing plane (y {ly0:.2f}), plug {plug_top - ly0:.2f} mm into its 7.5 mm port")
        else:
            check(ly0 > KD.K["h_back"] + 20, f"lift: laptop bottom y {ly0:.1f} clear of the cradle ({KD.K['h_back']:.0f})")
    if not fast:
        for dy in (10, 40, 80):
            interference(parts, {p: (0, dy, 0) for p in lp}, only=set(lp), label=f"laptop lifted {dy} mm")


def path_points(via, t, n=PATH_SAMPLES):
    pts, prev = [], np.zeros(3)
    for q in [np.array(v, float) for v in via] + [np.array(t, float)]:
        pts += [prev + (q - prev) * k / n for k in range(1, n + 1)]
        prev = q
    return pts


# ----------------------------------------------------------------------------
# 3. print fit, keep-outs, bays, stability
# ----------------------------------------------------------------------------

METAL_MATERIALS = {"steel", "aluminium", "laptop_alu", "copper"}
QI_ALLOWED = {"qi_pads"}          # the pads themselves


def check_kit(parts):
    print("\n[3] print fit, Qi keep-outs, bays, stability")
    import build
    from kit import electronics as EL
    nbad, npieces = [], 0
    for p in R.PARTS:
        if p.kind != "printed":
            continue
        for x in build.print_pieces(p.id, parts[p.id]):
            npieces += 1
            if not x["fits"]:
                nbad.append(f"{x['name']} {x['dims_mm']}")
    check(not nbad, f"{npieces} printed pieces, all within {C.PRINT_MAX:.0f} mm" + "".join(f"\n          {b}" for b in nbad))
    # Qi keep-outs: metal class (steel, aluminium, fasteners, LED channels, PCBs) and steel class
    for name, (bx, what) in EL.KEEPOUTS.items():
        ko = EL.keepout_solid(name)
        steel_only = name.endswith("_steel")
        hits = []
        for p in R.PARTS:
            if p.id in QI_ALLOWED or p.group in ("keyboard", "mouse", "deskmat"):
                continue
            cls = p.material == "steel" if steel_only else (p.material in METAL_MATERIALS or p.material in ("pcb", "amber_led")
                                                             or p.kind == "hardware")
            if not cls:
                continue
            if not bb_overlap(tight_bbox(parts[p.id]), tight_bbox(ko)):
                continue
            v = parts[p.id].intersect(ko).Volume()
            if v > 0.01:
                hits.append(f"{p.id} ({v:.1f} mm3)")
        check(not hits, f"keep-out {name}: {what}" + (f" -- violated by {hits}" if hits else ""))
    # bays: no printed material inside a bay
    printed = [p.id for p in R.PARTS if p.kind == "printed"]
    for name in EL.BAYS:
        bay = EL.bay_solid(name)
        hits = []
        for pid in printed:
            if not bb_overlap(tight_bbox(parts[pid]), tight_bbox(bay)):
                continue
            v = parts[pid].intersect(bay).Volume()
            if v > 1.0:
                hits.append(f"{pid} ({v:.0f} mm3)")
        check(not hits, f"bay {name} is clear of printed material" + (f" -- {hits}" if hits else ""))
    # stability
    from kit import stability as SB
    lines = []
    ok, res = SB.report(parts, out=lines.append)
    for l in lines:
        print("        " + l)
    for r in res:
        lab = "laptop docked" if r["laptop"] == "max" else "no laptop"
        check(r["min_tilt"] >= SB.TILT_DEG, f"stability ({lab}): 10-degree tilt in every direction "
                                            f"(critical tilt {r['min_tilt']:.1f} deg)")
        check(r["min_sf"] >= 1.0, f"stability ({lab}): 50 N push at the screen top, every direction "
                                  f"(worst safety factor {r['min_sf']:.2f})")


# ----------------------------------------------------------------------------
# 4. STEP / STL round trip (exchange files are Z-up)
# ----------------------------------------------------------------------------
# The model (and the GLBs) live in app axes: +Y up, +Z toward the user.  The STEP and STL files are written in
# Z-up CAD axes, CAD (x, y, z) = app (x, -z, y): up -> +Z, the user side -> -Y, +X unchanged.  The expected
# CAD boxes are mapped from the fresh app-axes B-rep here, independently of build.to_cad_axes, so an export left
# in app axes, rotated the wrong way or mirrored fails these checks (solid counts and volumes alone cannot tell).
STEP_BBOX_TOL = 0.01   # mm; the same exact geometry, re-imported
STL_IN_TOL = 0.01      # mm; STL vertices lie on the B-rep, so they never stick out of its box by more than this
STL_VOL_TOL = 0.01     # relative; chordal deflection (0.15 .. 0.3 mm) shaves the fillets (worst today: mouse, -0.3 %)


def cad_box(app_box):
    """(x0, y0, z0, x1, y1, z1) in app axes -> the same box in CAD axes: x = x, y = -z, z = y."""
    x0, y0, z0, x1, y1, z1 = app_box
    return (x0, -z1, y0, x1, -z0, y1)


def union_box(boxes):
    boxes = list(boxes)
    return tuple(min(b[i] for b in boxes) for i in range(3)) + tuple(max(b[i] for b in boxes) for i in range(3, 6))


def box_dev(a, b):
    return max(abs(p - q) for p, q in zip(a, b))


def f1(v):
    s = "%.1f" % v
    return "0.0" if s == "-0.0" else s


def fmt_box(b):
    return "x [%s, %s] y [%s, %s] z [%s, %s]" % tuple(f1(b[i]) for i in (0, 3, 1, 4, 2, 5))


def xcaf_parts(path):
    """Read a STEP with names + colours (XCAF): {leaf name: ([sRGB colour of each solid], located shape)}.

    The shape carries the placements of every assembly level above it, so its box is where the part really is."""
    from OCP.Quantity import Quantity_Color, Quantity_TOC_sRGB
    from OCP.STEPCAFControl import STEPCAFControl_Reader
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDataStd import TDataStd_Name
    from OCP.TDF import TDF_Label, TDF_LabelSequence
    from OCP.TDocStd import TDocStd_Document
    from OCP.TopAbs import TopAbs_SOLID
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopLoc import TopLoc_Location
    from OCP.XCAFDoc import XCAFDoc_ColorType, XCAFDoc_DocumentTool

    doc = TDocStd_Document(TCollection_ExtendedString("XmlOcaf"))
    r = STEPCAFControl_Reader()
    r.SetColorMode(True)
    r.SetNameMode(True)
    r.ReadFile(path)
    r.Transfer(doc)
    st = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    ct = XCAFDoc_DocumentTool.ColorTool_s(doc.Main())

    def name(lab):
        a = TDataStd_Name()
        return a.Get().ToExtString() if lab.FindAttribute(TDataStd_Name.GetID_s(), a) else ""

    def colour(shape):
        c = Quantity_Color()
        for t in (XCAFDoc_ColorType.XCAFDoc_ColorSurf, XCAFDoc_ColorType.XCAFDoc_ColorGen):
            if ct.GetColor(shape, t, c):
                v = c.Values(Quantity_TOC_sRGB)
                return tuple(v)
        return None

    out = {}

    def walk(lab, nm, loc):
        if st.IsAssembly_s(lab):
            ch = TDF_LabelSequence()
            st.GetComponents_s(lab, ch)
            for i in range(1, ch.Length() + 1):
                walk(ch.Value(i), name(ch.Value(i)), loc)
            return
        if st.IsReference_s(lab):
            ref = TDF_Label()
            st.GetReferredShape_s(lab, ref)
            walk(ref, nm, loc.Multiplied(st.GetLocation_s(lab)))
            return
        shape = st.GetShape_s(lab)
        cols = []
        e = TopExp_Explorer(shape, TopAbs_SOLID)
        while e.More():
            cols.append(colour(e.Current()) or colour(shape))
            e.Next()
        out[nm] = (cols, cq.Shape.cast(shape.Moved(loc)))

    free = TDF_LabelSequence()
    st.GetFreeShapes(free)
    for i in range(1, free.Length() + 1):
        walk(free.Value(i), name(free.Value(i)), TopLoc_Location())
    return out


def check_step_parts(path, parts, pids):
    """Names and colours survive, and every named part sits where the model has it, in CAD axes."""
    import build
    got = xcaf_parts(path)
    bad, off = [], []
    for pid in pids:
        hexc = build.MATERIALS[build.PART_INFO[pid]["material"]][1]
        exp = [int(hexc[i:i + 2], 16) / 255.0 for i in (1, 3, 5)]
        cols, shape = got.get(pid, (None, None))
        ok = (cols is not None and len(cols) == len(parts[pid].Solids())
              and all(c is not None and max(abs(a - b) for a, b in zip(c, exp)) < 3e-3 for c in cols))
        if not ok:
            bad.append(pid)
        if shape is not None:
            dev = box_dev(tight_bbox(shape), cad_box(tight_bbox(parts[pid])))
            if dev > STEP_BBOX_TOL:
                off.append(f"{pid} {dev:.2f} mm")
    rel = os.path.relpath(path, EXPORT)
    check(not bad, f"{rel}: every part named, every solid in its material colour" + (f" (bad: {bad})" if bad else ""))
    check(not off, f"{rel}: every named part's box = the model's, mapped to Z-up (within {STEP_BBOX_TOL} mm)"
          + (f" (off: {off})" if off else ""))
    return got


def read_stl(path):
    """Binary STL -> (stored normals (n, 3), triangle vertices (n, 3, 3)); raises on a malformed file."""
    with open(path, "rb") as f:
        data = f.read()
    ntri = struct.unpack_from("<I", data, 80)[0]
    if len(data) != 84 + 50 * ntri or ntri == 0:
        raise ValueError(f"{len(data)} bytes for {ntri} triangles")
    rec = np.frombuffer(data, dtype=np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")]), count=ntri,
                        offset=84)
    return rec["n"].astype(float), rec["v"].astype(float)


def check_stl(path, gid, pids, parts):
    """Binary, Z-up, mm, not mirrored or inside out: the box matches the model's (mapped to CAD axes) to within
    the tessellation, the enclosed (signed) volume matches the B-rep, and the stored normals follow the winding."""
    import build
    rel = os.path.relpath(path, EXPORT)
    try:
        n, v = read_stl(path)
    except (ValueError, struct.error) as ex:
        check(False, f"{rel}: not a valid binary STL ({ex})")
        return
    lin = build.STL_TESS.get(gid, build.STL_TESS_DEFAULT)[0]
    exp = cad_box(union_box(tight_bbox(parts[p]) for p in pids))
    pts = v.reshape(-1, 3)
    got = tuple(pts.min(0)) + tuple(pts.max(0))
    inside = all(got[i] >= exp[i] - STL_IN_TOL for i in range(3)) and all(got[i] <= exp[i] + STL_IN_TOL for i in range(3, 6))
    dev = box_dev(got, exp)
    check(inside and dev <= lin + 0.05,
          f"{rel}: {len(v)} triangles, box {fmt_box(got)} = the model's in Z-up axes (dev {dev:.2f} mm, "
          f"deflection {lin} mm)" + ("" if inside else f"; expected {fmt_box(exp)}"))
    a, b, c = v[:, 0], v[:, 1], v[:, 2]
    vol = float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0)
    exp_v = sum(parts[p].Volume() for p in pids)
    check(abs(vol - exp_v) / exp_v < STL_VOL_TOL,
          f"{rel}: enclosed volume {vol / 1000:.2f} cm3 vs B-rep {exp_v / 1000:.2f} cm3 "
          f"({(vol - exp_v) / exp_v * 100:+.2f} %; a mirrored or inside-out mesh is negative)")
    cr = np.cross(b - a, c - a)
    ln = np.linalg.norm(cr, axis=1)
    keep = ln > 1e-9
    agree = np.einsum("ij,ij->i", cr[keep] / ln[keep, None], n[keep]) > 0.5
    check(agree.mean() > 0.999, f"{rel}: stored facet normals follow the winding ({agree.mean() * 100:.2f} %)")


def check_step(parts):
    print("\n[4] STEP / STL re-import (Z-up CAD axes)")
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPControl import STEPControl_Reader

    def load(path):
        r = STEPControl_Reader()
        st = r.ReadFile(path)
        assert st == IFSelect_RetDone, path
        r.TransferRoots()
        return cq.Shape.cast(r.OneShape())

    total_vol = 0.0
    total_n = 0
    for g in R.GROUP_ORDER:
        pids = [p.id for p in R.PARTS if p.group == g]
        exp_n = sum(len(parts[p].Solids()) for p in pids)
        exp_v = sum(parts[p].Volume() for p in pids)
        exp_box = cad_box(union_box(tight_bbox(parts[p]) for p in pids))
        path = os.path.join(EXPORT, "files", "parts", g + ".step")
        s = load(path)
        n = len(s.Solids())
        v = sum(x.Volume() for x in s.Solids())
        total_vol += exp_v
        total_n += exp_n
        check(n == exp_n and abs(v - exp_v) / exp_v < 1e-3,
              f"parts/{g}.step: {n} solids (expect {exp_n}), {v / 1000:.2f} cm3 (expect {exp_v / 1000:.2f})")
        got_box = tight_bbox(s)
        check(box_dev(got_box, exp_box) <= STEP_BBOX_TOL,
              f"parts/{g}.step: Z-up box {fmt_box(got_box)}" + ("" if box_dev(got_box, exp_box) <= STEP_BBOX_TOL
                                                                 else f" (expected {fmt_box(exp_box)})"))
        check_step_parts(path, parts, pids)
        check_stl(os.path.join(EXPORT, "files", "parts", g + ".stl"), g, pids, parts)
    apath = os.path.join(EXPORT, "files", "night-array-assembly.step")
    s = load(apath)
    n = len(s.Solids())
    v = sum(x.Volume() for x in s.Solids())
    check(n == total_n and abs(v - total_vol) / total_vol < 1e-3,
          f"assembly STEP: {n} solids (expect {total_n}), {v / 1000:.1f} cm3 (expect {total_vol / 1000:.1f})")
    with open(apath, encoding="utf-8", errors="replace") as f:
        txt = f.read()
    names = [p.id for p in R.PARTS]
    missing = [p for p in names if f"'{p}'" not in txt]
    check(not missing, f"assembly STEP carries every part name (missing: {missing})")
    check("COLOUR_RGB" in txt, "assembly STEP carries colours")
    got = check_step_parts(apath, parts, names)
    # Upright, stated in the layout's terms rather than through cad_box: the station stands on the desk at z = 0,
    # the screens' active areas span their real heights, the user side is -Y (keyboard app z -> CAD -y), +X unchanged.
    from kit import purchased as PU
    from kit.neck import NECK
    ua, ub, ya, yb = PU.active_area()
    kz = LAYOUT["keyboard"]["z"]
    x0, y0, z0, x1, y1, z1 = tight_bbox(s)
    scr = tight_bbox(got["display_screen"][1]) if "display_screen" in got else (0,) * 6
    kb = tight_bbox(got["keyboard_body"][1]) if "keyboard_body" in got else (0,) * 6
    nk = tight_bbox(got["neck"][1]) if "neck" in got else (0,) * 6
    ok = (abs(z0) < TOL and abs(scr[2] - ya) < TOL and abs(scr[5] - yb) < TOL
          and abs(kb[1] + kz[1]) < TOL and abs(kb[4] + kz[0]) < TOL
          and abs(nk[1] + NECK["z_front"][0]) < TOL and abs(nk[4] + NECK["z_back"]) < TOL)
    check(ok, f"assembly STEP is Z-up with the user side at -Y: z [{f1(z0)}, {f1(z1)}], screen z [{f1(scr[2])}, "
          f"{f1(scr[5])}], keyboard y [{f1(kb[1])}, {f1(kb[4])}], neck y [{f1(nk[1])}, {f1(nk[4])}]")
    bx0 = LAYOUT["base"]["x"][0]
    dx1 = LAYOUT["dock"]["x"][1]
    check(abs(x0 - bx0) < TOL and abs(x1 - dx1) < TOL, f"assembly STEP: +X unchanged, x [{f1(x0)}, {f1(x1)}]")


# ----------------------------------------------------------------------------
# 5. scene.json + GLB
# ----------------------------------------------------------------------------

def read_glb_json(path):
    with open(path, "rb") as f:
        magic, ver, total = struct.unpack("<III", f.read(12))
        ln, kind = struct.unpack("<II", f.read(8))
        return json.loads(f.read(ln))


GLB_BBOX_TOL = 0.6


def check_scene(parts):
    print("\n[5] scene.json + GLB")
    import build
    sc = json.load(open(os.path.join(EXPORT, "model", "scene.json")))
    for k in ("version", "units", "name", "params", "bounds", "materials", "groups", "parts", "poses", "dock_sequence",
              "dims", "screen", "files", "drawings"):
        check(k in sc, f"key '{k}'")
    check(sc["units"] == "m" and sc["version"] == 1, "units m, version 1")
    check([g["id"] for g in sc["groups"]] == R.GROUP_ORDER, f"group order {R.GROUP_ORDER}")
    check(sorted(sc["materials"]) == sorted(R.MATERIALS), "material keys")
    ids = [p["id"] for p in sc["parts"]]
    check(ids == [p.id for p in R.PARTS], "parts list = registry")
    for p in sc["parts"]:
        need = ["id", "group", "name", "material", "internal", "kind", "explode", "bbox_mm", "volume_cm3", "mass_g"]
        if p["kind"] in ("purchased", "hardware", "metal") and p["group"] != "laptop":
            need.append("bom")
        if p["kind"] == "printed":
            need.append("print")
        miss = [k for k in need if k not in p]
        if miss:
            check(False, f"part {p['id']} missing {miss}")
        if p["kind"] not in ("printed", "purchased", "metal", "hardware"):
            check(False, f"part {p['id']} kind {p['kind']}")
        if p["kind"] == "printed":
            pr = p["print"]
            if not all(k in pr for k in ("file", "filament", "grams", "minutes", "plate")):
                check(False, f"part {p['id']} print block")
    check(set(sc["poses"]) == {"stow", "work"}, "poses: stow, work (standalone removed: the laptop is the computer)")
    check(sc["dock_sequence"] == build.dock_sequence(), "dock_sequence == build.dock_sequence()")
    raw = open(os.path.join(EXPORT, "model", "scene.json"), encoding="utf-8").read()
    check("latch" not in raw.lower(), "scene.json never mentions a latch")
    check("internals" not in [g["id"] for g in sc["groups"]], "no internals group (no computer in the base)")
    dims = {d["id"] for d in sc["dims"]}
    need = {"overall_w", "base_depth", "overall_h", "display_w", "panel_active_w", "seam", "work_offset"}
    check(need <= dims, f"dims include {sorted(need)}")
    check(sc["params"] == json.loads(json.dumps(build.scene_params())), "params == the kit's interface tables")
    stale = []
    for p in sc["parts"]:
        s = parts[p["id"]]
        x0, y0, z0, x1, y1, z1 = tight_bbox(s)
        bb = [x1 - x0, y1 - y0, z1 - z0]
        vol = s.Volume()
        mass = build.part_mass(p["id"], s)[0]
        if (max(abs(a - b) for a, b in zip(bb, p["bbox_mm"])) > 0.06 or abs(vol / 1000 - p["volume_cm3"]) > 0.006
                or abs(mass - p["mass_g"]) > 0.06 or p["explode"] != build.EXPLODE[p["id"]]):
            stale.append(p["id"])
    check(not stale, "parts[] bbox / volume / mass / explode match a fresh build" + (f" (stale: {stale})" if stale else ""))
    mm = 0.001
    pm = R.POSES_MM
    for g, key in (("keyboard", "work_keyboard"), ("mouse", "work_mouse")):
        e = sc["poses"]["work"][g]
        via = [list(np.array(v) * mm) for v in build.work_path(key)]
        ok = (np.allclose(e["t"], np.array(pm[key]) * mm, atol=1e-9) and len(e.get("via", [])) == len(via)
              and all(np.allclose(a, b, atol=1e-9) for a, b in zip(e["via"], via)))
        check(ok, f"poses.work.{g}: t {e['t']} via {e.get('via')}")
    for d in sc["dims"]:
        if d["id"] in ("seam", "panel_active_w"):
            continue
        length = float(np.linalg.norm(np.array(d["b"]) - np.array(d["a"]))) / mm
        try:
            val = float(d["label"].replace("mm", "").replace(" ", "").replace(" ", ""))
        except ValueError:
            check(False, f"dim {d['id']}: label '{d['label']}' is not a length")
            continue
        check(abs(val - length) <= 1.0, f"dim {d['id']}: label '{d['label']}' vs end points {length:.2f} mm apart")
    check(sc["screen"]["panels"] == 2 and abs(sc["screen"]["seam_mm"] - 17.0) < 0.5 and sc["screen"]["toe_in_deg"] == 10,
          f"screen block (seam {sc['screen']['seam_mm']} mm)")
    for f in sc["files"]:
        p = os.path.join(EXPORT, f["path"])
        ok = os.path.exists(p) and os.path.getsize(p) == f["bytes"] and f["bytes"] > 0
        check(ok, f"file {f['path']} ({f['bytes']} bytes)")
    for g, rel in sc["drawings"].items():
        check(os.path.exists(os.path.join(EXPORT, rel)), f"drawing {rel}")

    for name in ("station.glb", "station-edges.glb"):
        path = os.path.join(EXPORT, "model", name)
        js = read_glb_json(path)
        nodes = {n["name"]: n for n in js["nodes"]}
        check(set(nodes) == set(ids), f"{name}: one node per part ({len(nodes)})")
        bad = [n for n in js["nodes"] if "rotation" in n or "scale" in n or "matrix" in n]
        check(not bad, f"{name}: no rotation/scale on nodes")
        for p in sc["parts"]:
            ex = nodes[p["id"]].get("extras", {})
            if ex != {"group": p["group"], "material": p["material"], "internal": p["internal"], "kind": p["kind"]}:
                check(False, f"{name}: extras of {p['id']}")
        modes = {pr["mode"] for m in js["meshes"] for pr in m["primitives"]}
        check(modes == ({4} if name == "station.glb" else {1}), f"{name}: primitive modes {modes}")
        if name == "station.glb":
            check(sorted(m["name"] for m in js["materials"]) == sorted(R.MATERIALS), "station.glb: materials named by key")
            scr = js["meshes"][nodes["display_screen"]["mesh"]]
            check("TEXCOORD_0" in scr["primitives"][0]["attributes"], "display_screen has TEXCOORD_0")
            off = []
            for n in js["nodes"]:
                acc = js["accessors"][js["meshes"][n["mesh"]]["primitives"][0]["attributes"]["POSITION"]]
                lo = (np.array(n["translation"]) + acc["min"]) * 1000.0
                hi = (np.array(n["translation"]) + acc["max"]) * 1000.0
                bb = np.array(tight_bbox(parts[n["name"]]))
                dev = max(np.abs(lo - bb[:3]).max(), np.abs(hi - bb[3:]).max())
                if dev > GLB_BBOX_TOL:
                    off.append(f"{n['name']} {dev:.2f} mm")
            check(not off, f"station.glb: every node's mesh bounds match the B-rep within {GLB_BBOX_TOL} mm"
                  + (f" (off: {off})" if off else ""))
        size = os.path.getsize(path)
        check(size < 8e6, f"{name}: {size / 1e6:.2f} MB < 8 MB")
    js = read_glb_json(os.path.join(EXPORT, "model", "station.glb"))
    nodes = {n["name"]: n for n in js["nodes"]}
    for g in sc["groups"]:
        if g["id"] in R.ANIMATED_GROUPS:
            for pid in g["parts"]:
                check(np.allclose(nodes[pid]["translation"], g["pivot"], atol=1e-6), f"{pid} node translation = "
                                                                                    f"{g['id']} group pivot")
    total = 0
    for root, _, files in os.walk(EXPORT):
        total += sum(os.path.getsize(os.path.join(root, f)) for f in files)
    check(total < 30e6, f"export/ total {total / 1e6:.2f} MB (budget 30 MB)")


def main():
    global EXPORT
    if "--export" in sys.argv:
        EXPORT = os.path.abspath(sys.argv[sys.argv.index("--export") + 1])
        print("export:", EXPORT)
    fast = "--fast" in sys.argv
    t = time.time()
    parts = R.build_parts(verbose=False)
    check(not C.FILLET_LOG, "all fillets / chamfers applied" + "".join("\n          " + s for s in C.FILLET_LOG))
    for pid, s in parts.items():
        if not s.isValid():
            check(False, f"{pid} is not a valid B-rep")
    check_layout(parts)
    if "--no-interference" not in sys.argv:
        check_interference(parts, fast)
    check_kit(parts)
    if "--geometry-only" not in sys.argv:
        check_step(parts)
        check_scene(parts)
    print(f"\n{len(FAIL)} failure(s) in {time.time() - t:.0f}s")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
