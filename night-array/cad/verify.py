#!/usr/bin/env python3
"""Night Array -- verification of the CAD deliverables.

    cad/.venv/bin/python cad/verify.py [--fast] [--export DIR]

Checks
  1. every part's bounding box against the SPEC.md section 2 envelope numbers
  2. interference (boolean intersection volume) between every pair of parts in
     the stow pose, the work / standalone poses and every dock_sequence step, plus
     the paths between them: the stow <-> work waypoints, the laptop lift and the
     explode slider part-way (0.1 .. 0.9)
  3. re-imports every STEP file and compares solid counts and volumes
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
    "dock_latch": {"y": (18, 40)},
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
    # latch size
    x0, y0, z0, x1, y1, z1 = tight_bbox(parts["dock_latch"])
    check(abs((x1 - x0) - 34) < 0.5 and abs((y1 - y0) - 22) < 0.5 and abs((z1 - z0) - 14) < 0.5,
          f"dock_latch {x1 - x0:.1f} x {y1 - y0:.1f} x {z1 - z0:.1f}")


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
    latch = ["dock_latch", "dock_latch_led"]
    interference(parts, label="stow pose (all parts incl. desk mat)")
    work = {p: pm["work_keyboard"] for p in kb}
    work.update({p: pm["work_mouse"] for p in ms})
    interference(parts, work, only=set(kb + ms), label="work pose (keyboard + mouse on the mat)")
    interference(parts, work, only=set(kb + ms), hidden=set(lp), label="standalone pose (laptop hidden)")
    for step, mv in (("align", {p: (0, pm["dock_align_lift"], 0) for p in lp}),
                     ("release", {p: (0, 0, -pm["latch_travel"]) for p in latch}),
                     ("lift", {p: (0, pm["dock_lift_out"], 0) for p in lp})):
        interference(parts, mv, only=set(mv), label=f"dock_sequence '{step}'")
    # the laptop's travel path: sample the lift between seated and fully out
    if not fast:
        for dy in (10, 40, 80):
            interference(parts, {p: (0, dy, 0) for p in lp}, only=set(lp), label=f"laptop lifted {dy} mm")
    if fast:
        return
    check_paths(parts, kb, ms)
    check_explode(parts, kb, ms)


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
# 3. STEP round trip
# ----------------------------------------------------------------------------

def xcaf_parts(path):
    """Read a STEP with names + colours (XCAF): {leaf name: [sRGB colour of each solid]}."""
    from OCP.Quantity import Quantity_Color, Quantity_TOC_sRGB
    from OCP.STEPCAFControl import STEPCAFControl_Reader
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDataStd import TDataStd_Name
    from OCP.TDF import TDF_Label, TDF_LabelSequence
    from OCP.TDocStd import TDocStd_Document
    from OCP.TopAbs import TopAbs_SOLID
    from OCP.TopExp import TopExp_Explorer
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

    def walk(lab, nm):
        if st.IsAssembly_s(lab):
            ch = TDF_LabelSequence()
            st.GetComponents_s(lab, ch)
            for i in range(1, ch.Length() + 1):
                walk(ch.Value(i), name(ch.Value(i)))
            return
        if st.IsReference_s(lab):
            ref = TDF_Label()
            st.GetReferredShape_s(lab, ref)
            walk(ref, nm)
            return
        shape = st.GetShape_s(lab)
        cols = []
        e = TopExp_Explorer(shape, TopAbs_SOLID)
        while e.More():
            cols.append(colour(e.Current()) or colour(shape))
            e.Next()
        out[nm] = cols

    free = TDF_LabelSequence()
    st.GetFreeShapes(free)
    for i in range(1, free.Length() + 1):
        walk(free.Value(i), name(free.Value(i)))
    return out


def check_step_colours(path, parts, pids):
    sys.path.insert(0, HERE)
    import build
    got = xcaf_parts(path)
    bad = []
    for pid in pids:
        hexc = build.MATERIALS[build.PART_INFO[pid]["material"]][1]
        exp = [int(hexc[i:i + 2], 16) / 255.0 for i in (1, 3, 5)]
        cols = got.get(pid)
        ok = (cols is not None and len(cols) == len(parts[pid].Solids())
              and all(c is not None and max(abs(a - b) for a, b in zip(c, exp)) < 3e-3 for c in cols))
        if not ok:
            bad.append(pid)
    check(not bad, f"{os.path.relpath(path, EXPORT)}: every part named, every solid in its material colour"
          + (f" (bad: {bad})" if bad else ""))


def check_step(parts):
    print("\n[3] STEP re-import")
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
        path = os.path.join(EXPORT, "files", "parts", g + ".step")
        s = load(path)
        n = len(s.Solids())
        v = sum(x.Volume() for x in s.Solids())
        total_vol += exp_v
        total_n += exp_n
        check(n == exp_n and abs(v - exp_v) / exp_v < 1e-3,
              f"parts/{g}.step: {n} solids (expect {exp_n}), {v / 1000:.2f} cm3 (expect {exp_v / 1000:.2f})")
        check_step_colours(path, parts, pids)
        stl = os.path.join(EXPORT, "files", "parts", g + ".stl")
        with open(stl, "rb") as f:
            f.seek(80)
            ntri = struct.unpack("<I", f.read(4))[0]
        check(os.path.getsize(stl) == 84 + 50 * ntri and ntri > 0, f"parts/{g}.stl binary, {ntri} triangles")
    s = load(os.path.join(EXPORT, "files", "night-array-assembly.step"))
    n = len(s.Solids())
    v = sum(x.Volume() for x in s.Solids())
    check(n == total_n and abs(v - total_vol) / total_vol < 1e-3,
          f"assembly STEP: {n} solids (expect {total_n}), {v / 1000:.1f} cm3 (expect {total_vol / 1000:.1f})")
    with open(os.path.join(EXPORT, "files", "night-array-assembly.step"), encoding="utf-8", errors="replace") as f:
        txt = f.read()
    names = [pid for pid, *_ in model.PARTS]
    missing = [p for p in names if f"'{p}'" not in txt]
    check(not missing, f"assembly STEP carries every part name (missing: {missing})")
    check("COLOUR_RGB" in txt, "assembly STEP carries colours")
    check_step_colours(os.path.join(EXPORT, "files", "night-array-assembly.step"), parts, names)


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
    check([s["step"] for s in sc["dock_sequence"]] == ["align", "lower", "release", "lift"], "dock_sequence steps")
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
    sub = sc["groups"][model.GROUP_ORDER.index("dock")]["subgroups"]["dock_latch"]
    for pid in sub["parts"]:
        check(np.allclose(nodes[pid]["translation"], sub["pivot"], atol=1e-6), f"{pid} node translation = dock_latch pivot")
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
