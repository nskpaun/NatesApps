"""Builds the Night Array with the light-ribbon optics in Blender and path-traces it with Cycles.

    python scene.py --view hero --out out_dir [--samples 600] [--width 2400] [--band band.png]
    python scene.py --out out_dir --export model.glb        (geometry only, for the 3D viewer)

Needs the `bpy` module (pip install bpy) and the textures from screen_ui.py in out_dir. Writes
out_dir/<view>.exr: a multilayer EXR with one pass per light group, so develop.py can set the room light, the
band brightness and the exposure afterwards without rendering again:

    band    light from the hidden feed rows (everything the ribbon is made of)
    screen  light from the rest of the two panels
    room    window and ceiling light

Units: 1.0 = the panel's on-axis white (350 nits). Geometry comes from cad/export/model/station.glb (work
pose) plus the sill, mirrors and cove generated here from ribbon/designs.py, the same cross-section the
optics study traced.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from ribbon import designs as D  # noqa: E402

STATION = HERE.parent.parent / "cad" / "export" / "model"
PRESET = dict(h=12.0, drop=34.0)                 # Balanced
FINISH = D.FINISHES["fine"]                      # finer brush: roughness 0.05 along the ribbon, 0.08 across
KAPPA = 2.9                                      # panel angular falloff, as in the study
TOE = math.radians(10.0)
SEAM_Z = -62.0                                   # screen face at the seam (app z, mm)
ROW0_Y = 172.0                                   # lowest pixel row above the desk (app y, mm)
ACTIVE = (7.0, 7.0 + D.PANEL_W)                  # active area along a facet, from the seam
GLASS_END = 7.0 + D.PANEL_W + 9.0 + 1.5          # outer end of the sill and cove along a facet
DECK_Y = 30.0 - ROW0_Y                           # base deck, relative to the lowest pixel row (mm)
FOOT_Z = 2.0                                     # where the stand wall meets the deck, in front of the screen face
REAR_Z = -19.0                                   # back of the stand, behind the screen face


def stand_wall(cove, r_nose=5.0, r_foot=8.0, n=12):
    """Continues the cove down to the base deck so the brushed part is the stand, not an add-on: a rounded
    nose under the cove's front lip, a wall raked back so it clears the keyboard and mouse pockets, and a
    small foot fillet onto the deck. Points (z', y) from the cove's front end to the deck; the rake is solved
    so the foot lands at FOOT_Z. No band light reaches this part (it is under the lip), so the ribbon is
    unchanged."""
    cove = np.asarray(cove, float)
    t0 = cove[-1] - cove[-2]
    th0 = math.atan2(t0[1], t0[0])
    cw = lambda th: np.array([math.sin(th), -math.cos(th)])       # tangent heading th, rotated 90 deg clockwise
    centre = cove[-1] + r_nose * cw(th0)

    def build(th1):
        nose = [centre - r_nose * cw(th) for th in np.linspace(th0, th1, n)]
        t1 = np.array([math.cos(th1), math.sin(th1)])
        ccw = lambda th: -cw(th)
        f0y = DECK_Y + r_foot * (1 - ccw(th1)[1])
        length = (nose[-1][1] - f0y) / (-t1[1])
        f0 = nose[-1] + length * t1
        cf = f0 + r_foot * ccw(th1)
        foot = [cf - r_foot * ccw(th) for th in np.linspace(th1, 0.0, n)]
        return np.array(nose[1:] + foot)

    lo, hi = math.radians(-135), math.radians(-91)
    for _ in range(40):                                           # bisection on the rake
        mid = 0.5 * (lo + hi)
        if build(mid)[-1][0] < FOOT_Z:
            lo = mid
        else:
            hi = mid
    return build(0.5 * (lo + hi))


def app(x, y, z):
    """App axes (x right, y up, z toward the user; mm) -> Blender (x right, y away from the user, z up; m)."""
    return Vector((x / 1000.0, -z / 1000.0, y / 1000.0))


def facet(side, xp, zp, yr, z0=0.0):
    """Point on a facet: xp along it from the seam, zp in front of the screen face, yr above the lowest row."""
    c, s = math.cos(TOE), math.sin(TOE)
    zp = zp + z0
    return app(side * (xp * c - zp * s), ROW0_Y + yr, SEAM_Z + xp * s + zp * c)


def mitre(zp):
    """Where a facet extrusion starts so the two sides meet on the station's centre plane."""
    return zp * math.tan(TOE)


# --------------------------------------------------------------------------------------------- materials
def principled(name, base, rough, metallic=0.0, **extra):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*base, 1.0)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metallic
    for k, v in extra.items():
        b.inputs[k].default_value = v
    return m


def brushed(name, f0, along, across):
    """Anisotropic GGX metal. Cycles: alpha_tangent = r^2 / aspect, alpha_bitangent = r^2 * aspect with
    aspect = sqrt(1 - 0.9 * anisotropic); the tangent is the UV map's U direction, which the cove mesh lays
    ACROSS the ribbon, so `across` is the larger roughness."""
    r2 = math.sqrt(along * across)
    aspect = math.sqrt(along / across)
    m = principled(name, f0, math.sqrt(r2), 1.0, Anisotropic=(1 - aspect * aspect) / 0.9)
    nt = m.node_tree
    t = nt.nodes.new("ShaderNodeTangent")
    t.direction_type = "UV_MAP"
    t.uv_map = "UVMap"
    nt.links.new(t.outputs["Tangent"], nt.nodes["Principled BSDF"].inputs["Tangent"])
    return m


def emitter(name, image_path, reflect=False):
    """A panel surface: textured emission with the measured IPS angular falloff exp(kappa (cos - 1))."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(str(image_path))
    tex.extension = "EXTEND"
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    dot = nt.nodes.new("ShaderNodeVectorMath")
    dot.operation = "DOT_PRODUCT"
    nt.links.new(geo.outputs["Normal"], dot.inputs[0])
    nt.links.new(geo.outputs["Incoming"], dot.inputs[1])
    absn = nt.nodes.new("ShaderNodeMath")
    absn.operation = "ABSOLUTE"
    nt.links.new(dot.outputs["Value"], absn.inputs[0])
    sub = nt.nodes.new("ShaderNodeMath")
    sub.operation = "MULTIPLY_ADD"                       # (cos * kappa) - kappa
    sub.inputs[1].default_value = KAPPA
    sub.inputs[2].default_value = -KAPPA
    nt.links.new(absn.outputs[0], sub.inputs[0])
    ex = nt.nodes.new("ShaderNodeMath")
    ex.operation = "EXPONENT"
    nt.links.new(sub.outputs[0], ex.inputs[0])
    em = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(tex.outputs["Color"], em.inputs["Color"])
    nt.links.new(ex.outputs[0], em.inputs["Strength"])
    if reflect:                                          # matte anti-glare front surface
        gl = nt.nodes.new("ShaderNodeBsdfPrincipled")
        gl.inputs["Base Color"].default_value = (0.004, 0.004, 0.004, 1)
        gl.inputs["Roughness"].default_value = 0.32
        add = nt.nodes.new("ShaderNodeAddShader")
        nt.links.new(em.outputs[0], add.inputs[0])
        nt.links.new(gl.outputs[0], add.inputs[1])
        nt.links.new(add.outputs[0], out.inputs["Surface"])
    else:
        nt.links.new(em.outputs[0], out.inputs["Surface"])
    return m


def wood(name):
    m = principled(name, (0.07, 0.045, 0.032), 0.34, **{"Coat Weight": 0.25, "Coat Roughness": 0.12})
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    co = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (1.2, 14.0, 1.0)
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 6.0
    nz.inputs["Detail"].default_value = 8.0
    nz.inputs["Roughness"].default_value = 0.62
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.35
    ramp.color_ramp.elements[0].color = (0.035, 0.022, 0.016, 1)
    ramp.color_ramp.elements[1].position = 0.72
    ramp.color_ramp.elements[1].color = (0.105, 0.066, 0.045, 1)
    nt.links.new(co.outputs["Object"], mp.inputs["Vector"])
    nt.links.new(mp.outputs["Vector"], nz.inputs["Vector"])
    nt.links.new(nz.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
    return m


# --------------------------------------------------------------------------------------------- meshes
class Mesh:
    def __init__(self, name):
        self.name, self.v, self.f, self.mat, self.uv, self.mats, self.smooth = name, [], [], [], [], [], []

    def slot(self, material):
        if material not in self.mats:
            self.mats.append(material)
        return self.mats.index(material)

    def strip(self, side, pts, material, x1=GLASS_END, uv=False, smooth=False, z0=0.0):
        """Extrude an open (z', y) polyline along a facet, from the mitre at the seam to x1."""
        pts = np.asarray(pts, float)
        base = len(self.v)
        arc = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))])
        for (zp, yr) in pts:
            self.v.append(facet(side, mitre(zp), zp, yr, z0))
            self.v.append(facet(side, x1, zp, yr, z0))
        for i in range(len(pts) - 1):
            a, b, c, d = base + 2 * i, base + 2 * i + 1, base + 2 * i + 3, base + 2 * i + 2
            self.f.append((a, b, c, d))
            self.mat.append(self.slot(material))
            self.smooth.append(smooth)
            u0, u1 = arc[i] / 1000.0, arc[i + 1] / 1000.0
            self.uv.append([(u0, 0.0), (u0, x1 / 1000.0), (u1, x1 / 1000.0), (u1, 0.0)] if uv else [(0, 0)] * 4)

    def cap(self, side, poly, material, xp, z0=0.0):
        """A flat end plate with outline `poly` (z', y) at distance xp along a facet."""
        base = len(self.v)
        for (zp, yr) in poly:
            self.v.append(facet(side, xp, zp, yr, z0))
        self.f.append(tuple(range(base, base + len(poly))))
        self.mat.append(self.slot(material))
        self.smooth.append(False)
        self.uv.append([(0, 0)] * len(poly))

    def quad(self, corners, material, uvs):
        base = len(self.v)
        self.v.extend(corners)
        self.f.append((base, base + 1, base + 2, base + 3))
        self.mat.append(self.slot(material))
        self.smooth.append(False)
        self.uv.append(uvs)

    def build(self, collection):
        me = bpy.data.meshes.new(self.name)
        me.from_pydata([tuple(v) for v in self.v], [], self.f)
        layer = me.uv_layers.new(name="UVMap")
        k = 0
        for poly, uvs in zip(me.polygons, self.uv):
            for j in range(poly.loop_total):
                layer.data[k].uv = uvs[j]
                k += 1
        for m in self.mats:
            me.materials.append(m)
        for poly, mi, sm in zip(me.polygons, self.mat, self.smooth):
            poly.material_index = mi
            poly.use_smooth = sm
        me.update()
        ob = bpy.data.objects.new(self.name, me)
        collection.objects.link(ob)
        return ob


def ribbon_optics(col, mats, band_image, z0):
    """Sill, mirrors, cove and feed-row emitters for both facets, from the study's cross-section."""
    sc = D.sill(**PRESET, **FINISH)
    seg = {lab: (sc.a[i], sc.b[i]) for i, lab in enumerate(sc.labels) if lab not in ("cove",)}
    cove = np.array(sc.meta["cove"])                      # back end ... front end
    h, d, chin = PRESET["h"], sc.meta["slot"], D.CHIN
    bev_a, bev_b = seg["sill bevel"]                      # (0, y_s) -> (z_out, y_f)
    z_out, y_exit = bev_b[0], -chin
    # the cove and the stand are one brushed part: cove, nose, raked wall, foot on the base deck
    lower = stand_wall(cove)
    front_face = np.vstack([cove, lower])
    back_pt, front_pt = cove[0], cove[-1]
    rear_top, rear_foot = np.array([REAR_Z, -chin]), np.array([REAR_Z, DECK_Y])

    shell, mirror, cov, dark = Mesh("ribbon_sill"), Mesh("ribbon_mirrors"), Mesh("ribbon_cove"), Mesh("ribbon_dark")
    bands = []
    for side in (1, -1):
        shell.strip(side, [bev_a, bev_b, (z_out, y_exit)], mats["sill"], z0=z0)
        dark.strip(side, [(z_out, y_exit), (d, y_exit)], mats["black"], z0=z0)
        mirror.strip(side, [(d, y_exit), (d, 0.0), (0.0, h)], mats["mirror"], z0=z0)
        cov.strip(side, front_face, mats["cove"], uv=True, smooth=True, z0=z0)
        dark.strip(side, [(back_pt[0], -chin), back_pt], mats["black"], z0=z0)
        shell.strip(side, [rear_foot, rear_top], mats["titanium"], z0=z0)       # back of the stand
        # outer end: one cheek closes the sill, the slot and the channel between sill and cove
        cheek = [bev_a, bev_b, (z_out, y_exit), tuple(front_pt)] + [tuple(p) for p in lower] + [tuple(rear_foot), tuple(rear_top), (0.0, -chin), (0.0, 0.0)]
        dark.cap(side, cheek, mats["black"], GLASS_END - 0.4, z0=z0)
        shell.cap(side, cheek, mats["titanium"], GLASS_END, z0=z0)
        # the hidden feed rows: an emitter 0.05 mm in front of the panel face
        bm = Mesh(f"ribbon_band_{'r' if side > 0 else 'l'}")
        u0, u1 = (0.5, 1.0) if side > 0 else (0.5, 0.0)
        bm.quad([facet(side, ACTIVE[0], 0.05, 0.0, z0), facet(side, ACTIVE[1], 0.05, 0.0, z0),
                 facet(side, ACTIVE[1], 0.05, h, z0), facet(side, ACTIVE[0], 0.05, h, z0)], mats["band"],
                [(u0, 0.0), (u1, 0.0), (u1, 1.0), (u0, 1.0)])
        bands.append(bm.build(col))
    obs = [m.build(col) for m in (shell, mirror, cov, dark)]
    return obs, bands, dict(cove_mid=cove[len(cove) // 2].tolist(), z_out=float(z_out), hidden=float(sc.meta["hidden_mm"]),
                            stand=[[float(a), float(b)] for a, b in lower])


# --------------------------------------------------------------------------------------------- station
def load_station(col, mats, out_dir):
    bpy.ops.import_scene.gltf(filepath=str(STATION / "station.glb"))
    scene = json.loads((STATION / "scene.json").read_text())
    pose = scene["poses"]["work"]
    screen = None
    for ob in [o for o in bpy.data.objects if o.type == "MESH"]:
        if ob.get("internal") or ob.name in ("neck_light", "neck_badge", "base_glow"):
            bpy.data.objects.remove(ob, do_unlink=True)        # internals are enclosed; the amber LEDs are off
            continue
        grp = ob.get("group", "")
        if grp in pose and "t" in pose[grp]:
            tx, ty, tz = pose[grp]["t"]
            ob.location += Vector((tx, -tz, ty))
        key = ob.get("material", "")
        if key == "screen":
            screen = ob
            ob.data.materials.clear()
            ob.data.materials.append(mats["screen"])
        elif key in mats:
            ob.data.materials.clear()
            ob.data.materials.append(mats[key])
        for p in ob.data.polygons:
            p.use_smooth = True
    return screen


def screen_plane(screen):
    """How far the active surface sits in front of the nominal seam plane (mm), measured on the mesh."""
    n = Vector((-math.sin(TOE), -math.cos(TOE), 0.0))          # right facet normal in Blender axes (toward user)
    s0 = app(0, 0, SEAM_Z)
    zs = [(screen.matrix_world @ v.co - s0).dot(n) * 1000 for v in screen.data.vertices if (screen.matrix_world @ v.co).x > 0.05]
    return float(np.percentile(zs, 98))                        # the mesh is a thin solid: take its front face


def room(col, mats):
    def slab(name, lo, hi, mat):
        bpy.ops.mesh.primitive_cube_add(size=1)
        ob = bpy.context.active_object
        ob.name = name
        lo, hi = Vector(lo), Vector(hi)
        ob.scale = hi - lo
        ob.location = (lo + hi) / 2
        ob.data.materials.append(mat)
        return ob

    slab("desk", (-1.05, -0.62, -0.035), (1.25, 0.34, 0.0), mats["desk"])
    slab("wall_back", (-3.0, 0.36, -0.75), (3.0, 0.40, 2.0), mats["wall"])
    slab("floor", (-3.0, -4.0, -0.80), (3.0, 0.40, -0.75), mats["floor"])
    slab("ceiling", (-3.0, -4.0, 2.0), (3.0, 0.40, 2.05), mats["ceiling"])
    slab("wall_left", (-3.05, -4.0, -0.75), (-3.0, 0.40, 2.0), mats["wall"])
    slab("wall_right", (3.0, -4.0, -0.75), (3.05, 0.40, 2.0), mats["wall"])
    slab("wall_front", (-3.0, -4.05, -0.75), (3.0, -4.0, 2.0), mats["wall"])

    def area(name, loc, target, size, power, colour):
        ld = bpy.data.lights.new(name, "AREA")
        ld.shape = "RECTANGLE"
        ld.size, ld.size_y = size
        ld.energy = power
        ld.color = colour
        ob = bpy.data.objects.new(name, ld)
        ob.location = loc
        ob.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        col.objects.link(ob)
        ob.lightgroup = "room"
        return ob

    area("window", (-2.9, -1.3, 0.75), (0.2, -0.3, 0.1), (1.3, 1.5), 900.0, (1.0, 0.86, 0.70))
    area("ceiling_fill", (0.3, -1.6, 1.95), (0.3, -1.6, 0.0), (2.6, 2.6), 260.0, (1.0, 0.93, 0.85))
    # low sun through a window with glazing bars: a warm patch on the wall to the left of the station
    sd = bpy.data.lights.new("sun_patch", "SPOT")
    sd.energy, sd.color, sd.spot_size, sd.spot_blend, sd.shadow_soft_size = 9000.0, (1.0, 0.70, 0.44), math.radians(21), 0.06, 0.02
    sun = bpy.data.objects.new("sun_patch", sd)
    sun.location = (-2.75, -2.3, 1.75)
    aim = Vector((-1.22, 0.36, 0.86))
    sun.rotation_euler = (aim - sun.location).to_track_quat("-Z", "Y").to_euler()
    col.objects.link(sun)
    sun.lightgroup = "room"
    axis = (aim - sun.location).normalized()
    centre = sun.location + axis * 0.9
    right = axis.cross(Vector((0, 0, 1))).normalized()
    up = right.cross(axis).normalized()
    for k, (du, dv, w, h) in enumerate(((0.0, 0.0, 0.02, 0.5), (-0.085, 0.0, 0.014, 0.5), (0.085, 0.0, 0.014, 0.5),
                                         (0.0, 0.0, 0.5, 0.02), (0.0, 0.11, 0.5, 0.014), (0.0, -0.11, 0.5, 0.014))):
        bpy.ops.mesh.primitive_plane_add(size=1)
        bar = bpy.context.active_object
        bar.name = f"glazing_bar_{k}"
        bar.scale = (w, h, 1)
        bar.location = centre + right * du + up * dv
        bar.rotation_euler = (-axis).to_track_quat("Z", "Y").to_euler()
        bar.data.materials.append(mats["black"])
        bar.visible_camera = False


VIEWS = {
    # name: eye (app mm), look-at (app mm), focal length mm (36 mm sensor width), aspect
    "hero": ((0, 800, 1480), (55, 185, 60), 30.0, 2.0),        # over the shoulder, on the seat's sight line
    "seat": ((0, 452, 588), (30, 215, -30), 14.0, 2.0),        # the seated eye itself, wide lens
    "detail": ((-250, 500, 620), (-170, 135, -10), 50.0, 1.78),  # sill, slot and cove, left of the seam
    "front": ((0, 330, 1750), (55, 215, 0), 40.0, 2.37),       # low and frontal, like the concept picture
    "calib": ((0, 452, 588), (295.4, 127, -9.9), 60.0, 1.5),    # seat eye, aimed at the ribbon 300 mm along the right panel
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--view", default="hero", choices=list(VIEWS) + ["probe"])
    ap.add_argument("--out", required=True)
    ap.add_argument("--samples", type=int, default=600)
    ap.add_argument("--width", type=int, default=2400)
    ap.add_argument("--band", default="band.png")
    ap.add_argument("--tag", default="")
    ap.add_argument("--export", help="write the station with the ribbon optics as a GLB (for the 3D viewer) and stop")
    a = ap.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else None)
    out = Path(a.out)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    scn = bpy.context.scene
    col = scn.collection
    vl = bpy.context.view_layer
    for g in ("band", "screen", "room"):
        vl.lightgroups.add(name=g)

    f0 = (0.62, 0.58, 0.52)
    mats = dict(
        titanium=principled("titanium", (0.60, 0.565, 0.52), 0.34, 1.0),
        graphite=principled("graphite", (0.032, 0.030, 0.029), 0.55),
        glass_black=principled("glass_black", (0.004, 0.004, 0.004), 0.10),
        oxblood=principled("oxblood", (0.20, 0.028, 0.034), 0.38),
        keycap=principled("keycap", (0.028, 0.027, 0.027), 0.50),
        rubber=principled("rubber", (0.012, 0.012, 0.012), 0.85),
        laptop_alu=principled("laptop_alu", (0.74, 0.74, 0.75), 0.36, 1.0),
        felt=principled("felt", (0.045, 0.045, 0.05), 1.0),
        steel=principled("steel", (0.55, 0.55, 0.56), 0.40, 1.0),
        amber_led=principled("amber_led_off", (0.03, 0.02, 0.012), 0.30),
        black=principled("matte_black", (0.03, 0.03, 0.03), 0.95),
        # the sill's outside is dark satin, like the panel's own chin: a bright bevel right above the ribbon
        # would compete with it
        sill=principled("sill_graphite", (0.030, 0.028, 0.027), 0.42),
        mirror=principled("mirror", (D.MIRROR_R,) * 3, 0.0, 1.0),
        cove=brushed("cove_brushed", f0, FINISH["ax"], FINISH["at"]),
        desk=wood("desk_wood"),
        wall=principled("wall", (0.60, 0.54, 0.47), 0.92),
        floor=principled("floor", (0.16, 0.12, 0.09), 0.6),
        ceiling=principled("ceiling", (0.80, 0.78, 0.74), 0.95),
        screen=emitter("screen", out / "screen.png", reflect=True),
        band=emitter("band", out / a.band),
    )
    screen = load_station(col, mats, out)
    z0 = screen_plane(screen)
    optics, bands, info = ribbon_optics(col, mats, a.band, z0)
    info["screen_z0_mm"] = z0
    if a.export:
        # geometry only: the viewer assigns its own materials by name (Y-up, metres, like station.glb)
        (Path(a.export).with_suffix(".json")).write_text(json.dumps(info))
        bpy.ops.export_scene.gltf(filepath=a.export, export_format="GLB", export_yup=True, export_apply=True,
                                  export_texcoords=True, export_normals=True, export_materials="EXPORT",
                                  export_image_format="NONE", export_extras=True)
        print("wrote", a.export)
        return
    room(col, mats)
    screen.lightgroup = "screen"
    for b in bands:
        b.lightgroup = "band"
    info["screen_z0_mm"] = z0

    if a.view == "probe":
        # a white card flat on the desk, seen from straight above: its radiance x pi is the illuminance
        bpy.ops.mesh.primitive_plane_add(size=0.12, location=app(-90, 4.0, 520))
        card = bpy.context.active_object
        card.data.materials.append(principled("card", (1.0, 1.0, 1.0), 1.0, **{"Specular IOR Level": 0.0}))
        cd = bpy.data.cameras.new("cam")
        cd.type = "ORTHO"
        cd.ortho_scale = 0.08
        cam = bpy.data.objects.new("cam", cd)
        cam.location = app(-90, 600, 520)
        col.objects.link(cam)
        scn.render.resolution_x = scn.render.resolution_y = 64
    else:
        eye, look, focal, aspect = VIEWS[a.view]
        cd = bpy.data.cameras.new("cam")
        cd.lens = focal
        cd.sensor_width = 36.0
        cd.clip_start, cd.clip_end = 0.05, 30.0
        cam = bpy.data.objects.new("cam", cd)
        cam.location = app(*eye)
        cam.rotation_euler = (app(*look) - app(*eye)).to_track_quat("-Z", "Y").to_euler()
        col.objects.link(cam)
        scn.render.resolution_x = a.width
        scn.render.resolution_y = int(round(a.width / aspect / 2)) * 2
    scn.camera = cam
    scn.render.resolution_percentage = 100

    scn.render.engine = "CYCLES"
    c = scn.cycles
    c.device = "CPU"
    c.samples = a.samples
    c.use_adaptive_sampling = True
    c.adaptive_threshold = 0.01
    c.use_denoising = False                               # develop.py denoises each light group itself
    c.max_bounces, c.diffuse_bounces, c.glossy_bounces, c.transmission_bounces = 12, 5, 10, 0
    c.caustics_reflective = True
    c.blur_glossy = 0.0
    c.sample_clamp_direct = 0.0
    c.sample_clamp_indirect = 0.0
    vl.cycles.denoising_store_passes = True
    scn.world = bpy.data.worlds.new("world")
    scn.world.use_nodes = True
    scn.world.node_tree.nodes["Background"].inputs["Color"].default_value = (0, 0, 0, 1)
    scn.view_settings.view_transform = "Raw"
    scn.render.image_settings.media_type = "MULTI_LAYER_IMAGE"      # Blender 5: multilayer EXR is its own media type
    scn.render.image_settings.file_format = "OPEN_EXR_MULTILAYER"
    scn.render.image_settings.color_depth = "32"
    scn.render.image_settings.exr_codec = "ZIP"
    scn.render.filepath = str(out / f"{a.view}{a.tag}.exr")
    scn.render.threads_mode = "AUTO"
    (out / f"{a.view}{a.tag}.json").write_text(json.dumps(dict(view=a.view, samples=a.samples, info=info)))
    bpy.ops.render.render(write_still=True)
    print("wrote", scn.render.filepath)


if __name__ == "__main__":
    main()
