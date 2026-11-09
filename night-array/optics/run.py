"""Run every light-ribbon experiment and write figures + results to optics/out/.

    python3 night-array/optics/run.py            # full quality (~11 min on 4 cores)
    python3 night-array/optics/run.py --quick    # low sample counts, for iterating

Requires numpy and matplotlib only.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from ribbon.scene import Design, build_scene, PIXEL_PITCH  # noqa: E402
from ribbon.tracer import trace_camera, trace_forward  # noqa: E402
from ribbon.diagram import draw  # noqa: E402
from ribbon import analysis as an  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")

# Chart styling: validated reference palette (dataviz skill), light surface.
SURF, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
S1, S2, S3 = "#2a78d6", "#eb6834", "#1baf7a"
plt.rcParams.update({
    "figure.facecolor": SURF, "axes.facecolor": SURF, "axes.edgecolor": GRID, "axes.labelcolor": INK2,
    "xtick.color": INK2, "ytick.color": INK2, "text.color": INK, "axes.grid": True, "grid.color": GRID,
    "grid.linewidth": 0.8, "axes.spines.top": False, "axes.spines.right": False, "font.size": 9,
    "axes.titlesize": 10, "axes.titleweight": "bold", "legend.frameon": False, "lines.linewidth": 2,
})

# ------------------------------------------------------------------ designs
BASE = Design()  # dataclass defaults: flat 45 deg reflector, satin titanium ramp
FLAT45 = Design(name="A. Flat mirror, 45 deg", reflector="flat", mirror_deg=45, mirror_bottom_y=158,
                ramp_deg=30)
FLAT62 = Design(name="B. Flat mirror, 62 deg + chin mirror", reflector="flat", mirror_deg=62,
                mirror_bottom_y=135, chin_finish="mirror", ramp_deg=35)
PARA = Design(name="C. Parabolic reflector + chin mirror", reflector="parabolic", refl_psi=15, refl_f=20,
              refl_theta_min=-55, chin_finish="mirror", ramp_deg=32)
MATTE = PARA.with_(name="Matte white flat floor", ramp_deg=0.0, ramp_finish="matte_white")

FINISHES = [
    ("matte white", "matte_white"), ("satin white paint", "satin_white"),
    ("satin titanium, fine (a=0.12)", "satin_titanium_fine"), ("satin titanium (a=0.25)", "satin_titanium"),
    ("satin titanium, coarse (a=0.40)", "satin_titanium_coarse"), ("polished titanium (a=0.04)", "polished_titanium"),
    ("satin aluminium (a=0.25)", "satin_aluminium"),
]


def cam(design, q, **kw):
    W, H, spp = (200, 72, 16) if q else (320, 110, 64)
    W = kw.pop("W", W); H = kw.pop("H", H); spp = kw.pop("spp", spp)
    return trace_camera(build_scene(design), W=W, H=H, spp=spp, **kw)


def save(fig, name):
    path = os.path.join(OUT, name)
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=SURF)
    plt.close(fig)
    print("  wrote", os.path.relpath(path))


def tone(img):
    """Simple display mapping for the simulated views (luminance in cd/m^2 -> sRGB)."""
    x = img / 120.0
    x = x / (1 + x) * 1.6
    return np.clip(x, 0, 1) ** (1 / 2.2)


def concept_colors(xs):
    """Amber -> warm white -> magenta, like the concept image (linear RGB weights)."""
    t = np.clip((xs + 600) / 1200, 0, 1)
    amber = np.array([1.0, 0.45, 0.08]); white = np.array([1.0, 0.85, 0.65]); mag = np.array([0.9, 0.08, 0.35])
    c = np.where(t[:, None] < 0.45, amber + (white - amber) * (t[:, None] / 0.45),
                 white + (mag - white) * ((t[:, None] - 0.45) / 0.55))
    glow = 0.35 + 0.65 * np.exp(-((xs + 120) / 260) ** 2) + 0.5 * np.exp(-((xs - 330) / 160) ** 2)
    return c * np.clip(glow, 0, 1)[:, None]


# ------------------------------------------------------------------ experiments
def exp_reflectors(q, R):
    print("[1] reflector geometry")
    designs = [FLAT45, FLAT62, PARA]
    fig, axs = plt.subplots(1, 3, figsize=(15, 5.2))
    out = []
    for ax, d in zip(axs, designs):
        sc = build_scene(d)
        draw(ax, sc, d.name)
        fb = trace_forward(sc, n=60_000 if q else 300_000)
        res = cam(d, q)
        m = an.metrics(res)
        to_rib = fb.get("absorbed: ribbon surface", 0) + 0  # flux that reaches the ribbon surface first or later
        lost_band = fb.get("absorbed: light band", 0) + fb.get("absorbed: chin", 0)
        spill = sum(v for k, v in fb.items() if any(s in k for s in ("deck", "lip top", "lip front", "desk", "sideways")))
        out.append(dict(name=d.name, flux=fb, metrics=m))
        ax.text(0.02, 0.98, f"peak seen from the chair: {m['peak']:.0f} cd/m²\n"
                f"band light back into the panel: {lost_band:.0%}\nspill onto deck/desk: {spill:.0%}",
                transform=ax.transAxes, va="top", fontsize=8, color=INK,
                bbox=dict(fc=SURF, ec=GRID, boxstyle="round,pad=0.4"))
        ax.grid(False)
    fig.suptitle("Reflector geometry, x = 0 cross-section. Orange: band rays that reach the ribbon surface "
                 "(drawn as a perfect mirror to show the glint direction). Grey: absorbed. Pink: escaped.",
                 fontsize=9, color=INK2)
    save(fig, "1-reflectors.png")
    R["reflectors"] = out


def exp_finish_and_ramp(q, R):
    print("[2] ribbon surface finish and ramp angle")
    rows = []
    psf = {}
    for label, fin in FINISHES:
        d = PARA.with_(ramp_finish=fin) if fin != "matte_white" else MATTE
        res = cam(d, q)
        m = an.metrics(res)
        xs, prof = an.mean_psf(res, range(int(res.nbx * 0.12), int(res.nbx * 0.42), 2))
        w = an.energy_width(xs, prof)
        psf[label] = (xs, prof)
        rows.append(dict(finish=label, **{k: m[k] for k in ("peak", "mean", "k_amb", "k_content")},
                         c500=m["contrast"].get(500), c1000=m["contrast"].get(1000), fwhm_mm=w))
        print(f"   {label:34s} peak {m['peak']:6.1f}  C500 {m['contrast'].get(500, 0):5.2f}  FWHM {w:5.0f} mm")
    R["finishes"] = rows
    R["_psf"] = psf

    angles = [0, 10, 20, 26, 32, 38, 44, 50]
    ramp = []
    for a in angles:
        res = cam(PARA.with_(ramp_deg=a), q, spp=12 if q else 32)
        m = an.metrics(res)
        ramp.append(dict(ramp_deg=a, peak=m["peak"], mean=m["mean"], c500=m["contrast"].get(500)))
    R["ramp"] = ramp

    fig, axs = plt.subplots(1, 3, figsize=(15, 4.2))
    lab = [r["finish"] for r in rows]
    y = np.arange(len(rows))
    axs[0].barh(y, [r["mean"] for r in rows], color=S1, height=0.6)
    axs[0].set_yticks(y, lab); axs[0].invert_yaxis()
    axs[0].set_xlabel("ribbon luminance seen from the chair (cd/m², band full white)")
    axs[0].set_title("Brightness")
    for i, r in enumerate(rows):
        axs[0].text(r["mean"], i, f" {r['mean']:.0f}", va="center", fontsize=8, color=INK2)
    axs[1].barh(y, [r["c500"] for r in rows], color=S1, height=0.6)
    axs[1].set_yticks(y, [""] * len(rows)); axs[1].invert_yaxis()
    axs[1].axvline(1.5, color=INK2, lw=1, ls="--"); axs[1].text(1.5, -0.7, " noticeable", fontsize=7, color=INK2)
    axs[1].axvline(3, color=INK2, lw=1, ls=":"); axs[1].text(3, -0.7, " glowing", fontsize=7, color=INK2)
    axs[1].set_xlabel("contrast vs. the same surface unlit, at 500 lux")
    axs[1].set_title("Office-light contrast")
    for i, r in enumerate(rows):
        axs[1].text(r["c500"], i, f" {r['c500']:.1f}×", va="center", fontsize=8, color=INK2)
    axs[2].barh(y, [r["fwhm_mm"] for r in rows], color=S1, height=0.6)
    axs[2].set_yticks(y, [""] * len(rows)); axs[2].invert_yaxis()
    axs[2].set_xlabel("blur: width of one lit 9 mm band column on the ribbon (mm)")
    axs[2].set_title("Sharpest highlight the surface allows")
    for i, r in enumerate(rows):
        axs[2].text(r["fwhm_mm"], i, f" {r['fwhm_mm']:.0f}", va="center", fontsize=8, color=INK2)
    save(fig, "2-finishes.png")

    fig, ax = plt.subplots(figsize=(6.5, 3.6))
    ax.plot(angles, [r["mean"] for r in ramp], color=S1, marker="o", ms=5)
    ax.set_xlabel("ramp angle (deg, rising toward the display)")
    ax.set_ylabel("ribbon luminance (cd/m²)")
    ax.set_title("Ramp angle: the glint has to point at the eye")
    save(fig, "3-ramp-angle.png")


def exp_band_height(q, R):
    print("[3] band height")
    hs = [4, 8, 12, 16, 24, 32]
    rows = []
    for h in hs:
        for label, d in (("parabolic + satin titanium", PARA.with_(band_h=h, refl_f=None if h > 30 else 20)),
                         ("parabolic + matte white floor", MATTE.with_(band_h=h, refl_f=None if h > 30 else 20))):
            res = cam(d, q, spp=16 if q else 40)
            m = an.metrics(res)
            img = res.image(np.ones(res.A.shape[1]))
            total = float(img.sum())  # proportional to total light seen (brightness x area)
            rows.append(dict(design=label, band_h=h, rows=int(round(h / PIXEL_PITCH)), mean=m["mean"],
                             peak=m["peak"], area_px=m["area_px"], total=total, c500=m["contrast"].get(500)))
            print(f"   {label:30s} h={h:2d} mm mean {m['mean']:5.1f} area {m['area_px']}")
    R["band_height"] = rows
    fig, axs = plt.subplots(1, 2, figsize=(12, 3.8))
    for label, col in (("parabolic + satin titanium", S1), ("parabolic + matte white floor", S2)):
        rr = [r for r in rows if r["design"] == label]
        axs[0].plot([r["band_h"] for r in rr], [r["mean"] for r in rr], color=col, marker="o", ms=5, label=label)
        t0 = rr[2]["total"]
        axs[1].plot([r["band_h"] for r in rr], [r["total"] / t0 for r in rr], color=col, marker="o", ms=5,
                    label=label)
    axs[0].set_xlabel("band height (mm of screen; 12 mm ≈ 51 pixel rows)")
    axs[0].set_ylabel("ribbon luminance (cd/m²)")
    axs[0].set_title("How bright the ribbon looks")
    axs[0].legend(loc="upper left")
    axs[1].set_xlabel("band height (mm)")
    axs[1].set_ylabel("total light seen (× the 12 mm band)")
    axs[1].set_title("How much light the ribbon puts out (brightness × size)")
    save(fig, "4-band-height.png")


def exp_daylight(q, R):
    print("[4] daylight")
    res_p = cam(PARA, q)
    res_m = cam(MATTE, q)
    R["_res_matte"] = res_m
    lux = np.geomspace(20, 10000, 40)
    fig, axs = plt.subplots(1, 2, figsize=(12, 3.9))
    out = {}
    for res, label, col in ((res_p, "parabolic + satin titanium", S1), (res_m, "matte white floor", S2)):
        m = an.metrics(res, lux=list(lux))
        c = [m["contrast"][E] for E in lux]
        axs[0].plot(lux, c, color=col, label=label)
        need15 = [an.band_needed(res, 1.5, E, PARA.band_lum) for E in lux]
        need3 = [an.band_needed(res, 3.0, E, PARA.band_lum) for E in lux]
        axs[1].plot(lux, need3, color=col, label=f"{label}: glowing (3×)")
        axs[1].plot(lux, need15, color=col, ls="--", label=f"{label}: noticeable (1.5×)")
        out[label] = dict(contrast={int(E): float(an.metrics(res, lux=[E])["contrast"][E]) for E in (50, 150, 500, 1000, 5000)},
                          band_needed_glow={int(E): float(an.band_needed(res, 3.0, E, PARA.band_lum)) for E in (50, 150, 500, 1000, 5000)},
                          band_needed_notice={int(E): float(an.band_needed(res, 1.5, E, PARA.band_lum)) for E in (50, 150, 500, 1000, 5000)})
    for ax in axs:
        ax.set_xscale("log")
        ax.set_xlabel("room illuminance on the desk (lux)")
    axs[0].set_yscale("log")
    axs[0].axhline(1.5, color=INK2, lw=1, ls="--"); axs[0].axhline(3, color=INK2, lw=1, ls=":")
    axs[0].text(12000, 1.5, " noticeable", va="center", fontsize=7, color=INK2)
    axs[0].text(12000, 3, " glowing", va="center", fontsize=7, color=INK2)
    axs[0].set_ylabel("ribbon contrast (lit ÷ unlit)")
    axs[0].set_title("Contrast with the band at 350 cd/m²")
    axs[0].legend()
    axs[1].set_yscale("log")
    axs[1].axhline(350, color=INK, lw=1)
    axs[1].text(25, 380, "S60UD full white ≈ 350 cd/m²", fontsize=8, color=INK)
    axs[1].set_ylabel("band luminance needed (cd/m²)")
    axs[1].set_title("Band brightness needed")
    axs[1].legend(fontsize=7)
    save(fig, "5-daylight.png")
    R["daylight"] = out
    return res_p


def exp_pattern(q, R, res):
    print("[5] pattern transfer and inverse design")
    d = PARA
    full, mask, pk = an.ribbon_mask(res)
    xw = res.x_world
    nbx, nby = res.nbx, res.nby
    xb = (np.arange(nbx) + 0.5) / nbx * d.width - d.width / 2

    # (a) flat field: full white vs designed uniform
    w = mask.astype(float)
    target_level = np.percentile(full[mask], 30)
    p_flat = an.design_pattern(res, np.where(mask, target_level, 0.0), weight=w, smooth=0.3)
    img_flat = res.image(p_flat)

    def prof(img):
        ww = np.where(mask, full, 0.0)
        return (img * ww).sum(0) / np.maximum(ww.sum(0), 1e-9)
    xs_img = np.nanmean(np.where(mask, xw, np.nan), axis=0)

    # (b) a narrow "treble" highlight: naive (light the matching columns) vs designed
    def gauss(x0, s):
        return np.exp(-0.5 * ((xb - x0) / s) ** 2)
    rows_out = {}
    fig, axs = plt.subplots(2, 2, figsize=(13, 7.6), gridspec_kw=dict(hspace=0.45))
    ax = axs[0, 0]
    for k, (lab, col) in enumerate((("satin titanium (a=0.25)", S1), ("matte white", S2),
                                     ("satin titanium, fine (a=0.12)", S3))):
        xs, pr = R["_psf"][lab]
        ok = np.isfinite(xs)
        ax.plot(xs[ok], pr[ok], color=col, label=lab)
    ax.set_xlim(-400, 400)
    ax.set_xlabel("distance along the ribbon from the lit column (mm)"); ax.set_ylabel("relative luminance")
    ax.set_title("Blur: one lit 9 mm band column, as seen on the ribbon")
    ax.legend(fontsize=8)

    ax = axs[0, 1]
    ok = np.isfinite(xs_img)
    ax.plot(*an.bin_profile(xs_img, prof(full)), color=S2, label="band full white (naive)")
    ax.plot(*an.bin_profile(xs_img, prof(img_flat)), color=S1, label="designed pattern (uniform target)")
    ax.set_ylim(bottom=0)
    ax.set_xlabel("x along the ribbon (mm)"); ax.set_ylabel("cd/m²")
    ax.set_title("Flat field: ends and the 14 mm seam need compensation")
    ax.legend(fontsize=8)
    ax2 = axs[1, 1]
    ax2.step(xb, p_flat.reshape(nby, nbx).mean(0), where="mid", color=S1)
    ax2.set_xlabel("band column x (mm)"); ax2.set_ylabel("drive level (0-1)")
    ax2.set_title("The designed band pattern for the uniform ribbon")
    ax2.set_ylim(0, 1.05)

    ax = axs[1, 0]
    widths = [20, 40, 80, 160]
    gains = []
    for s in widths:
        p_naive = np.tile(gauss(-200, s / 2.355), nby)
        img_n = res.image(p_naive)
        pn = prof(img_n)
        # modulation achieved: peak over the local background at +-300 mm
        gains.append(pn[ok].max() / prof(full)[ok].max())
    ax.plot(widths, gains, color=S1, marker="o", ms=5, label="satin titanium")
    if "_res_matte" in R:
        rm = R["_res_matte"]; fm, mm_, _ = an.ribbon_mask(rm)
        def prof_m(img):
            ww = np.where(mm_, fm, 0.0)
            return (img * ww).sum(0) / np.maximum(ww.sum(0), 1e-9)
        gm = [prof_m(rm.image(np.tile(gauss(-200, s / 2.355), nby))).max() / prof_m(fm).max() for s in widths]
        ax.plot(widths, gm, color=S2, marker="o", ms=5, label="matte white floor")
        rows_out["highlight_peak_vs_width_matte"] = dict(zip(widths, [float(g) for g in gm]))
        ax.legend(fontsize=8)
    ax.set_xscale("log"); ax.set_xticks(widths, [str(w) for w in widths])
    ax.set_xlabel("width of the highlight drawn on the band (FWHM, mm)")
    ax.set_ylabel("peak brightness ÷ full-white peak")
    ax.set_title("Narrow highlights lose brightness, not position")
    rows_out["highlight_peak_vs_width"] = dict(zip(widths, [float(g) for g in gains]))
    save(fig, "6-pattern-transfer.png")

    # (c) rows -> vertical position
    cents = []
    yy = np.arange(res.H)[:, None]
    for r in range(nby):
        p = np.zeros(nbx * nby); p[r * nbx:(r + 1) * nbx] = 1
        im = res.image(p)
        cents.append(float((im * yy).sum() / max(im.sum(), 1e-9)))
    rows_out["row_bin_centroid_px"] = cents
    R["pattern"] = rows_out

    # (d) simulated views
    cols = concept_colors(xb)
    pat = np.stack([np.tile(cols[:, c], nby) for c in range(3)], 1)
    fig, axs = plt.subplots(3, 1, figsize=(11, 9))
    content = np.array([0.16, 0.15, 0.17]) * 60  # dark UI near the bottom of the screen
    for ax, (lux, ttl) in zip(axs, ((30, "evening, 30 lux"), (150, "lamp-lit room, 150 lux"),
                                    (500, "office, 500 lux"))):
        Lr = an.room_luminance(lux)
        rgb = np.stack([res.image(pat[:, c]) for c in range(3)], -1)
        rgb = rgb + res.ambient[..., None] * Lr * np.array([1.0, 0.97, 0.92]) + res.content[..., None] * content
        ax.imshow(tone(rgb), aspect="auto")
        ax.set_title(f"Simulated view from the chair, {ttl} (band drawing the concept's amber → magenta wave)")
        ax.axis("off")
    save(fig, "7-simulated-view.png")


def exp_slot(q, R):
    print("[7] reflector size: ribbon height vs contrast")
    out = []
    for f in (10, 12, 14, 17, 20, 24):
        d = PARA.with_(refl_f=f)
        res = cam(d, q, spp=16 if q else 40)
        m = an.metrics(res)
        # apparent height: pixels -> mm seen square-on at the ribbon's distance
        tw = math.tan(math.radians(res.cam["hfov"]) / 2)
        rad_px = 2 * tw / res.W
        ex, ey, ez = d.eye
        dist = math.hypot(ez + 40, ey - 60)
        out.append(dict(f=f, mean=m["mean"], height_mm=m["height_px"] * rad_px * dist, c500=m["contrast"].get(500),
                        c1000=m["contrast"].get(1000)))
        print(f"   f={f:2d} mm  mean {m['mean']:5.1f}  apparent height {out[-1]['height_mm']:4.0f} mm  C500 {m['contrast'].get(500):5.1f}")
    R["reflector_size"] = out
    fig, axs = plt.subplots(1, 2, figsize=(11, 3.4))
    axs[0].plot([o["f"] for o in out], [o["height_mm"] for o in out], color=S1, marker="o", ms=5)
    axs[0].set_xlabel("reflector focal length f (mm)"); axs[0].set_ylabel("apparent ribbon height (mm)")
    axs[0].set_title("A bigger reflector hides more of the cove…")
    axs[1].plot([o["f"] for o in out], [o["c500"] for o in out], color=S1, marker="o", ms=5)
    axs[1].set_xlabel("reflector focal length f (mm)"); axs[1].set_ylabel("contrast at 500 lux")
    axs[1].set_title("…and shades it from room light")
    for ax in axs:
        ax.set_ylim(bottom=0)
    save(fig, "9-reflector-size.png")


def exp_viewing(q, R):
    print("[6] viewing position")
    out = []
    for ey in (380, 420, 460, 500, 540, 580):
        res = cam(PARA, q, eye=(0, ey, 650), spp=12 if q else 32)
        out.append(dict(eye_y=ey, mean=an.metrics(res)["mean"]))
    side = []
    for ex in (-400, -200, 0, 200, 400):
        res = cam(PARA, q, eye=(ex, 460, 650), spp=12 if q else 32, target=(ex * 0.5, 60, -40))
        side.append(dict(eye_x=ex, mean=an.metrics(res)["mean"]))
    R["viewing"] = dict(height=out, lateral=side)
    fig, axs = plt.subplots(1, 2, figsize=(11, 3.4))
    axs[0].plot([o["eye_y"] for o in out], [o["mean"] for o in out], color=S1, marker="o", ms=5)
    axs[0].set_xlabel("eye height above desk (mm)"); axs[0].set_ylabel("ribbon luminance (cd/m²)")
    axs[0].set_title("Sitting higher or lower")
    axs[1].plot([o["eye_x"] for o in side], [o["mean"] for o in side], color=S1, marker="o", ms=5)
    axs[1].set_xlabel("eye offset left/right (mm)"); axs[1].set_ylabel("ribbon luminance (cd/m²)")
    axs[1].set_title("Moving sideways")
    for ax in axs:
        ax.set_ylim(bottom=0)
    save(fig, "8-viewing-position.png")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    R = {"designs": {d.name: d.__dict__ for d in (FLAT45, FLAT62, PARA, MATTE)}}
    t0 = time.time()
    exp_reflectors(a.quick, R)
    exp_finish_and_ramp(a.quick, R)
    exp_band_height(a.quick, R)
    res = exp_daylight(a.quick, R)
    exp_pattern(a.quick, R, res)
    exp_viewing(a.quick, R)
    exp_slot(a.quick, R)
    R.pop("_psf", None); R.pop("_res_matte", None)

    def clean(o):
        if isinstance(o, dict):
            return {str(k): clean(v) for k, v in o.items()}
        if isinstance(o, (list, tuple)):
            return [clean(v) for v in o]
        if isinstance(o, (np.floating, np.integer)):
            return o.item()
        return o
    with open(os.path.join(OUT, "results.json"), "w") as f:
        json.dump(clean(R), f, indent=1)
    print(f"done in {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
