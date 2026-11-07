#!/usr/bin/env python3
"""Night Array -- verification of the CAD deliverables.

    cad/.venv/bin/python cad/verify.py [--fast] [--export DIR]

Checks
  1. every part's bounding box against the SPEC.md section 2 envelope numbers
  2. interference (boolean intersection volume) between every pair of parts in
     the stow pose, the work / standalone poses and every dock_sequence step, plus
     the paths between them: the stow <-> work waypoints, the laptop lift and the
     explode slider part-way (0.1 .. 0.9)
  3. re-imports every STEP file (solid counts, volumes, names, colours) and STL file, and checks that they are
     in the Z-up CAD axes, CAD (x, y, z) = app (x, -z, y): the box of every group file and of every named part
     against the fresh B-rep mapped to those axes, the STL's enclosed volume and normals (not mirrored, not
     inside out), and the station standing on z = 0 with its user side toward -Y
  4. scene.json shape (keys, group order, parts, files index with real sizes), and
     its numbers against a fresh model build (params, part bbox / volume / mass,
     pose paths, dimension labels against their end points)
  5. GLB node names / extras / translations against scene.json, and each node's
     mesh bounds against the fresh B-rep
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

import model  # noqa: E402
from params import P  # noqa: E402

EXPORT = os.path.join(HERE, "export")
FAIL = []


def check(ok, msg):
    print(("  ok    " if ok else "  FAIL  ") + msg, flush=True)
    if not ok:
        FAIL.append(msg)


# ----------------------------------------------------------------------------
# 1. envelope
# ----------------------------------------------------------------------------
# part: {axis: (lo, hi)} -- SPEC numbers, mm; tolerance below
ENV = {
    "base_shell": {"x": (-640, 650), "z": (-150, 150), "y": (0, 36)},
    "tray_pad_kb": {"y": (16, 18)},
    "tray_pad_mouse": {"y": (16, 18)},
    "base_glow": {"x": (-560, 560), "y": (2, 5)},
    "neck": {"x": (-160, 160), "y": (36, 156), "z": (-140, -70)},
    "display_screen": {"y": (172, 507.7)},
    "display_glass": {"y": (156, 516.7)},
    "dock_cradle": {"x": (650, 775), "z": (-130, 130), "y": (0, 120)},
    "laptop_body": {"x": (714.5, 729.5), "y": (24, 328), "z": (-106, 106)},
    "keyboard_body": {"x": (-270, 90), "z": (2, 122), "y": (18, 31)},
    "mouse_shell": {"x": (217, 283), "z": (3, 121), "y": (18, 56)},
    "deskmat": {"x": (-350, 470), "y": (0, 3), "z": (235, 535)},
    "compute_board": {"x": (-600, -300), "z": (-120, 110)},
    "psu": {"x": (330, 470)},
    "qi_coil_kb": {"y": (12, 15)},
    "qi_coil_mouse": {"y": (12, 15)},
    "ferrite_kb": {"y": (10, 12)},
    "ferrite_mouse": {"y": (10, 12)},
    "dock_led": {"x": (707, 737), "y": (46, 48), "z": (129, 130)},
    "neck_light": {"x": (-75, 75), "y": (126, 131)},
}
TOL = 0.6


def tight_bbox(shape):
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    b = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape.wrapped, b, False, False)
    return b.Get()


def check_envelopes(parts):
    print("\n[1] envelopes")
    for pid, env in ENV.items():
        x0, y0, z0, x1, y1, z1 = tight_bbox(parts[pid])
        got = {"x": (x0, x1), "y": (y0, y1), "z": (z0, z1)}
        for ax, (lo, hi) in env.items():
            g = got[ax]
            ok = abs(g[0] - lo) <= TOL and abs(g[1] - hi) <= TOL
            check(ok, f"{pid}.{ax} = [{g[0]:.2f}, {g[1]:.2f}] (spec [{lo}, {hi}])")
    # display geometry: chord width and forward offset of the outer edges
    x0, y0, z0, x1, y1, z1 = tight_bbox(parts["display_frame"])
    check(abs((x1 - x0) - 1214) < 6, f"display chord {x1 - x0:.1f} mm (~1214)")
    check(abs(z1 - (-62) - 106) < 3, f"outer edges forward of seam {z1 + 62:.1f} mm (~106 + frame)")
    # the dock is latch-free: its only front-face feature besides the panel is the seated light, a slim ~30 x 2 strip
    # inlaid flush near the top edge, on the slot axis
    check(not [p for p, *_ in model.PARTS if "latch" in p], "no latch parts (the dock is latch-free)")
    x0, y0, z0, x1, y1, z1 = tight_bbox(parts["dock_led"])
    K = P["dock"]
    ok = (abs((x1 - x0) - 30) < 0.5 and abs((y1 - y0) - 2) < 0.2 and abs(z1 - K["z"][1]) < 0.01
          and abs((x0 + x1) / 2 - sum(K["slot"]["x"]) / 2) < 0.01 and K["h_front"] - 16 < y1 < K["h_front"])
    check(ok, f"dock_led {x1 - x0:.1f} x {y1 - y0:.1f}, flush at z {z1:.2f}, centred x {(x0 + x1) / 2:.1f} (slot axis), "
          f"top {y1:.1f} (front face {K['h_front']:.0f} tall)")
    # it sits in its pocket in the front panel (flush with it, both at the face), inside the panel's outline
    fp = K["front_panel"]
    check(fp["x"][0] < x0 and x1 < fp["x"][1] and fp["y"][0] < y0 and y1 < fp["y"][1],
          f"dock_led inlaid in the oxblood front panel (x {fp['x']}, y {fp['y']})")


# ----------------------------------------------------------------------------
# 2. interference
# ----------------------------------------------------------------------------

def bb_overlap(a, b, pad=0.05):
    return all(a[i] - pad <= b[i + 3] and b[i] - pad <= a[i + 3] for i in range(3))


PATH_SAMPLES = 8
EXPLODE_SAMPLES = [k / 10 for k in range(1, 10)]


def interference(parts, moved=None, only=None, label="", hidden=(), skip=None, quiet=False):
    """Pairwise intersection volumes. `moved` = {pid: (dx,dy,dz)}; `only` limits pairs to those involving these parts;
    `skip(a, b)` -> True leaves a pair out."""
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
    worst = []
    n = 0
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            if only and a not in only and b not in only:
                continue
            if skip and skip(a, b):
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
              + ("".join(f"\n          {a} x {b}: {v:.2f} mm3" for v, a, b in worst[:20])))
    return worst


def check_interference(parts, fast=False):
    print("\n[2] interference (intersection volume <= 0.5 mm3)")
    pm = P["poses_mm"]
    kb = [pid for pid, g, *_ in model.PARTS if g == "keyboard"]
    ms = [pid for pid, g, *_ in model.PARTS if g == "mouse"]
    lp = [pid for pid, g, *_ in model.PARTS if g == "laptop"]
    interference(parts, label="stow pose (all parts incl. desk mat)")
    work = {p: pm["work_keyboard"] for p in kb}
    work.update({p: pm["work_mouse"] for p in ms})
    interference(parts, work, only=set(kb + ms), label="work pose (keyboard + mouse on the mat)")
    interference(parts, work, only=set(kb + ms), hidden=set(lp), label="standalone pose (laptop hidden)")
    check_dock_sequence(parts, lp)
    # the laptop's travel path: sample the lift between seated and fully out
    if not fast:
        for dy in (10, 40, 80):
            interference(parts, {p: (0, dy, 0) for p in lp}, only=set(lp), label=f"laptop lifted {dy} mm")
    if fast:
        return
    check_paths(parts, kb, ms)
    check_explode(parts, kb, ms)


def check_dock_sequence(parts, lp):
    """Every dock_sequence step (latch-free: the laptop is the only thing that moves) is clear of everything, and each
    step is what its caption says: align = in the slot's lead-in, above the front lip, not yet on the plug; lower =
    standing on the slot floor with the USB-C plug inside its port; lift = straight up and clear of the cradle."""
    import build
    seq = build.dock_sequence()
    check([s["step"] for s in seq] == ["align", "lower", "lift"], "dock_sequence: align, lower, lift")
    check(all(set(s) == {"step", "title", "caption", "laptop"} for s in seq), "dock_sequence moves the laptop only")
    K, LP = P["dock"], P["laptop"]
    cn = K["connector"]
    plug_top = cn["boot_y"][1] + cn["plug"][1]
    for s in seq:
        d = np.array(s["laptop"]["t"]) * 1000.0
        mv = {p: tuple(d) for p in lp}
        interference(parts, mv, only=set(lp), label=f"dock_sequence '{s['step']}' (laptop {d[1]:+.0f} mm)")
        lx0, ly0, lz0, lx1, ly1, lz1 = tight_bbox(parts["laptop_body"].translate(Vector(*d)))
        if s["step"] == "align":
            ok = K["h_front"] < ly0 < K["h_back"] and ly0 > plug_top
            check(ok, f"align: laptop bottom at y {ly0:.1f}, in the lead-in (front lip {K['h_front']:.0f}, back "
                      f"{K['h_back']:.0f}) and above the plug ({plug_top:.1f})")
        elif s["step"] == "lower":
            ok = abs(ly0 - K["slot"]["floor_y"]) < 0.01 and ly0 < plug_top < ly0 + LP["port"][1]
            check(ok, f"lower: laptop stands on the slot floor (y {ly0:.2f}) with the plug {plug_top - ly0:.1f} mm into "
                      f"its {LP['port'][1]:.1f} mm port (seated by its own weight)")
        elif s["step"] == "lift":
            ok = ly0 > K["h_back"] + 20
            check(ok, f"lift: laptop bottom at y {ly0:.1f}, clear of the cradle top ({K['h_back']:.0f})")


def path_points(via, t, n=PATH_SAMPLES):
    """Points along stow -> via[0] -> ... -> t, n per segment (the stow end is the stow pose itself)."""
    pts, prev = [], np.zeros(3)
    for q in [np.array(v, float) for v in via] + [np.array(t, float)]:
        pts += [prev + (q - prev) * k / n for k in range(1, n + 1)]
        prev = q
    return pts


def check_paths(parts, kb, ms):
    """The stow <-> work / standalone move follows the waypoints the scene gives (lift, slide, set down), desk mat shown.
    Both poses share the keyboard / mouse path, and the laptop never comes near it, so one pass covers both."""
    import build
    pm = P["poses_mm"]
    kp = path_points(build.work_path("work_keyboard"), pm["work_keyboard"])
    mp = path_points(build.work_path("work_mouse"), pm["work_mouse"])
    worst = 0
    for i, (a, b) in enumerate(zip(kp, mp)):
        mv = {p: tuple(a) for p in kb}
        mv.update({p: tuple(b) for p in ms})
        worst += len(interference(parts, mv, only=set(kb + ms), label=f"stow -> work path {i + 1}/{len(kp)}", quiet=True))
    check(worst == 0, f"stow <-> work path: {len(kp)} samples ({PATH_SAMPLES} per segment), {worst} interfering")


# Explode moves every part along its own vector.  A shell with a closed floor that lifts off parts staying at desk
# level must pass through them on the way up (the base over its internals, the dock cradle over its PCB): those pairs
# are expected to cross part-way and are left out.  Everything else must stay clear for the whole slider travel.
EXPLODE_CROSSING = {
    "base_shell": {"compute_board", "compute_heatsink", "compute_fan", "psu", "qi_coil_kb", "qi_coil_mouse",
                   "ferrite_kb", "ferrite_mouse"},
    "dock_cradle": {"dock_board"},
}


def check_explode(parts, kb, ms):
    import build
    ex = {pid: np.array(v) * 1000.0 for pid, v in build.EXPLODE.items()}

    def skip(a, b):
        return (np.allclose(ex[a], ex[b])        # no relative motion: same as the pose itself
                or b in EXPLODE_CROSSING.get(a, ()) or a in EXPLODE_CROSSING.get(b, ()))

    pm = P["poses_mm"]
    work = {p: np.array(pm["work_keyboard"]) for p in kb}
    work.update({p: np.array(pm["work_mouse"]) for p in ms})
    bad = 0
    for e in EXPLODE_SAMPLES:
        mv = {pid: tuple(ex[pid] * e) for pid in parts}
        bad += len(interference(parts, mv, hidden={"deskmat"}, skip=skip, label=f"explode {e:.1f} (stow)", quiet=True))
        mv = {pid: tuple(work.get(pid, 0) + ex[pid] * e) for pid in parts}
        bad += len(interference(parts, mv, only=set(kb + ms + ["deskmat"]), skip=skip, label=f"explode {e:.1f} (work)",
                                quiet=True))
    check(bad == 0, f"explode 0.1 .. 0.9 in the stow and work poses: {bad} interfering"
          + f" (closed-floor shells over their contents left out: {sorted(EXPLODE_CROSSING)})")


# ----------------------------------------------------------------------------
# 3. STEP / STL round trip (exchange files are Z-up)
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
    print("\n[3] STEP / STL re-import (Z-up CAD axes)")
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
    for g in model.GROUP_ORDER:
        pids = [pid for pid, gg, *_ in model.PARTS if gg == g]
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
    names = [pid for pid, *_ in model.PARTS]
    missing = [p for p in names if f"'{p}'" not in txt]
    check(not missing, f"assembly STEP carries every part name (missing: {missing})")
    check("COLOUR_RGB" in txt, "assembly STEP carries colours")
    got = check_step_parts(apath, parts, names)
    # Upright, stated in SPEC terms rather than through cad_box: the station stands on the desk at z = 0, the
    # screen's active area spans z 172 .. 507.7 (SPEC section 2: app y), and the user side is -Y: the keyboard
    # (app z 2 .. 122) sits at y -122 .. -2, the neck (app z -140 .. -70) at y 70 .. 140.
    x0, y0, z0, x1, y1, z1 = tight_bbox(s)
    scr = tight_bbox(got["display_screen"][1]) if "display_screen" in got else (0,) * 6
    kb = tight_bbox(got["keyboard_body"][1]) if "keyboard_body" in got else (0,) * 6
    nk = tight_bbox(got["neck"][1]) if "neck" in got else (0,) * 6
    ok = (abs(z0) < TOL and abs(scr[2] - 172) < TOL and abs(scr[5] - 507.7) < TOL
          and abs(kb[1] + 122) < TOL and abs(kb[4] + 2) < TOL and abs(nk[1] - 70) < TOL and abs(nk[4] - 140) < TOL)
    check(ok, f"assembly STEP is Z-up with the user side at -Y: z [{f1(z0)}, {f1(z1)}], screen z [{f1(scr[2])}, "
          f"{f1(scr[5])}], keyboard y [{f1(kb[1])}, {f1(kb[4])}], neck y [{f1(nk[1])}, {f1(nk[4])}]")
    check(abs(x0 + 640) < TOL and abs(x1 - 775) < TOL, f"assembly STEP: +X unchanged, x [{f1(x0)}, {f1(x1)}]")


# ----------------------------------------------------------------------------
# 4/5. scene.json + GLB
# ----------------------------------------------------------------------------

def read_glb_json(path):
    with open(path, "rb") as f:
        magic, ver, total = struct.unpack("<III", f.read(12))
        ln, kind = struct.unpack("<II", f.read(8))
        return json.loads(f.read(ln))


def check_scene(parts):
    print("\n[4] scene.json")
    import build
    sc = json.load(open(os.path.join(EXPORT, "model", "scene.json")))
    for k in ("version", "units", "name", "params", "bounds", "materials", "groups", "parts", "poses", "dock_sequence",
              "dims", "screen", "files", "drawings"):
        check(k in sc, f"key '{k}'")
    check(sc["units"] == "m" and sc["version"] == 1, "units m, version 1")
    check([g["id"] for g in sc["groups"]] == model.GROUP_ORDER, "group order")
    mats = ["titanium", "graphite", "oxblood", "glass_black", "screen", "keycap", "rubber", "amber_led", "copper", "pcb",
            "ferrite", "laptop_alu", "felt", "steel"]
    check(sorted(sc["materials"]) == sorted(mats), "material keys")
    ids = [p["id"] for p in sc["parts"]]
    check(ids == [p for p, *_ in model.PARTS], "parts list")
    for p in sc["parts"]:
        for k in ("id", "group", "name", "material", "internal", "explode", "bbox_mm", "volume_cm3", "mass_g"):
            if k not in p:
                check(False, f"part {p['id']} key {k}")
        if p["material"] not in mats:
            check(False, f"part {p['id']} material {p['material']}")
    for g in sc["groups"]:
        for k in ("id", "name", "summary", "description", "parts", "pivot", "bbox_mm", "mass_g", "volume_cm3", "materials"):
            if k not in g:
                check(False, f"group {g['id']} key {k}")
    check(set(sc["poses"]) == {"stow", "work", "standalone"}, "poses")
    check(sc["dock_sequence"] == build.dock_sequence(), "dock_sequence == build.dock_sequence() (align, lower, lift)")
    check([(s["step"], s["title"]) for s in sc["dock_sequence"]] == [("align", "Align"), ("lower", "Lower"),
                                                                     ("lift", "Lift out")], "dock_sequence steps / titles")
    dock = sc["groups"][model.GROUP_ORDER.index("dock")]
    check("subgroups" not in dock, "dock group has no subgroups (nothing on it moves)")
    led = [p for p in sc["parts"] if p["id"] == "dock_led"]
    check(len(led) == 1 and led[0]["group"] == "dock" and led[0]["material"] == "amber_led" and not led[0]["internal"],
          "dock_led: group dock, amber_led, not internal")
    # latch-free copy: nothing in scene.json names a latch, and the dock / laptop text names no button, switch or lock
    import re
    raw = open(os.path.join(EXPORT, "model", "scene.json"), encoding="utf-8").read()
    check("latch" not in raw.lower(), "scene.json never mentions a latch")
    texts = [dock["summary"], dock["description"], sc["groups"][model.GROUP_ORDER.index("laptop")]["summary"],
             sc["groups"][model.GROUP_ORDER.index("laptop")]["description"]]
    texts += [p["name"] for p in sc["parts"] if p["group"] == "dock"]
    bad = [w for t in texts for w in re.findall(r"(?i)\b(latch\w*|button\w*|switch\w*|press-release|locks?|locked)\b", t)]
    check(not bad, "dock / laptop copy names no latch, button, switch or lock" + (f" (found {bad})" if bad else ""))
    dims = {d["id"] for d in sc["dims"]}
    need = {"overall_w", "base_depth", "overall_h", "display_w", "panel_active_w", "seam", "work_offset"}
    check(need <= dims, f"dims include {sorted(need)}")

    # numbers against the fresh build: a stale export (geometry or params changed, not rebuilt) fails here
    check(sc["params"] == json.loads(json.dumps(P)), "params == params.py")
    stale = []
    for p in sc["parts"]:
        s = parts[p["id"]]
        x0, y0, z0, x1, y1, z1 = tight_bbox(s)
        bb = [x1 - x0, y1 - y0, z1 - z0]
        vol = s.Volume()
        mass = build.part_mass(p["id"], vol)[0]
        if (max(abs(a - b) for a, b in zip(bb, p["bbox_mm"])) > 0.06 or abs(vol / 1000 - p["volume_cm3"]) > 0.006
                or abs(mass - p["mass_g"]) > 0.06 or p["explode"] != build.EXPLODE[p["id"]]):
            stale.append(p["id"])
    check(not stale, "parts[] bbox / volume / mass / explode match a fresh build" + (f" (stale: {stale})" if stale else ""))
    mm = 0.001
    pm = P["poses_mm"]
    for pose in ("work", "standalone"):
        for g, key in (("keyboard", "work_keyboard"), ("mouse", "work_mouse")):
            e = sc["poses"][pose][g]
            via = [list(np.array(v) * mm) for v in build.work_path(key)]
            ok = (np.allclose(e["t"], np.array(pm[key]) * mm, atol=1e-9) and len(e.get("via", [])) == len(via)
                  and all(np.allclose(a, b, atol=1e-9) for a, b in zip(e["via"], via)))
            check(ok, f"poses.{pose}.{g}: t {e['t']} via {e.get('via')}")
    seq = {s["step"]: s for s in sc["dock_sequence"]}
    check(np.isclose(seq["align"]["laptop"]["t"][1], pm["dock_align_lift"] * mm)
          and np.isclose(seq["lift"]["laptop"]["t"][1], pm["dock_lift_out"] * mm), "dock_sequence lifts = params.poses_mm")
    nominal = {"seam", "panel_active_w"}   # nominal along-facet values, not chord lengths
    for d in sc["dims"]:
        if d["id"] in nominal:
            continue
        length = float(np.linalg.norm(np.array(d["b"]) - np.array(d["a"]))) / mm
        try:
            val = float(d["label"].replace("mm", "").replace(" ", "").replace("\u00a0", ""))
        except ValueError:
            check(False, f"dim {d['id']}: label '{d['label']}' is not a length")
            continue
        check(abs(val - length) <= 1.0, f"dim {d['id']}: label '{d['label']}' vs end points {length:.2f} mm apart")
    check(sc["screen"]["panels"] == 2 and sc["screen"]["seam_mm"] == 14 and sc["screen"]["toe_in_deg"] == 10, "screen block")
    for f in sc["files"]:
        p = os.path.join(EXPORT, f["path"])
        ok = os.path.exists(p) and os.path.getsize(p) == f["bytes"] and f["bytes"] > 0
        check(ok, f"file {f['path']} ({f['bytes']} bytes)")
    for g, rel in sc["drawings"].items():
        check(os.path.exists(os.path.join(EXPORT, rel)), f"drawing {rel}")

    print("\n[5] GLB nodes")
    for name in ("station.glb", "station-edges.glb"):
        path = os.path.join(EXPORT, "model", name)
        js = read_glb_json(path)
        nodes = {n["name"]: n for n in js["nodes"]}
        check(set(nodes) == set(ids), f"{name}: one node per part ({len(nodes)})")
        bad = [n for n in js["nodes"] if "rotation" in n or "scale" in n or "matrix" in n]
        check(not bad, f"{name}: no rotation/scale on nodes")
        for p in sc["parts"]:
            ex = nodes[p["id"]].get("extras", {})
            if ex != {"group": p["group"], "material": p["material"], "internal": p["internal"]}:
                check(False, f"{name}: extras of {p['id']}")
        modes = {pr["mode"] for m in js["meshes"] for pr in m["primitives"]}
        check(modes == ({4} if name == "station.glb" else {1}), f"{name}: primitive modes {modes}")
        if name == "station.glb":
            mnames = [m["name"] for m in js["materials"]]
            check(sorted(mnames) == sorted(mats), "station.glb: materials named by key")
            scr = js["meshes"][js["nodes"][[n["name"] for n in js["nodes"]].index("display_screen")]["mesh"]]
            check("TEXCOORD_0" in scr["primitives"][0]["attributes"], "display_screen has TEXCOORD_0")
        if name == "station.glb":
            # node translation + POSITION accessor bounds = the fresh B-rep's bounding box (to within the tessellation)
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
        check(size < 6e6, f"{name}: {size / 1e6:.2f} MB < 6 MB")
    # groups that animate share the group pivot
    js = read_glb_json(os.path.join(EXPORT, "model", "station.glb"))
    nodes = {n["name"]: n for n in js["nodes"]}
    for g in sc["groups"]:
        if g["id"] in ("keyboard", "mouse", "laptop"):
            for pid in g["parts"]:
                ok = np.allclose(nodes[pid]["translation"], g["pivot"], atol=1e-6)
                check(ok, f"{pid} node translation = {g['id']} group pivot")
    # parts of groups that never move are pivoted at their own bottom-centre (SPEC section 3), dock_led included
    led = parts["dock_led"]
    x0, y0, z0, x1, y1, z1 = tight_bbox(led)
    check(np.allclose(nodes["dock_led"]["translation"], np.array([(x0 + x1) / 2, y0, (z0 + z1) / 2]) / 1000.0, atol=1e-6),
          "dock_led node translation = its bottom-centre")
    total = 0
    for root, _, files in os.walk(EXPORT):
        total += sum(os.path.getsize(os.path.join(root, f)) for f in files)
    check(total < 21e6, f"export/ total {total / 1e6:.2f} MB (budget ~20 MB)")


GLB_BBOX_TOL = 0.6   # mm; the coarsest tessellation is 0.5 mm chord deflection


def main():
    global EXPORT
    if "--export" in sys.argv:
        EXPORT = os.path.abspath(sys.argv[sys.argv.index("--export") + 1])
        print("export:", EXPORT)
    fast = "--fast" in sys.argv
    t = time.time()
    parts = model.build_all(verbose=False)
    check(not model.FILLET_LOG, "all fillets / chamfers applied" + "".join("\n          " + s for s in model.FILLET_LOG))
    for pid, s in parts.items():
        if not s.isValid():
            check(False, f"{pid} is not a valid B-rep")
    check_envelopes(parts)
    if "--no-interference" not in sys.argv:
        check_interference(parts, fast)
    if "--geometry-only" not in sys.argv:
        check_step(parts)
        check_scene(parts)
    print(f"\n{len(FAIL)} failure(s) in {time.time() - t:.0f}s")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
