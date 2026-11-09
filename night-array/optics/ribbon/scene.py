"""Light-ribbon optics: scene description.

The station is modelled as a cross-section in the (z, y) plane, extruded along x over the
station width. Units are mm, in the Night Array app axes (SPEC.md section 1): +Y up, +Z toward
the user, y = 0 is the desk, z = 0 is the front-to-back centre of the base.

Numbers that come from SPEC.md:
  * screen front plane at the seam  z = -62
  * active area starts at           y = 172 (16 mm chin, y 156..172)
  * active width per panel 596.7 mm, 2560 px -> 0.2331 mm pixel pitch
  * the seam: 14 mm with no pixels (7 mm each side of x = 0)
  * base top y = 36, keyboard pocket starts at z = -6

Simplifications (stated in the README):
  * the 10 deg toe-in of each panel is ignored: the band, reflector and cove are straight
    and 1200 mm wide;
  * the neck (320 mm wide at the back, centre only) is not modelled;
  * the screen face is an emitter and an absorber (anti-glare film, no specular reflection).
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
import math

import numpy as np

PIXEL_PITCH = 596.7 / 2560.0  # mm per pixel row/column

# ---------------------------------------------------------------- materials
# kind: 'emit_band' | 'emit_screen' | 'mirror' | 'brdf'
# brdf = Lambert (rho_d) + GGX microfacet (F0, alpha); alpha is the GGX alpha (not squared).


@dataclass(frozen=True)
class Material:
    name: str
    kind: str = "brdf"
    rho_d: float = 0.0
    f0: float = 0.04
    alpha: float = 0.3
    reflectance: float = 0.0   # mirrors


MATERIALS = {
    "band": Material("band", kind="emit_band"),
    "screen": Material("screen", kind="emit_screen"),
    # protected aluminium first-surface mirror (~92 % in the visible)
    "mirror": Material("mirror", kind="mirror", reflectance=0.92),
    # glossy black glass of the panel chin
    "black_glass": Material("black_glass", rho_d=0.01, f0=0.04, alpha=0.05),
    # the station's charcoal graphite finish: dark, satin (lips, sidewalls, awning cap)
    "graphite": Material("graphite", rho_d=0.05, f0=0.04, alpha=0.35),
    # flat black flocked paint inside the reflector housing / back wall
    "black_matte": Material("black_matte", rho_d=0.03, f0=0.02, alpha=0.6),
    "desk": Material("desk", rho_d=0.25, f0=0.04, alpha=0.4),
    # candidate finishes for the ribbon surface
    "matte_white": Material("matte_white", rho_d=0.85, f0=0.0, alpha=1.0),
    "satin_white": Material("satin_white", rho_d=0.70, f0=0.04, alpha=0.25),
    "satin_titanium": Material("satin_titanium", rho_d=0.0, f0=0.55, alpha=0.25),
    "satin_titanium_fine": Material("satin_titanium_fine", rho_d=0.0, f0=0.55, alpha=0.12),
    "satin_titanium_coarse": Material("satin_titanium_coarse", rho_d=0.0, f0=0.55, alpha=0.40),
    "polished_titanium": Material("polished_titanium", rho_d=0.0, f0=0.55, alpha=0.04),
    "satin_aluminium": Material("satin_aluminium", rho_d=0.0, f0=0.90, alpha=0.25),
    "satin_oxblood": Material("satin_oxblood", rho_d=0.08, f0=0.40, alpha=0.25),
}
MAT_IDS = {k: i for i, k in enumerate(MATERIALS)}


# ---------------------------------------------------------------- design parameters
@dataclass(frozen=True)
class Design:
    name: str = "satin cove"
    # light band (bottom rows of the active area)
    band_h: float = 12.0            # mm of screen height given to the band
    band_lum: float = 350.0         # cd/m^2 at full white, on axis (S60UD typical)
    lcd_exponent: float = 0.7       # IPS luminance falls as cos(theta)^n off axis
    louver_deg: float | None = None  # optional privacy/louver film: horizontal cut-off angle
    louver_t: float = 0.7           # its on-axis transmission
    seam_gap: float = 14.0          # mm with no pixels at x = 0
    # concealed reflector ("awning"): starts at the band's top edge, slopes forward-down
    mirror_deg: float = 45.0        # angle below horizontal
    mirror_bottom_y: float = 158.0  # lower edge height (below the band, in front of the chin)
    reflector: str = "flat"         # "flat" | "parabolic"
    # parabolic reflector: focus on the band centre, beam axis tilted psi back from straight down
    refl_f: float | None = None     # focal length (mm); None = smallest that clears the band
    refl_psi: float = 20.0          # beam tilt behind vertical (deg)
    refl_theta_min: float = -60.0   # lowest emission angle the reflector still catches (deg, 0 = straight out)
    chin_finish: str = "black_glass"  # "mirror" = reflective film on the 16 mm chin below the band
    # the cove that receives the light
    ramp_deg: float = 30.0          # receiving surface rises toward the back at this angle
    ramp_finish: str = "satin_titanium"
    ramp_sag: float = 0.0           # curvature of the ribbon surface: sagitta in mm (+ concave, - convex)
    floor_y: float = 18.0           # foot of the ramp (base top is y = 36)
    cove_front_z: float = -20.0     # front lip of the cove (keyboard pocket begins at z = -6)
    cove_back_z: float = -140.0     # back wall (the base ends at z = -150)
    lip_h: float = 4.0              # front lip stands this far above the deck (y = 36)
    width: float = 1200.0
    # scale < 1 shrinks the cove about the band's bottom edge (z = -62, y = 172); pass band_h and refl_f
    # already scaled. Below ~0.8 the cove becomes a shelf hanging under the display, clear of the base.
    scale: float = 1.0
    # viewer
    eye: tuple = (0.0, 460.0, 650.0)  # (x, y, z); seated eye ~460 mm above the desk, ~710 mm from the glass

    def with_(self, **kw) -> "Design":
        return replace(self, **kw)

    @property
    def band_rows(self) -> int:
        return int(round(self.band_h / PIXEL_PITCH))


SCREEN_Z = -62.0
ACTIVE_BOTTOM = 172.0
ACTIVE_TOP = 507.7
CHIN_BOTTOM = 156.0
BASE_TOP = 36.0
BASE_FRONT_Z = 150.0


@dataclass
class Scene:
    design: Design
    p0: np.ndarray            # (S, 2) as (z, y)
    p1: np.ndarray
    mat_front: np.ndarray     # material id hit from the +normal side
    mat_back: np.ndarray      # material id hit from the -normal side
    finite: np.ndarray        # True: exists only for |x| <= width/2
    labels: list
    cap_poly: np.ndarray      # (K, 2) closed polygon of the cove end caps (z, y)
    band_y0: float
    band_y1: float

    @property
    def normals(self):
        t = self.p1 - self.p0
        t = t / np.linalg.norm(t, axis=1, keepdims=True)
        return np.stack([-t[:, 1], t[:, 0]], axis=1)  # (z, y), left of p0->p1


def reflector_points(d: Design, y0: float, y1: float) -> np.ndarray:
    """Reflector profile as (z, y) points from its top edge (on the screen plane) downward."""
    z_s = SCREEN_Z
    if d.reflector == "flat":
        a = math.radians(d.mirror_deg)
        L = (y1 - d.mirror_bottom_y) / math.sin(a)
        return np.array([(z_s, y1), (z_s + L * math.cos(a), d.mirror_bottom_y)])
    # Off-axis parabola with its focus at the band centre. Rays from the focus leave along the
    # axis u, which points down and psi degrees back toward the display.
    yc = 0.5 * (y0 + y1)
    psi = math.radians(d.refl_psi)
    theta_u = -math.pi / 2 - psi                      # direction angle of u in the (z, y) plane
    f = d.refl_f if d.refl_f is not None else (0.5 * (y1 - y0) + 1.0) * (1 + math.cos(psi)) / 2
    pts = []
    for th in np.linspace(math.pi / 2, math.radians(d.refl_theta_min), 40):
        gamma = abs(th - theta_u)
        r = 2 * f / (1 - math.cos(gamma))
        pts.append((z_s + r * math.cos(th), yc + r * math.sin(th)))
    pts = np.array(pts)
    if pts[0, 1] < y1 + 0.5:
        raise ValueError("parabola meets the screen inside the band: increase refl_f")
    return pts


def build_scene(d: Design) -> Scene:
    segs = []   # (p0, p1, front, back, finite, label); "front" = side the normal points to

    def seg(a, b, front, back=None, finite=True, label=""):
        segs.append((a, b, front, back or front, finite, label))

    z_s = SCREEN_Z
    y0, y1 = ACTIVE_BOTTOM, ACTIVE_BOTTOM + d.band_h
    # Screen face, going down so the normal (left of the direction) points +z (toward the user).
    refl_top = reflector_points(d, y0, y1)[0, 1]
    seg((z_s, ACTIVE_TOP), (z_s, refl_top), "screen", "black_matte", label="screen content")
    if refl_top > y1 + 1e-6:
        # rows inside the reflector above the band: held black by the OS
        seg((z_s, refl_top), (z_s, y1), "black_matte", label="hidden rows (black)")
    seg((z_s, y1), (z_s, y0), "band", "black_matte", label="light band")
    seg((z_s, y0), (z_s, CHIN_BOTTOM), d.chin_finish, "black_matte", label="chin")
    # Display underside, from the glass back to the cove back wall (normal down).
    seg((z_s, CHIN_BOTTOM), (d.cove_back_z, CHIN_BOTTOM), "black_matte", label="display underside")

    # Reflector ("awning"): mirror face toward the band, graphite cap toward the user.
    refl_pts = reflector_points(d, y0, y1)
    for a_, b_ in zip(refl_pts[:-1], refl_pts[1:]):
        # polyline runs top -> bottom around the band; its left normal points away from the band
        seg(tuple(a_), tuple(b_), "graphite", "mirror", label="reflector (cap / mirror)")
    m1 = refl_pts[-1]

    # Cove: ramp from the front foot up to the back wall (optionally scaled about the band's bottom edge).
    k = d.scale
    sz = lambda z: z_s + (z - z_s) * k
    sy = lambda y: ACTIVE_BOTTOM + (y - ACTIVE_BOTTOM) * k
    b = math.radians(d.ramp_deg)
    zf, zb = sz(d.cove_front_z), sz(d.cove_back_z)
    floor_y = sy(d.floor_y)
    y_top = floor_y + (zf - zb) * math.tan(b)
    y_top = min(y_top, CHIN_BOTTOM - 5.0 * k)
    A_, B_ = np.array([zb, y_top]), np.array([zf, floor_y])
    nrm = np.array([-(B_ - A_)[1], (B_ - A_)[0]]); nrm /= np.linalg.norm(nrm)   # up/forward
    ts = np.linspace(0, 1, 17 if d.ramp_sag else 2)
    rp = A_[None] + ts[:, None] * (B_ - A_)[None] - (4 * d.ramp_sag * k * ts * (1 - ts))[:, None] * nrm[None]
    for a_, b_ in zip(rp[:-1], rp[1:]):
        seg(tuple(a_), tuple(b_), d.ramp_finish, "black_matte", label="ribbon surface")
    seg((zb, CHIN_BOTTOM), (zb, y_top), "black_matte", label="back wall")
    lip_top = sy(BASE_TOP + d.lip_h)
    lw = 12.0 * k
    seg((zf, floor_y), (zf, lip_top), "graphite", label="front lip (inside)")
    seg((zf, lip_top), (zf + lw, lip_top), "graphite", label="lip top")
    if k >= 0.999:
        seg((zf + lw, lip_top), (zf + lw, BASE_TOP), "graphite", label="lip front")
        seg((zf + lw, BASE_TOP), (BASE_FRONT_Z, BASE_TOP), "graphite", label="deck")
    else:
        shelf_bot = floor_y - 3.0
        seg((zf + lw, lip_top), (zf + lw, shelf_bot), "graphite", label="lip front")
        seg((zf + lw, shelf_bot), (zb, shelf_bot), "graphite", label="shelf underside")
        seg((zb, shelf_bot), (zb, y_top), "graphite", label="shelf back")
        seg((-150.0, BASE_TOP), (BASE_FRONT_Z, BASE_TOP), "graphite", label="deck")
    seg((BASE_FRONT_Z, BASE_TOP), (BASE_FRONT_Z, 0.0), "graphite", label="base front")
    seg((BASE_FRONT_Z, 0.0), (3000.0, 0.0), "desk", finite=False, label="desk")

    p0 = np.array([s[0] for s in segs], float)
    p1 = np.array([s[1] for s in segs], float)
    # Every surface except the screen/reflector pair is single-material, so the side does not matter.
    mf = np.array([MAT_IDS[s[2]] for s in segs])
    mb = np.array([MAT_IDS[s[3]] for s in segs])
    fin = np.array([s[4] for s in segs])
    labels = [s[5] for s in segs]

    # The end caps close the cove below the display: polygon under the display/reflector.
    cap = np.array([(z_s, CHIN_BOTTOM), (zb, CHIN_BOTTOM), (zb, y_top), (zf, floor_y),
                    (zf, lip_top)] + [tuple(p) for p in refl_pts[::-1]], float)
    return Scene(d, p0, p1, mf, mb, fin, labels, cap, y0, y1)
