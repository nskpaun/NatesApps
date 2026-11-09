"""Figures for the optics study, from results/results.json and results/preview.npz -> figures/*.png."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from ribbon import designs as D
from ribbon import patterns as P
from ribbon import preview as V
from ribbon import study as S

HERE = Path(__file__).parent
OUT = HERE / "figures"
INK, MUTED, GRID = "#1d1b19", "#6f6a64", "#dedad4"
# layouts use the first four slots of a validated categorical palette, in a fixed order
C = dict(compact="#2a78d6", sill="#eb6834", bulky="#1baf7a", deck="#eda100", ray="#e9a13b", mirror="#2a78d6",
         satin="#eb6834", screen="#111111", shell="#9a948c", dark="#3a3735", band="#f2a04a")
NAMES = dict(sill="Sill periscope (proposed)", as_drawn_bulky="As drawn, mirror out front",
             as_drawn_compact="As drawn, mirror on the base", deck="No mirror: satin deck")
COL = dict(sill=C["sill"], as_drawn_bulky=C["bulky"], as_drawn_compact=C["compact"], deck=C["deck"])

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "axes.edgecolor": MUTED, "axes.labelcolor": INK,
                     "xtick.color": MUTED, "ytick.color": MUTED, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.titlesize": 10, "axes.titleweight": "bold", "axes.titlelocation": "left",
                     "figure.dpi": 160, "savefig.bbox": "tight", "savefig.facecolor": "white"})


def draw_section(ax, lay, xlim, ylim, title="", rays=True, lw=1.0):
    style = {"screen": (C["screen"], 2.2 * lw), "mirror": (C["mirror"], 2.2 * lw), "ggx": (C["shell"], 1.2 * lw),
             "matte": (C["dark"], 1.2 * lw), "black": (C["dark"], 1.2 * lw)}
    if rays:
        for p in lay["rays"]:
            p = np.array(p)
            ax.plot(p[:, 0], p[:, 1], color=C["ray"], lw=0.55 * lw, alpha=0.75, zorder=1)
    for g in lay["geometry"]:
        p = np.array(g["pts"])
        col, w = style[g["kind"]]
        if g["label"] == "cove":
            col, w = C["satin"], 2.4 * lw
        if g["label"] == "desk":
            col, w = MUTED, 0.8
        ax.plot(p[:, 0], p[:, 1], color=col, lw=w, solid_capstyle="round", zorder=2)
    ax.set_aspect("equal")
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    ax.set_title(title)
    ax.set_xlabel("mm in front of the screen face")
    ax.tick_params(length=2)


def fig_layouts(res):
    fig, axs = plt.subplots(1, 3, figsize=(11.5, 4.3), sharey=True)
    for ax, key in zip(axs, ("as_drawn_compact", "as_drawn_bulky", "sill")):
        lay = res["layouts"][key]
        draw_section(ax, lay, (-70, 190), (-180, 60), NAMES[key])
        b = lay["box"]
        ax.add_patch(plt.Rectangle((b["z"][0], b["y"][0]), b["z"][1] - b["z"][0], b["y"][1] - b["y"][0], fill=False,
                                   ec=COL[key], lw=0.8, ls=(0, (3, 2)), zorder=3))
        n = lay["nits"]
        ax.text(0.98, 0.03, f"{n['mean']:.0f} nits over {lay['metrics']['height']:.0f} mm\noptics box "
                            f"{lay['size'][0]:.0f} × {lay['size'][1]:.0f} mm", transform=ax.transAxes, ha="right",
                va="bottom", fontsize=8.5, color=INK, bbox=dict(fc="white", ec=GRID, boxstyle="round,pad=0.35"))
    axs[0].set_ylabel("mm above the lowest pixel row")
    fig.text(0.01, 0.0, "Same scale, same seat, same 350-nit panel. Dashed box = volume the optics need.", fontsize=9, color=MUTED)
    fig.savefig(OUT / "layouts.png")
    plt.close(fig)


def fig_sill(res):
    lay = res["variants"]["balanced/brushed"]
    fig, ax = plt.subplots(figsize=(6.4, 6.6))
    draw_section(ax, lay, (-32, 52), (-78, 34), "Balanced sill, to scale", lw=1.4)
    pr = lay["params"]
    h, d = pr["h"], pr["h"]
    ax.add_patch(plt.Rectangle((-1.2, 0), 1.2, h, color=C["band"], zorder=4))
    note = dict(fontsize=8, color=INK, arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.6))
    ax.annotate(f"hidden feed rows\n{h:.0f} mm = {lay['feed_rows']} rows", xy=(-0.6, h / 2), xytext=(-30, 22), **note)
    ax.annotate("45° mirror", xy=(d / 2, h / 2), xytext=(22, 26), **note)
    ax.annotate(f"sill: {lay['sill_proud']:.1f} mm proud", xy=(lay["sill_proud"], -6), xytext=(24, -8), **note)
    ax.annotate("mirror inside\nthe apron", xy=(d, -9), xytext=(24, -22), **note)
    ax.annotate("slot", xy=(d / 2, -pr["chin"]), xytext=(-28, -24), **note)
    cv = np.array([g["pts"] for g in lay["geometry"] if g["label"] == "cove"][0])
    mid = cv[len(cv) // 2]
    ax.annotate("satin cove\n(brushed along its length)", xy=mid, xytext=(-30, -70), **note)
    ax.annotate("first visible row", xy=(0, lay["hidden_mm"]), xytext=(-30, 31), **note)
    ax.set_ylabel("mm above the lowest pixel row")
    fig.savefig(OUT / "sill.png")
    plt.close(fig)


def fig_profiles(res):
    fig, ax = plt.subplots(figsize=(6.6, 3.6))
    for key in ("sill", "as_drawn_bulky", "deck", "as_drawn_compact"):
        c = res["layouts"][key]["column"]
        ys, b = np.array(c["ys"]), np.array(c["band"]) * res["panel"]["nits"]
        m = res["layouts"][key]["metrics"]
        ax.plot(ys - 0.5 * (m["y_lo"] + m["y_hi"]), np.convolve(b, np.ones(5) / 5, mode="same"), color=COL[key], lw=1.6,
                label=f"{NAMES[key]}: {res['layouts'][key]['nits']['mean']:.0f} nits")
    ax.set_xlim(-60, 60)
    ax.set_xlabel("apparent height across the ribbon, mm (centred)")
    ax.set_ylabel("ribbon luminance, nits (white band)")
    ax.set_title("What the seated eye sees: ribbon cross-profile")
    ax.grid(axis="y", color=GRID, lw=0.6)
    ax.legend(frameon=False, fontsize=8)
    fig.savefig(OUT / "profiles.png")
    plt.close(fig)


def fig_daylight(res):
    rooms = list(res["rooms"])
    keys = ("sill", "as_drawn_bulky", "deck", "as_drawn_compact")
    fig, axs = plt.subplots(1, 2, figsize=(11, 3.8), sharey=True)
    for ax, colour in zip(axs, ("white", "amber")):
        x = np.arange(len(rooms))
        for i, key in enumerate(keys):
            w = [res["layouts"][key]["contrast"][r][colour]["weber"] for r in rooms]
            ax.bar(x + (i - 1.5) * 0.2, w, 0.18, color=COL[key], label=NAMES[key])
        ax.set_yscale("log")
        ax.set_ylim(0.01, 300)
        for lvl, lab in ((0.05, "faint"), (0.2, "visible"), (0.6, "clear"), (2.0, "vivid")):
            ax.axhline(lvl, color=GRID, lw=0.8, zorder=0)
            ax.text(len(rooms) - 0.42, lvl * 1.08, lab, fontsize=7, color=MUTED, ha="right")
        ax.set_xticks(x)
        ax.set_xticklabels([f"{r}\n{res['rooms'][r]:g} lux" for r in rooms])
        ax.set_title(f"{colour.capitalize()} band ({res['colours'][colour]['luma'] * 100:.0f} % of white's luminance)")
    axs[0].set_ylabel("ribbon ÷ background on the same surface")
    axs[0].legend(frameon=False, fontsize=8, loc="upper right")
    fig.savefig(OUT / "daylight.png")
    plt.close(fig)


def fig_eyebox(res):
    fig, axs = plt.subplots(1, 3, figsize=(11, 3.2), sharey=True)
    for ax, key in zip(axs, ("slim", "balanced", "tall")):
        e = res["variants"][key + "/brushed"]["eyebox"]
        g = np.array(e["mean"])
        im = ax.imshow(g, origin="lower", cmap="magma", vmin=0, vmax=80, aspect="auto",
                       extent=(e["eye_z"][0] - 50, e["eye_z"][-1] + 50, e["eye_y"][0] - 30, e["eye_y"][-1] + 30))
        for i, y in enumerate(e["eye_y"]):
            for j, z in enumerate(e["eye_z"]):
                ax.text(z, y, f"{g[i, j]:.0f}", ha="center", va="center", fontsize=7.5,
                        color="white" if g[i, j] < 55 else "black")
        ax.plot([res["eye"]["z"]], [res["eye"]["y"]], marker="o", mfc="none", mec="white", ms=16, mew=1)
        ax.set_title(f"{key.capitalize()}")
        ax.set_xlabel("eye distance from the screen, mm")
    axs[0].set_ylabel("eye height above the lowest pixel row, mm")
    fig.colorbar(im, ax=axs, label="ribbon nits (white band)", shrink=0.9, pad=0.015)
    fig.savefig(OUT / "eyebox.png")
    plt.close(fig)


def fig_sweeps(res):
    sw = res["sweeps"]
    fig, axs = plt.subplots(2, 2, figsize=(11, 6.4))
    h = [r["h"] for r in sw["band_height"]]
    for ax, key, lab in ((axs[0, 0], "mean", "ribbon nits (white band)"), (axs[0, 1], "height", "ribbon apparent height, mm")):
        ax.plot(h, [r[key] for r in sw["band_height"]], color=C["sill"], marker="o", ms=4, lw=2)
        ax.set_xlabel("hidden feed band, mm (1 mm = 4.3 pixel rows)")
        ax.set_ylabel(lab)
        ax.set_ylim(0)
        ax.grid(axis="y", color=GRID, lw=0.6)
    axs[0, 0].set_title("Brightness: fast to 12 mm, slowly after")
    axs[0, 1].set_title("Ribbon height tops out near 16 mm")
    ax = axs[1, 0]
    labs = [r["label"] for r in sw["finish"]]
    y = np.arange(len(labs))[::-1]
    ax.barh(y, [r["mean"] for r in sw["finish"]], color=C["sill"], height=0.5)
    for yy, r in zip(y, sw["finish"]):
        ax.text(r["mean"] + 2, yy, f"{r['mean']:.0f} nits · sideways blur {r['lateral_fwhm']:.0f} mm · office ×{r['office_white']:.1f}",
                va="center", fontsize=7.5, color=INK)
    ax.set_yticks(y)
    ax.set_yticklabels(labs, fontsize=7.5)
    ax.set_xlim(0, 260)
    ax.set_xlabel("ribbon nits (white band)")
    ax.set_title("Cove finish")
    ax = axs[1, 1]
    k = [r["kappa"] for r in sw["kappa"]]
    for key in ("sill", "as_drawn_bulky", "as_drawn_compact"):
        v = [r[key] for r in sw["kappa"]]
        ax.plot(k, v, color=COL[key], marker="o", ms=4, lw=2)
        ax.text(k[-1] + 0.03, v[-1], NAMES[key], color=INK, fontsize=7.5, va="center")
    ax.set_yscale("log")
    ax.set_xlim(2.5, 4.3)
    ax.set_xlabel("panel angular falloff κ (measured IPS monitors: 2.6 to 3.4)")
    ax.set_ylabel("ribbon nits, log scale")
    ax.set_title("Sensitivity to the panel's off-axis light")
    ax.grid(axis="y", color=GRID, lw=0.6)
    fig.tight_layout()
    fig.savefig(OUT / "sweeps.png")
    plt.close(fig)


def fig_preview(res):
    z = np.load(HERE / "results" / "preview.npz")
    r = dict(band={k[5:]: z[k] for k in z.files if k.startswith("band_")},
             echo={k[5:]: z[k] for k in z.files if k.startswith("echo_")}, content=z["content"], ambient=z["ambient"])
    rows = [("glow", "dark", 2.0), ("glow", "home office", 200.0), ("glow", "office", 500.0),
            ("glow", "by a window", 2000.0), ("bars", "home office", 200.0)]
    tiles = []
    for name, room, lux in rows:
        img = V.tonemap(V.combine(r, name, lux=lux))
        tiles.append(np.repeat(np.repeat(img, 2, 0), 2, 1))
    fig, axs = plt.subplots(len(rows), 1, figsize=(11, 2.05 * len(rows)))
    for ax, t, (name, room, lux) in zip(axs, tiles, rows):
        ax.imshow(t, extent=(z["xs"][0], z["xs"][-1], z["ys"][0], z["ys"][-1]), aspect="equal")
        ax.set_title(f"{'Concept gradient' if name == 'glow' else 'Resolution bars: 80, 40, 20, 10, 5, 2.5 mm'} · {room}, {lux:g} lux",
                     fontsize=8.5)
        ax.set_yticks([-150, -100, -50, 0])
        ax.tick_params(labelsize=7, length=2)
        for s in ax.spines.values():
            s.set_visible(False)
    axs[-1].set_xlabel("mm across the station (flat pair of panels, eye centred at 650 mm)")
    fig.tight_layout()
    fig.savefig(OUT / "preview.png", dpi=110)
    plt.close(fig)


def main():
    OUT.mkdir(exist_ok=True)
    res = json.loads((HERE / "results" / "results.json").read_text())
    for f in (fig_layouts, fig_sill, fig_profiles, fig_daylight, fig_eyebox, fig_sweeps, fig_preview):
        f(res)
        print("wrote", f.__name__)


if __name__ == "__main__":
    main()
