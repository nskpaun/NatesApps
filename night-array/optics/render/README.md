# Light ribbon renders

Path-traced renders (Blender Cycles) of the light ribbon on the Night Array station. They use the station's own CAD model plus the ribbon optics that [`../run.py`](../README.md) validated:

- a 12 mm light band in the screen's bottom rows;
- an off-axis parabolic reflector with mirror film on the chin;
- a satin titanium ramp rising 32° toward the back, inside a dark cove.

The reflector and cove follow each panel's 10° toe-in, mitred at the seam.

**Nothing in the ribbon is faked.** No light in the scene stands in for it. Every bit of ribbon light starts as screen pixels and reaches the camera through the mirror and the satin metal. The brightness and contrast you see are the physics, not an art direction.

| Shot | What it shows |
|---|---|
| `hero_open`, `seated_open` | The open variant (reflector f = 12 mm) in an evening room: a taller, softer ribbon |
| `hero`, `seated` | The recommended high-contrast design (f = 20 mm): the reflector is a larger hood and the ribbon reads as a thin line |
| `cove` | Close-up along the glint direction, shallow depth of field (open variant) |
| `office` | Seated view with a 500-lux room |
| `daylight` | Sun through the window blinds, 5,000 lux: the ribbon all but disappears, as the optics study predicts |
| `bass`, `treble`, `dock` | Software patterns: a slow bass swell, treble highlights (blurred to soft spots), and the docking sweep mid-way |

```bash
python3 -m venv .venv && .venv/bin/pip install bpy==5.2.3 pillow   # Blender as a Python module (needs Python 3.13)
.venv/bin/python render.py --list
.venv/bin/python render.py seated_open hero_open --samples 192     # → out/<shot>.png
.venv/bin/python render.py all --scale 0.3 --samples 48            # quick previews of every shot
```

`screen.py` draws the 5120 × 1440 screen canvas: a RoseOS-style desktop, the light band in the bottom 51 rows, and black rows inside the reflector. It also draws the band patterns (`concept`, `bass`, `treble`, `dock`).

## Notes and concept changes

- **Scale:** 1 scene radiance unit = 350 cd/m² (panel full white). Room light is given in lux: the evening scenes are about 30 lux plus a warm lamp.
- **Base:** rebuilt 60 mm deeper, with the charging pockets moved 60 mm forward, so the cove fits between the display and the pockets. The keyboard and mouse are in the work pose on the desk mat.
- **Neck light bar:** removed, because it would sit inside the cove.
- **Neck:** still passes through the cove behind the seam, so it shows as a dark block in the middle of the ribbon. A real build would route the neck behind the cove or split the ramp around it.
- **Materials:** satin titanium is GGX α ≈ 0.25 (Blender roughness 0.5) on a metal with F0 ≈ 0.55. The mirror reflects 92 %. The screen is an emitter under an anti-glare dielectric.
