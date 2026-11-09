"""Cross-sections of the full-size optic and scaled-down versions (scale shrinks the band, reflector
and cove together about the band's bottom edge; brightness and contrast stay the same)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from ribbon.scene import Design, build_scene
from ribbon.diagram import draw
B = Design(reflector="parabolic", refl_psi=15, refl_f=20, refl_theta_min=-55, chin_finish="mirror", ramp_deg=32, band_h=12)
rows = [("Current: full size (band 12 mm, f 20)\n41 cd/m² · 8.3× at 500 lux · ribbon ≈34 mm", B),
        ("½ scale (band 6 mm, f 10)\n40 cd/m² · 9.2× · ribbon ≈22 mm", B.with_(scale=.5, band_h=6, refl_f=10)),
        ("⅓ scale (band 4 mm, f 7)\n36 cd/m² · 9.1× · ribbon ≈17 mm", B.with_(scale=.35, band_h=4.2, refl_f=7))]
fig, axs = plt.subplots(1, 3, figsize=(16, 5.6), facecolor="#fcfcfb")
for ax, (t, d) in zip(axs, rows):
    draw(ax, build_scene(d), t)
    ax.set_facecolor("#fcfcfb"); ax.grid(False)
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out", "10-slim-options.png")
fig.savefig(out, dpi=140, bbox_inches="tight"); print(out)
