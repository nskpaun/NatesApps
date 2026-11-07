"""Night Array -- parametric B-rep model (CadQuery 2.8).

Every part is built directly in app axes (+Y up, +Z toward the user, mm) and in
the STOW pose.  One function per part; PARTS lists them with group, material and
internal flag exactly as SPEC.md section 2 names them.

Display facets are modelled in a local "facet frame" (u along the panel away
from the seam, y up, w = the panel's front normal) and placed with
place_facet(): rotate -10 deg about +Y, move to the seam axis (x=0, z=-62),
trim at x = 0, mirror for the left panel.
"""

import math
from functools import lru_cache

import cadquery as cq
from cadquery import Vector

from params import P, COS_T, SIN_T

TOE = P["display"]["toe_in_deg"]
SEAM_Z = P["display"]["seam_axis_xz"][1]

# ----------------------------------------------------------------------------
# primitives
# ----------------------------------------------------------------------------


def box(x0, x1, y0, y1, z0, z1):
    return cq.Solid.makeBox(x1 - x0, y1 - y0, z1 - z0, pnt=Vector(x0, y0, z0))


def _rr(wp, w, h, r):
    if r and r > 0:
        r = min(r, 0.499 * min(w, h))
        return wp.sketch().rect(w, h).vertices().fillet(r).finalize()
    return wp.rect(w, h)


def prism_y(x0, x1, z0, z1, y0, y1, r=0.0):
    """Plan rounded rectangle extruded vertically between y0 and y1."""
    wp = cq.Workplane("XZ", origin=(0, y1, 0)).center((x0 + x1) / 2, (z0 + z1) / 2)
    return _rr(wp, x1 - x0, z1 - z0, r).extrude(y1 - y0).val()


def prism_z(x0, x1, y0, y1, z0, z1, r=0.0):
    """Front-view rounded rectangle extruded along +Z between z0 and z1."""
    wp = cq.Workplane("XY", origin=(0, 0, z0)).center((x0 + x1) / 2, (y0 + y1) / 2)
    return _rr(wp, x1 - x0, y1 - y0, r).extrude(z1 - z0).val()


def prism_x(z0, z1, y0, y1, x0, x1, r=0.0):
    """Side-view rounded rectangle extruded along X between x0 and x1."""
    wp = cq.Workplane("ZY", origin=(x1, 0, 0)).center((z0 + z1) / 2, (y0 + y1) / 2)
    return _rr(wp, z1 - z0, y1 - y0, r).extrude(x1 - x0).val()


def cyl_y(cx, cz, r, y0, y1):
    return cq.Solid.makeCylinder(r, y1 - y0, Vector(cx, y0, cz), Vector(0, 1, 0))


def cyl_x(cy, cz, r, x0, x1):
    return cq.Solid.makeCylinder(r, x1 - x0, Vector(x0, cy, cz), Vector(1, 0, 0))


def cyl_z(cx, cy, r, z0, z1):
    return cq.Solid.makeCylinder(r, z1 - z0, Vector(cx, cy, z0), Vector(0, 0, 1))


def stadium_y(cx, cz, length, width, y0, y1, along="x"):
    """Stadium (slot) in plan, extruded vertically. `length` along x or z."""
    wp = cq.Workplane("XZ", origin=(0, y1, 0)).center(cx, cz)
    ang = 0 if along == "x" else 90
    return wp.slot2D(length, width, ang).extrude(y1 - y0).val()


def stadium_z(cx, cy, length, width, z0, z1, along="x"):
    """Stadium in the front (x-y) plane, extruded along +Z."""
    wp = cq.Workplane("XY", origin=(0, 0, z0)).center(cx, cy)
    ang = 0 if along == "x" else 90
    return wp.slot2D(length, width, ang).extrude(z1 - z0).val()


def compound(shapes):
    return cq.Compound.makeCompound([s for s in shapes if s is not None])


def fuse(*shapes):
    shapes = [s for s in shapes if s is not None]
    if len(shapes) == 1:
        return shapes[0]
    r = shapes[0].fuse(*shapes[1:]).clean()
    return single(r)


def cut(a, *tools):
    tools = [t for t in tools if t is not None]
    if not tools:
        return a
    return single(a.cut(*tools).clean())


def single(shape):
    """Return the lone Solid inside a compound result, else the shape itself."""
    sols = shape.Solids()
    if len(sols) == 1:
        return sols[0]
    return shape


def edges_where(shape, pred):
    out = []
    for e in shape.Edges():
        bb = e.BoundingBox()
        c = e.Center()
        if pred(c, bb, e):
            out.append(e)
    return out


FILLET_LOG = []


def fillet(shape, r, edges, label=""):
    if not edges:
        FILLET_LOG.append(f"{label}: no edges")
        return shape
    try:
        out = shape.fillet(r, edges)
        if not out.isValid():
            raise ValueError("invalid result")
        return single(out)
    except Exception as ex:  # noqa: BLE001
        FILLET_LOG.append(f"{label}: fillet r={r} on {len(edges)} edges failed ({ex})")
        return shape


def chamfer(shape, d, edges, label=""):
    if not edges:
        FILLET_LOG.append(f"{label}: no edges")
        return shape
    try:
        out = shape.chamfer(d, None, edges)
        if not out.isValid():
            raise ValueError("invalid result")
        return single(out)
    except Exception as ex:  # noqa: BLE001
        FILLET_LOG.append(f"{label}: chamfer d={d} on {len(edges)} edges failed ({ex})")
        return shape


def near(a, b, tol=0.05):
    return abs(a - b) <= tol


def on_plane(axis, value, tol=0.05):
    """Predicate: edge lies in the plane axis = value."""
    i = "xyz".index(axis)

    def pred(c, bb, e):
        lo = (bb.xmin, bb.ymin, bb.zmin)[i]
        hi = (bb.xmax, bb.ymax, bb.zmax)[i]
        return abs(lo - value) <= tol and abs(hi - value) <= tol

    return pred


def in_box(x0, x1, y0, y1, z0, z1):
    def pred(c, bb, e):
        return (x0 - 1e-6 <= bb.xmin and bb.xmax <= x1 + 1e-6 and y0 - 1e-6 <= bb.ymin and bb.ymax <= y1 + 1e-6
                and z0 - 1e-6 <= bb.zmin and bb.zmax <= z1 + 1e-6)

    return pred


def frame_plane(origin, xdir, normal):
    return cq.Plane(origin=Vector(*origin), xDir=Vector(*xdir), normal=Vector(*normal))


def _perp(n):
    n = Vector(*n).normalized()
    a = Vector(1, 0, 0) if abs(n.x) < 0.9 else Vector(0, 1, 0)
    return n.cross(a).normalized()


def halfspace(point, normal, size=4000.0):
    """Solid filling the half-space on the +normal side of the plane through `point` (planar faces only)."""
    pl = frame_plane(point, _perp(normal).toTuple(), Vector(*normal).normalized().toTuple())
    return to_frame(box(-size, size, -size, size, 0, size), pl)


def _offset_pt(point, normal, d):
    n = Vector(*normal).normalized()
    return (Vector(*point) - n * d).toTuple()


def to_frame(shape, plane):
    """Move a shape built around the global origin (XY = face, +Z = outward) onto `plane`."""
    return shape.moved(cq.Location(plane))


# ----------------------------------------------------------------------------
# display facet helpers
# ----------------------------------------------------------------------------


def place_facet(shape, side=1, trim=True):
    s = shape.rotate(Vector(0, 0, 0), Vector(0, 1, 0), -TOE).translate(Vector(0, 0, SEAM_Z))
    if trim:
        s = single(s.intersect(box(0, 3000, -100, 3000, -3000, 3000)))
    if side < 0:
        s = s.mirror("YZ")
    return s


def both_facets(local_shape, trim=True):
    r = place_facet(local_shape, 1, trim)
    l = place_facet(local_shape, -1, trim)
    return r, l


def lbox(u0, u1, y0, y1, w0, w1):
    """Box in the facet frame (u = X, y = Y, w = Z)."""
    return box(u0, u1, y0, y1, w0, w1)


def lrr(u0, u1, y0, y1, w0, w1, r_outer):
    """Facet-frame slab whose two corners at the outer (u1) end are rounded."""
    s = box(u0, u1, y0, y1, w0, w1)
    if r_outer > 0:
        es = edges_where(s, lambda c, bb, e: near(bb.xmin, u1) and near(bb.xmax, u1) and (bb.zmax - bb.zmin) > 0.1)
        s = fillet(s, r_outer, es, "lrr")
    return s


# ----------------------------------------------------------------------------
# BASE
# ----------------------------------------------------------------------------

B = P["base"]


def _pocket_rect(pk, grow=0.0):
    (cx, cz), (w, d) = pk["c"], pk["size"]
    return cx - w / 2 - grow, cx + w / 2 + grow, cz - d / 2 - grow, cz + d / 2 + grow


def _plinth_prism(y0, y1, grow=0.0):
    pl = P["base"]["plinth"]
    zf, hf, hb = pl["z_front"], pl["half_w_front"], pl["half_w_back"]
    zb = -140.0
    hb2 = hf + (hb - hf) * (zb - zf) / (-134.0 - zf)
    # grow each edge outward by `grow` (sides are slanted)
    ang = math.atan2(hb2 - hf, zf - zb)
    dg = grow / math.cos(ang)
    zf2 = zf + grow
    hf2 = hf + dg - (hb2 - hf) / (zf - zb) * grow
    hb3 = hb2 + dg
    wp = cq.Workplane("XZ", origin=(0, y1, 0))
    s = wp.polyline([(-hf2, zf2), (hf2, zf2), (hb3, zb), (-hb3, zb)]).close().extrude(y1 - y0).val()
    es = edges_where(s, lambda c, bb, e: near(c.z, zf2, 0.5) and (bb.ymax - bb.ymin) > 0.5)
    return fillet(s, pl["r"] + grow, es, "plinth corners")


def _post(cx, cz, y0, y1, r=3.5):
    return cyl_y(cx, cz, r, y0, y1)


def internal_posts():
    """Mounting bosses rising from the base floor (part of base_shell)."""
    I = P["internals"]
    fl = B["floor_t"]
    posts = []
    bx0, bx1 = I["board"]["x"]
    bz0, bz1 = I["board"]["z"]
    for x in (bx0 + 8, bx1 - 8):
        for z in (bz0 + 8, bz1 - 8):
            posts.append(_post(x, z, fl, I["board"]["y"][0]))
    px0, px1 = I["psu"]["x"]
    pz0, pz1 = I["psu"]["z"]
    for x in (px0 + 10, px1 - 10):
        for z in (pz0 + 14, pz1 - 10):
            posts.append(_post(x, z, fl, I["psu"]["y"][0]))
    fy = I["ferrite"]["y"][0]
    for cx in I["qi_coils_kb_x"] + [I["qi_coil_mouse_x"]]:
        for dx in (-23, 23):
            for dz in (-23, 23):
                posts.append(_post(cx + dx, I["qi_z"] + dz, fl, fy, 3.0))
    return posts


def coil_centres():
    I = P["internals"]
    return [(x, I["qi_z"]) for x in I["qi_coils_kb_x"]] + [(I["qi_coil_mouse_x"], I["qi_z"])]


@lru_cache(None)
def base_shell():
    x0, x1 = B["x"]
    z0, z1 = B["z"]
    H = B["height"]
    rim, deck = B["rim_w"], B["deck_y"]

    s = prism_y(x0, x1, z0, z1, 0, H, B["corner_r"])
    s = fillet(s, B["top_fillet"], edges_where(s, on_plane("y", H)), "base top")
    s = fillet(s, B["bottom_fillet"], edges_where(s, on_plane("y", 0)), "base bottom")

    # recessed deck, leaving the plinth under the neck
    dk = prism_y(x0 + rim, x1 - rim, z0 + rim, z1 - rim, deck, H + 10, B["corner_r"] - rim)
    dk = cut(dk, _plinth_prism(deck - 1, H + 11))
    zr = z0 + rim
    es = edges_where(dk, lambda c, bb, e: near(c.z, zr, 0.6) and (bb.ymax - bb.ymin) > 5 and 150 < abs(c.x) < 230)
    dk = fillet(dk, 8.0, es, "plinth junction")
    dk = fillet(dk, B["deck_fillet"], edges_where(dk, on_plane("y", deck)), "deck fillet")
    s = cut(s, dk)

    # charging pockets (floor fillet = pad inset so the pads only touch)
    pockets = []
    for key in ("kb_pocket", "mouse_pocket"):
        pk = B[key]
        a, b, c, d = _pocket_rect(pk)
        pc = prism_y(a, b, c, d, pk["floor_y"], H + 10, pk["r"])
        pc = fillet(pc, 1.0, edges_where(pc, on_plane("y", pk["floor_y"])), key + " floor")
        pockets.append(pc)
    s = cut(s, *pockets)

    # soften the rim's inner top edge and the pocket mouths
    inner = in_box(x0 + rim - 2.5, x1 - rim + 2.5, H - 0.01, H + 0.01, z0 + rim - 2.5, z1 - rim + 2.5)
    s = fillet(s, B["rim_inner_fillet"], edges_where(s, inner), "rim inner")
    mouth = []
    for key in ("kb_pocket", "mouse_pocket"):
        a, b, c, d = _pocket_rect(B[key], 0.3)
        mouth += edges_where(s, in_box(a, b, deck - 0.01, deck + 0.01, c, d))
    s = fillet(s, B["pocket_edge_fillet"], mouth, "pocket mouths")

    # recess for the graphite deck liner (its top is the visible deck at y = deck_y)
    s = cut(s, _liner_footprint(deck - B["liner_t"], deck + 1.0))

    # ---- hollow interior (closed bottom, internals live here) --------------
    w, fl, dt, pw = B["wall"], B["floor_t"], B["deck_t"], B["pocket_wall"]
    cav = prism_y(x0 + w, x1 - w, z0 + w, z1 - w, fl, deck - dt, B["corner_r"] - w)
    keep = []
    for key in ("kb_pocket", "mouse_pocket"):
        pk = B[key]
        a, b, c, d = _pocket_rect(pk, pw)
        keep.append(prism_y(a, b, c, d, pk["floor_y"] - pw, H + 5, pk["r"] + pw))
    keep.append(box(x0 - 5, x1 + 5, -1, 9.0, z1 - B["undercut"]["depth"] - 4.0, z1 + 5))   # glow undercut
    keep += internal_posts()
    cav = cut(cav, *keep)
    s = cut(s, cav)

    # cable chase through the plinth into the neck
    cc = B["cable_chase"]
    s = cut(s, prism_y(cc["x"][0], cc["x"][1], cc["z"][0], cc["z"][1], deck - dt - 1, H + 1, 8))

    # coil windows in the titanium pocket floors (metal would block Qi2)
    wins = [cyl_y(cx, cz, B["coil_window_d"] / 2, B["kb_pocket"]["floor_y"] - pw - 1, B["kb_pocket"]["floor_y"] - 0.0)
            for cx, cz in coil_centres()]
    s = cut(s, *wins)

    # front under-glow undercut
    uc = B["undercut"]
    s = cut(s, prism_y(uc["x"][0], uc["x"][1], z1 - uc["depth"], z1 + 20, uc["y"][0] - 1, uc["y"][1], 3))

    # charge indicator slots in the front rim
    for key in ("kb_led", "mouse_led"):
        L = B[key]
        s = cut(s, prism_y(L["x"] - L["w"] / 2, L["x"] + L["w"] / 2, L["z"] - L["d"] / 2, L["z"] + L["d"] / 2,
                           H - L["depth"], H + 2, 0.9))

    # feet grooves
    s = cut(s, *[_foot(zc, -1, B["feet"]["depth"]) for zc in B["feet"]["z"]])

    # rear I/O bay + ports, exhaust grille, AC inlet
    s = cut(s, *rear_cutters())
    return s


def _liner_footprint(y0, y1):
    """Deck area inside the rim, clear of the rim fillet, pockets and plinth, with a titanium reveal."""
    x0, x1 = B["x"]
    z0, z1 = B["z"]
    ins = B["rim_w"] + B["deck_fillet"] + B["liner_reveal"]
    f = prism_y(x0 + ins, x1 - ins, z0 + ins, z1 - ins, y0, y1, B["corner_r"] - ins)
    holes = [_plinth_prism(y0 - 1, y1 + 1, B["deck_fillet"] + B["liner_reveal"])]
    for key in ("kb_pocket", "mouse_pocket"):
        a, b, c, d = _pocket_rect(B[key], B["pocket_edge_fillet"] + B["liner_reveal"])
        holes.append(prism_y(a, b, c, d, y0 - 1, y1 + 1, B[key]["r"] + B["pocket_edge_fillet"] + B["liner_reveal"]))
    return cut(f, *holes)


def deck_liner():
    t = B["liner_t"]
    s = _liner_footprint(B["deck_y"] - t, B["deck_y"])
    return fillet(s, 0.4, edges_where(s, on_plane("y", B["deck_y"])), "liner top")


IO_PORTS = [  # (kind, x, y_centre, w, h, stadium)
    ("usb-c", -591.0, 7.3, 9.0, 3.4, True),
    ("usb-c", -579.0, 7.3, 9.0, 3.4, True),
    ("usb-a", -561.0, 8.5, 13.2, 5.8, False),
    ("usb-a", -544.0, 8.5, 13.2, 5.8, False),
    ("hdmi", -524.0, 8.5, 15.2, 5.8, False),
    ("rj45", -496.0, 12.4, 16.2, 13.6, False),
]


def rear_cutters():
    z0 = B["z"][0]
    io = B["io_bay"]
    out = [prism_z(io["x"][0], io["x"][1], 3.5, 22.5, z0 - 1, z0 + io["depth"], 2.5)]
    for kind, x, y, w, h, st in IO_PORTS:
        if st:
            out.append(stadium_z(x, y, w, h, z0 - 1, z0 + B["wall"] + 1))
        else:
            out.append(prism_z(x - w / 2, x + w / 2, y - h / 2, y + h / 2, z0 - 1, z0 + B["wall"] + 1, 0.6))
    ex = B["exhaust"]
    n = int((ex["x"][1] - ex["x"][0] - ex["slot_w"]) // ex["pitch"]) + 1
    for i in range(n):
        x = ex["x"][0] + ex["slot_w"] / 2 + i * ex["pitch"]
        out.append(stadium_z(x, (ex["y"][0] + ex["y"][1]) / 2, ex["y"][1] - ex["y"][0], ex["slot_w"],
                             z0 - 1, z0 + B["wall"] + 1, along="y"))
    ac = B["ac_inlet"]
    out.append(stadium_z(ac["x"], ac["y"], 11.6, 7.0, z0 - 1, z0 + B["wall"] + 1))
    return out


def _foot(zc, y0, y1):
    f = B["feet"]
    L = f["x"][1] - f["x"][0]
    return stadium_y((f["x"][0] + f["x"][1]) / 2, zc, L, f["w"], y0, y1)


@lru_cache(None)
def _pad(key):
    pk = B[key]
    a, b, c, d = _pocket_rect(pk, -1.0)
    y0 = pk["floor_y"]
    p = prism_y(a, b, c, d, y0, y0 + B["pad_t"], pk["r"] - 1.0)
    p = fillet(p, 0.6, edges_where(p, on_plane("y", y0 + B["pad_t"])), key + " pad top")
    rings = []
    for cx, cz in coil_centres():
        if a < cx < b:
            R = B["pad_ring_d"] / 2
            ring = cut(cyl_y(cx, cz, R + 0.5, y0 + B["pad_t"] - 0.4, y0 + B["pad_t"] + 1),
                       cyl_y(cx, cz, R - 0.5, y0, y0 + B["pad_t"] + 2))
            rings.append(ring)
    return cut(p, *rings)


def tray_pad_kb():
    return _pad("kb_pocket")


def tray_pad_mouse():
    return _pad("mouse_pocket")


def base_glow():
    g = B["glow"]
    return prism_y(g["x"][0], g["x"][1], g["z"][0], g["z"][1], g["y"][0], g["y"][1], 1.2)


def _led(key):
    L = B[key]
    H = B["height"]
    return prism_y(L["x"] - L["w"] / 2, L["x"] + L["w"] / 2, L["z"] - L["d"] / 2, L["z"] + L["d"] / 2,
                   H - L["depth"], H, 0.9)


def kb_charge_led():
    return _led("kb_led")


def mouse_charge_led():
    return _led("mouse_led")


def base_feet():
    return compound([_foot(zc, 0, B["feet"]["depth"]) for zc in B["feet"]["z"]])


# ----------------------------------------------------------------------------
# STAND (neck)
# ----------------------------------------------------------------------------

N = P["neck"]


def _neck_front_z(y):
    (zb0, zb1), (zt0, zt1) = N["z_bottom"], N["z_top"]
    y0, y1 = N["y"]
    return zb1 + (zt1 - zb1) * (y - y0) / (y1 - y0)


def _neck_face_plane(y):
    y0, y1 = N["y"]
    dz = N["z_top"][1] - N["z_bottom"][1]
    dy = y1 - y0
    L = math.hypot(dy, dz)
    normal = (0.0, -dz / L, dy / L)  # (0, 0.083, 0.9965)
    return frame_plane((0.0, y, _neck_front_z(y)), (1, 0, 0), normal)


def _neck_loft(inset=0.0, ext=0.0):
    """Neck body from planar half-space cuts (front/back lean, tapered sides); inset > 0 -> cavity."""
    y0, y1 = N["y"]
    (zb0, zb1), (zt0, zt1) = N["z_bottom"], N["z_top"]
    hb, ht = N["bottom_w"] / 2, N["top_w"] / 2
    s = box(-hb - 1, hb + 1, y0 - ext, y1 + ext, zt0 - 1, zb1 + 1)
    dy = y1 - y0
    cuts = [
        ((0, y0, zb1), (0, -(zt1 - zb1), dy)),        # front face, leaning back
        ((0, y0, zb0), (0, (zt0 - zb0), -dy)),        # back face
        ((hb, y0, 0), (dy, hb - ht, 0)),              # right side
        ((-hb, y0, 0), (-dy, hb - ht, 0)),            # left side
    ]
    hs = [halfspace(_offset_pt(pt, n, inset), n) for pt, n in cuts]
    return cut(s, *hs)


@lru_cache(None)
def _neck_text():
    bd = N["badge"]
    size = bd["size"]
    glyphs = []
    x = 0.0
    for ch in bd["text"]:
        if ch == " ":
            x += 0.62 * size
            continue
        g = cq.Workplane("XY").text(ch, size, bd["depth"], halign="left", valign="bottom",
                                    font=bd["font"], kind=bd["kind"]).val()
        bb = g.BoundingBox()
        g = g.translate(Vector(x - bb.xmin, 0, 0))
        glyphs.append(g)
        x += bb.xlen + bd["tracking"] * size
    x -= bd["tracking"] * size
    allg = compound(glyphs)
    bb = allg.BoundingBox()
    allg = allg.translate(Vector(-(bb.xmin + bb.xmax) / 2, -(bb.ymin + bb.ymax) / 2, -bd["depth"]))
    return to_frame(allg, _neck_face_plane(bd["y"]))


def _neck_light_box(grow=0.0, proud=0.0):
    L = N["light"]
    yc = (L["y"][0] + L["y"][1]) / 2
    b = box(-L["w"] / 2 - grow, L["w"] / 2 + grow, -L["h"] / 2 - grow, L["h"] / 2 + grow, -L["depth"], proud)
    b = fillet(b, min(1.2, L["h"] / 2 - 0.1) + grow * 0.5, edges_where(b, lambda c, bb, e: (bb.zmax - bb.zmin) > 0.5),
               "light ends")
    return to_frame(b, _neck_face_plane(yc))


@lru_cache(None)
def _neck_outer():
    s = _neck_loft()
    es = edges_where(s, lambda c, bb, e: (bb.ymax - bb.ymin) > 50)
    s = fillet(s, N["edge_fillet"], es, "neck edges")
    return fillet(s, 1.2, edges_where(s, on_plane("y", N["y"][1])), "neck top edge")


@lru_cache(None)
def neck():
    s = _neck_outer()
    inner = _neck_loft(N["wall"], 2.0)
    es = edges_where(inner, lambda c, bb, e: (bb.ymax - bb.ymin) > 50)
    inner = fillet(inner, max(N["edge_fillet"] - N["wall"], 1.0), es, "neck inner")
    s = cut(s, inner)
    s = cut(s, _neck_light_box(), _neck_text())
    return s


def neck_light():
    return _neck_light_box()


def neck_badge():
    return _neck_text()


# ----------------------------------------------------------------------------
# DISPLAY
# ----------------------------------------------------------------------------

D = P["display"]


def _glass_len():
    return D["inner_border"] + D["active"][0] + D["outer_border"]


def _frame_outer():
    L = _glass_len() + D["frame_w"]
    gy0, gy1 = D["glass_y"]
    return L, gy0 - D["frame_w"], gy1 + D["frame_w"]


def display_screen():
    u0 = D["inner_border"]
    u1 = u0 + D["active"][0]
    y0, y1 = D["active_y"]
    loc = lbox(u0, u1, y0, y1, 0.0, D["screen_proud"])
    r, l = both_facets(loc, trim=False)
    return compound([l, r])


def display_glass():
    gy0, gy1 = D["glass_y"]
    loc = lrr(0.0, _glass_len(), gy0, gy1, -D["glass_t"], 0.0, D["glass_corner_r"])
    r, l = both_facets(loc, trim=False)
    return compound([l, r])


@lru_cache(None)
def display_frame():
    L, fy0, fy1 = _frame_outer()
    gy0, gy1 = D["glass_y"]
    w0, w1 = -D["frame_depth"], D["frame_proud"]
    outer = lrr(-60, L, fy0, fy1, w0, w1, D["frame_corner_r"])
    inner = lrr(-70, _glass_len(), gy0, gy1, w0 - 1, w1 + 1, D["glass_corner_r"])
    band = cut(outer, inner)
    fr = edges_where(band, lambda c, bb, e: near(bb.zmin, w1) and near(bb.zmax, w1) and bb.xmin > -59
                     and (c.y < gy0 - 0.5 or c.y > gy1 + 0.5 or c.x > _glass_len() + 0.5))
    band = fillet(band, 1.2, fr, "frame front outer")
    fi = edges_where(band, lambda c, bb, e: near(bb.zmin, w1) and near(bb.zmax, w1) and bb.xmin > -59
                     and gy0 - 0.5 < c.y < gy1 + 0.5 and c.x < _glass_len() + 0.5 and (bb.xmax - bb.xmin) > 0.01
                     or (near(bb.zmin, w1) and near(bb.zmax, w1) and bb.xmin > -59 and (c.y < gy0 + 0.5 and c.y > gy0 - 0.5)))
    band = chamfer(band, 0.4, fi, "frame front inner")
    r, l = both_facets(band)
    return fuse(r, l)


def display_seam():
    mw = D["mullion_w"] / 2
    zb = SEAM_Z + mw * math.tan(math.radians(TOE))
    zf = D["mullion_front_z"]
    gy0, gy1 = D["glass_y"]
    wp = cq.Workplane("XZ", origin=(0, gy1, 0))
    s = wp.polyline([(-mw, zb), (0, SEAM_Z), (mw, zb), (mw, zf), (-mw, zf)]).close().extrude(gy1 - gy0).val()
    es = edges_where(s, lambda c, bb, e: near(c.z, zf, 0.01) and (bb.ymax - bb.ymin) > 100)
    return fillet(s, 0.6, es, "mullion")


def _shroud_local(inset=0.0, front_ext=0.0):
    """Right-half shroud body in the facet frame (planar facets); inset > 0 gives the cavity."""
    L, fy0, fy1 = _frame_outer()
    t = D["shroud_thin"]
    wf = -D["frame_depth"]
    i = inset
    thin = lrr(-60, L - i, fy0 + i, fy1 - i, -t + i, wf + front_ext, max(D["frame_corner_r"] - i, 1.0))
    bf, bb = D["bump_front"], D["bump_back"]
    wa, wb = -t, -D["shroud_depth"]
    bump = box(-60, bf["u_max"], bf["y"][0], bf["y"][1], wb, wa + (i + 1.0 if i else 0.0))
    facets = [
        ((0, bf["y"][1], wa), (0, wa - wb, -(bf["y"][1] - bb["y"][1]))),        # top facet
        ((0, bf["y"][0], wa), (0, -(wa - wb), -(bb["y"][0] - bf["y"][0]))),     # bottom facet
        ((bf["u_max"], 0, wa), (wa - wb, 0, -(bf["u_max"] - bb["u_max"]))),     # outer end facet
        ((0, 0, wb), (0, 0, -1)),                                                # back plateau
    ]
    bump = cut(bump, *[halfspace(_offset_pt(pt, n, i), n) for pt, n in facets])
    return fuse(thin, bump)


def _keel(inset=0.0):
    k = D["keel"]
    fy0 = _frame_outer()[1]
    i = inset
    yb, yt = fy0 + i, k["y_top"] - i
    hb, ht = k["bottom_w"] / 2 - i, k["top_w"] / 2 - i
    front = (cq.Workplane("XY", origin=(0, 0, -300)).polyline([(-hb, yb), (hb, yb), (ht, yt), (-ht, yt)]).close()
             .extrude(300).val())
    zbb, zbt = k["z_back_bottom"] + i, k["z_back_top"] + i
    side = (cq.Workplane("ZY", origin=(400, 0, 0)).polyline([(-30, yb - 1), (zbb - (zbt - zbb) / (yt - yb) * 1, yb - 1),
                                                           (zbt, yt), (-30, yt)]).close().extrude(800).val())
    s = single(front.intersect(side))
    ch = k["chamfer"]
    es = edges_where(s, lambda c, bb, e: (bb.ymax - bb.ymin) > 100 and c.z < -90)
    s = chamfer(s, ch, es, "keel rear edges")
    es = edges_where(s, lambda c, bb, e: near(bb.ymin, yt, 0.2) and near(bb.ymax, yt, 0.2) and c.z < -95)
    s = chamfer(s, 18.0 - i * 0.4, es, "keel top")
    # never in front of the shroud front plane
    fr = lbox(-200, 900, -100, 900, -D["frame_depth"] + (3.0 if inset else 0.0), 300)
    fr_r, fr_l = both_facets(fr, trim=False)
    s = cut(s, fr_r, fr_l)
    return s


def _keel_rear_plane(y):
    k = D["keel"]
    fy0 = _frame_outer()[1]
    yb, yt = fy0, k["y_top"]
    zb, zt = k["z_back_bottom"], k["z_back_top"]
    z = zb + (zt - zb) * (y - yb) / (yt - yb)
    L = math.hypot(zt - zb, yt - yb)
    n = (0.0, (zt - zb) / L, -(yt - yb) / L)  # outward (back, slightly up)
    return frame_plane((0, y, z), (-1, 0, 0), n)


def _vent_cutters():
    v = D["vents"]
    t = D["shroud_thin"]
    bf, bb = D["bump_front"], D["bump_back"]
    out = []
    # top facet of the bump: from (y=bf.y1, w=-t) to (y=bb.y1, w=-depth)
    for (ya, yb_), sign, start, step in (((bf["y"][1], bb["y"][1]), 1, v["u0"], v["pitch"]),
                                        ((bf["y"][0], bb["y"][0]), -1, 135.0, v["pitch"] * 2)):
        wa, wb = -t, -D["shroud_depth"]
        ym, wm = (ya + yb_) / 2, (wa + wb) / 2
        dy, dw = yb_ - ya, wb - wa
        Lf = math.hypot(dy, dw)
        n = (0.0, sign * abs(dw) / Lf, -abs(dy) / Lf * (1 if sign > 0 else 1))
        # outward normal: top facet points up/back, bottom facet points down/back
        n = (0.0, sign * (-dw) / Lf, -(abs(dy)) / Lf)
        u = start
        umax = (bf["u_max"] + bb["u_max"]) / 2 - 30
        while u <= umax:
            pl = frame_plane((u, ym, wm), (1, 0, 0), n)
            c = cq.Workplane(pl).slot2D(v["len"], v["w"], 90).extrude(4, both=True).val()
            out.append(c)
            u += step
    return out


@lru_cache(None)
def display_back():
    body = _shroud_local(0.0)
    cav = _shroud_local(D["shroud_wall"], front_ext=6.0)
    vents = compound(_vent_cutters())
    body_r, body_l = both_facets(body)
    cav_r, cav_l = both_facets(cav)
    vent_r, vent_l = place_facet(vents, 1, trim=False), place_facet(vents, -1, trim=False)
    keel = _keel(0.0)
    s = fuse(body_r, body_l, keel)

    # VESA 100 hub on the keel's rear face
    hub = D["vesa_hub"]
    pl = _keel_rear_plane(hub["y"])
    hb = box(-58, 58, -58, 58, -1.0, hub["proud"])
    hb = fillet(hb, 16.0, edges_where(hb, lambda c, bb, e: (bb.zmax - bb.zmin) > 1), "hub corners")
    hb = fillet(hb, 1.0, edges_where(hb, on_plane("z", hub["proud"])), "hub face")
    s = fuse(s, to_frame(hb, pl))
    holes = [to_frame(cyl_z(px, py, 2.6, -1.0, hub["proud"] + 1), pl)
             for px in (-hub["pattern"] / 2, hub["pattern"] / 2) for py in (-hub["pattern"] / 2, hub["pattern"] / 2)]

    keel_cav = _keel(D["keel"]["wall"])
    socket = single(_neck_outer().intersect(box(-300, 300, _frame_outer()[1] - 1, N["y"][1], -400, 0)))
    s = cut(s, cav_r, cav_l, keel_cav, vent_r, vent_l, socket, *holes)
    return s


def _plate_local():
    pt = D["plate"]
    u0, u1 = pt["u"]
    y0, y1 = pt["y"]
    gt = D["glass_t"]
    p = box(u0, u1, y0, y1, -gt - pt["t"], -gt)
    p = fillet(p, 8.0, edges_where(p, lambda c, bb, e: (bb.zmax - bb.zmin) > 1), "plate corners")
    uc, yc = (u0 + u1) / 2, (y0 + y1) / 2
    holes = [cyl_z(uc + a, yc + b, 3.0, -10, 0) for a in (-50, 50) for b in (-50, 50)]
    win = box(uc - 30, uc + 30, yc - 30, yc + 30, -10, 0)
    win = fillet(win, 6.0, edges_where(win, lambda c, bb, e: (bb.zmax - bb.zmin) > 1), "plate window")
    return cut(p, *holes, win)


@lru_cache(None)
def display_spine():
    arm = D["spine_arm"]
    a = lbox(-60, arm["u_max"], arm["y"][0], arm["y"][1], arm["w"][0], arm["w"][1])
    a = fuse(a, _plate_local())
    ar, al = both_facets(a)
    sp, ft = D["spine_post"], D["spine_foot"]
    post = box(-sp["x"], sp["x"], sp["y"][0], sp["y"][1], sp["z"][0], sp["z"][1])
    foot = box(-ft["x"], ft["x"], ft["y"][0], ft["y"][1], ft["z"][0], ft["z"][1])
    foot = fillet(foot, 6.0, edges_where(foot, lambda c, bb, e: (bb.ymax - bb.ymin) > 1), "foot")
    gus = box(-sp["x"], sp["x"], ft["y"][1], ft["y"][1] + 40, ft["z"][0] + 6, sp["z"][0])
    return fuse(ar, al, post, foot, gus)


def _board_local():
    bd = D["board"]
    u0, u1 = bd["u"]
    y0, y1 = bd["y"]
    w0, w1 = bd["w_pcb"]
    pcb = box(u0, u1, y0, y1, w0, w1)
    parts = [pcb]
    pw = D["glass_t"] + D["plate"]["t"]
    for su in (u0 + 24, u1 - 8):
        for sy in (y0 + 8, y1 - 8):
            parts.append(cyl_z(su, sy, 3.0, w1, -pw))
    parts.append(box(250, 274, 292, 316, w0 - 7, w0))                   # scaler + heatsink
    parts.append(box(296, 324, 300, 330, w0 - 3, w0))                   # DDR / flash
    parts.append(box(345, 371, 270, 292, w0 - 15, w0))                  # PSU transformer
    for (cu, cy) in ((390, 282), (390, 330), (340, 330)):
        parts.append(cyl_z(cu, cy, 5.0, w0 - 14, w0))                   # caps
    parts.append(box(228, 244, 336, 346, w0 - 6, w0))                   # panel eDP connector
    return fuse(*parts)


def display_boards():
    b = _board_local()
    r, l = place_facet(b, 1, trim=False), place_facet(b, -1, trim=False)
    return compound([l, r])


# ----------------------------------------------------------------------------
# DOCK
# ----------------------------------------------------------------------------

K = P["dock"]


def _dock_profile_wp(x1, inset=0.0):
    pts = K["profile_pts"]
    z0, z1 = K["z"]
    wp = cq.Workplane("ZY", origin=(x1, 0, 0))
    pf = list(reversed(pts))  # front -> back
    w = (wp.moveTo(z0, 0).lineTo(z1, 0).lineTo(z1, K["h_front"]).lineTo(pf[1][0], pf[1][1])
         .spline([tuple(p) for p in pf[2:-1]], tangents=[(-1, 0), (-1, 0)], includeCurrent=True)
         .lineTo(z0, K["h_back"]).close())
    if inset:
        w = w.offset2D(-inset, "arc")
    return w


def _dock_prism(x0, x1, inset=0.0):
    """Side-profile prism between x0 and x1.  Offset profiles are converted to NURBS first:
    Geom_OffsetCurve edges do not survive a STEP round trip."""
    w = _dock_profile_wp(x1, inset)
    if not inset:
        return w.extrude(x1 - x0).val()
    from OCP.BRepBuilderAPI import BRepBuilderAPI_NurbsConvert
    wire = w.val()
    nurbs = cq.Wire(BRepBuilderAPI_NurbsConvert(wire.wrapped, True).Shape())
    face = cq.Face.makeFromWires(nurbs)
    return cq.Solid.extrudeLinear(face, Vector(-(x1 - x0), 0, 0))


@lru_cache(None)
def dock_cradle():
    x0, x1 = K["x"]
    z0, z1 = K["z"]
    s = _dock_prism(x0, x1)
    # plan corners on the outer wing
    es = edges_where(s, lambda c, bb, e: near(c.x, x1, 0.01) and (bb.ymax - bb.ymin) > 30 and (bb.zmax - bb.zmin) < 0.01)
    s = fillet(s, K["plan_r"], es, "dock plan corners")
    es = edges_where(s, lambda c, bb, e: bb.ymin > 1.0 and not (near(c.x, x0, 0.01) and c.y < 40))
    s = fillet(s, K["edge_fillet"], es, "dock edges")
    s = fillet(s, 1.0, edges_where(s, lambda c, bb, e: near(bb.ymax, 0) and c.x > x0 + 0.5), "dock bottom")

    sl = K["slot"]
    slot = prism_y(sl["x"][0], sl["x"][1], sl["z"][0], sl["z"][1], sl["floor_y"], 200, sl["r"])
    slot = fillet(slot, 1.0, edges_where(slot, on_plane("y", sl["floor_y"])), "slot floor")
    s = cut(s, slot)
    sx0, sx1 = sl["x"]
    lead = edges_where(s, lambda c, bb, e: bb.ymin > sl["floor_y"] + 20 and sx0 - 0.1 <= bb.xmin and bb.xmax <= sx1 + 0.1
                       and (bb.xmax - bb.xmin > 0.5 or bb.zmax - bb.zmin > 0.5 or near(c.x, sx0, 0.1) or near(c.x, sx1, 0.1))
                       and (bb.ymax - bb.ymin) < 70)
    s2 = chamfer(s, sl["lead_in"], lead, "slot lead-in")
    s = s2

    # hollow: under-slot cavity + cheek cavities
    cy0, cy1 = K["cavity_y"]
    wl = K["wall"]
    cav = [box(x0 + wl, x1 - wl - 3, cy0, cy1, z0 + wl, z1 - 6)]
    cav.append(single(_dock_prism(x0 + wl, sx0 - 6, 4.0).intersect(box(0, 2000, cy0, 500, z0 + wl, z1 - 6))))
    cav.append(single(_dock_prism(sx1 + 6, x1 - 6, 4.0).intersect(box(0, 2000, cy0, 500, z0 + wl, z1 - 6))))
    for x in (K["x"][0] + 20, K["x"][1] - 20):
        pass
    db = P["internals"]["dock_board"]
    posts = [cyl_y(px, pz, 3.0, cy0 - 0.5, db["y"][0]) for px in (db["x"][0] + 6, db["x"][1] - 6)
             for pz in (db["z"][0] + 6, db["z"][1] - 6)]
    cav = cut(fuse(*cav), *posts)
    s = cut(s, cav)

    # connector well
    cn = K["connector"]
    s = cut(s, prism_y(722 - 4.0, 722 + 4.0, cn["z"] - 7.5, cn["z"] + 7.5, cy1 - 1, sl["floor_y"] + 1, 2.0))

    # oxblood panel recesses
    s = cut(s, _side_panel(K["x"][1] - K["panel_t"], K["x"][1] + 1), _front_panel(z1 - K["panel_t"], z1 + 1))

    # latch pocket
    lt = K["latch"]
    c = lt["clear"]
    s = cut(s, prism_z(lt["x"][0] - c, lt["x"][1] + c, lt["y"][0] - c, lt["y"][1] + c, lt["pocket_z0"], z1 + 1, 2.0))
    return s


def _side_panel(xa, xb):
    return single(_dock_prism(xa, xb, K["panel_inset"]).intersect(box(0, 2000, K["panel_inset"], 500, -500, 500)))


def _front_panel(za, zb):
    fp = K["front_panel"]
    return prism_z(fp["x"][0], fp["x"][1], fp["y"][0], fp["y"][1], za, zb, 3.0)


def dock_panels():
    side = single(_side_panel(K["x"][1] - K["panel_t"], K["x"][1]))
    front = _front_panel(K["z"][1] - K["panel_t"], K["z"][1])
    return compound([side, front])


@lru_cache(None)
def _latch_body():
    lt = K["latch"]
    b = box(lt["x"][0], lt["x"][1], lt["y"][0], lt["y"][1], lt["z"][0], lt["z"][1])
    b = fillet(b, 2.0, edges_where(b, lambda c, bb, e: c.z > lt["z"][0] + 0.5), "latch")
    grooves = [box(lt["x"][0] + 4, lt["x"][1] - 4, y - 0.4, y + 0.4, lt["z"][1] - 0.5, lt["z"][1] + 1)
               for y in (22.5, 25.5, 28.5)]
    led = _latch_led_box(lt["y"][1] + 1)
    return cut(b, *grooves, led)


def _latch_led_box(ytop):
    ll, lt = K["latch_led"], K["latch"]
    xc = (lt["x"][0] + lt["x"][1]) / 2
    return prism_y(xc - ll["w"] / 2, xc + ll["w"] / 2, ll["z"][0], ll["z"][1], lt["y"][1] - ll["depth"], ytop, 1.2)


def dock_latch():
    return _latch_body()


def dock_latch_led():
    return _latch_led_box(K["latch"]["y"][1])


def dock_connector():
    cn = K["connector"]
    bx, by, bz = cn["boot"]
    y0, y1 = cn["boot_y"]
    boot = prism_y(722 - bx / 2, 722 + bx / 2, cn["z"] - bz / 2, cn["z"] + bz / 2, y0, y1, 1.6)
    px, ph, pz = cn["plug"]
    plug = stadium_y(722, cn["z"], pz, px, y1, y1 + ph, along="z")
    plug = fillet(plug, 0.5, edges_where(plug, on_plane("y", y1 + ph)), "plug tip")
    return fuse(boot, plug)


# ----------------------------------------------------------------------------
# LAPTOP
# ----------------------------------------------------------------------------

LP = P["laptop"]


def laptop_body():
    x0, x1 = LP["x"]
    y0, y1 = LP["y"]
    z0, z1 = LP["z"]
    s = box(x0, x1, y0, y1, z0, z1)
    s = fillet(s, LP["corner_r"], edges_where(s, lambda c, bb, e: (bb.xmax - bb.xmin) > 5), "laptop corners")
    s = fillet(s, LP["edge_r"], edges_where(s, lambda c, bb, e: near(bb.xmin, x0) and near(bb.xmax, x0)
                                            or near(bb.xmin, x1) and near(bb.xmax, x1)), "laptop faces")
    # lid seam groove
    xs = x1 - LP["lid_t"]
    g = LP["seam_groove"]
    slab = box(xs - g, xs, y0 - 5, y1 + 5, z0 - 5, z1 + 5)
    keep = prism_x(z0 + g, z1 - g, y0 + g, y1 - g, xs - g - 1, xs + 1, LP["corner_r"] - g)
    s = cut(s, cut(slab, keep))
    # dock port (bottom edge) + side ports on the top edge
    pz = LP["port_z"]
    px, pd, pl = LP["port"]
    xc = (x0 + x1) / 2
    cutters = [stadium_y(xc, pz, pl, px, y0 - 1, y0 + pd, along="z")]
    for zc in (-84.0, -68.0):
        cutters.append(stadium_y(xc - 1.0, zc, 8.9, 3.2, y1 - 6, y1 + 1, along="z"))
    cutters.append(cyl_y(xc - 1.0, 70.0, 1.8, y1 - 8, y1 + 1))
    # hinge relief on the hinge (-z) edge
    cutters.append(box(x1 - LP["lid_t"] - 0.3, x1 - LP["lid_t"] + 0.3, y0 + 30, y1 - 30, z0 - 1, z0 + 0.5))
    return cut(s, *cutters)


# ----------------------------------------------------------------------------
# KEYBOARD (built at the origin, then moved to its stow position)
# ----------------------------------------------------------------------------

KB = P["keyboard"]
KB_ROWS = [
    [1] * 16,
    [1] * 13 + [2, 1],
    [1.5] + [1] * 12 + [1.5, 1],
    [1.75] + [1] * 11 + [2.25, 1],
    [2.25] + [1] * 10 + [1.75, 1, 1],
    [1.25, 1.25, 1.25, 6.25, 1, 1, 1, 1, 1, 1],
]


def _kb_slope():
    W, Dp = KB["size"]
    return math.atan2(KB["h_back"] - KB["h_front"], Dp)


def _kb_top_plane():
    a = _kb_slope()
    yc = (KB["h_front"] + KB["h_back"]) / 2
    # local X = x, local Y = top normal, local Z = down-slope toward the front
    return frame_plane((0, yc, 0), (1, 0, 0), (0, math.cos(a), math.sin(a)))


def _kb_local_to_world(shape):
    """Shape built in the flat key frame (y = 0 is the top surface) -> sloped body frame."""
    a = math.degrees(_kb_slope())
    yc = (KB["h_front"] + KB["h_back"]) / 2
    return shape.rotate(Vector(0, 0, 0), Vector(1, 0, 0), a).translate(Vector(0, yc, 0))


def _kb_place(shape):
    cx, cz = KB["stow_c"]
    return shape.translate(Vector(cx, KB["stow_y"], cz))


def _kb_well(depth_extra=0.0):
    u = KB["unit"]
    W = 16 * u + 2 * KB["well_margin"]
    Dp = 6 * u + 2 * KB["well_margin"]
    s = box(-W / 2, W / 2, -KB["well_depth"], depth_extra, -Dp / 2, Dp / 2)
    s = fillet(s, 3.5, edges_where(s, lambda c, bb, e: (bb.ymax - bb.ymin) > 0.5), "kb well")
    return s


@lru_cache(None)
def _kb_body_local():
    W, Dp = KB["size"]
    hf, hb = KB["h_front"], KB["h_back"]
    s = prism_y(-W / 2, W / 2, -Dp / 2, Dp / 2, 0, hb + 2, KB["corner_r"])
    wedge = (cq.Workplane("ZY", origin=(W, 0, 0)).polyline([(Dp / 2 + 1, hf - (hb - hf) / Dp), (-Dp / 2 - 1, hb + (hb - hf) / Dp),
                                                          (-Dp / 2 - 1, 40), (Dp / 2 + 1, 40)]).close().extrude(2 * W).val())
    s = cut(s, wedge)
    s = fillet(s, 1.6, edges_where(s, lambda c, bb, e: bb.ymin > hf - 0.5), "kb top")
    s = fillet(s, 0.8, edges_where(s, on_plane("y", 0)), "kb bottom")
    s = cut(s, _kb_local_to_world(_kb_well(5.0)))
    cd = KB["coil_d"][0] + 2
    s = cut(s, *[cyl_y(x, 0, cd / 2, -1, KB["coil_t"] + 1.2) for x in KB["coil_x"]])
    return s


def keyboard_body():
    return _kb_place(_kb_body_local())


@lru_cache(None)
def _kb_keys_local():
    u = KB["unit"]
    g = KB["cap_gap"]
    caps = []
    for r, row in enumerate(KB_ROWS):
        zc = (r - 2.5) * u
        x = -8 * u
        for wu in row:
            w = wu * u
            cx = x + w / 2
            cap = (cq.Workplane("XZ", origin=(0, 0, 0)).center(cx, zc).sketch().rect(w - g, u - g).vertices()
                   .fillet(KB["cap_r"]).finalize().extrude(-KB["cap_h"], taper=KB["cap_taper"]).val())
            caps.append(cap)
            x += w
    web = _kb_well(0.0)
    keys = web.fuse(*caps, glue=True).clean()
    keys = single(keys)
    return _kb_local_to_world(keys)


def keyboard_keys():
    return _kb_place(_kb_keys_local())


def keyboard_coil():
    d0, d1 = KB["coil_d"]
    t = KB["coil_t"]
    y0 = 0.9
    rings = [cut(cyl_y(x, 0, d0 / 2, y0, y0 + t), cyl_y(x, 0, d1 / 2, y0 - 1, y0 + t + 1)) for x in KB["coil_x"]]
    return _kb_place(compound(rings))


# ----------------------------------------------------------------------------
# MOUSE
# ----------------------------------------------------------------------------

MS = P["mouse"]


def _mouse_section(z, a, h):
    pts = [(a, 0.0), (a * 1.0, 0.24 * h), (a * 0.94, 0.55 * h), (a * 0.74, 0.83 * h), (a * 0.40, 0.975 * h), (0.0, h),
           (-a * 0.40, 0.975 * h), (-a * 0.74, 0.83 * h), (-a * 0.94, 0.55 * h), (-a * 1.0, 0.24 * h), (-a, 0.0)]
    vs = [Vector(x, y, z) for x, y in pts]
    sp = cq.Edge.makeSpline(vs, tangents=[Vector(0, 1, 0), Vector(0, -1, 0)])
    ln = cq.Edge.makeLine(Vector(-a, 0, z), Vector(a, 0, z))
    return cq.Wire.assembleEdges([sp, ln])


def _mouse_dims(t):
    A = 33.0 + 2.0 * t - 5.0 * t * t
    H = 38.0 - 13.0 * (t - 0.22) ** 2
    ea = (1 - abs(t) ** 2.4) ** (1 / 2.4)
    eh = (1 - abs(t) ** 3.0) ** (1 / 3.0)
    return A * ea, H * eh


MOUSE_TS = [-0.996, -0.975, -0.92, -0.8, -0.55, -0.25, 0.05, 0.3, 0.55, 0.75, 0.88, 0.96, 0.99, 0.998]


def _mouse_loft(sx, sy, sz):
    Lh = MS["size"][1] / 2
    wires = []
    for t in MOUSE_TS:
        a, h = _mouse_dims(t)
        wires.append(_mouse_section(t * Lh * sz, a * sx, h * sy))
    return cq.Solid.makeLoft(wires, False)


@lru_cache(None)
def _mouse_raw():
    """Lofted shell sized to the 66 x 118 x 38 envelope by iterating the section scale (no geometry scaling)."""
    W, L, H = MS["size"]
    sx = sy = sz = 1.0
    for _ in range(4):
        s = _mouse_loft(sx, sy, sz)
        x0, y0, z0, x1, y1, z1 = _tight(s)
        sx *= W / (x1 - x0)
        sy *= H / (y1 - y0)
        sz *= L / (z1 - z0)
    s = _mouse_loft(sx, sy, sz)
    x0, y0, z0, x1, y1, z1 = _tight(s)
    return single(s.translate(Vector(-(x0 + x1) / 2, -y0, -(z0 + z1) / 2)))


def _tight(shape):
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    b = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape.wrapped, b, False, False)
    return b.Get()


def _mouse_place(shape):
    cx, cz = MS["stow_c"]
    return shape.translate(Vector(cx, MS["stow_y"], cz))


def _wheel_local():
    r = MS["wheel_d"] / 2
    w = MS["wheel_w"]
    wh = cyl_x(MS["wheel_cy"], MS["wheel_z"], r, -w / 2, w / 2)
    wh = fillet(wh, 1.2, wh.Edges(), "wheel")
    ribs = [cyl_x(MS["wheel_cy"], MS["wheel_z"], r + 0.2, x - 0.25, x + 0.25) for x in ()]
    return wh


def _skin(shape, d):
    return cut(shape, shape.translate(Vector(*d)))


def _mouse_profile_z(x, y, s=None):
    """Rear-most z of the raw shell at (x, y) (probe with a thin box)."""
    s = s or _mouse_raw()
    probe = single(s.intersect(box(x - 0.05, x + 0.05, y - 0.05, y + 0.05, 0, 100)))
    return _tight(probe)[5]


def _mouse_top_y(z, s=None):
    s = s or _mouse_raw()
    probe = single(s.intersect(box(-0.05, 0.05, 0, 100, z - 0.05, z + 0.05)))
    return _tight(probe)[4]


@lru_cache(None)
def _mouse_shell_local():
    s = _mouse_raw()
    r = MS["wheel_d"] / 2
    zc = MS["wheel_z"]
    slot = prism_y(-(MS["wheel_w"] / 2 + 0.8), MS["wheel_w"] / 2 + 0.8, zc - r - 1.5, zc + r + 1.5,
                   MS["wheel_cy"] - r - 2.0, 60, 1.5)
    # centre button split: thin cutter whose floor follows the top line ~1 mm down (planar, tilted)
    za, zb = zc - r - 1.0, -MS["size"][1] / 2 - 2
    ya, yb = _mouse_top_y(za + 0.5) - 1.0, _mouse_top_y(-MS["size"][1] / 2 + 6) - 1.0
    groove = (cq.Workplane("ZY", origin=(0.45, 0, 0)).polyline([(za, ya), (zb, yb - 1.2), (zb, 80), (za, 80)]).close()
              .extrude(0.9).val())
    s = cut(s, slot, groove, _mouse_glow_local())
    # receiver coil pocket
    s = cut(s, cyl_y(0, 0, MS["coil_d"][0] / 2 + 1.0, -1, MS["coil_t"] + 1.2))
    return s


@lru_cache(None)
def _mouse_glow_local():
    """Amber tail strip: shell skin at the rear between two planes, inner face a fitted cylinder 1.4 mm in."""
    s = _mouse_raw()
    y0, y1 = 3.6, 6.2
    ym = (y0 + y1) / 2
    half = 15.0
    t = 1.4
    z0 = _mouse_profile_z(0.0, ym, s) - t
    z1 = _mouse_profile_z(half, ym, s) - t
    zc = (z0 * z0 - z1 * z1 - half * half) / (2 * (z0 - z1))
    R = z0 - zc
    band = single(s.intersect(box(-half, half, y0, y1, zc, 100)))
    return cut(band, cyl_y(0, zc, R, y0 - 1, y1 + 1))


def mouse_shell():
    return _mouse_place(_mouse_shell_local())


def mouse_wheel():
    return _mouse_place(_wheel_local())


def mouse_glow():
    return _mouse_place(_mouse_glow_local())


def mouse_coil():
    d0, d1 = MS["coil_d"]
    t = MS["coil_t"]
    y0 = 0.7
    ring = cut(cyl_y(0, 0, d0 / 2, y0, y0 + t), cyl_y(0, 0, d1 / 2, y0 - 1, y0 + t + 1))
    return _mouse_place(ring)


# ----------------------------------------------------------------------------
# DESK MAT
# ----------------------------------------------------------------------------


def deskmat():
    dm = P["deskmat"]
    W, T, Dp = dm["size"]
    cx, cz = dm["c"]
    s = prism_y(cx - W / 2, cx + W / 2, cz - Dp / 2, cz + Dp / 2, 0, T, dm["corner_r"])
    return fillet(s, 1.2, edges_where(s, on_plane("y", T)), "deskmat")


# ----------------------------------------------------------------------------
# INTERNALS
# ----------------------------------------------------------------------------

I = P["internals"]


def compute_board():
    bd = I["board"]
    x0, x1 = bd["x"]
    z0, z1 = bd["z"]
    y0, y1 = bd["y"]
    pcb = prism_y(x0, x1, z0, z1, y0, y1, 3.0)
    pcb = cut(pcb, *[cyl_y(x, z, 1.6, y0 - 1, y1 + 1) for x in (x0 + 8, x1 - 8) for z in (z0 + 8, z1 - 8)])
    comps = []
    for kind, x, yc, w, h, st in IO_PORTS:
        comps.append(box(x - w / 2 - 0.4, x + w / 2 + 0.4, y1, y1 + h + 0.8 if kind != "rj45" else y1 + h + 1.0,
                         z0, z0 + (21.0 if kind == "rj45" else 14.0)))
    for i in range(4):
        comps.append(box(-506, -492, y1, y1 + 1.2, -102 + i * 17, -90 + i * 17))      # LPDDR5X
    for i in range(6):
        comps.append(box(-526, -519, y1, y1 + 5.0, -108 + i * 12, -101 + i * 12))     # VRM chokes
    comps.append(box(-590, -510, y1, y1 + 2.4, 62, 84))                               # M.2 2280 SSD
    comps.append(box(-588, -558, y1, y1 + 2.0, 24, 46))                               # M.2 2230 Wi-Fi
    comps.append(box(-338, -308, y1, y1 + 6.0, 70, 100))                              # display / power header
    return fuse(pcb, *comps)


def compute_heatsink():
    vc, fn = I["vapor_chamber"], I["fins"]
    plate = prism_y(vc["x"][0], vc["x"][1], vc["z"][0], vc["z"][1], vc["y"][0], vc["y"][1], 3.0)
    fins = []
    x = fn["x"][0]
    while x + fn["t"] <= fn["x"][1] + 1e-6:
        fins.append(box(x, x + fn["t"], fn["y"][0], fn["y"][1], fn["z"][0], fn["z"][1]))
        x += fn["pitch"]
    cap = box(fn["x"][0], fn["x"][1], fn["y"][1] - 0.6, fn["y"][1], fn["z"][0], fn["z"][0] + 6)
    return single(plate.fuse(*fins, cap, glue=True).clean())


def compute_fan():
    f = I["fan"]
    x0, x1 = f["x"]
    z0, z1 = f["z"]
    y0, y1 = f["y"]
    R = (x1 - x0) / 2 - 6
    cx, cz = (x0 + x1) / 2, z1 - R - 1
    body = cyl_y(cx, cz, R, y0, y1)
    duct = box(cx - R, cx + R - 10, y0, y1, z0, cz)
    s = fuse(body, duct)
    s = fillet(s, 1.5, edges_where(s, on_plane("y", y1)), "fan top")
    inlet = cut(cyl_y(cx, cz, 23, y1 - 1.2, y1 + 1), cyl_y(cx, cz, 9, y1 - 2, y1 + 2))
    blades = [box(-0.6, 0.6, y1 - 1.2, y1 + 1, 9.5, 22.5).rotate(Vector(0, 0, 0), Vector(0, 1, 0), i * 24 + 8)
              .translate(Vector(cx, 0, cz)) for i in range(15)]
    inlet = cut(inlet, *blades)
    out = box(cx - R + 3, cx + R - 13, y0 + 2, y1 - 2, z0 - 1, z0 + 2)
    return cut(s, inlet, out)


def psu():
    p = I["psu"]
    x0, x1 = p["x"]
    z0, z1 = p["z"]
    y0, y1 = p["y"]
    s = prism_y(x0, x1, z0, z1, y0, y1, 4.0)
    s = fillet(s, 1.5, edges_where(s, on_plane("y", y1)), "psu top")
    vents = [box(x0 + 14 + i * 7, x0 + 17 + i * 7, y1 - 0.8, y1 + 1, z0 + 30, z0 + 92) for i in range(16)]
    s = cut(s, *vents)
    ac = B["ac_inlet"]
    zb = B["z"][0] + B["wall"]
    inlet = stadium_z(ac["x"], ac["y"], 11.0, 6.4, zb, z0 + 0.5)
    pins = [cyl_z(ac["x"] + dx, ac["y"], 1.1, zb - 0.1, zb + 3) for dx in (-2.4, 2.4)]
    inlet = cut(inlet, *pins)
    return fuse(s, inlet)


def _coil(cx, cz):
    c = I["qi_coil"]
    y0, y1 = c["y"]
    r0, r1 = c["d"][0] / 2, c["d"][1] / 2
    s = cut(cyl_y(cx, cz, r0, y0, y1), cyl_y(cx, cz, r1, y0 - 1, y1 + 1))
    grooves = [cut(cyl_y(cx, cz, r + 0.35, y1 - 0.5, y1 + 1), cyl_y(cx, cz, r - 0.35, y1 - 1, y1 + 2))
               for r in [r1 + 3.0 + i * 3.0 for i in range(4)]]
    return cut(s, *grooves)


def _ferrite(cx, cz):
    f = I["ferrite"]
    a = f["size"] / 2
    return prism_y(cx - a, cx + a, cz - a, cz + a, f["y"][0], f["y"][1], 4.0)


def qi_coil_kb():
    return compound([_coil(x, I["qi_z"]) for x in I["qi_coils_kb_x"]])


def qi_coil_mouse():
    return _coil(I["qi_coil_mouse_x"], I["qi_z"])


def ferrite_kb():
    return compound([_ferrite(x, I["qi_z"]) for x in I["qi_coils_kb_x"]])


def ferrite_mouse():
    return _ferrite(I["qi_coil_mouse_x"], I["qi_z"])


def dock_board():
    db = I["dock_board"]
    x0, x1 = db["x"]
    z0, z1 = db["z"]
    y0, y1 = db["y"]
    pcb = prism_y(x0, x1, z0, z1, y0, y1, 3.0)
    cn = K["connector"]
    pogo = box(719, 725, y1, cn["boot_y"][0] - 0.5, cn["z"] - 6, cn["z"] + 6)
    chip = box(690, 712, y1, y1 + 1.4, -20, 2)
    pd = box(740, 756, y1, y1 + 2.0, -40, -24)
    lt = K["latch"]
    switch = box(744, 760, y1, lt["y"][0] - 0.5 - 6, 104, lt["pocket_z0"] - 1)
    return fuse(pcb, pogo, chip, pd, switch)


# ----------------------------------------------------------------------------
# registry
# ----------------------------------------------------------------------------

#  id, group, display name, material, internal, builder
PARTS = [
    ("display_screen", "display", "Active screen (2 x 27\" QHD)", "screen", False, display_screen),
    ("display_glass", "display", "Panel front glass & bezels", "glass_black", False, display_glass),
    ("display_seam", "display", "Titanium seam mullion", "titanium", False, display_seam),
    ("display_frame", "display", "Shroud front rim", "titanium", False, display_frame),
    ("display_back", "display", "Rear shroud & VESA keel", "graphite", False, display_back),
    ("display_spine", "display", "Steel VESA spine", "steel", True, display_spine),
    ("display_boards", "display", "Monitor scaler & power boards", "pcb", True, display_boards),

    ("neck", "stand", "Trapezoid neck", "graphite", False, neck),
    ("neck_light", "stand", "Neck light bar", "amber_led", False, neck_light),
    ("neck_badge", "stand", "NIGHT ARRAY inlay", "titanium", False, neck_badge),

    ("base_shell", "base", "Base shell", "titanium", False, base_shell),
    ("deck_liner", "base", "Graphite deck liner", "graphite", False, deck_liner),
    ("tray_pad_kb", "base", "Keyboard charging pad", "graphite", False, tray_pad_kb),
    ("tray_pad_mouse", "base", "Mouse charging pad", "graphite", False, tray_pad_mouse),
    ("base_glow", "base", "Front under-glow strip", "amber_led", False, base_glow),
    ("kb_charge_led", "base", "Keyboard charge indicator", "amber_led", False, kb_charge_led),
    ("mouse_charge_led", "base", "Mouse charge indicator", "amber_led", False, mouse_charge_led),
    ("base_feet", "base", "Recessed rubber feet", "rubber", False, base_feet),

    ("dock_cradle", "dock", "Dock cradle", "titanium", False, dock_cradle),
    ("dock_panels", "dock", "Oxblood accent panels", "oxblood", False, dock_panels),
    ("dock_latch", "dock", "Press-release latch", "graphite", False, dock_latch),
    ("dock_latch_led", "dock", "Latch status light", "amber_led", False, dock_latch_led),
    ("dock_connector", "dock", "Sprung USB-C connector", "steel", False, dock_connector),

    ("laptop_body", "laptop", "Laptop", "laptop_alu", False, laptop_body),

    ("keyboard_body", "keyboard", "Keyboard chassis", "graphite", False, keyboard_body),
    ("keyboard_keys", "keyboard", "Keycaps (75%)", "keycap", False, keyboard_keys),
    ("keyboard_coil", "keyboard", "Keyboard receiver coils", "copper", True, keyboard_coil),

    ("mouse_shell", "mouse", "Mouse shell", "graphite", False, mouse_shell),
    ("mouse_wheel", "mouse", "Scroll wheel", "rubber", False, mouse_wheel),
    ("mouse_glow", "mouse", "Mouse amber accent", "amber_led", False, mouse_glow),
    ("mouse_coil", "mouse", "Mouse receiver coil", "copper", True, mouse_coil),

    ("deskmat", "deskmat", "Felt desk mat", "felt", False, deskmat),

    ("compute_board", "internals", "Compute mainboard", "pcb", True, compute_board),
    ("compute_heatsink", "internals", "Vapor chamber & fin stack", "steel", True, compute_heatsink),
    ("compute_fan", "internals", "Slim blower", "graphite", True, compute_fan),
    ("psu", "internals", "Internal power supply", "graphite", True, psu),
    ("qi_coil_kb", "internals", "Qi2 coils, keyboard pocket", "copper", True, qi_coil_kb),
    ("qi_coil_mouse", "internals", "Qi2 coil, mouse pocket", "copper", True, qi_coil_mouse),
    ("ferrite_kb", "internals", "Ferrite shields, keyboard", "ferrite", True, ferrite_kb),
    ("ferrite_mouse", "internals", "Ferrite shield, mouse", "ferrite", True, ferrite_mouse),
    ("dock_board", "internals", "Dock PCB", "pcb", True, dock_board),
]

GROUP_ORDER = ["display", "stand", "base", "dock", "laptop", "keyboard", "mouse", "deskmat", "internals"]


def build_all(only=None, verbose=True):
    import time
    out = {}
    for pid, grp, name, mat, internal, fn in PARTS:
        if only and pid not in only:
            continue
        t = time.time()
        s = fn()
        if verbose:
            print(f"  {pid:18s} {time.time() - t:6.2f}s  solids={len(s.Solids())} valid={s.isValid()}", flush=True)
        out[pid] = s
    return out
