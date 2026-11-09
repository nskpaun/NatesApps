"""Sanity checks of the tracer against closed-form answers.  python3 night-array/optics/test_tracer.py"""
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ribbon.tracer import sample_brdf, _smith_G1  # noqa: E402
from ribbon.scene import MAT_IDS  # noqa: E402

rng = np.random.default_rng(0)


def albedo(mat, theta_deg, n=400_000):
    th = math.radians(theta_deg)
    wo = np.tile([math.sin(th), 0.0, math.cos(th)], (n, 1))
    _, w = sample_brdf(np.full(n, MAT_IDS[mat]), wo, rng)
    return w.mean()


def test_lambert_albedo():
    # A Lambertian surface under a uniform sky of luminance 1 has luminance rho at every angle.
    for th in (0, 45, 75):
        a = albedo("matte_white", th)
        assert abs(a - 0.85) < 0.01, (th, a)


def test_metal_energy():
    # GGX metal with F0 = 0.55: directional albedo between the masking loss and F0..1 (Schlick).
    for th in (0, 30, 60):
        a = albedo("satin_titanium", th)
        assert 0.45 < a < 0.75, (th, a)
    # smooth metal at normal incidence reflects ~F0
    a = albedo("polished_titanium", 0)
    assert abs(a - 0.55) < 0.03, a


def test_no_energy_gain():
    for m in ("satin_white", "graphite", "black_glass", "satin_aluminium", "satin_oxblood"):
        for th in (0, 40, 80):
            assert albedo(m, th, 200_000) <= 1.0 + 1e-2, (m, th)


def test_smith():
    assert abs(_smith_G1(np.array([1.0]), 0.3)[0] - 1.0) < 1e-9


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); print("ok", name)
