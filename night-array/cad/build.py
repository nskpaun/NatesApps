#!/usr/bin/env python3
"""Night Array -- build every deliverable from the kit package (cad/kit/), one command.

    cad/.venv/bin/python cad/build.py                              # everything -> cad/export (wipes it first)
    cad/.venv/bin/python cad/build.py --only glb|step|drawings     # one export stage into cad/export (no wipe)
    cad/.venv/bin/python cad/build.py --only base --out /tmp/x     # ONE MODULE + the full assembly into a scratch dir
                                                                   # (module = display|neck|base|dock|structure|electronics)

Module builds never touch cad/export: they write <out>/model/{station.glb, station-edges.glb, scene.json} (the full
assembly with the module's changes), <out>/parts/<part>.step|.stl for the module's parts, <out>/print/<filament>/
<piece>.stl (Z-up, flat face down, at the origin) for its printed pieces, <out>/report.json (sizes, fits, masses,
interference against everything else) and, for --only structure, <out>/metal/*.dxf.  Render previews of <out> with
    node cad/tools/preview.mjs <out>                               # hero / back / top / section PNGs

Outputs of the full build (SPEC.md section 3) under cad/export/:
  model/station.glb, model/station-edges.glb, model/scene.json     app axes: +Y up, metres
  files/night-array-assembly.step, files/parts/<group>.step|.stl   CAD axes: +Z up, mm (see to_cad_axes)
  files/drawings/<group>.svg|<group>-top.dxf, drawings/<group>.png
"""

import os
import sys

if __name__ == "__main__" and os.environ.get("PYTHONHASHSEED") != "0":
    # Python salts str hashes per process, and ezdxf writes a few DXF objects in set order:
    # pin the seed (re-exec before the heavy imports) so every build is byte-identical.
    os.environ["PYTHONHASHSEED"] = "0"
    os.execv(sys.executable, [sys.executable] + sys.argv)

import argparse  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import shutil  # noqa: E402
import struct  # noqa: E402
import time  # noqa: E402

import numpy as np  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import cadquery as cq  # noqa: E402
from OCP.BRep import BRep_Tool  # noqa: E402
from OCP.BRepAdaptor import BRepAdaptor_Curve  # noqa: E402
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform  # noqa: E402
from OCP.BRepLib import BRepLib_ToolTriangulatedShape  # noqa: E402
from OCP.BRepMesh import BRepMesh_IncrementalMesh  # noqa: E402
from OCP.BRepTools import BRepTools  # noqa: E402
from OCP.GCPnts import GCPnts_TangentialDeflection  # noqa: E402
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_REVERSED  # noqa: E402
from OCP.TopExp import TopExp, TopExp_Explorer  # noqa: E402
from OCP.TopLoc import TopLoc_Location  # noqa: E402
from OCP.TopoDS import TopoDS  # noqa: E402
from OCP.TopTools import TopTools_IndexedMapOfShape  # noqa: E402
from OCP.gp import gp_Trsf  # noqa: E402

import stepfile  # noqa: E402
from kit import common as C  # noqa: E402
from kit import registry as R  # noqa: E402
from kit import purchased as PU  # noqa: E402

EXPORT = os.path.join(HERE, "export")
PREVIEW = os.path.join(HERE, "preview")
COS_T, SIN_T = C.COS_T, C.SIN_T

MATERIALS = R.MATERIALS
MATERIAL_ORDER = list(MATERIALS.keys())
PART_INFO = {p.id: dict(group=p.group, name=p.name, material=p.material, internal=p.internal, kind=p.kind)
             for p in R.PARTS}
PARTDEF = R.BY_ID
GROUPS = R.GROUP_ORDER
ANIMATED_GROUPS = R.ANIMATED_GROUPS
GROUP_TEXT = R.GROUP_TEXT
EXPLODE = R.EXPLODE

# tessellation: (linear deflection mm, angular deflection rad)
TESS_DEFAULT = (0.3, 0.35)
TESS = {
    "base_shell": (0.45, 0.4), "display_back": (0.5, 0.45), "monitor_housings": (0.4, 0.4),
    "display_frame": (0.2, 0.35), "keyboard_keys": (0.2, 0.6), "neck_badge": (0.04, 0.35), "mouse_shell": (0.12, 0.2),
    "laptop_body": (0.2, 0.3), "dock_cradle": (0.2, 0.25), "display_screen": (0.5, 0.5), "deskmat": (0.4, 0.4),
    "fasteners": (0.2, 0.6), "lv_hub": (0.2, 0.6),
}
STL_TESS_DEFAULT = (0.3, 0.6)
STL_TESS = {"mouse": (0.15, 0.4), "dock": (0.2, 0.5), "base": (0.3, 0.5), "stand": (0.2, 0.5),
            "laptop": (0.2, 0.5), "deskmat": (0.2, 0.5)}


# ----------------------------------------------------------------------------
# helpers (geometry -> meshes, GLB writer, STEP canonicalisation, axes)
# ----------------------------------------------------------------------------

def log(*a):
    print(*a, flush=True)


def tight_bbox(shape):
    x0, y0, z0, x1, y1, z1 = C.tight_bbox(shape)
    return [x0, y0, z0], [x1, y1, z1]


def srgb_to_lin(h):
    h = h.lstrip("#")
    out = []
    for i in (0, 2, 4):
        c = int(h[i:i + 2], 16) / 255.0
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return out


def tessellate(shape, lin, ang):
    BRepTools.Clean_s(shape.wrapped)
    BRepMesh_IncrementalMesh(shape.wrapped, lin, False, ang, True)
    pos, nrm, idx = [], [], []
    off = 0
    exp = TopExp_Explorer(shape.wrapped, TopAbs_FACE)
    while exp.More():
        face = TopoDS.Face_s(exp.Current())
        exp.Next()
        loc = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(face, loc)
        if tri is None:
            continue
        trsf = loc.Transformation()
        BRepLib_ToolTriangulatedShape.ComputeNormals_s(face, tri)
        rev = face.Orientation() == TopAbs_REVERSED
        n = tri.NbNodes()
        P_ = np.empty((n, 3))
        N_ = np.empty((n, 3))
        for i in range(1, n + 1):
            p = tri.Node(i).Transformed(trsf)
            d = tri.Normal(i).Transformed(trsf)
            P_[i - 1] = (p.X(), p.Y(), p.Z())
            N_[i - 1] = (d.X(), d.Y(), d.Z())
        if rev:
            N_ = -N_
        m = tri.NbTriangles()
        T_ = np.empty((m, 3), dtype=np.int64)
        for i in range(1, m + 1):
            a, b, c = tri.Triangle(i).Get()
            T_[i - 1] = (a - 1, c - 1, b - 1) if rev else (a - 1, b - 1, c - 1)
        # drop degenerate triangles
        v0, v1, v2 = P_[T_[:, 0]], P_[T_[:, 1]], P_[T_[:, 2]]
        area2 = np.linalg.norm(np.cross(v1 - v0, v2 - v0), axis=1)
        T_ = T_[area2 > 1e-9]
        # make vertex normals agree with the triangle winding where the surface normal is unreliable
        if len(T_):
            fn = np.cross(P_[T_[:, 1]] - P_[T_[:, 0]], P_[T_[:, 2]] - P_[T_[:, 0]])
            acc = np.zeros_like(N_)
            for k in range(3):
                np.add.at(acc, T_[:, k], fn)
            dots = np.einsum("ij,ij->i", acc, N_)
            bad = (dots < 0) | ~np.isfinite(N_).all(axis=1) | (np.linalg.norm(N_, axis=1) < 0.5)
            if bad.any():
                ln = np.linalg.norm(acc[bad], axis=1, keepdims=True)
                ln[ln == 0] = 1
                N_[bad] = acc[bad] / ln
        pos.append(P_)
        nrm.append(N_)
        idx.append(T_ + off)
        off += n
    if not pos:
        return np.zeros((0, 3)), np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64)
    P_ = np.concatenate(pos)
    N_ = np.concatenate(nrm)
    T_ = np.concatenate(idx)
    ln = np.linalg.norm(N_, axis=1, keepdims=True)
    ln[ln == 0] = 1
    N_ = N_ / ln
    # remove unreferenced vertices
    used = np.zeros(len(P_), bool)
    used[T_.ravel()] = True
    remap = np.cumsum(used) - 1
    return P_[used], N_[used], remap[T_]


def edge_lines(shape, ang=0.2, curv=0.08):
    """Unique B-rep edges (no seams / degenerate edges) as line segments."""
    seams = TopTools_IndexedMapOfShape()
    fexp = TopExp_Explorer(shape.wrapped, TopAbs_FACE)
    while fexp.More():
        face = TopoDS.Face_s(fexp.Current())
        fexp.Next()
        eexp = TopExp_Explorer(face, TopAbs_EDGE)
        while eexp.More():
            e = TopoDS.Edge_s(eexp.Current())
            eexp.Next()
            if BRep_Tool.IsClosed_s(e, face):
                seams.Add(e)
    emap = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape.wrapped, TopAbs_EDGE, emap)
    pts, segs = [], []
    for i in range(1, emap.Extent() + 1):
        e = TopoDS.Edge_s(emap.FindKey(i))
        if BRep_Tool.Degenerated_s(e) or seams.Contains(e):
            continue
        try:
            c = BRepAdaptor_Curve(e)
            d = GCPnts_TangentialDeflection(c, ang, curv)
            n = d.NbPoints()
        except Exception:  # noqa: BLE001
            continue
        if n < 2:
            continue
        base = len(pts)
        for k in range(1, n + 1):
            p = d.Value(k)
            pts.append((p.X(), p.Y(), p.Z()))
        for k in range(n - 1):
            segs.append((base + k, base + k + 1))
    return np.array(pts, dtype=np.float64).reshape(-1, 3), np.array(segs, dtype=np.int64).reshape(-1, 2)


def screen_uv(P_):
    """Split UV: left panel u 0 -> 0.5 (outer edge -> seam), right 0.5 -> 1; v 0 = top (one 5120 x 1440 canvas)."""
    sz = C.seam_z()
    u0, u1, ya, yb = PU.active_area()
    x, y, z = P_[:, 0], P_[:, 1], P_[:, 2]
    s_dist = np.abs(x) * COS_T + (z - sz) * SIN_T
    frac = np.clip((s_dist - u0) / (u1 - u0), 0.0, 1.0)
    u = np.where(x >= 0, 0.5 + 0.5 * frac, 0.5 - 0.5 * frac)
    v = np.clip((yb - y) / (yb - ya), 0.0, 1.0)
    return np.stack([u, v], axis=1)


class GLB:
    def __init__(self):
        self.bin = bytearray()
        self.views, self.accessors, self.meshes, self.nodes, self.materials = [], [], [], [], []

    def _view(self, data, target=None):
        while len(self.bin) % 4:
            self.bin.append(0)
        off = len(self.bin)
        self.bin += data
        v = {"buffer": 0, "byteOffset": off, "byteLength": len(data)}
        if target:
            v["target"] = target
        self.views.append(v)
        return len(self.views) - 1

    def accessor(self, arr, kind, comp, target, minmax=False):
        arr = np.ascontiguousarray(arr)
        view = self._view(arr.tobytes(), target)
        a = {"bufferView": view, "componentType": comp, "count": int(arr.shape[0]), "type": kind}
        if minmax:
            a["min"] = [float(v) for v in arr.min(axis=0)]
            a["max"] = [float(v) for v in arr.max(axis=0)]
        self.accessors.append(a)
        return len(self.accessors) - 1

    def add_mesh(self, name, positions, indices, normals=None, uvs=None, material=None, mode=4):
        attrs = {"POSITION": self.accessor(positions.astype(np.float32), "VEC3", 5126, 34962, True)}
        if normals is not None:
            attrs["NORMAL"] = self.accessor(normals.astype(np.float32), "VEC3", 5126, 34962)
        if uvs is not None:
            attrs["TEXCOORD_0"] = self.accessor(uvs.astype(np.float32), "VEC2", 5126, 34962)
        flat = indices.reshape(-1)
        if len(positions) < 65535:
            ia = self.accessor(flat.astype(np.uint16), "SCALAR", 5123, 34963)
        else:
            ia = self.accessor(flat.astype(np.uint32), "SCALAR", 5125, 34963)
        prim = {"attributes": attrs, "indices": ia, "mode": mode}
        if material is not None:
            prim["material"] = material
        self.meshes.append({"name": name, "primitives": [prim]})
        return len(self.meshes) - 1

    def add_node(self, name, mesh, translation, extras):
        self.nodes.append({"name": name, "mesh": mesh, "translation": [float(t) for t in translation], "extras": extras})

    def write(self, path, generator):
        doc = {
            "asset": {"version": "2.0", "generator": generator},
            "scene": 0,
            "scenes": [{"name": "Night Array", "nodes": list(range(len(self.nodes)))}],
            "nodes": self.nodes,
            "meshes": self.meshes,
            "materials": self.materials,
            "accessors": self.accessors,
            "bufferViews": self.views,
            "buffers": [{"byteLength": len(self.bin)}],
        }
        js = json.dumps(doc, separators=(",", ":")).encode()
        while len(js) % 4:
            js += b" "
        while len(self.bin) % 4:
            self.bin.append(0)
        total = 12 + 8 + len(js) + 8 + len(self.bin)
        with open(path, "wb") as f:
            f.write(struct.pack("<III", 0x46546C67, 2, total))
            f.write(struct.pack("<II", len(js), 0x4E4F534A))
            f.write(js)
            f.write(struct.pack("<II", len(self.bin), 0x004E4942))
            f.write(self.bin)


def gltf_material(key):
    label, hexc, met, rough, dens, emis, desc = MATERIALS[key]
    m = {"name": key, "pbrMetallicRoughness": {"baseColorFactor": srgb_to_lin(hexc) + [1.0],
                                               "metallicFactor": met, "roughnessFactor": rough}}
    if emis:
        m["emissiveFactor"] = srgb_to_lin(emis)
    return m


def cq_color(key):
    r, gg, b = [int(MATERIALS[key][1][i:i + 2], 16) / 255.0 for i in (1, 3, 5)]
    return cq.Color(r, gg, b, 1.0)


def normalise_step(path):
    """Fixed FILE_NAME stamp + canonical order of the colour/style tail (see stepfile.py) -> reproducible bytes."""
    stepfile.canonicalise_file(path)


# The model is built in app axes (+Y up, +Z toward the user; SPEC.md section 1), and the GLBs / scene.json stay
# there.  The CAD exchange files (STEP, STL) are written Z-up, the convention of FreeCAD, Onshape, current Fusion
# and every slicer:
#     CAD (x, y, z) = app (x, -z, y)
# i.e. a +90 deg rotation about +X (right-handed, det +1): up (+Y app) -> +Z, the user side (+Z app) -> -Y, so
# the CAD "Front" view (looking along +Y) faces the user side, and +X stays +X.  The desk is still z = 0.
# Rows of the matrix, applied to column vectors (x_app, y_app, z_app).  The matrix is set entry by entry rather
# than with SetRotation(90 deg), so every coordinate maps exactly (no cos(90 deg) = 6e-17 noise in the files).
APP_TO_CAD = ((1, 0, 0), (0, 0, -1), (0, 1, 0))


def to_cad_axes(shape):
    """A copy of `shape` (app axes) with its geometry moved into the Z-up CAD axes (baked, no location)."""
    t = gp_Trsf()
    (a11, a12, a13), (a21, a22, a23), (a31, a32, a33) = APP_TO_CAD
    t.SetValues(a11, a12, a13, 0, a21, a22, a23, 0, a31, a32, a33, 0)
    return cq.Shape.cast(BRepBuilderAPI_Transform(shape.wrapped, t, True).Shape())




# ----------------------------------------------------------------------------
# masses, pivots, print pieces
# ----------------------------------------------------------------------------

def part_mass(pid, shape):
    return R.part_mass(pid, shape)


def print_orient(shape, down):
    """App-axes solid -> Z-up print orientation with the `down` face on the bed, min corner at the origin."""
    rot = {"-y": None, "+y": ((1, 0, 0), 180), "+z": ((1, 0, 0), 90), "-z": ((1, 0, 0), -90),
           "+x": ((0, 0, 1), -90), "-x": ((0, 0, 1), 90)}[down]
    s = shape
    if rot:
        s = s.rotate(cq.Vector(0, 0, 0), cq.Vector(*rot[0]), rot[1])
    s = to_cad_axes(s)
    x0, y0, z0, x1, y1, z1 = C.tight_bbox(s)
    return s.translate(cq.Vector(-x0, -y0, -z0))


def print_pieces(pid, shape):
    """[{name, solid, dims_mm, fits, grams, minutes}] for a printed part (one entry per solid)."""
    p = PARTDEF[pid]
    out = []
    sols = shape.Solids()
    for i, s in enumerate(sols):
        fits, dims = C.print_fit(s)
        g = C.print_mass_g(s.Volume(), s.Area(), p.print)
        nm = pid if len(sols) == 1 else f"{pid}_{i + 1:02d}"
        out.append({"name": nm, "solid": s, "dims_mm": [round(d, 1) for d in dims], "fits": fits,
                    "grams": round(g, 1), "minutes": round(C.print_minutes(g))})
    return out


def group_bbox(parts, gid):
    mins, maxs = [], []
    for pid, s in parts.items():
        if PART_INFO[pid]["group"] == gid:
            a, b = tight_bbox(s)
            mins.append(a)
            maxs.append(b)
    return np.min(mins, axis=0), np.max(maxs, axis=0)


def bottom_centre(a, b):
    return [(a[0] + b[0]) / 2, a[1], (a[2] + b[2]) / 2]


def compute_pivots(parts):
    gp = {}
    for g in GROUPS:
        a, b = group_bbox(parts, g)
        gp[g] = bottom_centre(a, b)
    node_pivot = {}
    for pid, s in parts.items():
        g = PART_INFO[pid]["group"]
        if g in ANIMATED_GROUPS:
            node_pivot[pid] = gp[g]
        else:
            a, b = tight_bbox(s)
            node_pivot[pid] = bottom_centre(a, b)
    return gp, node_pivot


# ----------------------------------------------------------------------------
# GLB / STEP / STL export
# ----------------------------------------------------------------------------

def export_glbs(parts, node_pivot, outdir):
    os.makedirs(outdir, exist_ok=True)
    g = GLB()
    g.materials = [gltf_material(k) for k in MATERIAL_ORDER]
    e = GLB()
    e.materials = [{"name": "edge", "pbrMetallicRoughness": {"baseColorFactor": [0.02, 0.02, 0.02, 1.0],
                                                             "metallicFactor": 0.0, "roughnessFactor": 1.0}}]
    stats = {}
    for pid, s in parts.items():
        info = PART_INFO[pid]
        lin, ang = TESS.get(pid, TESS_DEFAULT)
        P_, N_, T_ = tessellate(s, lin, ang)
        piv = np.array(node_pivot[pid])
        uvs = screen_uv(P_) if pid == "display_screen" else None
        mi = MATERIAL_ORDER.index(info["material"])
        mesh = g.add_mesh(pid, (P_ - piv) / 1000.0, T_, N_, uvs, mi)
        extras = {"group": info["group"], "material": info["material"], "internal": bool(info["internal"]),
                  "kind": info["kind"]}
        g.add_node(pid, mesh, piv / 1000.0, extras)
        EP, ES = edge_lines(s)
        emesh = e.add_mesh(pid + "_edges", (EP - piv) / 1000.0, ES, material=0, mode=1)
        e.add_node(pid, emesh, piv / 1000.0, extras)
        stats[pid] = (len(P_), len(T_), len(ES))
    gen = "Night Array CAD pipeline (CadQuery %s, OCP)" % cq.__version__
    g.write(os.path.join(outdir, "station.glb"), gen)
    e.write(os.path.join(outdir, "station-edges.glb"), gen)
    return stats


def export_step_stl(parts, files_dir):
    pdir = os.path.join(files_dir, "parts")
    os.makedirs(pdir, exist_ok=True)
    root = cq.Assembly(name="night-array")
    for gid in GROUPS:
        ga = cq.Assembly(name="NA-" + gid)
        sub = cq.Assembly(name="NA-" + gid)
        solids = []
        for pid, s in parts.items():
            if PART_INFO[pid]["group"] != gid:
                continue
            s = to_cad_axes(s)
            col = cq_color(PART_INFO[pid]["material"])
            ga.add(s, name=pid, color=col)
            sub.add(s, name=pid, color=col)
            solids.append(s)
        root.add(ga, name="NA-" + gid)
        p = os.path.join(pdir, gid + ".step")
        sub.export(p, "STEP", write_pcurves=False)
        normalise_step(p)
        comp = cq.Compound.makeCompound(solids)
        BRepTools.Clean_s(comp.wrapped)
        lin, ang = STL_TESS.get(gid, STL_TESS_DEFAULT)
        comp.exportStl(os.path.join(pdir, gid + ".stl"), tolerance=lin, angularTolerance=ang, ascii=False, relative=False)
    p = os.path.join(files_dir, "night-array-assembly.step")
    root.export(p, "STEP", write_pcurves=False)
    normalise_step(p)


# ----------------------------------------------------------------------------
# scene.json
# ----------------------------------------------------------------------------

def r6(v):
    return [round(float(x), 6) for x in v]


def fmt_mm(v):
    v = round(v)
    s = f"{v:,}".replace(",", " ")
    return f"{s} mm"


def work_path(key):
    """Waypoints (mm deltas from stow) a device passes through on its way from its pocket to `key`'s work position."""
    pm = R.POSES_MM
    t = pm[key]
    return [[0.0, pm["work_lift"], 0.0], [t[0], pm["work_lift"], pm["work_clear_z"]]]


def dock_sequence():
    """Latch-free: align (in the lead-in above the 60 mm front lip), lower (seated by its own weight: stow pose),
    lift (straight up, clear of the cradle)."""
    pm = R.POSES_MM
    return [
        {"step": "align", "title": "Align", "caption": "Guide it into the open cradle",
         "laptop": {"t": [0, round(pm["dock_align_lift"] * 0.001, 6), 0]}},
        {"step": "lower", "title": "Lower", "caption": "Its own weight seats it on the USB-C", "laptop": {"t": [0, 0, 0]}},
        {"step": "lift", "title": "Lift out", "caption": "Lift straight up — nothing to unlock",
         "laptop": {"t": [0, round(pm["dock_lift_out"] * 0.001, 6), 0]}},
    ]


def scene_params():
    """params: the kit's interface numbers (common.LAYOUT + each module's table), plus the keys the app reads by dot
    path (kept where cheap so the current app still finds them)."""
    from kit import base as KB, dock as KD, display as KDI, neck as KN, structure as KS, electronics as KE
    L = C.LAYOUT
    kbp = KB.kb_pocket()
    u0, u1, ya, yb = PU.active_area()
    return {
        "units": "mm",
        "axes": "+X right, +Y up, +Z toward the user; desk y=0; x=0 at the display seam; z=0 base depth centre",
        "pose": "stow",
        "layout": L,
        "tolerances": C.TOL,
        "hardware": {"insert": C.INSERT, "dowel": C.DOWEL, "joint_screw": C.JOINT_SCREW, "magnet": C.MAGNET},
        "print_max_mm": C.PRINT_MAX,
        # --- backward-compatible keys the app reads (Content.kt / Specs.kt) -------------------------------
        "base": {"x": L["base"]["x"], "z": L["base"]["z"], "height": L["base"]["height"], "deck_y": L["base"]["deck_y"],
                 "rim_w": L["base"]["rim_w"],
                 "kb_pocket": {"c": [(kbp[0] + kbp[1]) / 2, (kbp[2] + kbp[3]) / 2], "size": [kbp[1] - kbp[0], kbp[3] - kbp[2]],
                               "floor_y": L["qi"]["kb_floor_y"]},
                 "mouse_pocket": {"c": L["mouse"]["c"], "floor_y": L["qi"]["mouse_floor_y"]},
                 "floor_over_coil": L["qi"]["floor_over_coil"], "pad": L["qi"]["pad"]},
        "display": {"toe_in_deg": C.TOE_IN_DEG, "seam_mm": round(2 * u0, 2), "mullion_w": KDI.DISPLAY["seam"]["w"],
                    "shroud_depth": -KDI.DISPLAY["shroud"]["inner_w"] + KDI.DISPLAY["shroud"]["wall"],
                    "active": PU.S60UD["active"], "active_y": [round(ya, 2), round(yb, 2)],
                    "face_bottom_y": L["display"]["face_bottom_y"], "vesa_y": L["display"]["vesa_y"],
                    "seam_axis_xz": L["display"]["seam_axis_xz"], "monitor": "Samsung S60UD (LS27D606UANXGO)"},
        "neck": {"y": KN.NECK["y"], "bottom_w": KN.NECK["bottom_w"], "top_w": KN.NECK["top_w"],
                 "light": {"w": KN.NECK["light"]["w"], "y": KN.NECK["light"]["y"]}},
        "dock": {"x": KD.K["x"], "z": KD.K["z"], "h_back": KD.K["h_back"], "h_front": KD.K["h_front"],
                 "slot": KD.K["slot"], "landing_y": KD.K["landing_y"], "overmold_below": KD.K["overmold_below"],
                 "led": KD.K["led"], "connector": {"z": KD.K["plug_z"], "cable": "Newnex U4T1C01CR5P010"},
                 "laptop_t_range": [11.0, 20.0]},
        "laptop": {"t": PU.LAPTOP["t"], "h": PU.LAPTOP["h"], "d": PU.LAPTOP["d"], "port_z": KD.K["plug_z"]},
        "keyboard": {"model": "Keychron K3 Ultra 8K", "size": [PU.K3U["w"], PU.K3U["d"]], "h_front": PU.K3U["h_front"],
                     "h_back": PU.K3U["h_rear"], "stow_x": L["keyboard"]["x"], "stow_z": L["keyboard"]["z"]},
        "mouse": {"model": "Lenovo X9 4Y51R29290", "size": [PU.X9["w"], PU.X9["l"], PU.X9["h"]], "stow_c": L["mouse"]["c"]},
        "deskmat": {"size": [PU.DESKMAT["w"], PU.DESKMAT["t"], PU.DESKMAT["d"]], "c": list(KB.DESKMAT_C)},
        "structure": {"spine": KS.SPINE, "front_bar": KS.FRONT_BAR, "wing": KS.WING, "centre": KS.CENTRE,
                      "feet_xz": KS.FEET_XZ},
        "electronics": {"bays": {k: v[0] for k, v in KE.BAYS.items()}, "keepouts": {k: v[0] for k, v in KE.KEEPOUTS.items()}},
        "poses_mm": R.POSES_MM,
    }


def build_scene(parts, gp, files_index, drawings, pieces):
    mm = 0.001
    mins, maxs = [], []
    pinfo = {}
    for pid, s in parts.items():
        a, b = tight_bbox(s)
        pinfo[pid] = (a, b, s.Volume())
        if pid != "deskmat":
            mins.append(a)
            maxs.append(b)
    bmin, bmax = np.min(mins, axis=0), np.max(maxs, axis=0)
    masses = {pid: part_mass(pid, s) for pid, s in parts.items()}

    groups = []
    for gid in GROUPS:
        pids = [p.id for p in R.PARTS if p.group == gid]
        a, b = group_bbox(parts, gid)
        mats = []
        for p in pids:
            if PART_INFO[p]["material"] not in mats:
                mats.append(PART_INFO[p]["material"])
        groups.append({"id": gid, **GROUP_TEXT[gid], "parts": pids, "pivot": r6(np.array(gp[gid]) * mm),
                       "bbox_mm": [round(float(x), 1) for x in (b - a)],
                       "mass_g": round(sum(masses[p][0] for p in pids), 1),
                       "volume_cm3": round(sum(pinfo[p][2] for p in pids) / 1000.0, 1), "materials": mats})

    plist = []
    for p in R.PARTS:
        a, b, vol = pinfo[p.id]
        g, dens, note = masses[p.id]
        e = {"id": p.id, "group": p.group, "name": p.name, "material": p.material, "internal": bool(p.internal),
             "kind": p.kind, "explode": EXPLODE[p.id], "bbox_mm": [round(float(x), 1) for x in (np.array(b) - np.array(a))],
             "volume_cm3": round(vol / 1000.0, 2), "mass_g": round(g, 1), "density_g_cm3": round(dens, 3),
             "owner": p.owner}
        if note:
            e["mass_note"] = note
        if p.bom:
            e["bom"] = p.bom
        if p.kind == "printed":
            pcs = pieces[p.id]
            fil = C.FILAMENT[p.print.filament]
            e["print"] = {"filament": p.print.filament, "filament_product": f"{fil[0]} {fil[1]}", "down": p.print.down,
                          "supports": p.print.supports, "infill": p.print.infill,
                          "grams": round(sum(x["grams"] for x in pcs), 1),
                          "minutes": int(sum(x["minutes"] for x in pcs)), "plate": p.print.plate,
                          "file": f"print/{p.print.filament}/{pcs[0]['name']}.stl",
                          "pieces": [{"name": x["name"], "file": f"print/{p.print.filament}/{x['name']}.stl",
                                      "dims_mm": x["dims_mm"], "fits": x["fits"], "grams": x["grams"],
                                      "minutes": x["minutes"]} for x in pcs]}
            if p.split:
                e["print"]["split"] = p.split
        if len(parts[p.id].Solids()) > 1:
            e["solids"] = len(parts[p.id].Solids())
        plist.append(e)

    pm = R.POSES_MM

    def out_of_pocket(key):
        return {"t": r6(np.array(pm[key]) * mm), "via": [r6(np.array(v) * mm) for v in work_path(key)]}

    poses = {"stow": {"deskmat": {"hidden": True}},
             "work": {"keyboard": out_of_pocket("work_keyboard"), "mouse": out_of_pocket("work_mouse")}}

    u0, u1, ya, yb = PU.active_area()
    fr_a, fr_b = tight_bbox(parts["display_frame"])
    bk_a, bk_b = tight_bbox(parts["display_back"])
    L = C.LAYOUT
    bx0, bx1 = L["base"]["x"]
    bz0, bz1 = L["base"]["z"]
    outer_l = (fr_a[0], (fr_a[1] + fr_b[1]) / 2, fr_b[2])
    outer_r = (fr_b[0], (fr_a[1] + fr_b[1]) / 2, fr_b[2])
    a_in = C.facet_point(1, u0, yb, 0.3)
    a_out = C.facet_point(1, u1, yb, 0.3)
    s_l = C.facet_point(-1, u0, ya, 0.3)
    s_r = C.facet_point(1, u0, ya, 0.3)
    kz1 = L["keyboard"]["z"][0] + pm["work_keyboard"][2]
    kxc = sum(L["keyboard"]["x"]) / 2
    from kit import dock as KD
    dims = [
        {"id": "overall_w", "a": r6([bmin[0] * mm, 0, bz1 * mm]), "b": r6([bmax[0] * mm, 0, bz1 * mm]), "dir": [0, 0, 1]},
        {"id": "base_depth", "a": r6([bx0 * mm, 0, bz0 * mm]), "b": r6([bx0 * mm, 0, bz1 * mm]), "dir": [-1, 0, 0]},
        {"id": "overall_h", "a": r6([bmin[0] * mm, 0, fr_b[2] * mm]), "b": r6([bmin[0] * mm, bmax[1] * mm, fr_b[2] * mm]),
         "dir": [-1, 0, 0]},
        {"id": "display_w", "a": r6(np.array(outer_l) * mm), "b": r6(np.array(outer_r) * mm), "dir": [0, 1, 0]},
        {"id": "panel_active_w", "label": f"{PU.S60UD['active'][0]:.1f} mm · 27″ active", "a": r6(np.array(a_in) * mm),
         "b": r6(np.array(a_out) * mm), "dir": [0, 1, 0]},
        {"id": "seam", "label": f"{2 * u0:.0f} mm seam", "a": r6(np.array(s_l) * mm), "b": r6(np.array(s_r) * mm),
         "dir": [0, -1, 0]},
        {"id": "work_offset", "pose": "work", "a": r6([kxc * mm, 0.003, bz1 * mm]), "b": r6([kxc * mm, 0.003, kz1 * mm]),
         "dir": [-1, 0, 0]},
        {"id": "dock_h", "a": r6([KD.K["x"][1] * mm, 0, KD.K["z"][0] * mm]),
         "b": r6([KD.K["x"][1] * mm, KD.K["h_back"] * mm, KD.K["z"][0] * mm]), "dir": [1, 0, 0]},
        {"id": "base_h", "a": r6([bx1 * mm - 0.04, 0, bz1 * mm]), "b": r6([bx1 * mm - 0.04, L["base"]["height"] * mm, bz1 * mm]),
         "dir": [0, 0, 1]},
    ]
    order = ("id", "label", "pose", "a", "b", "dir")
    for i, dm in enumerate(dims):
        if "label" not in dm:
            dm["label"] = fmt_mm(np.linalg.norm(np.array(dm["b"]) - np.array(dm["a"])) / mm)
        dims[i] = {k: dm[k] for k in order if k in dm}
    screen = {"part": "display_screen", "layout": "dual", "panels": 2, "panel_inch": 27,
              "panel_active_mm": PU.S60UD["active"], "resolution_each": [2560, 1440], "seam_mm": round(2 * u0, 2),
              "toe_in_deg": C.TOE_IN_DEG, "seam_axis": [0, 0, round(C.seam_z() * mm, 6)], "canvas": [5120, 1440],
              "active_y_mm": [round(ya, 2), round(yb, 2)],
              "uv": "TEXCOORD_0: left panel u 0->0.5 (outer edge -> seam), right panel u 0.5->1 (seam -> outer edge); v 0 = top"}
    mats = {k: {"label": v[0], "color": v[1], "metallic": v[2], "roughness": v[3], "density_g_cm3": v[4],
                "spec": v[6], **({"emissive": True} if v[5] else {})} for k, v in MATERIALS.items()}
    kinds = {}
    for p in plist:
        kinds[p["kind"]] = kinds.get(p["kind"], 0) + 1
    return {
        "version": 1,
        "units": "m",
        "name": "Night Array — Work & Stow (buildable kit)",
        "tagline": "Your hardware. Your OS.",
        "params": scene_params(),
        "bounds": {"min": r6(bmin * mm), "max": r6(bmax * mm)},
        "materials": mats,
        "groups": groups,
        "parts": plist,
        "poses": poses,
        "dock_sequence": dock_sequence(),
        "dims": dims,
        "screen": screen,
        "files": files_index,
        "drawings": drawings,
        "kit": {"kinds": kinds, "print_max_mm": C.PRINT_MAX,
                "total_mass_g": round(sum(m[0] for pid, m in masses.items() if pid != "deskmat"), 0)},
        "mass_note": ("Purchased parts use manufacturer / research weights (monitors 3.6 kg each); steel and aluminium "
                      "use volume x density; printed parts use a shell + infill model of the slicer mass."),
    }


def files_index_for(export_dir):
    out = []

    def add(fid, grp, fmt, label, rel):
        p = os.path.join(export_dir, rel)
        out.append({"id": fid, "group": grp, "format": fmt, "label": label, "path": rel,
                    "bytes": os.path.getsize(p) if os.path.exists(p) else 0})

    add("assembly-step", None, "STEP", "Full assembly", "files/night-array-assembly.step")
    add("assembly-glb", None, "GLB", "Full assembly", "model/station.glb")
    for gid in GROUPS:
        label = GROUP_TEXT[gid]["name"]
        add(f"{gid}-step", gid, "STEP", label, f"files/parts/{gid}.step")
        add(f"{gid}-stl", gid, "STL", label, f"files/parts/{gid}.stl")
        add(f"{gid}-svg", gid, "SVG", label + " drawing", f"files/drawings/{gid}.svg")
        add(f"{gid}-dxf", gid, "DXF", label + " top view", f"files/drawings/{gid}-top.dxf")
    return out


# ----------------------------------------------------------------------------
# module build (scratch dir)
# ----------------------------------------------------------------------------

def interference_report(parts, pids, others=None, tol=0.5):
    """[(a, b, mm3)] for every pair (a in pids, b anywhere) whose solids intersect by more than tol."""
    boxes = {pid: C.tight_bbox(s) for pid, s in parts.items()}
    out = []
    ids = list(parts)
    seen = set()
    for a in pids:
        for b in (others or ids):
            if a == b or (b, a) in seen:
                continue
            seen.add((a, b))
            A, B = boxes[a], boxes[b]
            if not all(A[i] - 0.05 <= B[i + 3] and B[i] - 0.05 <= A[i + 3] for i in range(3)):
                continue
            v = parts[a].intersect(parts[b]).Volume()
            if v > tol:
                out.append((a, b, round(v, 2)))
    return out


def write_print_stls(pid, pcs, outdir):
    p = PARTDEF[pid]
    d = os.path.join(outdir, "print", p.print.filament)
    os.makedirs(d, exist_ok=True)
    files = []
    for x in pcs:
        s = print_orient(x["solid"], p.print.down)
        fn = os.path.join(d, x["name"] + ".stl")
        s.exportStl(fn, tolerance=0.05, angularTolerance=0.2, ascii=False, relative=False)
        files.append(fn)
    return files


def build_module(module, outdir, parts):
    from kit import structure as KS
    pids = R.parts_of_module(module)
    log(f"module {module}: {len(pids)} parts -> {outdir}")
    os.makedirs(os.path.join(outdir, "model"), exist_ok=True)
    os.makedirs(os.path.join(outdir, "parts"), exist_ok=True)
    gp, node_pivot = compute_pivots(parts)
    export_glbs(parts, node_pivot, os.path.join(outdir, "model"))
    pieces = {pid: print_pieces(pid, s) for pid, s in parts.items() if PARTDEF[pid].kind == "printed"}
    rep = {"module": module, "parts": {}, "interference": [], "too_big": []}
    for pid in pids:
        s = parts[pid]
        sc = to_cad_axes(s)
        cq.exporters.export(sc, os.path.join(outdir, "parts", pid + ".step"))
        sc.exportStl(os.path.join(outdir, "parts", pid + ".stl"), tolerance=0.1, angularTolerance=0.3, ascii=False,
                     relative=False)
        g, dens, note = part_mass(pid, s)
        a, b = tight_bbox(s)
        e = {"kind": PARTDEF[pid].kind, "solids": len(s.Solids()), "bbox_mm": [round(v, 1) for v in (np.array(b) - np.array(a))],
             "mass_g": round(g, 1)}
        if pid in pieces:
            write_print_stls(pid, pieces[pid], outdir)
            e["pieces"] = [{k: v for k, v in x.items() if k != "solid"} for x in pieces[pid]]
            rep["too_big"] += [x["name"] for x in pieces[pid] if not x["fits"]]
        rep["parts"][pid] = e
    if module == "structure":
        KS.write_metal(os.path.join(outdir, "metal"))
        rep["metal_problems"] = KS.check_flat_patterns()
    log("interference (module parts vs everything, stow) ...")
    rep["interference"] = interference_report(parts, pids)
    for a, b, v in rep["interference"]:
        log(f"  INTERFERENCE {a} x {b}: {v} mm3")
    for n in rep["too_big"]:
        log(f"  TOO BIG FOR THE BED: {n}")
    scene = build_scene(parts, gp, files_index_for(outdir), {}, pieces)
    with open(os.path.join(outdir, "model", "scene.json"), "w") as f:
        json.dump(scene, f, indent=1, ensure_ascii=False)
        f.write("\n")
    with open(os.path.join(outdir, "report.json"), "w") as f:
        json.dump(rep, f, indent=1)
    log(f"report: {os.path.join(outdir, 'report.json')}  (preview: node cad/tools/preview.mjs {outdir})")


# ----------------------------------------------------------------------------
# main
# ----------------------------------------------------------------------------

MODULE_NAMES = list(R.MODULES)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["glb", "step", "drawings", "all"] + MODULE_NAMES, default="all")
    ap.add_argument("--keep", action="store_true", help="do not wipe export/ first")
    ap.add_argument("--out", default=None, help="write somewhere other than cad/export (module builds: a scratch dir)")
    args = ap.parse_args()
    t0 = time.time()
    if args.only in MODULE_NAMES:
        out = os.path.abspath(args.out) if args.out else os.path.join(PREVIEW, args.only)
        if os.path.abspath(out).startswith(os.path.abspath(EXPORT)):
            sys.exit("module builds never write into cad/export: pass --out <scratch dir>")
        log("building parts ...")
        parts = R.build_parts()
        if C.FILLET_LOG:
            log("WARNING fillet/chamfer fallbacks:\n  " + "\n  ".join(C.FILLET_LOG))
        build_module(args.only, out, parts)
        log(f"done in {time.time() - t0:.1f}s")
        return
    EXP = os.path.abspath(args.out) if args.out else EXPORT
    if args.only == "all" and not args.keep and os.path.isdir(EXP):
        if os.listdir(EXP) and not os.path.isdir(os.path.join(EXP, "model")):
            sys.exit(f"refusing to wipe {EXP}: it does not look like an export directory")
        shutil.rmtree(EXP)
    for d in ("model", "files/parts", "files/drawings", "drawings"):
        os.makedirs(os.path.join(EXP, d), exist_ok=True)

    log("building parts ...")
    parts = R.build_parts()
    if C.FILLET_LOG:
        log("WARNING fillet/chamfer fallbacks:\n  " + "\n  ".join(C.FILLET_LOG))
    gp, node_pivot = compute_pivots(parts)
    pieces = {pid: print_pieces(pid, s) for pid, s in parts.items() if PARTDEF[pid].kind == "printed"}

    if args.only in ("all", "glb"):
        log("writing GLBs ...")
        st = export_glbs(parts, node_pivot, os.path.join(EXP, "model"))
        log(f"  {sum(v[0] for v in st.values())} vertices, {sum(v[1] for v in st.values())} triangles")
    if args.only in ("all", "step"):
        log("writing STEP / STL ...")
        export_step_stl(parts, os.path.join(EXP, "files"))
    drawings = {gid: f"drawings/{gid}.png" for gid in GROUPS}
    if args.only in ("all", "drawings"):
        import drawings as dr
        log("writing drawings ...")
        dr.export_all(parts, PART_INFO, GROUP_TEXT, MATERIALS, lambda pid, vol: part_mass(pid, parts[pid]), EXP,
                      group_order=GROUPS)

    files = files_index_for(EXP)
    scene = build_scene(parts, gp, files, drawings, pieces)
    with open(os.path.join(EXP, "model", "scene.json"), "w") as f:
        json.dump(scene, f, indent=1, ensure_ascii=False)
        f.write("\n")
    log(f"done in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
