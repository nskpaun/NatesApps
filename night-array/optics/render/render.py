"""Path-traced renders of the light ribbon on the Night Array station (Blender Cycles).

    pip install bpy==5.2.3 pillow        # Blender as a Python module (Python 3.13)
    python render.py hero                # one shot  -> out/hero.png
    python render.py all --scale 0.5     # every shot at half resolution
    python render.py --list

The geometry is the station's own CAD (cad/export/model/station.glb) plus the ribbon optics that
optics/run.py validated: a light band in the screen's bottom 12 mm, an off-axis parabolic
reflector (f = 20 mm, beam 15 deg behind vertical), mirror film on the chin, and a satin titanium
ramp rising 32 deg toward the back. The reflector, ramp and cove follow each panel's 10 deg
toe-in. All ribbon light in these images comes from the screen pixels through that geometry;
nothing is faked with extra lights.

Concept changes for the render: the base is rebuilt 60 mm deeper with the charging pockets moved
forward to make room for the cove, and the neck light bar is removed (it would sit inside the cove).

Radiometric scale: 1.0 scene unit = 350 cd/m^2 (the panel's full white). Room light is set in lux.
"""
from __future__ import annotations

import argparse
import math
import os
import sys
import time

import bpy
import bmesh
import numpy as np
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
from screen import screen_image, W as SW, H as SH  # noqa: E402
from ribbon.scene import Design, reflector_points  # noqa: E402

GLB = os.path.normpath(os.path.join(HERE, "..", "..", "cad", "export", "model", "station.glb"))
OUT = os.path.join(HERE, "out")
NITS = 350.0                       # cd/m^2 per scene radiance unit
T10, C10, S10 = math.tan(math.radians(10)), math.cos(math.radians(10)), math.sin(math.radians(10))
FACET_LEN = 612.0                  # mm from the seam to the glass edge along each facet

PARA = Design(reflector="parabolic", refl_psi=15, refl_f=20, refl_theta_min=-55, chin_finish="mirror",
              ramp_deg=32, band_h=12)
RAMP_TOP = PARA.floor_y + (PARA.cove_front_z - PARA.cove_back_z) * math.tan(math.radians(PARA.ramp_deg))
D_FRONT = PARA.cove_front_z + 62.0      # +42: ramp foot / lip, measured out from the glass
D_BACK = PARA.cove_back_z + 62.0        # -78: back wall


# ------------------------------------------------------------------ materials
def principled(name, color, rough, metal=0.0, spec=0.5, coat=0.0, aniso=0.0, sheen=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    b.inputs["Specular IOR Level"].default_value = spec
    if coat:
        b.inputs["Coat Weight"].default_value = coat
        b.inputs["Coat Roughness"].default_value = 0.08
    if aniso:
        b.inputs["Anisotropic"].default_value = aniso
    if sheen:
        b.inputs["Sheen Weight"].default_value = sheen
    return m


def emissive(name, color, strength):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    e = nt.nodes.new("ShaderNodeEmission")
    e.inputs["Color"].default_value = (*color, 1)
    e.inputs["Strength"].default_value = strength
    o = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(e.outputs[0], o.inputs[0])
    return m


def screen_material(img):
    """Emission from the canvas (scene units: 1.0 = full white) plus the panel's anti-glare surface."""
    m = bpy.data.materials.new("screen_rt")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    tex = nt.nodes.new("ShaderNodeTexImage"); tex.image = img; tex.interpolation = "Closest"
    em = nt.nodes.new("ShaderNodeEmission"); em.inputs["Strength"].default_value = 1.0
    gl = nt.nodes.new("ShaderNodeBsdfPrincipled")
    gl.inputs["Base Color"].default_value = (0.004, 0.004, 0.005, 1)
    gl.inputs["Roughness"].default_value = 0.32
    add = nt.nodes.new("ShaderNodeAddShader")
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(tex.outputs["Color"], em.inputs["Color"])
    nt.links.new(em.outputs[0], add.inputs[0]); nt.links.new(gl.outputs[0], add.inputs[1])
    nt.links.new(add.outputs[0], out.inputs[0])
    return m


def walnut():
    m = bpy.data.materials.new("walnut")
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Roughness"].default_value = 0.42
    b.inputs["Coat Weight"].default_value = 0.25
    b.inputs["Coat Roughness"].default_value = 0.2
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping"); mp.inputs["Scale"].default_value = (1.0, 22.0, 1.0)
    wave = nt.nodes.new("ShaderNodeTexWave"); wave.wave_type = "BANDS"; wave.bands_direction = "X"
    wave.inputs["Scale"].default_value = 3.0; wave.inputs["Distortion"].default_value = 9.0
    wave.inputs["Detail"].default_value = 4.0; wave.inputs["Detail Roughness"].default_value = 0.7
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.035, 0.018, 0.010, 1)
    ramp.color_ramp.elements[1].color = (0.11, 0.058, 0.030, 1)
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    nt.links.new(mp.outputs["Vector"], wave.inputs["Vector"])
    nt.links.new(wave.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
    return m


def make_materials(img):
    M = {
        "titanium": principled("titanium", (0.56, 0.53, 0.50), 0.32, metal=1.0, aniso=0.4),
        "graphite": principled("graphite", (0.030, 0.030, 0.032), 0.45),
        "glass_black": principled("glass_black", (0.004, 0.004, 0.005), 0.04, spec=0.5),
        "steel": principled("steel", (0.55, 0.55, 0.56), 0.35, metal=1.0),
        "oxblood": principled("oxblood", (0.22, 0.025, 0.04), 0.33, metal=0.6, coat=0.3),
        "laptop_alu": principled("laptop_alu", (0.70, 0.70, 0.71), 0.28, metal=1.0),
        "keycap": principled("keycap", (0.05, 0.05, 0.055), 0.55),
        "felt": principled("felt", (0.10, 0.10, 0.105), 1.0, spec=0.2, sheen=0.6),
        "rubber": principled("rubber", (0.02, 0.02, 0.02), 0.8),
        "pcb": principled("pcb", (0.02, 0.08, 0.03), 0.5),
        "copper": principled("copper", (0.80, 0.45, 0.30), 0.3, metal=1.0),
        "ferrite": principled("ferrite", (0.03, 0.03, 0.03), 0.7),
        "amber_led": emissive("amber_led", (1.0, 0.42, 0.08), 2.5),
        "screen": screen_material(img),
        # ribbon optics, matching the validated design
        "mirror": principled("mirror", (0.92, 0.92, 0.93), 0.015, metal=1.0),
        # satin titanium: F0 ~0.55, GGX alpha 0.25 -> Blender roughness sqrt(0.25) = 0.5
        "satin_ramp": principled("satin_ramp", (0.55, 0.53, 0.50), 0.5, metal=1.0),
        "black_matte": principled("black_matte", (0.012, 0.012, 0.013), 0.9, spec=0.2),
        "walnut": walnut(),
        "plaster": principled("plaster", (0.62, 0.60, 0.57), 0.9, spec=0.3),
        "blind": principled("blind", (0.75, 0.73, 0.70), 0.6),
    }
    return M


# ------------------------------------------------------------------ geometry helpers
def app_to_b(x, y, z):
    """App axes mm (+Y up, +Z to the user) -> Blender metres (+Z up, -Y to the user)."""
    return Vector((x / 1000.0, -z / 1000.0, y / 1000.0))


def facet_point(side, s, d, y):
    """Point on a panel facet. side -1 left / +1 right; s mm along the facet from the seam;
    d mm out from the glass toward the user; y mm above the desk."""
    o = Vector((0.0, 0.062, 0.0))
    u = Vector((side * C10, -S10, 0.0))
    n = Vector((-side * S10, -C10, 0.0))
    return o + u * (s / 1000) + n * (d / 1000) + Vector((0, 0, y / 1000))


def facet_mesh(name, profile, closed, mats, s_end=FACET_LEN, mitre=True, s_start=None):
    """Extrude a (d, y) mm profile along both facets, mitred at the seam (x = 0)."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    for side in (-1, 1):
        a, b = [], []
        for d, y in profile:
            s0 = d * T10 if mitre else (s_start if s_start is not None else 0.0)
            a.append(bm.verts.new(facet_point(side, s0, d, y)))
            b.append(bm.verts.new(facet_point(side, s_end, d, y)))
        n = len(profile)
        rng = range(n) if closed else range(n - 1)
        for i in rng:
            j = (i + 1) % n
            f = bm.faces.new((a[i], a[j], b[j], b[i]) if side < 0 else (a[i], b[i], b[j], a[j]))
        if closed:
            bm.faces.new(a if side > 0 else a[::-1])
            bm.faces.new(b[::-1] if side > 0 else b)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces) if closed else None
    bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    for m in mats:
        me.materials.append(m)
    return ob


def facet_frame(c):
    side = 1.0 if c.x >= 0 else -1.0
    n = Vector((-side * S10, -C10, 0.0))
    d = (c - Vector((0.0, 0.062, c.z))).dot(n)
    return n, d


def orient_sheet(ob, toward):
    """Flip a sheet's normals so they face `toward` (a function of a face centre -> Vector)."""
    me = ob.data
    bm = bmesh.new(); bm.from_mesh(me)
    for f in bm.faces:
        c = f.calc_center_median()
        if f.normal.dot(toward(c) - c) < 0:
            f.normal_flip()
    bm.to_mesh(me); bm.free()


def solidify(ob, t, offset=-1.0, mat_offset=0, rim_offset=0):
    md = ob.modifiers.new("solid", "SOLIDIFY")
    md.thickness = t; md.offset = offset
    md.material_offset = mat_offset; md.material_offset_rim = rim_offset
    md.use_even_offset = True
    return md


def rounded_box(name, x0, x1, y0, y1, z0, z1, r, mat):
    bpy.ops.mesh.primitive_cube_add(size=1)
    ob = bpy.context.object; ob.name = name
    ob.scale = ((x1 - x0), (y1 - y0), (z1 - z0))
    ob.location = ((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)
    bpy.ops.object.transform_apply(scale=True)
    if r:
        bv = ob.modifiers.new("bevel", "BEVEL"); bv.width = r; bv.segments = 6; bv.limit_method = "ANGLE"
    ob.data.materials.append(mat)
    return ob


def boolean(target, cutter, op="DIFFERENCE"):
    md = target.modifiers.new("bool", "BOOLEAN")
    md.operation = op; md.object = cutter; md.solver = "EXACT"
    md.material_mode = "TRANSFER"
    bpy.context.view_layer.objects.active = target
    bpy.ops.object.modifier_apply(modifier=md.name)
    bpy.data.objects.remove(cutter)


# ------------------------------------------------------------------ scene
INTERNAL = ("compute_", "psu", "qi_coil", "ferrite", "dock_board", "display_boards", "display_spine",
            "keyboard_coil", "mouse_coil")
REPLACED = ("base_shell", "deck_liner", "tray_pad_kb", "tray_pad_mouse", "base_feet", "neck_light", "base_glow",
            "kb_charge_led", "mouse_charge_led")


def build(mode="concept", t=0.0, room="evening", lux=None, refl_f=20.0):
    global PARA
    PARA = PARA.with_(refl_f=refl_f)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    arr = screen_image(mode, t)
    img = bpy.data.images.new("canvas", SW, SH, float_buffer=True)
    img.colorspace_settings.name = "Linear Rec.709"
    rgba = np.concatenate([arr[::-1], np.ones((SH, SW, 1), np.float32)], -1)
    img.pixels.foreach_set(rgba.ravel())
    img.pack()
    M = make_materials(img)

    bpy.ops.import_scene.gltf(filepath=GLB)
    for ob in list(bpy.data.objects):
        if ob.type != "MESH":
            continue
        if ob.name.startswith(INTERNAL) or ob.name in REPLACED:
            bpy.data.objects.remove(ob)
            continue
        for i, slot in enumerate(ob.material_slots):
            nm = slot.material.name.split(".")[0] if slot.material else ""
            if nm in M:
                ob.material_slots[i].material = M[nm]
        if ob.name.startswith(("keyboard", "mouse")):          # work pose (scene.json "work")
            ob.location += Vector((0.04 if ob.name.startswith("mouse") else 0.0, -0.298, -0.015))
    for ob in list(bpy.data.objects):
        if ob.type == "MESH":
            bpy.context.view_layer.objects.active = ob
            for p in ob.data.polygons:
                p.use_smooth = False

    # --- rebuilt base: 60 mm deeper, pockets moved forward 60 mm, cove trench cut along the facets
    base = rounded_box("base", -0.640, 0.650, -0.210, 0.150, 0.0, 0.036, 0.004, M["titanium"])
    for (cx, w, d_) in ((-0.090, 0.376, 0.136), (0.250, 0.082, 0.134)):
        cz = 0.122
        c = rounded_box("pocket", cx - w / 2, cx + w / 2, -cz - d_ / 2, -cz + d_ / 2, 0.016, 0.06, 0.0, M["graphite"])
        boolean(base, c)
        rounded_box("pad", cx - w / 2 + 0.001, cx + w / 2 - 0.001, -cz - d_ / 2 + 0.001, -cz + d_ / 2 - 0.001,
                    0.016, 0.018, 0.0, M["graphite"])
    slope = math.tan(math.radians(PARA.ramp_deg))
    cut = facet_mesh("trench", [(D_FRONT + 1, PARA.floor_y - 1), (D_FRONT + 1, 70), (-20, 70),
                                (-20, PARA.floor_y - 1 + (D_FRONT + 21) * slope)], True, [M["satin_ramp"]],
                     s_end=FACET_LEN - 0.5)
    boolean(base, cut)
    rounded_box("feet", -0.60, 0.61, -0.18, 0.12, -0.0005, 0.0015, 0.0, M["rubber"])

    # --- ribbon optics
    rp = reflector_points(PARA, 172.0, 172.0 + PARA.band_h)
    refl = facet_mesh("reflector", [(z + 62.0, y) for z, y in rp], False, [M["mirror"], M["graphite"]])
    focus_y = 172.0 + PARA.band_h / 2
    def to_focus(c):
        n, d = facet_frame(c)
        f = c - n * d
        return Vector((f.x, f.y, focus_y / 1000))
    orient_sheet(refl, to_focus)
    solidify(refl, 0.0015, offset=-1.0, mat_offset=1, rim_offset=1)

    chin = facet_mesh("chin_mirror", [(0.6, 171.5), (0.6, 156.5)], False, [M["mirror"]])
    orient_sheet(chin, lambda c: c + facet_frame(c)[0])

    ramp = facet_mesh("ramp", [(D_BACK, RAMP_TOP), (D_FRONT, PARA.floor_y)], False, [M["satin_ramp"]])
    orient_sheet(ramp, lambda c: c + Vector((0, -1, 2)))
    solidify(ramp, 0.002, offset=-1.0)
    back = facet_mesh("back_wall", [(D_BACK, 154.0), (D_BACK, RAMP_TOP - 1)], False, [M["black_matte"]])
    solidify(back, 0.002, offset=0.0)
    under = facet_mesh("display_underside", [(D_BACK - 2, 153.5), (-1.0, 153.5)], False, [M["black_matte"]])
    solidify(under, 0.002, offset=0.0)
    facet_mesh("front_lip", [(D_FRONT, PARA.floor_y - 2), (D_FRONT + 12, PARA.floor_y - 2),
                             (D_FRONT + 12, 40.0), (D_FRONT, 40.0)], True, [M["graphite"]])
    # end caps that close each end of the cove
    cap_prof = [(D_BACK - 2, 156.0), (-1.0, 156.0)] + [(z + 62.0, y) for z, y in rp[::4]] + \
               [(D_FRONT + 12, 40.0), (D_FRONT + 12, PARA.floor_y - 2), (D_BACK - 2, PARA.floor_y - 2)]
    facet_mesh("end_caps", cap_prof, True, [M["graphite"]], mitre=False, s_start=FACET_LEN, s_end=FACET_LEN + 3)

    # --- room
    desk = rounded_box("desk", -1.5, 1.5, -0.85, 0.45, -0.04, 0.0, 0.003, M["walnut"])
    wall = rounded_box("wall", -3.0, 3.0, 0.62, 0.66, -0.9, 2.2, 0.0, M["plaster"])
    lwall = rounded_box("left_wall", -2.2, -2.16, -3.0, 0.66, -0.9, 2.2, 0.0, M["plaster"])
    win = rounded_box("window_cut", -2.3, -2.0, -1.6, -0.2, 0.25, 1.5, 0.0, M["plaster"])
    boolean(lwall, win)
    for i in range(16):                                  # blinds, tilted: they stripe the light
        z = 0.28 + i * 0.075
        sl = rounded_box(f"slat{i}", -2.19, -2.17, -1.6, -0.2, z, z + 0.004, 0.0, M["blind"])
        sl.rotation_euler = (math.radians(30), 0, 0)
    floor = rounded_box("floor", -3, 3, -3, 0.66, -0.76, -0.74, 0.0, M["plaster"])

    world = bpy.data.worlds.new("room"); bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    sc = bpy.context.scene
    if room == "evening":
        L = (lux or 30) / math.pi / NITS
        bg.inputs["Color"].default_value = (1.0, 0.86, 0.72, 1); bg.inputs["Strength"].default_value = L
        lamp = bpy.data.lights.new("lamp", "AREA"); lamp.shape = "DISK"; lamp.size = 0.35
        lamp.energy = 3.5; lamp.color = (1.0, 0.72, 0.45)
        lo = bpy.data.objects.new("lamp", lamp); sc.collection.objects.link(lo)
        lo.location = (1.6, -0.3, 1.4); lo.rotation_euler = (math.radians(50), math.radians(40), 0)
    else:  # daylight through the window
        E = lux or 5000
        bg.inputs["Color"].default_value = (0.85, 0.9, 1.0, 1); bg.inputs["Strength"].default_value = E * 0.25 / math.pi / NITS
        sun = bpy.data.lights.new("sun", "SUN"); sun.energy = E / NITS; sun.angle = math.radians(1.5)
        sun.color = (1.0, 0.94, 0.86)
        so = bpy.data.objects.new("sun", sun); sc.collection.objects.link(so)
        so.rotation_euler = Vector((2.2, 1.52, -0.45)).to_track_quat("-Z", "Y").to_euler()
        # window light: a big soft area in the opening
        sky = bpy.data.lights.new("sky", "AREA"); sky.shape = "RECTANGLE"; sky.size = 1.4; sky.size_y = 1.2
        sky.energy = E / NITS * 6; sky.color = (0.85, 0.92, 1.0)
        ko = bpy.data.objects.new("sky", sky); sc.collection.objects.link(ko)
        ko.location = (-2.12, -0.9, 0.9); ko.rotation_euler = (0, math.radians(-90), 0)
    return M


SHOTS = {
    # name: camera location, look-at, lens mm, size, extra
    "hero": dict(loc=(-0.80, -1.30, 0.80), at=(0.0, 0.0, 0.17), lens=34, size=(1920, 1080), room="evening"),
    "hero_open": dict(loc=(-0.80, -1.30, 0.80), at=(0.0, 0.0, 0.17), lens=34, size=(1920, 1080), room="evening", f=12.0),
    "seated_open": dict(loc=(0.0, -0.65, 0.46), at=(0.0, 0.03, 0.2), lens=30, size=(1920, 1080), room="evening", f=12.0),
    "seated": dict(loc=(0.0, -0.65, 0.46), at=(0.0, 0.03, 0.2), lens=30, size=(1920, 1080), room="evening"),
    "cove": dict(loc=(-0.50, -0.50, 0.42), at=(-0.17, 0.02, 0.08), lens=55, size=(1920, 1080), room="evening",
                 f=12.0, dof=dict(focus=(-0.20, 0.02, 0.05), fstop=2.8)),
    "office": dict(loc=(0.0, -0.65, 0.46), at=(0.0, 0.03, 0.2), lens=30, size=(1920, 1080), room="evening", lux=500, exposure=-0.2),
    "daylight": dict(loc=(-0.80, -1.30, 0.80), at=(0.0, 0.0, 0.17), lens=34, size=(1920, 1080), room="day", lux=5000),
    "bass": dict(loc=(0.0, -0.65, 0.46), at=(0.0, 0.03, 0.2), lens=30, size=(1280, 720), room="evening", f=12.0, mode="bass"),
    "treble": dict(loc=(0.0, -0.65, 0.46), at=(0.0, 0.03, 0.2), lens=30, size=(1280, 720), room="evening", f=12.0, mode="treble"),
    "dock": dict(loc=(0.0, -0.65, 0.46), at=(0.0, 0.03, 0.2), lens=30, size=(1280, 720), room="evening", f=12.0, mode="dock", t=0.62),
}


def render(name, scale=1.0, samples=384, out=OUT):
    s = SHOTS[name]
    build(s.get("mode", "concept"), s.get("t", 0.0), s["room"], s.get("lux"), s.get("f", 20.0))
    sc = bpy.context.scene
    cam = bpy.data.cameras.new("cam"); cam.lens = s["lens"]; cam.sensor_width = 36
    co = bpy.data.objects.new("cam", cam); sc.collection.objects.link(co)
    co.location = s["loc"]
    co.rotation_euler = (Vector(s["at"]) - Vector(s["loc"])).to_track_quat("-Z", "Y").to_euler()
    if "dof" in s:
        cam.dof.use_dof = True
        cam.dof.focus_distance = (Vector(s["dof"]["focus"]) - Vector(s["loc"])).length
        cam.dof.aperture_fstop = s["dof"]["fstop"]
    sc.camera = co
    sc.render.engine = "CYCLES"
    cy = sc.cycles
    cy.device = "CPU"; cy.samples = samples; cy.use_denoising = True; cy.denoiser = "OPENIMAGEDENOISE"
    cy.use_adaptive_sampling = True; cy.adaptive_threshold = 0.01
    cy.max_bounces = 10; cy.glossy_bounces = 8; cy.diffuse_bounces = 4; cy.transmission_bounces = 4
    cy.caustics_reflective = True; cy.blur_glossy = 0.0
    cy.use_light_tree = True
    sc.render.resolution_x = int(s["size"][0] * scale); sc.render.resolution_y = int(s["size"][1] * scale)
    sc.render.film_transparent = False
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Medium High Contrast"
    sc.view_settings.exposure = s.get("exposure", 0.9 if s["room"] == "evening" else -0.6)
    sc.render.image_settings.file_format = "PNG"
    os.makedirs(out, exist_ok=True)
    sc.render.filepath = os.path.join(out, f"{name}.png")
    t0 = time.time()
    bpy.ops.render.render(write_still=True)
    print(f"{name}: {time.time() - t0:.0f} s -> {sc.render.filepath}", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("shots", nargs="*", default=["hero"])
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--samples", type=int, default=384)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    if a.list:
        print("\n".join(SHOTS)); sys.exit()
    names = list(SHOTS) if a.shots == ["all"] else a.shots
    for n in names:
        render(n, a.scale, a.samples, a.out)
