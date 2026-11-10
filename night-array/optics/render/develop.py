"""Develops a render from scene.py: denoises each light group, sets the room light and band level, tone-maps.

    python develop.py out_dir/hero.exr --lux 150 [--band 1.0] [--exposure 1.0] [--probe out_dir/probe.exr] -o hero.jpg

The EXR holds linear light in units of the panel's white (1.0 = 350 nits) in three groups: band, screen, room.
The room group is scaled so the desk receives --lux, using the probe render (a white card on the desk).
Needs: pip install OpenEXR oidn pillow numpy.
"""
from __future__ import annotations

import argparse
import ctypes
import json
from pathlib import Path

import numpy as np
import OpenEXR
from PIL import Image

PANEL_NITS = 350.0
LUMA = np.array([0.2126, 0.7152, 0.0722])


def load(path):
    f = OpenEXR.File(str(path))
    ch = {}
    for p in f.parts:
        for k, v in p.channels.items():
            ch[k.split(".", 1)[1] if k.startswith("ViewLayer.") else k] = np.asarray(v.pixels, np.float32)
    out = {g: ch[f"Combined_{g}"][..., :3] for g in ("band", "screen", "room")}
    out["albedo"] = ch["Denoising Albedo"][..., :3]
    out["normal"] = np.stack([ch[f"Denoising Normal.{a}"] for a in "XYZ"], -1)
    return out


def denoise(colour, albedo, normal):
    """Open Image Denoise on one HDR light-group image, guided by albedo and normal."""
    import importlib.util
    libdir = next(Path(importlib.util.find_spec("oidn").origin).parent.glob("lib.*"))
    for tbb in libdir.glob("libtbb.so*"):                       # the wheel ships TBB under a versioned name only
        ctypes.CDLL(str(tbb), mode=ctypes.RTLD_GLOBAL)
    import oidn
    h, w, _ = colour.shape
    colour, albedo, normal = (np.ascontiguousarray(a, np.float32) for a in (colour, albedo, normal))
    out = np.zeros_like(colour)
    dev = oidn.NewDevice()
    oidn.CommitDevice(dev)
    flt = oidn.NewFilter(dev, "RT")
    oidn.SetSharedFilterImage(flt, "color", colour, oidn.FORMAT_FLOAT3, w, h)
    oidn.SetSharedFilterImage(flt, "albedo", albedo, oidn.FORMAT_FLOAT3, w, h)
    oidn.SetSharedFilterImage(flt, "normal", normal, oidn.FORMAT_FLOAT3, w, h)
    oidn.SetSharedFilterImage(flt, "output", out, oidn.FORMAT_FLOAT3, w, h)
    # the wrapper does not expose the "hdr" switch; call the library it loaded directly
    lib = ctypes.CDLL(str(next(libdir.glob("libOpenImageDenoise.so*"))))
    lib.oidnSetFilter1b.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_bool]
    lib.oidnSetFilter1b.restype = None
    lib.oidnSetFilter1b(flt, b"hdr", True)
    oidn.CommitFilter(flt)
    oidn.ExecuteFilter(flt)
    oidn.ReleaseFilter(flt)
    oidn.ReleaseDevice(dev)
    return out


def room_scale(probe_path, lux):
    """Factor for the room group so that the desk card receives `lux`. A matte white card has L = E / pi."""
    p = load(probe_path)
    h, w, _ = p["room"].shape
    c = p["room"][h // 4: 3 * h // 4, w // 4: 3 * w // 4]
    e_unit = float(np.pi * (c @ LUMA).mean())                      # illuminance per unit room power, panel-white units
    return (lux / PANEL_NITS) / e_unit, e_unit


def tonemap(x, exposure=1.0, knee=0.62):
    """Linear up to the knee, then a soft shoulder; sRGB encoding. With exposure 1 the panel's white is close
    to display white, so everything is seen relative to the screen as it would be at the desk."""
    x = np.maximum(x * exposure, 0.0)
    y = np.where(x <= knee, x, knee + (1 - knee) * (1 - np.exp(-(x - knee) / (1 - knee))))
    return np.where(y <= 0.0031308, y * 12.92, 1.055 * np.power(y, 1 / 2.4) - 0.055)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("exr")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--probe")
    ap.add_argument("--lux", type=float, default=150.0)
    ap.add_argument("--band", type=float, default=1.0)
    ap.add_argument("--exposure", type=float, default=1.0)
    ap.add_argument("--no-denoise", action="store_true")
    ap.add_argument("--stats", action="store_true")
    a = ap.parse_args()
    r = load(a.exr)
    cache = Path(a.exr).with_suffix(".dn.npz")
    if a.no_denoise:
        dn = {g: r[g] for g in ("band", "screen", "room")}
    elif cache.exists() and cache.stat().st_mtime > Path(a.exr).stat().st_mtime:
        dn = dict(np.load(cache))
    else:
        dn = {g: denoise(r[g], r["albedo"], r["normal"]) for g in ("band", "screen", "room")}
        np.savez_compressed(cache, **dn)
    k = 1.0
    if a.probe:
        k, e_unit = room_scale(a.probe, a.lux)
    img = dn["band"] * a.band + dn["screen"] + dn["room"] * k
    out = (tonemap(img, a.exposure) * 255 + 0.5).astype(np.uint8)
    Image.fromarray(out).save(a.out, quality=93)
    if a.stats:
        print(json.dumps(dict(room_scale=k, band_max_nits=float((dn["band"] @ LUMA).max() * PANEL_NITS))))
    print("wrote", a.out)


if __name__ == "__main__":
    main()
