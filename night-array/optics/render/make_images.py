"""Develops the final frames from the EXRs written by scene.py and builds the gallery page.

    python make_images.py exr_dir          -> out/*.jpg, out/index.html, out/calibration.json

The hero frame is developed for four rooms, each with the ribbon on and with the feed rows black; the other
views for a home office. Exposure follows the room the way a camera would; within a frame nothing else changes.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

import develop as dv

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
ROOMS = {"dark": (2.0, 1.4), "home": (200.0, 1.4), "office": (500.0, 1.0), "window": (2000.0, 0.5)}   # lux, exposure


def groups(exr):
    r = dv.load(exr)
    cache = Path(exr).with_suffix(".dn.npz")
    if cache.exists() and cache.stat().st_mtime > Path(exr).stat().st_mtime:
        return dict(np.load(cache))
    dn = {g: dv.denoise(r[g], r["albedo"], r["normal"]) for g in ("band", "screen", "room")}
    np.savez_compressed(cache, **dn)
    return dn


def save(dn, k_per_lux, lux, exposure, band, path):
    img = dn["band"] * band + dn["screen"] + dn["room"] * (k_per_lux * lux)
    Image.fromarray((dv.tonemap(img, exposure) * 255 + 0.5).astype(np.uint8)).save(path, quality=90, optimize=True)
    print("wrote", path.name)


def main(src):
    src = Path(src)
    OUT.mkdir(exist_ok=True)
    k1, _ = dv.room_scale(src / "probe.exr", 1.0)                 # room-group factor per lux on the desk
    hero = groups(src / "hero.exr")
    for room, (lux, exp) in ROOMS.items():
        save(hero, k1, lux, exp, 1.0, OUT / f"hero-{room}-on.jpg")
        save(hero, k1, lux, exp, 0.0, OUT / f"hero-{room}-off.jpg")
    for view in ("detail", "seat", "front"):
        save(groups(src / f"{view}.exr"), k1, 200.0, 1.4, 1.0, OUT / f"{view}.jpg")

    # calibration: white band, seen from the seat, against the study's tracer
    nums = {}
    cal = src / "calib.exr"
    if cal.exists():
        sys.path.insert(0, str(HERE.parent))
        from ribbon import designs as D
        from ribbon import study as S
        b = dv.load(cal)["band"] @ dv.LUMA * dv.PANEL_NITS
        h, w = b.shape
        col = b[:, w // 2 - 20: w // 2 + 20].mean(1)
        sm = np.convolve(col, np.ones(5) / 5, mode="same")
        cyc = float(col[sm >= 0.5 * sm.max()].mean())
        sc = D.sill(h=12.0, drop=34.0, **D.FINISHES["fine"])
        # the seat, in the right panel's own frame (10 degree toe-in), looking 300 mm along the panel
        trc = S.metrics(S.column(sc, np.array([112.9, 280.0, 640.1]), x=300.0, spp=1500))["mean"] * dv.PANEL_NITS
        nums = {"n-cyc": f"{cyc:.0f}", "n-trc": f"{trc:.0f}"}
        (OUT / "calibration.json").write_text(json.dumps(dict(cycles_nits=cyc, tracer_nits=trc), indent=1))
    info = json.loads((src / "hero.json").read_text())["info"]
    st = np.array(info["stand"])
    k = len(st) // 2
    t = st[k] - st[k - 1]
    nums["n-rake"] = f"{np.degrees(np.arctan2(-t[0], -t[1])):.0f}"
    nums["n-clear"] = "11"
    html = (HERE / "page" / "index.html").read_text().replace("/*__NUMS__*/{}", json.dumps(nums))
    (OUT / "index.html").write_text(html)
    print("wrote index.html", nums)


if __name__ == "__main__":
    main(sys.argv[1])
