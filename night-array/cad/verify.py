#!/usr/bin/env python3
"""Night Array -- verification of the CAD deliverables.

    cad/.venv/bin/python cad/verify.py [--fast]

Checks
  1. every part's bounding box against the SPEC.md section 2 envelope numbers
  2. interference (boolean intersection volume) between every pair of parts in
     the stow pose, the work / standalone poses and every dock_sequence step
  3. re-imports every STEP file and compares solid counts and volumes
  4. scene.json shape (keys, group order, parts, files index with real sizes)
  5. GLB node names / extras / translations against scene.json
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


def interference(parts, moved=None, only=None, label="", hidden=()):
    """Pairwise intersection volumes. `moved` = {pid: (dx,dy,dz)}; `only` limits pairs to those involving these parts."""
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


# ----------------------------------------------------------------------------
# 3. STEP round trip
# ----------------------------------------------------------------------------

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


# ----------------------------------------------------------------------------
# 4/5. scene.json + GLB
# ----------------------------------------------------------------------------

def read_glb_json(path):
    with open(path, "rb") as f:
        magic, ver, total = struct.unpack("<III", f.read(12))
        ln, kind = struct.unpack("<II", f.read(8))
        return json.loads(f.read(ln))


def check_scene():
    print("\n[4] scene.json")
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


def main():
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
        check_scene()
    print(f"\n{len(FAIL)} failure(s) in {time.time() - t:.0f}s")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
