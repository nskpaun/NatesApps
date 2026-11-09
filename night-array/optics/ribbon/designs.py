"""Cross-sections of the candidate optical layouts.

Axes (mm): z = 0 is the screen face, +z points at the user; y = 0 is the lowest pixel row, +y is up.
Everything is extruded along x. Station numbers come from night-array/SPEC.md (27" QHD panels, active area
596.7 x 335.7 mm, 16 mm chin, active area starting 172 mm above the desk, base top 36 mm above the desk).
"""
from __future__ import annotations

import numpy as np

from .trace import BLACK, Band, Builder, Lcd, Material

# ----------------------------------------------------------------------------------------------- station
PANEL_W, PANEL_H = 596.7, 335.7          # one panel's active area
ROW_MM = PANEL_H / 1440                  # 0.2331 mm per pixel row
CHIN = 16.0                              # non-emitting border under the lowest pixel row
BODY_DEPTH = 45.0                        # display shroud depth behind the screen face
DESK_Y = -172.0                          # desk surface (lowest pixel row is 172 mm above it)
BASE_TOP_Y = -136.0                      # top of the base rim
BASE_Z = (-141.0, 159.0)                 # base front-to-back at mid-panel (screen face 9 mm ahead of base centre)
PANEL_NITS = 350.0                       # Samsung S60UD typical; 280 minimum

# Seated eye, relative to the lowest pixel row: about level with the top quarter of the screen, 650 mm away.
EYE = dict(y=280.0, z=650.0)

# ----------------------------------------------------------------------------------------------- finishes
MIRROR_R = 0.90      # between an acrylic second-surface mirror (0.80-0.90) and enhanced aluminium (0.95)


def mirror(r=MIRROR_R):
    return Material("mirror", "mirror", (r, r, r))


def satin(ax=0.05, at=0.14, f0=(0.62, 0.58, 0.52), haze=0.03, name="satin"):
    """Satin metal. Defaults: brushed ALONG x (the long axis). Ward/Beckmann fits to brushed aluminium give
    roughness about 0.04 along the brush and 0.135 across it (Ngan, Durand & Matusik 2005). f0 is a warm
    light metal (clear-anodised aluminium is higher, titanium about 0.55)."""
    return Material(name, "ggx", tuple(f0), ax, at, (haze, haze, haze))


# Cove finishes the study compares. "brushed" is the one with measured data behind it; "fine" is a finer brush
# across the grain (an estimate: between that measurement and a near-mirror finish).
FINISHES = {"brushed": dict(ax=0.05, at=0.14), "fine": dict(ax=0.05, at=0.08)}

MATTE_BLACK = Material("matte black", "matte", (0.04, 0.04, 0.04))
SHELL = Material("titanium shell", "ggx", (0.55, 0.52, 0.48), 0.30, 0.30, (0.05, 0.05, 0.05))
DESK = Material("desk", "matte", (0.30, 0.28, 0.25))
SCREEN = Material("screen", "screen")


# ----------------------------------------------------------------------------------------------- helpers
def aplanat(src, eye, through, a_lo, a_hi, n=64):
    """Section of the ellipse with foci `src` and `eye` passing through `through`: every ray leaving `src`
    is reflected to `eye`. a_lo / a_hi (degrees) are how far the section extends either side of the direction
    src -> through, measured as seen from src (a_lo clockwise, a_hi counter-clockwise in a z-right, y-up
    drawing). Returns points [n, 2] and unit normals [n, 2] facing the foci, ordered so the reflective side
    is the Builder's front side."""
    src, eye, through = (np.asarray(v, float) for v in (src, eye, through))
    k = np.linalg.norm(through - src) + np.linalg.norm(through - eye)
    delta = src - eye
    th0 = np.arctan2(*(through - src)[::-1])
    th = th0 + np.radians(np.linspace(-a_lo, a_hi, n))
    u = np.stack([np.cos(th), np.sin(th)], 1)
    r = (k * k - delta @ delta) / (2 * (u @ delta + k))
    pts = src + r[:, None] * u
    to_s = src - pts
    to_e = eye - pts
    nrm = to_s / np.linalg.norm(to_s, axis=1, keepdims=True) + to_e / np.linalg.norm(to_e, axis=1, keepdims=True)
    nrm /= np.linalg.norm(nrm, axis=1, keepdims=True)
    e = pts[1] - pts[0]
    if np.array([-e[1], e[0]]) @ nrm[0] < 0:
        pts, nrm = pts[::-1], nrm[::-1]
    return pts, nrm


def _common(b: Builder, screen_top=PANEL_H, body=True, base_mat=SHELL, desk=True):
    b.seg((0, screen_top), (0, 0), SCREEN, MATTE_BLACK, "screen")
    if body:
        top = screen_top + 9
        b.seg((0, top), (0, screen_top), MATTE_BLACK, MATTE_BLACK, "top bezel")
        b.seg((-BODY_DEPTH, top), (0, top), SHELL, MATTE_BLACK, "display top")
        b.seg((-BODY_DEPTH, -CHIN), (-BODY_DEPTH, top), SHELL, MATTE_BLACK, "display back")
    if base_mat is not None:
        b.seg((BASE_Z[0], BASE_TOP_Y), (BASE_Z[1], BASE_TOP_Y), base_mat, MATTE_BLACK, "base top")
        b.seg((BASE_Z[1], BASE_TOP_Y), (BASE_Z[1], DESK_Y), SHELL, MATTE_BLACK, "base front")
        b.seg((BASE_Z[0], DESK_Y), (BASE_Z[0], BASE_TOP_Y), SHELL, MATTE_BLACK, "base back")
    if desk:
        b.seg((-600, DESK_Y), (1500, DESK_Y), DESK, MATTE_BLACK, "desk")


def _patterns(extra=None):
    p = {"white": np.array([1.0, 1.0, 1.0])}
    if extra:
        p.update(extra)
    return p


# ----------------------------------------------------------------------------------------------- the sill
SILL_DEFAULTS = dict(
    h=12.0,            # height of the hidden feed rows (mm). 12 mm = 51 rows = 3.6 % of the screen
    chin=CHIN,         # non-emitting border under the lowest pixel row
    tilt=45.0,         # fold mirror, degrees from the screen plane
    wall=1.6,          # sill shell thickness
    lip=0.0,           # how far the sill's front apron hangs below the chin (a visor)
    apron_mirror=True, # mirror on the inside of the apron (turns forward-going light back under the display)
    chin_mirror=False, # mirror strip on the chin face
    drop=34.0,         # distance from the slot straight down to the cove
    fan_fwd=18.0,      # cove extent, as seen from the slot: degrees forward of straight down
    fan_back=52.0,     # ... and backward
    cove="aplanat",    # "aplanat" (ellipse: slot -> eye), "flat" (ramp), or "matte" (same shape, diffuse white)
    ax=0.05, at=0.14,  # satin roughness along x / across
    f0=(0.62, 0.58, 0.52), haze=0.03,
    echo=20.0,         # height of the visible, decorative band above the sill (0 = none)
    eye_y=EYE["y"], eye_z=EYE["z"],   # the eye position the cove is shaped for
)


def sill(lcd=None, patterns=None, x_span=(-1e6, 1e6), **kw):
    """Hidden feed rows -> 45 degree mirror inside a slim sill -> down through a slot -> satin cove -> eye."""
    p = {**SILL_DEFAULTS, **kw}
    h, c, w = p["h"], p["chin"], p["wall"]
    d = h * np.tan(np.radians(p["tilt"]))            # slot depth = how far the mirror reaches forward
    m = mirror()
    b = Builder()
    y_exit = -c - p["lip"]

    # fold mirror (front faces the screen and down) and the shell over it
    b.seg((d, 0), (0.0, h), m, MATTE_BLACK, "fold mirror")
    n_out = np.array([h, d]) / np.hypot(h, d)
    q0, q1 = np.array([d, 0.0]) + w * n_out, np.array([0.0, h]) + w * n_out
    slope = (q1[1] - q0[1]) / (q1[0] - q0[0])
    y_at_screen = q1[1] + slope * (0 - q1[0])
    z_out = d + w
    y_at_front = q0[1] + slope * (z_out - q0[0])
    b.seg((0, y_at_screen), (z_out, y_at_front), SHELL, MATTE_BLACK, "sill bevel")
    b.seg((z_out, y_at_front), (z_out, y_exit), SHELL, MATTE_BLACK, "sill apron")
    b.seg((z_out, y_exit), (d, y_exit), MATTE_BLACK, MATTE_BLACK, "apron edge")
    b.seg((d, y_exit), (d, 0), m if p["apron_mirror"] else MATTE_BLACK, MATTE_BLACK, "apron inside")
    b.seg((0, 0), (0, -c), m if p["chin_mirror"] else MATTE_BLACK, MATTE_BLACK, "chin")

    # cove: an ellipse with the slot at one focus and the eye at the other
    src = np.array([d / 2, y_exit])
    eye = np.array([p["eye_z"], p["eye_y"]])
    through = src + np.array([0.0, -p["drop"]])
    pts, nrm = aplanat(src, eye, through, p["fan_back"], p["fan_fwd"], 72)   # ordered back end ... front end
    cove_mat = (Material("matte white", "matte", (0.8, 0.8, 0.8)) if p["cove"] == "matte"
                else satin(p["ax"], p["at"], p["f0"], p["haze"]))
    back_pt, front_pt = pts[0], pts[-1]
    if p["cove"] == "flat":
        b.seg(back_pt, front_pt, cove_mat, MATTE_BLACK, "cove")
    else:
        b.curve(pts, cove_mat, MATTE_BLACK, "cove", nrm)
    # dark back wall from the cove up to the display underside, underside, and the stand face below the cove
    b.seg(back_pt, (back_pt[0], -c), MATTE_BLACK, MATTE_BLACK, "back wall")
    b.seg((back_pt[0], -c), (0, -c), MATTE_BLACK, MATTE_BLACK, "display underside")
    b.seg((-BODY_DEPTH, -c), (back_pt[0], -c), MATTE_BLACK, MATTE_BLACK, "display underside (rear)")
    b.seg((front_pt[0], BASE_TOP_Y), front_pt, SHELL, MATTE_BLACK, "stand face")
    _common(b)

    y_vis = y_at_screen + 0.5                                   # first visible row above the sill
    bands = [Band(0.0, h, x_span[0], x_span[1], _patterns(patterns), "band")]
    if p["echo"] > 0:
        bands.append(Band(y_vis, y_vis + p["echo"], x_span[0], x_span[1], _patterns(patterns), "echo"))
    meta = dict(kind="sill", params=p, slot=d, src=src.tolist(), eye=eye.tolist(), cove=pts.tolist(),
                content_y0=y_vis + p["echo"], y_vis=y_vis, sill_proud=z_out,
                hidden_mm=y_vis, hidden_rows=int(round(y_vis / ROW_MM)),
                module_box=dict(z=(float(back_pt[0]), float(max(z_out, front_pt[0]))),
                                y=(float(front_pt[1]), float(y_at_screen))))
    return b.build(lcd or Lcd(), bands, x_span, meta=meta)


# ----------------------------------------------------------------------------------------------- as drawn
def as_drawn(variant="compact", lcd=None, patterns=None, x_span=(-1e6, 1e6), band_h=25.0, ax=0.05, at=0.14,
             eye_y=EYE["y"], eye_z=EYE["z"]):
    """The concept as first described: the band stays visible on the open screen, a flat mirror below the
    display catches what the band throws downward and sends it into a cove under the display.

    compact: the mirror lies on the base, 35-95 mm in front of the screen (inside the station's footprint).
    bulky:   the mirror stands as a lip 95 mm in front of the screen, just under the display's bottom edge,
             so it can catch light that leaves the screen at a gentler angle.
    The cove is the ideal one for each case (an ellipse from the band's mirror image to the eye)."""
    m = mirror()
    b = Builder()
    eye = np.array([eye_z, eye_y])
    band_c = np.array([0.0, band_h / 2])
    if variant == "compact":
        mc, half = np.array([65.0, BASE_TOP_Y + 23.0]), 30.0
        cove_c = np.array([-28.0, -72.0])
    else:
        mc, half = np.array([95.0, -38.0]), 19.0
        cove_c = np.array([-28.0, -78.0])
    u1 = (band_c - mc) / np.linalg.norm(band_c - mc)
    u2 = (cove_c - mc) / np.linalg.norm(cove_c - mc)
    n = (u1 + u2) / np.linalg.norm(u1 + u2)
    t = np.array([n[1], -n[0]])
    pa, pb = mc - half * t, mc + half * t
    e = pb - pa
    if np.array([-e[1], e[0]]) @ n < 0:
        pa, pb = pb, pa
    b.seg(pa, pb, m, SHELL, "fold mirror")
    virt = band_c - 2 * ((band_c - mc) @ n) * n                 # mirror image of the band centre
    pts, nrm = aplanat(virt, eye, cove_c, 9.0, 9.0, 48)
    b.curve(pts, satin(ax, at), MATTE_BLACK, "cove", nrm)
    hi, lo = (pts[0], pts[-1]) if pts[0][1] > pts[-1][1] else (pts[-1], pts[0])
    b.seg(hi, (hi[0], -CHIN), MATTE_BLACK, MATTE_BLACK, "back wall")
    b.seg((-BODY_DEPTH, -CHIN), (0, -CHIN), MATTE_BLACK, MATTE_BLACK, "display underside")
    b.seg((lo[0], BASE_TOP_Y), lo, MATTE_BLACK, MATTE_BLACK, "stand face")
    b.seg((0, 0), (0, -CHIN), MATTE_BLACK, MATTE_BLACK, "chin")
    _common(b)
    bands = [Band(0.0, band_h, x_span[0], x_span[1], _patterns(patterns), "band")]
    meta = dict(kind="as_drawn", variant=variant, eye=eye.tolist(), cove=pts.tolist(), mirror=[pa.tolist(), pb.tolist()],
                content_y0=band_h, band_h=band_h, emit_angle=float(np.degrees(np.arctan2(band_c[1] - mc[1], mc[0]))),
                module_box=dict(z=(float(min(pts[:, 0].min(), 0)), float(max(pa[0], pb[0]))),
                                y=(float(min(pa[1], pb[1], pts[:, 1].min())), float(band_h))))
    return b.build(lcd or Lcd(), bands, x_span, meta=meta)


def deck_reflection(lcd=None, patterns=None, x_span=(-1e6, 1e6), band_h=25.0, ax=0.05, at=0.14,
                    eye_y=EYE["y"], eye_z=EYE["z"]):
    """No mirror at all: the visible band simply reflects in a satin base deck in front of the screen."""
    b = Builder()
    b.seg((0, 0), (0, -CHIN), MATTE_BLACK, MATTE_BLACK, "chin")
    b.seg((-BODY_DEPTH, -CHIN), (0, -CHIN), MATTE_BLACK, MATTE_BLACK, "display underside")
    _common(b, base_mat=satin(ax, at))
    bands = [Band(0.0, band_h, x_span[0], x_span[1], _patterns(patterns), "band")]
    meta = dict(kind="deck", eye=[eye_z, eye_y], content_y0=band_h, band_h=band_h,
                module_box=dict(z=(0.0, BASE_Z[1]), y=(BASE_TOP_Y, band_h)))
    return b.build(lcd or Lcd(), bands, x_span, meta=meta)
