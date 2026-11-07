"""Night Array kit -- shared units, layout datums, tolerances and CAD primitives.

FROZEN INTERFACE (owner: CAD architect; changes go through the integrator).  Every other kit module imports
from here; nothing here imports another kit module.

Axes (SPEC.md section 1, app axes, mm): +X right, +Y up, +Z toward the user.  Desk y = 0, x = 0 at the display
seam, z = 0 at the base's front-to-back centre.  Everything is modelled in the STOW pose.

Contents
  LAYOUT        the shared datums every module builds against (base envelope, rows, tiling grid, seam axis,
                VESA, keep-outs, bays).  Numbers here are the contract; ARCHITECTURE.md explains them.
  TOL           print clearances and fits
  HW            hardware tables (heat-set inserts, screw clearances and heads, magnets, dowels, T-nuts)
  primitives    box / prism / cylinder / fillet / chamfer helpers (from the concept model, unchanged behaviour)
  facet frame   place_facet(), facet_point(): the two 10-degree toed-in monitor facets
  hardware      insert_boss(), screw_clearance(), magnet_pocket(), dowel_hole(), dowel_pin()
  tiling        split_solid(): cut a solid into <= 245 mm tiles along planes with dowel / insert joint features
  print spec    PrintSpec: filament, orientation to the bed, supports, infill, estimates
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import cadquery as cq
from cadquery import Vector

# =============================================================================
# units / global constants
# =============================================================================

MM = 1.0
PRINT_MAX = 245.0            # Bambu 256 bed minus 5 mm margin each side: every printed part fits 245^3
TOE_IN_DEG = 10.0
COS_T = math.cos(math.radians(TOE_IN_DEG))
SIN_T = math.sin(math.radians(TOE_IN_DEG))
TAN_T = math.tan(math.radians(TOE_IN_DEG))

# densities, g/cm3
DENSITY = {
    "steel": 7.85, "aluminium": 2.70, "petg": 1.27, "petg_cf": 1.25, "pla": 1.24, "pc": 1.20,
}

# =============================================================================
# tolerances (printed parts)
# =============================================================================

TOL = {
    "print_clear": 0.2,      # per side, sliding/assembly fit between two printed parts (the kit standard)
    "print_locate": 0.1,     # per side, locating fit (dowel in its hole when one side is a press)
    "purchased_clear": 0.5,  # per side, printed pocket around a purchased part (measured-on-arrival parts: 1.0)
    "purchased_loose": 1.0,  # per side, around parts whose size we only know from photos / a 3D model
    "paint": 0.15,           # per painted face (primer + metallic + clear), see research
    "hole_comp": 0.1,        # printed holes come out ~0.1 mm small in diameter: add to vertical holes
    "steel_cut": 0.127,      # SendCutSend laser cut tolerance
    "steel_bend_deg": 2.0,   # SendCutSend bend tolerance on parts > 24 in (1 deg below)
}

# =============================================================================
# hardware tables
# =============================================================================

# ruthex / CNC Kitchen heat-set inserts.  hole = modelled hole diameter (compromise between the two brands where
# they differ), depth = min hole depth (L + 1), boss = min boss OD (conservative d1 + 2W), len = insert length.
INSERT = {
    "M3": {"len": 5.7, "od": 4.6, "hole": 4.0, "depth": 6.7, "boss": 7.8, "wall": 1.6},
    "M4": {"len": 8.1, "od": 6.3, "hole": 5.65, "depth": 9.1, "boss": 10.5, "wall": 2.1},
    "M5": {"len": 9.5, "od": 7.1, "hole": 6.45, "depth": 10.5, "boss": 12.3, "wall": 2.6},
}

# clearance holes (ISO 273 medium) and head sizes: ISO 7380 button head, ISO 4762 socket head, ISO 10642 csk
SCREW = {
    "M3": {"clear": 3.4, "b7380_d": 5.7, "b7380_k": 1.65, "s4762_d": 5.5, "s4762_k": 3.0},
    "M4": {"clear": 4.5, "b7380_d": 7.6, "b7380_k": 2.2, "s4762_d": 7.0, "s4762_k": 4.0},
    "M5": {"clear": 5.5, "b7380_d": 9.5, "b7380_k": 2.75, "s4762_d": 8.5, "s4762_k": 5.0},
    "M6": {"clear": 6.6, "b7380_d": 10.5, "b7380_k": 3.3, "s4762_d": 10.0, "s4762_k": 6.0, "csk10642_d": 12.0},
}

# magnets: K&J D42-N52 (primary) and supermagnete S-06-03-N (alternate); pocket = glued slip fit
MAGNET = {
    "D42": {"d": 6.35, "t": 3.175, "pocket_d": 6.55, "pocket_depth": 3.4},
    "S0603": {"d": 6.0, "t": 3.0, "pocket_d": 6.2, "pocket_depth": 3.2},
}

# Joint standard between printed tiles (ARCHITECTURE.md "Joint standard"):
#   printed PETG dowel pins 6.0 x 16 (printed standing, 100 % infill), hole 6.4 dia x 8.5 deep in each tile
#   (0.2 clearance per side), plus M3 x 10 ISO 7380 through a 3.4 hole in one tile's boss into an M3 x 5.7
#   insert in the other's.  Dowels at <= 120 mm pitch along every joint, >= 12 mm from any outer face.
DOWEL = {"d": 6.0, "len": 16.0, "hole_d": 6.4, "hole_depth": 8.5, "pitch_max": 120.0, "edge_min": 12.0,
         "chamfer": 0.6}
JOINT_SCREW = {"size": "M3", "len": 10.0, "head": "ISO 7380", "boss_clear_t": 4.0}

# T-slot (ZYLtech / Misumi 20-series): 6 mm slot, hammer nut M5
TSLOT = {"slot_w": 6.0, "slot_depth": 6.1, "hammer_nut": "M5", "screw_rail": "M5x10 ISO 7380"}

# =============================================================================
# LAYOUT -- the shared datums (mm, app axes).  ARCHITECTURE.md is the prose version of this block.
# =============================================================================

LAYOUT = {
    # ---- base envelope ---------------------------------------------------------------------------------
    "base": {
        "x": [-640.0, 650.0], "z": [-165.0, 165.0], "height": 50.0,   # KIT_SPEC: h <= 50, depth <= 330
        "corner_r": 40.0, "rim_w": 16.0, "deck_y": 46.0,               # rim top 50, recessed deck 46
        "plinth_x": [-360.0, 360.0],                                   # rear-row centre stays at rim height (strip bay)
        "skirt_y": 2.0,                                                # printed walls stop 2 mm above the desk
        "wall": 3.0, "deck_t": 2.5,
        "row_joint_z": -37.0,                                          # rear 'spine' row | front 'pocket' row
        "tile_joints_x": [-455.0, -280.0, -125.0, 115.0, 355.0, 500.0],  # same in both rows (deliberate reveals)
        "reveal": {"w": 1.2, "depth": 0.8},                            # V-reveal on every visible tile joint
    },
    # ---- display / monitors --------------------------------------------------------------------------
    "display": {
        "toe_in_deg": TOE_IN_DEG,
        "seam_axis_xz": [0.0, -76.9],     # vertical fold axis through the front faces of both screens at the seam
        "seam_gap": 0.84,                 # housing-to-housing gap at the seam (16.16 bezels + 0.84 = 17.0 seam)
        "face_bottom_y": 156.0,           # housing face bottom edge (not the logo nub)
        "vesa_y": 337.2,                  # = face_bottom_y + 181.2 (S60UD VESA centre above face bottom)
        "vesa_spacer": 10.0,              # Al spacers in the 8.2 deep VESA pocket -> wing web front at w = -41.4
    },
    # ---- structure (interfaces only; geometry in structure.py) -----------------------------------------
    "structure": {
        "foot_h": 7.6,                    # 3M SJ5023 under every foot (steel only)
        "plate_t": 6.35,                  # 1/4 in A36
        "bracket_t": 4.78,                # 3/16 in A36
        "posts_x": [-45.0, 45.0],         # 2040 post centres
        "posts_z": [-158.0, -118.0],      # strong axis fore-aft (40 mm in z)
        "post_len": 400.0,                # ZYLtech EXT-2040-REG-400, not cut
        "rail_front": {"z": [136.0, 156.0], "y0": 20.3},
        "rail_mid": {"z": [-47.0, -27.0], "y0": 23.0},
    },
    # ---- Qi charging (keyboard / mouse) ------------------------------------------------------------------
    "qi": {
        "pad": [100.0, 100.0, 11.2],      # Anker 313 A2503
        "kb_floor_y": 27.0,               # keyboard pocket floor top (device surface); 1.0 solid PETG over the coil
        "mouse_floor_y": 22.0,
        "floor_over_coil": 1.0,
        "kb_coil": [-202.8, 45.0], "kb_adjust": [12.5, 10.0],          # +- x, +- z carrier travel
        "mouse_coil": [250.0, 50.0], "mouse_adjust": [10.0, 10.0],
        "keepout_metal": 10.0, "keepout_steel": 20.0,                 # grown from the pad footprint incl. travel
        "keepout_above": 10.0,                                         # keep-out volume ends 10 mm above the floor
    },
    # ---- devices (stow) ----------------------------------------------------------------------------------
    "keyboard": {"x": [-250.31, 70.31], "z": [0.0, 126.0]},            # K3 Ultra 320.62 x 126
    "mouse": {"c": [250.0, 50.0]},                                      # Lenovo X9 59 x 101 x 34
    "dock": {"x": [650.0, 775.0], "z": [-150.0, 150.0], "slot_axis_x": 722.0},
}

L = LAYOUT


def seam_z():
    return LAYOUT["display"]["seam_axis_xz"][1]


# =============================================================================
# primitives (behaviour identical to the concept model.py)
# =============================================================================

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


def poly_y(pts_xz, y0, y1):
    """Plan polygon [(x, z), ...] extruded vertically between y0 and y1."""
    wp = cq.Workplane("XZ", origin=(0, y1, 0))
    return wp.polyline([(x, z) for x, z in pts_xz]).close().extrude(y1 - y0).val()


def poly_x(pts_zy, x0, x1):
    """Side-view polygon [(z, y), ...] extruded along +X between x0 and x1."""
    wp = cq.Workplane("ZY", origin=(x1, 0, 0))
    return wp.polyline(list(pts_zy)).close().extrude(x1 - x0).val()


def poly_z(pts_xy, z0, z1):
    """Front-view polygon [(x, y), ...] extruded along +Z between z0 and z1."""
    wp = cq.Workplane("XY", origin=(0, 0, z0))
    return wp.polyline(list(pts_xy)).close().extrude(z1 - z0).val()


def cyl_y(cx, cz, r, y0, y1):
    return cq.Solid.makeCylinder(r, y1 - y0, Vector(cx, y0, cz), Vector(0, 1, 0))


def cyl_x(cy, cz, r, x0, x1):
    return cq.Solid.makeCylinder(r, x1 - x0, Vector(x0, cy, cz), Vector(1, 0, 0))


def cyl_z(cx, cy, r, z0, z1):
    return cq.Solid.makeCylinder(r, z1 - z0, Vector(cx, cy, z0), Vector(0, 0, 1))


def cyl_axis(p0, p1, r):
    """Cylinder between two points."""
    a, b = Vector(*p0), Vector(*p1)
    d = b - a
    return cq.Solid.makeCylinder(r, d.Length, a, d.normalized())


def stadium_y(cx, cz, length, width, y0, y1, along="x"):
    wp = cq.Workplane("XZ", origin=(0, y1, 0)).center(cx, cz)
    return wp.slot2D(length, width, 0 if along == "x" else 90).extrude(y1 - y0).val()


def stadium_z(cx, cy, length, width, z0, z1, along="x"):
    wp = cq.Workplane("XY", origin=(0, 0, z0)).center(cx, cy)
    return wp.slot2D(length, width, 0 if along == "x" else 90).extrude(z1 - z0).val()


def compound(shapes):
    return cq.Compound.makeCompound([s for s in shapes if s is not None])


def single(shape):
    """Return the lone Solid inside a compound result, else the shape itself."""
    sols = shape.Solids()
    if len(sols) == 1:
        return sols[0]
    return shape


def fuse(*shapes):
    shapes = [s for s in shapes if s is not None]
    if len(shapes) == 1:
        return shapes[0]
    return single(shapes[0].fuse(*shapes[1:]).clean())


def cut(a, *tools):
    tools = [t for t in tools if t is not None]
    if not tools:
        return a
    return single(a.cut(*tools).clean())


def intersect(a, b):
    return single(a.intersect(b).clean())


def edges_where(shape, pred):
    out = []
    for e in shape.Edges():
        bb = e.BoundingBox()
        if pred(e.Center(), bb, e):
            out.append(e)
    return out


FILLET_LOG: list[str] = []


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
    i = "xyz".index(axis)

    def pred(c, bb, e):
        lo = (bb.xmin, bb.ymin, bb.zmin)[i]
        hi = (bb.xmax, bb.ymax, bb.zmax)[i]
        return abs(lo - value) <= tol and abs(hi - value) <= tol

    return pred


def vertical_edges(min_len=1.0):
    return lambda c, bb, e: (bb.ymax - bb.ymin) > min_len and (bb.xmax - bb.xmin) < 1e-3 and (bb.zmax - bb.zmin) < 1e-3


def frame_plane(origin, xdir, normal):
    return cq.Plane(origin=Vector(*origin), xDir=Vector(*xdir), normal=Vector(*normal))


def to_frame(shape, plane):
    """Move a shape built around the global origin (XY = face, +Z = outward) onto `plane`."""
    return shape.moved(cq.Location(plane))


def _perp(n):
    n = Vector(*n).normalized()
    a = Vector(1, 0, 0) if abs(n.x) < 0.9 else Vector(0, 1, 0)
    return n.cross(a).normalized()


def halfspace(point, normal, size=4000.0):
    """Solid filling the half-space on the +normal side of the plane through `point`."""
    pl = frame_plane(point, _perp(normal).toTuple(), Vector(*normal).normalized().toTuple())
    return to_frame(box(-size, size, -size, size, 0, size), pl)


def tight_bbox(shape):
    """(x0, y0, z0, x1, y1, z1) from OCC's optimal box (tight on splines)."""
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    b = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape.wrapped, b, False, False)
    return b.Get()


def centroid(shape):
    """Volume centroid (x, y, z) and volume of a shape (all solids)."""
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    g = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape.wrapped, g)
    c = g.CentreOfMass()
    return (c.X(), c.Y(), c.Z()), g.Mass()


# =============================================================================
# facet frame: the two monitors, toed in about the seam axis
# =============================================================================
# Facet frame: u = along the panel away from the seam axis, y = up, w = the panel's front normal (toward the user).
# The right panel (side +1) is rotated -10 deg about +Y and moved to the seam axis; the left is its mirror in YZ.

def facet_point(side, u, y, w=0.0):
    """World point of facet-frame (u, y, w).  side = +1 right panel, -1 left panel."""
    sx, sz = LAYOUT["display"]["seam_axis_xz"]
    x = side * (u * COS_T - w * SIN_T)
    z = sz + u * SIN_T + w * COS_T
    return (x, y, z)


def facet_u_w(side, x, z):
    """Inverse of facet_point in plan: world (x, z) -> facet (u, w)."""
    sx, sz = LAYOUT["display"]["seam_axis_xz"]
    xs = side * x
    dz = z - sz
    return xs * COS_T + dz * SIN_T, -xs * SIN_T + dz * COS_T


def place_facet(shape, side=1, trim=False):
    """Facet-frame shape (u = X, y = Y, w = Z) -> world, right panel; mirrored in YZ for side = -1.
    trim=True keeps only x >= 0 before mirroring (for shells that meet at the seam)."""
    s = shape.rotate(Vector(0, 0, 0), Vector(0, 1, 0), -TOE_IN_DEG).translate(Vector(0, 0, seam_z()))
    if trim:
        s = single(s.intersect(box(0, 3000, -100, 3000, -3000, 3000)))
    if side < 0:
        s = s.mirror("YZ")
    return s


def both_facets(local_shape, trim=False):
    return place_facet(local_shape, 1, trim), place_facet(local_shape, -1, trim)


# =============================================================================
# hardware primitives (all return solids in world coordinates; axis = 'y' up by default)
# =============================================================================

def _cyl_along(axis, c, r, a0, a1):
    """Cylinder radius r along `axis` ('x'|'y'|'z' or '-x' etc.) through point c, from a0 to a1 along that axis."""
    ax = axis[-1]
    x, y, z = c
    lo, hi = min(a0, a1), max(a0, a1)
    if ax == "x":
        return cyl_x(y, z, r, lo, hi)
    if ax == "y":
        return cyl_y(x, z, r, lo, hi)
    return cyl_z(x, y, r, lo, hi)


def insert_boss(size, c, axis="y", top=None, height=None, extra_wall=0.0):
    """(boss solid, hole cutter) for a heat-set insert.  `c` = point on the boss's top face centre (the face the
    insert goes in from); the boss extends `height` against the axis direction ('-y' means the insert goes in
    from below, the boss grows up).  Fuse the boss, then cut the hole."""
    ins = INSERT[size]
    ax = axis[-1]
    sgn = -1.0 if axis.startswith("-") else 1.0
    i = "xyz".index(ax)
    h = height if height is not None else ins["depth"] + 1.5
    a1 = c[i]
    a0 = a1 - sgn * h
    r = ins["boss"] / 2 + extra_wall
    boss = _cyl_along(ax, c, r, a0, a1)
    hole = _cyl_along(ax, c, ins["hole"] / 2, a1 + sgn * 1.0, a1 - sgn * ins["depth"])
    return boss, hole


def screw_clearance(size, c, axis="y", length=20.0, head=None, head_depth=0.0):
    """Clearance-hole cutter for `size` from point c going `length` against the axis; optional counterbore for an
    ISO 7380 ('b7380') or ISO 4762 ('s4762') head of depth head_depth at c."""
    s = SCREW[size]
    ax = axis[-1]
    sgn = -1.0 if axis.startswith("-") else 1.0
    i = "xyz".index(ax)
    a1 = c[i] + sgn * 1.0
    a0 = c[i] - sgn * length
    cut_ = _cyl_along(ax, c, s["clear"] / 2, a0, a1)
    if head:
        hd = s[head + "_d"] + 1.0
        cut_ = fuse(cut_, _cyl_along(ax, c, hd / 2, c[i] - sgn * head_depth, c[i] + sgn * 2.0))
    return cut_


def magnet_pocket(kind, c, axis="y"):
    """Pocket cutter for a disc magnet, open at c, going against the axis (glue it in, mind the polarity)."""
    m = MAGNET[kind]
    ax = axis[-1]
    sgn = -1.0 if axis.startswith("-") else 1.0
    i = "xyz".index(ax)
    return _cyl_along(ax, c, m["pocket_d"] / 2, c[i] + sgn * 1.0, c[i] - sgn * m["pocket_depth"])


def dowel_hole(c, axis="x", depth=None):
    """Blind hole for the printed dowel, both directions from the joint plane point c along axis (both tiles)."""
    d = DOWEL
    ax = axis[-1]
    i = "xyz".index(ax)
    dep = depth if depth is not None else d["hole_depth"]
    return _cyl_along(ax, c, d["hole_d"] / 2, c[i] - dep, c[i] + dep)


def dowel_pin(c, axis="x"):
    d = DOWEL
    ax = axis[-1]
    i = "xyz".index(ax)
    return _cyl_along(ax, c, d["d"] / 2, c[i] - d["len"] / 2, c[i] + d["len"] / 2)


# =============================================================================
# tiling helper
# =============================================================================

@dataclass
class Joint:
    """One cut plane of a tiled part: axis 'x'|'y'|'z', value, and the dowel points on it as (a, b) in the other two
    axes (in xyz order without the cut axis, e.g. for axis 'x' -> (y, z))."""
    axis: str
    value: float
    dowels: list = field(default_factory=list)
    reveal: bool = True


def _halfbox(axis, value, side, big=5000.0):
    lo, hi = (-big, value) if side < 0 else (value, big)
    b = [-big, big, -big, big, -big, big]
    i = "xyz".index(axis)
    b[2 * i], b[2 * i + 1] = lo, hi
    return box(*b)


def split_solid(shape, joints, name="part", dowels=True, min_volume=1.0):
    """Split `shape` at every joint plane.  Returns [(piece_name, solid)], pieces ordered by their position
    (x, then z, then y).  Dowel holes are cut into both sides of each joint at the joint's dowel points.

    Piece names: `name` + '_' + index letters per axis, e.g. base_x3z1.  Pieces smaller than min_volume are
    dropped (slivers).  The caller adds insert bosses (they depend on the inside of the part)."""
    pieces = [(name, shape)]
    for jt in joints:
        nxt = []
        for nm, s in pieces:
            lo = s.intersect(_halfbox(jt.axis, jt.value, -1))
            hi = s.intersect(_halfbox(jt.axis, jt.value, +1))
            for part_, tag in ((lo, "a"), (hi, "b")):
                sols = [x for x in part_.Solids() if x.Volume() > min_volume]
                if not sols:
                    continue
                nxt.append((nm, compound(sols) if len(sols) > 1 else sols[0]))
        pieces = nxt
    if dowels:
        holes = []
        for jt in joints:
            others = [a for a in "xyz" if a != jt.axis]
            for a, b in jt.dowels:
                p = {jt.axis: jt.value, others[0]: a, others[1]: b}
                holes.append(dowel_hole((p["x"], p["y"], p["z"]), jt.axis))
        if holes:
            hc = compound(holes)
            pieces = [(nm, single(s.cut(hc).clean())) for nm, s in pieces]
    # stable order and names
    def key(p):
        x0, y0, z0, x1, y1, z1 = tight_bbox(p[1])
        return (round((x0 + x1) / 2, 1), round((z0 + z1) / 2, 1), round((y0 + y1) / 2, 1))
    pieces.sort(key=key)
    return [(f"{name}_{i + 1:02d}", s) for i, (nm, s) in enumerate(pieces)]


def print_fit(shape, limit=PRINT_MAX):
    """(fits, sorted dims) -- does the part's axis-aligned box fit the printer cube in some axis-aligned orientation?
    (Every kit print is laid flat on a principal face, so the axis-aligned check is the honest one.)"""
    x0, y0, z0, x1, y1, z1 = tight_bbox(shape)
    dims = sorted([x1 - x0, y1 - y0, z1 - z0], reverse=True)
    return dims[0] <= limit + 1e-6, dims


# =============================================================================
# print-orientation record
# =============================================================================

FILAMENT = {
    # key: (Bambu product, colour code, material, density g/cm3, note)
    "petg_titanium": ("Bambu PETG Basic Gray", "30107", "PETG", 1.27, "prime + Rust-Oleum 245220 Titanium Silver"),
    "petg_beige": ("Bambu PETG Basic Dark Beige", "30403", "PETG", 1.27, "raw-colour titanium alternative"),
    "petg_cf_graphite": ("Bambu PETG-CF Titan Gray", "31101", "PETG-CF", 1.25, "hardened nozzle"),
    "pla_oxblood": ("Bambu PLA Basic Maroon Red", "10205", "PLA", 1.24, "cool accents only"),
    "petg_clear": ("Bambu PETG Translucent Clear", "32101", "PETG", 1.25, "light pipes / diffusers"),
    "petg_black": ("Bambu PETG Basic Black", "30105", "PETG", 1.27, "IR-opaque liners, hidden parts"),
}


@dataclass
class PrintSpec:
    """How a printed part goes on the bed.  `down` = the part face that lies on the build plate, as an app-axes
    direction ('-y' = its bottom face down, '+y' = upside down, '+z' = front face down ...).  Estimates are
    filled by build.py from the volume (shell + infill model) unless given."""
    filament: str = "petg_titanium"
    down: str = "-y"
    supports: str = "none"
    infill: float = 0.15
    walls: int = 3
    layer: float = 0.2
    note: str = ""
    plate: str | None = None
    grams: float | None = None
    minutes: float | None = None


def print_mass_g(volume_mm3, area_mm2, spec: PrintSpec):
    """Printed mass: perimeter shell (walls x 0.45 mm line, solid top/bottom ~ same) over the surface area, plus
    infill on the remaining core.  Good to ~15 % for slicer-style parts."""
    dens = FILAMENT[spec.filament][3]
    shell_t = max(spec.walls * 0.45, 0.8)
    shell = min(volume_mm3, area_mm2 * shell_t * 0.5)       # each wall is shared by two faces on thin parts
    core = max(volume_mm3 - shell, 0.0)
    return (shell + core * spec.infill) / 1000.0 * dens


def print_minutes(grams):
    """Bambu P1S/X1C class at 0.2 mm, PETG: ~ 0.9-1.1 min per gram including travel; use 1.0."""
    return grams * 1.0


# =============================================================================
# part registry record (each module exposes PARTS = [PartDef(...), ...])
# =============================================================================

@dataclass
class PartDef:
    id: str
    group: str
    name: str
    material: str                 # scene.json material key
    kind: str                     # printed | purchased | metal | hardware
    builder: object               # () -> cq.Shape (world, stow pose)
    internal: bool = False
    bom: str | None = None        # parts.json id (purchased / hardware / metal)
    print: PrintSpec | None = None
    mass_g: float | None = None   # override (purchased parts: research weight); None = volume x density
    mass_note: str | None = None
    split: str | None = None      # for printed parts not yet tiled: how they will be split (must say <= 245)
    owner: str = "architect"      # module owner for the next phase
    note: str = ""
