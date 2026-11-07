#!/usr/bin/env python3
"""Night Array -- build every deliverable from params.py + model.py.

    cad/.venv/bin/python cad/build.py            # everything, from scratch
    cad/.venv/bin/python cad/build.py --only glb # just station.glb / edges / scene.json (fast iteration)

Outputs (SPEC.md section 3) under cad/export/:
  model/station.glb, model/station-edges.glb, model/scene.json
  files/night-array-assembly.step, files/parts/<group>.step|.stl,
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
import shutil  # noqa: E402
import struct  # noqa: E402
import time  # noqa: E402

import numpy as np  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import cadquery as cq  # noqa: E402
from OCP.BRep import BRep_Tool  # noqa: E402
from OCP.BRepAdaptor import BRepAdaptor_Curve  # noqa: E402
from OCP.BRepLib import BRepLib_ToolTriangulatedShape  # noqa: E402
from OCP.BRepMesh import BRepMesh_IncrementalMesh  # noqa: E402
from OCP.BRepTools import BRepTools  # noqa: E402
from OCP.GCPnts import GCPnts_TangentialDeflection  # noqa: E402
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_REVERSED  # noqa: E402
from OCP.TopExp import TopExp, TopExp_Explorer  # noqa: E402
from OCP.TopLoc import TopLoc_Location  # noqa: E402
from OCP.TopoDS import TopoDS  # noqa: E402
from OCP.TopTools import TopTools_IndexedMapOfShape  # noqa: E402

import model  # noqa: E402
import stepfile  # noqa: E402
from params import P, COS_T, SIN_T, facet_point  # noqa: E402

EXPORT = os.path.join(HERE, "export")

# ----------------------------------------------------------------------------
# materials
# ----------------------------------------------------------------------------

def srgb_to_lin(h):
    h = h.lstrip("#")
    out = []
    for i in (0, 2, 4):
        c = int(h[i:i + 2], 16) / 255.0
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return out


# key: label, sRGB colour, metallic, roughness, density g/cm3, (emissive sRGB)
MATERIALS = {
    "titanium":    ("Neutral Titanium", "#BDB2A4", 1.0, 0.32, 4.43, None, "Grade 5 titanium, bead-blasted and brushed"),
    "graphite":    ("Charcoal Graphite", "#3A3735", 0.55, 0.48, 2.70, None, "anodised aluminium, charcoal graphite finish"),
    "oxblood":     ("Brushed Oxblood", "#7A2E2A", 0.75, 0.36, 2.70, None, "brushed aluminium, oxblood anodise"),
    "glass_black": ("Black Glass", "#060606", 0.0, 0.06, 2.50, None, "cover glass with black print"),
    "screen":      ("Active Screen", "#08080A", 0.0, 0.12, 2.50, None, "IPS active area (2560x1440 each)"),
    "keycap":      ("PBT Keycap", "#1C1A19", 0.0, 0.62, 1.30, None, "double-shot PBT"),
    "rubber":      ("Rubber", "#141313", 0.0, 0.88, 1.20, None, "silicone rubber"),
    "amber_led":   ("Amber Light", "#F2A04A", 0.0, 0.40, 1.19, "#F2A04A", "diffused amber LED under PMMA"),
    "copper":      ("Copper", "#C9805A", 1.0, 0.33, 8.96, None, "copper windings"),
    "pcb":         ("PCB", "#1D2A22", 0.0, 0.55, 1.85, None, "FR-4 with components"),
    "ferrite":     ("Ferrite", "#2A2828", 0.0, 0.80, 4.80, None, "MnZn ferrite"),
    "laptop_alu":  ("Laptop Aluminium", "#8C847B", 1.0, 0.38, 2.70, None, "aluminium unibody"),
    "felt":        ("Wool Felt", "#2B2724", 0.0, 0.96, 0.30, None, "pressed wool felt"),
    "steel":       ("Steel", "#9A9C9E", 1.0, 0.40, 7.85, None, "stainless steel"),
}
MATERIAL_ORDER = list(MATERIALS.keys())

# Parts modelled as a solid envelope of a hollow device: effective density
# (the material's real density x fill factor) so masses read like real devices.
EFFECTIVE_DENSITY = {
    "laptop_body": (1.35, "solid envelope; effective density of a 14\" aluminium laptop"),
    "keyboard_body": (1.10, "solid envelope; aluminium chassis with internals, effective density"),
    "mouse_shell": (0.45, "solid envelope; hollow PC/ABS shell with internals, effective density"),
    "psu": (1.25, "solid envelope; GaN power supply, effective density"),
    "compute_fan": (0.55, "solid envelope; blower housing and impeller, effective density"),
    "display_boards": (1.10, "PCB + components, effective density"),
    "compute_board": (1.60, "PCB + components, effective density"),
    "dock_board": (1.60, "PCB + components, effective density"),
    "qi_coil_kb": (5.40, "litz-wire winding, ~60% copper fill"),
    "qi_coil_mouse": (5.40, "litz-wire winding, ~60% copper fill"),
    "keyboard_coil": (5.40, "litz-wire winding, ~60% copper fill"),
    "mouse_coil": (5.40, "litz-wire winding, ~60% copper fill"),
    "compute_heatsink": (8.50, "copper vapor chamber + fins (nickel plated)"),
}

PART_INFO = {pid: dict(group=g, name=n, material=m, internal=i) for pid, g, n, m, i, _ in model.PARTS}
GROUPS = model.GROUP_ORDER
ANIMATED_GROUPS = {"laptop", "keyboard", "mouse"}
LATCH_PARTS = {"dock_latch", "dock_latch_led"}

GROUP_TEXT = {
    "display": dict(
        name="Dual 27\" display",
        summary="Two mainstream 27\" QHD panels, toed in 10 degrees, one 5120 x 1440 canvas with an honest titanium seam.",
        description=("Two off-the-shelf 27-inch 2560 x 1440 IPS monitors are stripped of their plastic and hung on one steel "
                     "VESA spine inside a shared graphite shroud. Each panel is toed in 10 degrees about the seam, so the outer "
                     "edges come 106 mm toward you and the 1.2 m wide canvas wraps your field of view like a 49-inch "
                     "super-ultrawide. The 14 mm gap between the active areas is not hidden: a 4 mm titanium mullion runs the "
                     "full height of the glass, and your OS already treats it as the border between two displays. A dead panel "
                     "is a cheap swap, not a new monitor.")),
    "stand": dict(
        name="Neck & light bar",
        summary="Trapezoid aluminium neck that carries the display and the cables, with the amber light bar under the screen.",
        description=("A hollow trapezoid neck (320 mm at the foot, 180 mm at the top) leans back 4.8 degrees and plugs 3 mm into "
                     "the display's keel, so the steel spine sits directly on it. The hollow core is the cable chase from the "
                     "compute board to the monitors' scaler boards. NIGHT ARRAY is inlaid in titanium on the front face and an "
                     "amber light bar washes the top edge just below the glass.")),
    "base": dict(
        name="Base & charging trays",
        summary="1.29 m machined titanium tray with a recessed deck and two Qi2 charging pockets.",
        description=("The base is one long titanium tray: a 16 mm rim, a deck recessed 6 mm, and two pockets that take the "
                     "keyboard and mouse flush with the rim. Soft-touch pads cover non-metallic windows in the pocket floors, "
                     "because titanium would block Qi2; set a device down and it charges. Amber indicators sit on the front "
                     "lip, an under-glow strip lights the desk, and the shell is hollow inside to hold the compute, power and "
                     "coils. Rear I/O and the exhaust grille are on the back face, left side.")),
    "dock": dict(
        name="Laptop dock",
        summary="Right-wing cradle with a swept profile, lead-in slot, sprung USB-C and a press-release latch.",
        description=("The dock wing rises 120 mm at the back and sweeps down in a concave curve to a 60 mm front, wrapped in "
                     "brushed oxblood panels. A 20 mm slot with 4 mm lead-in chamfers guides a closed laptop on its side onto a "
                     "sprung USB-C plug standing up from the slot floor. Press the latch (3 mm travel) to release, then lift "
                     "out; the amber strip on the latch shows charge and link state.")),
    "laptop": dict(
        name="Laptop",
        summary="Any slim laptop, standing closed on its side in the dock: your hardware.",
        description=("A generic 14-inch class laptop (304 x 212 x 15 mm) stands closed on its left side, hinge toward the back, "
                     "with its USB-C port seated on the dock's sprung connector. Docked, it drives the dual display and charges; "
                     "lifted out, the station keeps running on the compute in the base. Mass is an estimate for a real device.")),
    "keyboard": dict(
        name="Low-profile keyboard",
        summary="75% low-profile keyboard that charges wirelessly in its pocket.",
        description=("A 360 x 120 mm aluminium wedge (9 mm at the front, 13 mm at the back) with an 84-key 75% layout on an "
                     "18.5 mm pitch. Two receiver coils under the chassis line up with the base's Qi2 coils when it is stowed. "
                     "In work mode it comes 298 mm forward onto the felt mat, leaving 150 mm of open desk in front of the base.")),
    "mouse": dict(
        name="Mouse",
        summary="Ambidextrous ergonomic mouse with an amber tail light and a Qi2 receiver coil.",
        description=("A 66 x 118 x 38 mm ambidextrous shell lofted through fourteen sections, with a rubber scroll wheel, split "
                     "buttons and an amber accent at the rear. Its receiver coil sits over the pocket's Qi2 coil when stowed. "
                     "The mass is an effective estimate for a real hollow mouse.")),
    "deskmat": dict(
        name="Felt desk mat",
        summary="820 x 300 mm wool felt mat for work mode.",
        description=("A 3 mm pressed wool felt mat that defines the work zone in front of the base. It only appears in work and "
                     "standalone modes, when the keyboard and mouse come out of their pockets.")),
    "internals": dict(
        name="Internals",
        summary="Compute stays in the base: mainboard, vapor chamber, blower, PSU, Qi2 coils and the dock PCB.",
        description=("Inside the hollow base: a 300 x 230 mm compute board with a vapor chamber and fin stack exhausting through "
                     "the rear grille, a slim blower, a 140 x 158 mm internal power supply, three Qi2 transmitter coils on "
                     "ferrite shields under the pocket windows, and the dock PCB with its pogo contact under the cradle. "
                     "Because compute stays in the base, the station works with or without the laptop.")),
}

# explode vectors, metres (offset at explode = 1)
EXPLODE = {
    # display: lifts clear of the neck, layers fan out along the view axis
    "display_screen": [0.0, 0.42, 0.20],
    "display_seam": [0.0, 0.42, 0.25],
    "display_glass": [0.0, 0.42, 0.13],
    "display_frame": [0.0, 0.42, 0.07],
    "display_spine": [0.0, 0.42, -0.08],
    "display_boards": [0.0, 0.42, -0.14],
    "display_back": [0.0, 0.42, -0.23],
    # stand
    "neck": [0.0, 0.22, -0.03],
    "neck_light": [0.0, 0.22, 0.03],
    "neck_badge": [0.0, 0.22, 0.07],
    # base: the shell lifts off its internals, which stay at desk level
    "base_shell": [0.0, 0.12, 0.0],
    "deck_liner": [0.0, 0.145, 0.0],
    "tray_pad_kb": [0.0, 0.17, 0.0],
    "tray_pad_mouse": [0.0, 0.17, 0.0],
    "base_glow": [0.0, 0.10, 0.07],
    "kb_charge_led": [0.0, 0.15, 0.06],
    "mouse_charge_led": [0.0, 0.15, 0.06],
    "base_feet": [0.0, 0.0, 0.0],
    # dock wing slides out to the right
    "dock_cradle": [0.24, 0.12, 0.0],
    "dock_panels": [0.33, 0.12, 0.05],
    "dock_latch": [0.24, 0.12, 0.12],
    "dock_latch_led": [0.24, 0.15, 0.12],
    "dock_connector": [0.24, 0.20, 0.0],
    "laptop_body": [0.24, 0.50, 0.0],
    # devices rise above their pads, receiver coils between pad and device
    "keyboard_body": [0.0, 0.25, 0.12],
    "keyboard_keys": [0.0, 0.29, 0.12],
    "keyboard_coil": [0.0, 0.21, 0.12],
    "mouse_shell": [0.0, 0.25, 0.12],
    "mouse_wheel": [0.0, 0.30, 0.12],
    "mouse_glow": [0.0, 0.25, 0.16],
    "mouse_coil": [0.0, 0.21, 0.12],
    "deskmat": [0.0, 0.0, 0.08],
    # internals stay on the desk, slightly fanned out
    "compute_board": [0.0, 0.0, 0.0],
    "compute_heatsink": [0.0, 0.035, 0.0],
    "compute_fan": [0.0, 0.035, 0.03],
    "psu": [0.0, 0.0, 0.0],
    "qi_coil_kb": [0.0, 0.03, 0.0],
    "qi_coil_mouse": [0.0, 0.03, 0.0],
    "ferrite_kb": [0.0, 0.0, 0.0],
    "ferrite_mouse": [0.0, 0.0, 0.0],
    "dock_board": [0.24, 0.0, 0.0],
}

# tessellation: (linear deflection mm, angular deflection rad)
TESS_DEFAULT = (0.25, 0.32)
TESS = {
    "base_shell": (0.45, 0.38), "display_back": (0.5, 0.42), "display_frame": (0.15, 0.3),
    "keyboard_keys": (0.12, 0.6), "compute_heatsink": (0.3, 0.6), "neck_badge": (0.04, 0.35),
    "mouse_shell": (0.12, 0.2), "mouse_glow": (0.1, 0.25), "laptop_body": (0.2, 0.3),
    "dock_cradle": (0.2, 0.25), "display_screen": (0.5, 0.5), "display_glass": (0.3, 0.35),
    "deskmat": (0.4, 0.4),
}

# STL tessellation per group: (absolute linear deflection mm, angular deflection rad).  Organic and
# small parts get finer meshes; the big, mostly planar groups stay coarse to keep export/ ~20 MB.
STL_TESS_DEFAULT = (0.3, 0.6)
STL_TESS = {"mouse": (0.15, 0.4), "dock": (0.2, 0.5), "base": (0.25, 0.5), "stand": (0.2, 0.5),
            "laptop": (0.2, 0.5), "deskmat": (0.2, 0.5)}


# ----------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------

def log(*a):
    print(*a, flush=True)


def bbox_of(shape):
    bb = shape.BoundingBox()
    return [bb.xmin, bb.ymin, bb.zmin], [bb.xmax, bb.ymax, bb.zmax]


def tight_bbox(shape):
    """Bounding box from the triangulation (OCC's BoundingBox can be loose on splines)."""
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    b = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape.wrapped, b, False, False)
    x0, y0, z0, x1, y1, z1 = b.Get()
    return [x0, y0, z0], [x1, y1, z1]


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
    """Split UV: left panel u 0 -> 0.5 (outer edge -> seam), right 0.5 -> 1; v 0 = top."""
    d = P["display"]
    sz = d["seam_axis_xz"][1]
    x, y, z = P_[:, 0], P_[:, 1], P_[:, 2]
    s_dist = np.abs(x) * COS_T + (z - sz) * SIN_T
    frac = np.clip((s_dist - d["inner_border"]) / d["active"][0], 0.0, 1.0)
    u = np.where(x >= 0, 0.5 + 0.5 * frac, 0.5 - 0.5 * frac)
    v = np.clip((d["active_y"][1] - y) / (d["active_y"][1] - d["active_y"][0]), 0.0, 1.0)
    return np.stack([u, v], axis=1)


# ----------------------------------------------------------------------------
# GLB writer
# ----------------------------------------------------------------------------

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


# ----------------------------------------------------------------------------
# pivots / mass
# ----------------------------------------------------------------------------

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
    la, lb = None, None
    for pid in LATCH_PARTS:
        a, b = tight_bbox(parts[pid])
        la = a if la is None else np.minimum(la, a)
        lb = b if lb is None else np.maximum(lb, b)
    latch_pivot = bottom_centre(la, lb)
    node_pivot = {}
    for pid, s in parts.items():
        g = PART_INFO[pid]["group"]
        if pid in LATCH_PARTS:
            node_pivot[pid] = latch_pivot
        elif g in ANIMATED_GROUPS:
            node_pivot[pid] = gp[g]
        else:
            a, b = tight_bbox(s)
            node_pivot[pid] = bottom_centre(a, b)
    return gp, latch_pivot, node_pivot


def part_mass(pid, vol_mm3):
    dens = EFFECTIVE_DENSITY.get(pid, (MATERIALS[PART_INFO[pid]["material"]][4], None))[0]
    return vol_mm3 / 1000.0 * dens, dens


# ----------------------------------------------------------------------------
# GLB export
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
        extras = {"group": info["group"], "material": info["material"], "internal": bool(info["internal"])}
        g.add_node(pid, mesh, piv / 1000.0, extras)
        EP, ES = edge_lines(s)
        emesh = e.add_mesh(pid + "_edges", (EP - piv) / 1000.0, ES, material=0, mode=1)
        e.add_node(pid, emesh, piv / 1000.0, extras)
        stats[pid] = (len(P_), len(T_), len(ES))
    gen = "Night Array CAD pipeline (CadQuery %s, OCP)" % cq.__version__
    g.write(os.path.join(outdir, "station.glb"), gen)
    e.write(os.path.join(outdir, "station-edges.glb"), gen)
    return stats


# ----------------------------------------------------------------------------
# STEP / STL
# ----------------------------------------------------------------------------

def cq_color(key):
    r, gg, b = [int(MATERIALS[key][1][i:i + 2], 16) / 255.0 for i in (1, 3, 5)]
    return cq.Color(r, gg, b, 1.0)


def normalise_step(path):
    """Fixed FILE_NAME stamp + canonical order of the colour/style tail (see stepfile.py) -> reproducible bytes."""
    stepfile.canonicalise_file(path)


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
            col = cq_color(PART_INFO[pid]["material"])
            ga.add(s, name=pid, color=col)
            sub.add(s, name=pid, color=col)
            solids.append(s)
        root.add(ga, name="NA-" + gid)
        p = os.path.join(pdir, gid + ".step")
        sub.export(p, "STEP", write_pcurves=False)
        normalise_step(p)
        comp = cq.Compound.makeCompound(solids)
        BRepTools.Clean_s(comp.wrapped)   # drop the finer GLB triangulation so the STL tolerance applies
        lin, ang = STL_TESS.get(gid, STL_TESS_DEFAULT)
        # absolute deflection (CadQuery's default is relative to edge length, which faceted the mouse badly)
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
    return f"{s} mm"


def build_scene(parts, gp, latch_pivot, files_index, drawings):
    mm = 0.001
    # bounds (stow pose, all parts except the hidden desk mat)
    mins, maxs = [], []
    pinfo = {}
    for pid, s in parts.items():
        a, b = tight_bbox(s)
        pinfo[pid] = (a, b, s.Volume())
        if pid != "deskmat":
            mins.append(a)
            maxs.append(b)
    bmin, bmax = np.min(mins, axis=0), np.max(maxs, axis=0)

    groups = []
    for gid in GROUPS:
        pids = [pid for pid, *_ in model.PARTS if PART_INFO[pid]["group"] == gid]
        a, b = group_bbox(parts, gid)
        vol = sum(pinfo[p][2] for p in pids)
        mass = sum(part_mass(p, pinfo[p][2])[0] for p in pids)
        mats = []
        for p in pids:
            m = PART_INFO[p]["material"]
            if m not in mats:
                mats.append(m)
        g = {"id": gid, **GROUP_TEXT[gid], "parts": pids, "pivot": r6(np.array(gp[gid]) * mm),
             "bbox_mm": [round(float(x), 1) for x in (b - a)], "mass_g": round(mass, 1),
             "volume_cm3": round(vol / 1000.0, 1), "materials": mats}
        if gid == "dock":
            g["subgroups"] = {"dock_latch": {"parts": sorted(LATCH_PARTS), "pivot": r6(np.array(latch_pivot) * mm)}}
        groups.append(g)

    plist = []
    for pid, grp, name, mat, internal, _ in model.PARTS:
        a, b, vol = pinfo[pid]
        mass, dens = part_mass(pid, vol)
        e = {"id": pid, "group": grp, "name": name, "material": mat, "internal": bool(internal),
             "explode": EXPLODE[pid], "bbox_mm": [round(float(x), 1) for x in (np.array(b) - np.array(a))],
             "volume_cm3": round(vol / 1000.0, 2), "mass_g": round(mass, 1), "density_g_cm3": dens}
        if pid in EFFECTIVE_DENSITY:
            e["mass_note"] = EFFECTIVE_DENSITY[pid][1]
        if len(parts[pid].Solids()) > 1:
            e["solids"] = len(parts[pid].Solids())
        plist.append(e)

    pm = P["poses_mm"]
    poses = {
        "stow": {"deskmat": {"hidden": True}},
        "work": {"keyboard": {"t": r6(np.array(pm["work_keyboard"]) * mm)},
                 "mouse": {"t": r6(np.array(pm["work_mouse"]) * mm)}},
        "standalone": {"keyboard": {"t": r6(np.array(pm["work_keyboard"]) * mm)},
                       "mouse": {"t": r6(np.array(pm["work_mouse"]) * mm)},
                       "laptop": {"hidden": True}},
    }
    dock_sequence = [
        {"step": "align", "title": "Align", "caption": "Guide into the open cradle",
         "laptop": {"t": [0, round(pm["dock_align_lift"] * mm, 6), 0]}},
        {"step": "lower", "title": "Lower", "caption": "Seat the laptop onto the connector", "laptop": {"t": [0, 0, 0]}},
        {"step": "release", "title": "Press-release & lift", "caption": "Press to release, then lift out",
         "laptop": {"t": [0, 0, 0]}, "dock_latch": {"t": [0, 0, round(-pm["latch_travel"] * mm, 6)]}},
        {"step": "lift", "title": "Lift out", "caption": "Laptop free; compute stays in the base",
         "laptop": {"t": [0, round(pm["dock_lift_out"] * mm, 6), 0]}},
    ]

    d = P["display"]
    fr_a, fr_b = tight_bbox(parts["display_frame"])
    disp_a, disp_b = tight_bbox(parts["display_back"])
    dmin_x = min(fr_a[0], disp_a[0])
    dmax_x = max(fr_b[0], disp_b[0])
    L_out = d["inner_border"] + d["active"][0] + d["outer_border"] + d["frame_w"]
    outer_r = facet_point(1, L_out, d["glass_y"][1] + d["frame_w"], d["frame_proud"])
    outer_l = facet_point(-1, L_out, d["glass_y"][1] + d["frame_w"], d["frame_proud"])
    a_in = facet_point(1, d["inner_border"], d["active_y"][1], d["screen_proud"])
    a_out = facet_point(1, d["inner_border"] + d["active"][0], d["active_y"][1], d["screen_proud"])
    s_l = facet_point(-1, d["inner_border"], d["active_y"][0], d["screen_proud"])
    s_r = facet_point(1, d["inner_border"], d["active_y"][0], d["screen_proud"])
    bx0, bx1 = P["base"]["x"]
    bz0, bz1 = P["base"]["z"]
    kbz = P["keyboard"]["stow_c"][1] - P["keyboard"]["size"][1] / 2 + pm["work_keyboard"][2]
    dims = [
        {"id": "overall_w", "label": fmt_mm(bmax[0] - bmin[0]), "a": r6([bmin[0] * mm, 0, bz1 * mm]),
         "b": r6([bmax[0] * mm, 0, bz1 * mm]), "dir": [0, 0, 1]},
        {"id": "base_depth", "label": fmt_mm(bz1 - bz0), "a": r6([bx0 * mm, 0, bz0 * mm]), "b": r6([bx0 * mm, 0, bz1 * mm]),
         "dir": [-1, 0, 0]},
        {"id": "overall_h", "label": fmt_mm(bmax[1] - bmin[1]), "a": r6([dmin_x * mm, 0, outer_l[2] * mm]),
         "b": r6([dmin_x * mm, bmax[1] * mm, outer_l[2] * mm]), "dir": [-1, 0, 0]},
        {"id": "display_w", "label": fmt_mm(dmax_x - dmin_x), "a": r6(np.array(outer_l) * mm), "b": r6(np.array(outer_r) * mm),
         "dir": [0, 1, 0]},
        {"id": "panel_active_w", "label": "596.7 mm · 27\" active", "a": r6(np.array(a_in) * mm),
         "b": r6(np.array(a_out) * mm), "dir": [0, 1, 0]},
        {"id": "seam", "label": "14 mm seam", "a": r6(np.array(s_l) * mm), "b": r6(np.array(s_r) * mm), "dir": [0, -1, 0]},
        {"id": "work_offset", "label": "150 mm", "pose": "work",
         "a": r6([P["keyboard"]["stow_c"][0] * mm, 0.003, bz1 * mm]), "b": r6([P["keyboard"]["stow_c"][0] * mm, 0.003, kbz * mm]),
         "dir": [-1, 0, 0]},
        {"id": "dock_h", "label": fmt_mm(P["dock"]["h_back"]), "a": r6([P["dock"]["x"][1] * mm, 0, P["dock"]["z"][0] * mm]),
         "b": r6([P["dock"]["x"][1] * mm, P["dock"]["h_back"] * mm, P["dock"]["z"][0] * mm]), "dir": [1, 0, 0]},
        {"id": "base_h", "label": fmt_mm(P["base"]["height"]), "a": r6([bx1 * mm - 0.04, 0, bz1 * mm]),
         "b": r6([bx1 * mm - 0.04, P["base"]["height"] * mm, bz1 * mm]), "dir": [0, 0, 1]},
    ]
    screen = {"part": "display_screen", "layout": "dual", "panels": 2, "panel_inch": d["panel_inch"],
              "panel_active_mm": d["active"], "resolution_each": d["resolution_each"], "seam_mm": d["seam_mm"],
              "toe_in_deg": d["toe_in_deg"], "seam_axis": [0, 0, round(d["seam_axis_xz"][1] * mm, 6)],
              "canvas": [5120, 1440], "active_y_mm": d["active_y"],
              "uv": "TEXCOORD_0: left panel u 0->0.5 (outer edge -> seam), right panel u 0.5->1 (seam -> outer edge); v 0 = top"}

    mats = {k: {"label": v[0], "color": v[1], "metallic": v[2], "roughness": v[3], "density_g_cm3": v[4],
                "spec": v[6], **({"emissive": True} if v[5] else {})} for k, v in MATERIALS.items()}
    return {
        "version": 1,
        "units": "m",
        "name": "Night Array — Work & Stow",
        "tagline": "Your hardware. Your OS.",
        "params": P,
        "bounds": {"min": r6(bmin * mm), "max": r6(bmax * mm)},
        "materials": mats,
        "groups": groups,
        "parts": plist,
        "poses": poses,
        "dock_sequence": dock_sequence,
        "dims": dims,
        "screen": screen,
        "files": files_index,
        "drawings": drawings,
        "mass_note": "Masses are concept-level estimates from the B-rep volumes and real densities; solid envelopes of hollow devices use effective densities (see parts[].mass_note).",
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
# main
# ----------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["glb", "step", "drawings", "all"], default="all")
    ap.add_argument("--keep", action="store_true", help="do not wipe export/ first")
    ap.add_argument("--out", default=None, help="write somewhere other than cad/export (e.g. to diff two builds)")
    args = ap.parse_args()
    EXPORT = os.path.abspath(args.out) if args.out else globals()["EXPORT"]
    t0 = time.time()
    if args.only == "all" and not args.keep and os.path.isdir(EXPORT):
        if os.listdir(EXPORT) and not os.path.isdir(os.path.join(EXPORT, "model")):
            sys.exit(f"refusing to wipe {EXPORT}: it does not look like an export directory")
        shutil.rmtree(EXPORT)
    for d in ("model", "files/parts", "files/drawings", "drawings"):
        os.makedirs(os.path.join(EXPORT, d), exist_ok=True)

    log("building parts ...")
    parts = model.build_all()
    if model.FILLET_LOG:
        log("WARNING fillet/chamfer fallbacks:\n  " + "\n  ".join(model.FILLET_LOG))
    gp, latch_pivot, node_pivot = compute_pivots(parts)

    if args.only in ("all", "glb"):
        log("writing GLBs ...")
        st = export_glbs(parts, node_pivot, os.path.join(EXPORT, "model"))
        nv = sum(v[0] for v in st.values())
        nt = sum(v[1] for v in st.values())
        log(f"  {nv} vertices, {nt} triangles")
    if args.only in ("all", "step"):
        log("writing STEP / STL ...")
        export_step_stl(parts, os.path.join(EXPORT, "files"))
    drawings = {gid: f"drawings/{gid}.png" for gid in GROUPS}
    if args.only in ("all", "drawings"):
        import drawings as dr
        log("writing drawings ...")
        dr.export_all(parts, PART_INFO, GROUP_TEXT, MATERIALS, part_mass, EXPORT)

    files = files_index_for(EXPORT)
    scene = build_scene(parts, gp, latch_pivot, files, drawings)
    with open(os.path.join(EXPORT, "model", "scene.json"), "w") as f:
        json.dump(scene, f, indent=1, ensure_ascii=False)
        f.write("\n")
    log(f"done in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
