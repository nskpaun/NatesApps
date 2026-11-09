"""Light-ribbon optics study. Traces every layout and writes results/results.json and results/preview.npz.

    python run.py            full run (a few minutes)
    python run.py --quick    low sample counts, for a smoke test
    python -m ribbon.checks  tracer checks against closed-form cases

figures.py turns the results into the PNGs in figures/.
"""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import time
from pathlib import Path

import numpy as np

from ribbon import designs as D
from ribbon import patterns as P
from ribbon import preview as V
from ribbon import study as S
from ribbon.trace import Lcd, luma

HERE = Path(__file__).parent
PRESETS = {
    "slim": dict(h=9.0, drop=24.0),
    "balanced": dict(h=12.0, drop=34.0),
    "tall": dict(h=16.0, drop=56.0),
}


def rnd(v, n=4):
    if isinstance(v, dict):
        return {k: rnd(x, n) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [rnd(x, n) for x in v]
    if isinstance(v, np.ndarray):
        return rnd(v.tolist(), n)
    if isinstance(v, (float, np.floating)):
        return float(f"{float(v):.{n}g}")
    if isinstance(v, (np.integer,)):
        return int(v)
    return v


def geometry(sc):
    """Segments for drawing: consecutive segments with the same label merge into one polyline."""
    out = []
    kinds = [m.kind for m in sc.materials]
    for i, lab in enumerate(sc.labels):
        a, b = sc.a[i].tolist(), sc.b[i].tolist()
        kind = kinds[sc.front[i]]
        if out and out[-1]["label"] == lab and np.allclose(out[-1]["pts"][-1], a):
            out[-1]["pts"].append(b)
        else:
            out.append(dict(label=lab, kind=kind, pts=[a, b]))
    return rnd(out, 5)


def rays(sc):
    """A few illustrative rays from the band for the cross-section drawings."""
    if sc.meta["kind"] == "sill":
        h = sc.bands[0].y1
        fan = S.forward_fan(sc, [0.2 * h, 0.5 * h, 0.8 * h], [-32, -20, -8, 4])
        keep = [p for p, last in fan if last in ("room", "cove")]
    elif sc.meta["kind"] == "as_drawn":
        (za, ya), (zb, yb) = sc.meta["mirror"]
        yc = sc.meta["band_h"] / 2
        ang = [np.degrees(np.arctan2(y - yc, z)) for z, y in
               zip(np.linspace(za, zb, 7)[1:-1], np.linspace(ya, yb, 7)[1:-1])]
        keep = [p for p, last in S.forward_fan(sc, [yc], ang)]
    else:
        yc = sc.meta["band_h"] / 2
        keep = [p for p, last in S.forward_fan(sc, [yc], [-62, -55, -48])]
    out = []
    for p in keep:
        p = np.array(p)
        if len(p) > 1 and np.linalg.norm(p[-1] - p[-2]) > 260:          # shorten the leg that leaves for the eye
            p[-1] = p[-2] + (p[-1] - p[-2]) / np.linalg.norm(p[-1] - p[-2]) * 260
        out.append(p.tolist())
    return rnd(out, 5)


def summarise(sc, spp):
    col = S.column(sc, spp=spp)
    m = S.metrics(col)
    table = {room: {c: S.contrast(m, colour=c, lux=lux) | {"verdict": S.verdict(S.contrast(m, colour=c, lux=lux)["weber"])}
                    for c in S.COLOURS} for room, lux in S.ROOMS.items()}
    return dict(metrics=m, nits=dict(peak=m["peak"] * D.PANEL_NITS, mean=m["mean"] * D.PANEL_NITS,
                                     integral=m["integral"] * D.PANEL_NITS),
                column=dict(ys=col["ys"], band=col["band"], ambient=col["ambient"], content=col["content"]),
                contrast=table, box=sc.meta["module_box"],
                size=[sc.meta["module_box"]["z"][1] - sc.meta["module_box"]["z"][0],
                      sc.meta["module_box"]["y"][1] - sc.meta["module_box"]["y"][0]],
                geometry=geometry(sc), rays=rays(sc))


def variant(job):
    pn, fn, q, spp = job
    kw = {**PRESETS[pn], **D.FINISHES[fn]}
    sc = D.sill(**kw)
    s = summarise(sc, spp)
    s["params"] = dict(sc.meta["params"])
    s["hidden_rows"] = sc.meta["hidden_rows"]
    s["hidden_mm"] = sc.meta["hidden_mm"]
    s["feed_rows"] = int(round(kw["h"] / D.ROW_MM))
    s["sill_proud"] = sc.meta["sill_proud"]
    ey = [160, 220, 280, 340, 400, 460]
    ez = [450, 550, 650, 750, 850]
    grid = np.zeros((len(ey), len(ez)))
    for i, y in enumerate(ey):
        for j, z in enumerate(ez):
            grid[i, j] = S.metrics(S.column(sc, np.array([0.0, y, z]), spp=max(40, int(400 * q)), n=240))["mean"]
    s["eyebox"] = dict(eye_y=ey, eye_z=ez, mean=grid * D.PANEL_NITS)
    st = V.stations(sc, spp=max(80, int(1500 * q)))
    s["stations"] = [dict(x=t["x"], band=t["band"], echo=t["echo"], content=t["content"], ambient=t["ambient"],
                          shift=t["shift"], fwhm=t["fwhm"], kernel=t["kernel"], rowshift=t["rowshift"]) for t in st]
    return f"{pn}/{fn}", s, st


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    a = ap.parse_args()
    q = 0.15 if a.quick else 1.0
    spp = max(60, int(900 * q))
    t0 = time.time()
    res = dict(panel=dict(nits=D.PANEL_NITS, nits_min=280.0, row_mm=D.ROW_MM, rows=1440, chin=D.CHIN,
                          kappa=Lcd().kappa_v, mirror_r=D.MIRROR_R),
               eye=D.EYE, rooms=S.ROOMS, colours={k: dict(srgb=v, luma=S.colour_luma(k)) for k, v in S.COLOURS.items()})

    # ---- the layouts, side by side
    layouts = {
        "as_drawn_compact": D.as_drawn("compact"),
        "as_drawn_bulky": D.as_drawn("bulky"),
        "deck": D.deck_reflection(),
        "sill": D.sill(**PRESETS["balanced"]),
    }
    res["layouts"] = {}
    for name, sc in layouts.items():
        res["layouts"][name] = summarise(sc, spp)
        if sc.meta["kind"] == "as_drawn":
            res["layouts"][name]["emit_angle"] = sc.meta["emit_angle"]
        print(f"[{time.time() - t0:5.0f}s] layout {name}: {res['layouts'][name]['nits']['mean']:.1f} nits mean")

    # ---- sill variants (preset x cove finish): summary, eyebox, stations for the live preview
    jobs = [(pn, fn, q, spp) for pn in PRESETS for fn in D.FINISHES]
    with mp.get_context("fork").Pool(min(4, len(jobs))) as pool:
        done = pool.map(variant, jobs)
    res["variants"] = {key: s for key, s, _ in done}
    prev = {key: st for key, _, st in done}
    for key, s, _ in done:
        print(f"[{time.time() - t0:5.0f}s] variant {key}: {s['nits']['mean']:.1f} nits, {s['metrics']['height']:.0f} mm tall")
    res["presets"] = list(PRESETS)
    res["finishes"] = {k: dict(v) for k, v in D.FINISHES.items()}
    res["view"] = dict(ys=V.VIEW_Y, kernel_x=V.KERNEL_X, x0=P.X0, x1=P.X1, seam=P.SEAM, wall=V.WALL)

    # ---- sweeps around the balanced preset
    base = PRESETS["balanced"]

    def one(**kw):
        sc = D.sill(**{**base, **kw.pop("sill", {})}, **kw)
        m = S.metrics(S.column(sc, spp=max(60, int(500 * q))))
        return dict(mean=m["mean"] * D.PANEL_NITS, peak=m["peak"] * D.PANEL_NITS, height=m["height"],
                    integral=m["integral"] * D.PANEL_NITS, ambient=m["ambient"],
                    office_white=S.contrast(m, lux=500)["weber"], hidden_rows=sc.meta["hidden_rows"],
                    size=[sc.meta["module_box"]["z"][1] - sc.meta["module_box"]["z"][0],
                          sc.meta["module_box"]["y"][1] - sc.meta["module_box"]["y"][0]])

    sw = {}
    sw["band_height"] = [dict(h=h, **one(sill=dict(h=float(h)))) for h in (4, 6, 8, 10, 12, 14, 16, 20, 24)]
    finishes = {"brushed along the ribbon, as measured (0.05 / 0.14)": dict(ax=0.05, at=0.14),
                "finer brush along the ribbon (0.05 / 0.08)": dict(ax=0.05, at=0.08),
                "brushed across the ribbon (0.14 / 0.05)": dict(ax=0.14, at=0.05),
                "fine bead blast (0.12)": dict(ax=0.12, at=0.12),
                "coarse bead blast (0.25)": dict(ax=0.25, at=0.25),
                "near-mirror (0.03)": dict(ax=0.03, at=0.03)}
    sw["finish"] = []
    for label, kw in finishes.items():
        r = one(**kw)
        r["label"] = label
        r["lateral_fwhm"] = S.lateral_psf(D.sill(**base, **kw), spp=max(20000, int(120000 * q)))["fwhm"]
        r["window_amber"] = S.contrast(S.metrics(S.column(D.sill(**base, **kw), spp=max(60, int(500 * q)))),
                                       lux=2000, colour="amber")["weber"]
        sw["finish"].append(r)
    sw["mirror_tilt"] = [dict(tilt=t, **one(tilt=float(t))) for t in (41, 43, 45, 47, 49)]
    sw["chin"] = [dict(chin=c, **one(chin=float(c))) for c in (10, 16, 24)]
    sw["apron"] = [dict(label="mirror inside the apron", **one()), dict(label="dark apron", **one(apron_mirror=False))]
    sw["matte_cove"] = one(cove="matte")
    sw["flat_cove"] = one(cove="flat")
    sw["kappa"] = []
    for k in (2.6, 2.9, 3.4):
        lcd = Lcd(k, k)
        row = dict(kappa=k)
        for name, fn in (("sill", lambda: D.sill(lcd=lcd, **base)), ("as_drawn_compact", lambda: D.as_drawn("compact", lcd=lcd)),
                         ("as_drawn_bulky", lambda: D.as_drawn("bulky", lcd=lcd))):
            row[name] = S.metrics(S.column(fn(), spp=max(60, int(500 * q))))["mean"] * D.PANEL_NITS
        sw["kappa"].append(row)
    res["sweeps"] = sw
    print(f"[{time.time() - t0:5.0f}s] sweeps done")

    # ---- preview: direct render vs the separable shortcut the page uses
    xs = np.arange(-616.0, 617.0, 2.0)
    dr = V.direct(D.sill, xs, spp=max(6, int(48 * q)), **base)
    cmp = {}
    for name in ("glow", "bars"):
        a_ = luma(dr["band"][name] * D.PANEL_NITS)
        b_ = luma(V.compose(prev["balanced/brushed"], P.ALL[name], xs, lux=0.0, content_nits=0.0, echo=False))
        # compare on 16 x 4 mm blocks (the direct render is noisy per pixel); mask from the noise-free shortcut
        ny, nx = (a_.shape[0] // 4) * 4, (a_.shape[1] // 8) * 8
        blk = lambda v: v[:ny, :nx].reshape(ny // 4, 4, nx // 8, 8).mean((1, 3))
        ab, bb = blk(a_), blk(b_)
        core = bb > 0.2 * bb.max()
        cmp[name] = dict(direct_mean=float(ab[core].mean()), shortcut_mean=float(bb[core].mean()),
                         rms_rel=float(np.sqrt(np.mean((ab[core] - bb[core]) ** 2)) / ab[core].mean()))
    res["shortcut_check"] = cmp
    print(f"[{time.time() - t0:5.0f}s] shortcut check {cmp}")
    (HERE / "results").mkdir(exist_ok=True)
    np.savez_compressed(HERE / "results" / "preview.npz", xs=xs, ys=V.VIEW_Y,
                        **{f"band_{k}": v.astype(np.float32) for k, v in dr["band"].items()},
                        **{f"echo_{k}": v.astype(np.float32) for k, v in dr["echo"].items()},
                        content=dr["content"].astype(np.float32), ambient=dr["ambient"].astype(np.float32))
    (HERE / "results" / "results.json").write_text(json.dumps(rnd(res), separators=(",", ":")))
    print(f"[{time.time() - t0:5.0f}s] wrote results/results.json and results/preview.npz")


if __name__ == "__main__":
    main()
