# Night Array: CAD pipeline

Parametric B-rep model of the Night Array station (dual 27" QHD display on a titanium
tray base with Qi2 charging pockets and a right-wing laptop dock), written in Python with
CadQuery 2.8 / OpenCASCADE. One command regenerates every deliverable in `export/`
from scratch, byte for byte. `SPEC.md` (one level up) is the contract for coordinates,
part ids, file paths and the `scene.json` shape.

## Source files

| File | What it is |
|---|---|
| `params.py` | Every dimension in mm (single source of truth). Copied verbatim into `scene.json` → `params`. |
| `model.py` | One function per part, built directly in app axes (+Y up, +Z toward the user) in the stow pose. `PARTS` lists id, group, name, material and the internal flag. |
| `build.py` | Builds all parts and writes everything in `export/`: GLBs, `scene.json`, STEP, STL, then calls `drawings.py`. |
| `drawings.py` | Drawing sheets: exact hidden-line projections (CadQuery SVG exporter / OCC HLR), A3 layout, dimensions, parts list, title block, top-view DXF, PNG rasters. |
| `stepfile.py` | Makes OCC-written STEP files reproducible (fixed timestamp, canonical order of the colour/style block). |
| `verify.py` | Checks the deliverables (see "Verification" below). |
| `requirements.txt` | `cadquery==2.8.0` (brings OCP 7.9, numpy, ezdxf, Pillow). |

## Deliverables (`export/`)

| Path | Contents |
|---|---|
| `model/station.glb` | glTF 2.0, metres. One node per part (`node.name` = part id, translation = pivot, no rotation/scale), `extras {group, material, internal}`, PBR materials named by material key. Tessellated per B-rep face, so normals are smooth within a face and crisp across edges. `display_screen` carries `TEXCOORD_0`: one 5120 × 1440 canvas split across the two panels (left u 0→0.5 outer edge → seam, right u 0.5→1; v 0 = top). |
| `model/station-edges.glb` | Same nodes; each mesh is one `LINES` primitive of the part's B-rep edges (seam and degenerate edges dropped). |
| `model/scene.json` | Params, bounds, materials, groups (with names and descriptions, pivots, mass, volume), parts (with explode vectors, bbox, mass), poses (`stow`, `work`, `standalone`), `dock_sequence`, dimension callouts, the `screen` block, the files index with real byte sizes, and the drawing index. |
| `files/night-array-assembly.step` | Full assembly, AP214, mm, stow pose. Nested by group (`NA-display`, `NA-stand`, …); every part named by its id; every solid coloured by its material. |
| `files/parts/<group>.step` | One coloured, multi-solid STEP per group. |
| `files/parts/<group>.stl` | One binary STL per group (mm). |
| `files/drawings/<group>.svg` | A3 drawing sheet: top / front / right side (third-angle) + isometric, overall dimensions, parts list, title block. Ivory and amber linework on a transparent background (made for the app's dark `#15110F` panel). |
| `files/drawings/<group>-top.dxf` | Top-view outline, layer `OUTLINE`, mm. |
| `drawings/<group>.png` | The sheet rasterised with headless Chromium, 2000 × 1414 px, transparent. |

Groups, in order: `display`, `stand`, `base`, `dock`, `laptop`, `keyboard`, `mouse`,
`deskmat`, `internals`. `dock_latch` + `dock_latch_led` form the `dock_latch` sub-group
pivot (it moves −z by 3 mm in the `release` dock step).

## Rebuild

```sh
cd night-array/cad
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt   # once
.venv/bin/python build.py            # wipes export/ and regenerates everything (about a minute)
.venv/bin/python verify.py           # geometry + file checks (~45 s); exit code 1 on any failure
```

* `build.py --only glb|step|drawings` regenerates one stage (no wipe). `--out DIR` writes somewhere
  else, which is how reproducibility is checked: `build.py --out /tmp/na && diff -r export /tmp/na`.
* Rasterising the PNG sheets needs Node 22 with the `playwright` package and its Chromium.
  `drawings.py` adds the global module dirs (`/usr/local/lib/node_modules_global`,
  `/opt/node22/lib/node_modules`) to `NODE_PATH`; set `NODE_PATH` yourself if Playwright lives elsewhere.
* Everything is deterministic: two builds produce identical bytes for all 49 files. STEP needs help for
  that. OCC writes the colour/style entities in pointer-hash order, so `stepfile.py` sorts that block
  and renumbers it without touching the geometry entities. DXF metadata (dates, GUIDs) is fixed through
  ezdxf's fixed-metadata mode.

## Opening the files

The STEP files are **Y-up** (the same axes as the app and glTF). FreeCAD and Onshape are Z-up, and so
is Fusion with its Z-up preference, so the station first appears lying on its back. Rotate it +90°
about X (this maps +Y to +Z and puts the user side toward −Y, the "Front" view) or just orbit to it.

* **FreeCAD** (0.21+ / 1.0): *File → Open* `night-array-assembly.step`. Under *Preferences →
  Import-Export → STEP* choose an import mode that keeps the assembly tree (Assembly or LinkGroup).
  Parts arrive named by id (`base_shell`, `dock_cradle`, …) under one node per group, coloured by
  material, in mm.
* **Autodesk Fusion**: upload the STEP through the Data Panel, or use *Insert → Insert Mesh/CAD* in
  an open design. You get one component per group with one body per solid, plus colours. With
  *Preferences → General → Default modeling orientation* set to Y up, it stands upright as exported.
* **Onshape**: *Import* (the upload arrow in the Documents page or a document's tab bar) and pick the
  STEP. Leave "Import as a single part studio" off to get an Assembly with the group/part tree, or turn
  it on for one Part Studio holding all 58 solids. Colours come through as part appearances.
* **Per-group files**: `files/parts/<group>.step` opens the same way. The STLs are mesh-only (mm,
  binary) for slicers and viewers.
* **Blender / any glTF viewer**: open `model/station.glb` (Y-up metres, stands upright). Its nodes
  are the parts, and `extras` carry group, material and the internal flag.

## Coordinates and units

App/glTF space is metres, +X right, +Y up, +Z toward the user. The desk is y = 0, x = 0 is the centre
of the base slab, z = 0 is the base's depth centre. STEP, STL, DXF and SVG are in mm in the same axes.
Everything is exported in the stow pose (laptop docked, keyboard and mouse in their pockets).

## How the model is built (short tour)

* **Display:** two 27" QHD panels (active area 596.7 × 335.7 mm each), toed in 10° about a vertical axis
  at x = 0, z = −62. Each facet is modelled once in a local "facet frame" (u along the panel away from
  the seam, w = panel normal) and placed with `place_facet()`, which rotates it, moves it to the seam
  axis, trims it at x = 0 and mirrors it for the left panel. The 14 mm gap between the active areas is
  covered by a 4 mm titanium mullion. The shared titanium rim, faceted graphite rear shroud (vents,
  keel, VESA hub), internal steel VESA spine and the two monitors' own scaler/power boards follow the
  same frame.
* **Stand:** a hollow trapezoid neck (320 → 180 mm, 4.8° rearward lean) from planar half-space
  cuts, filleted. `NIGHT ARRAY` is inlaid in titanium (CadQuery `text`), and an amber light bar sits
  under the glass.
* **Base:** a 1.29 m titanium tray with a 16 mm rim, a deck recessed to y = 30 (graphite liner with a
  titanium reveal), and keyboard and mouse pockets with floors at y = 16. Soft-touch pads sit over
  non-metallic coil windows. The shell is hollow, with mounting bosses. Rear I/O, exhaust grille and AC
  inlet are on the back face, with an amber under-glow and charge indicators at the front.
* **Dock:** a swept side profile (spline, 120 mm at the back down to 60 at the front), a 20 mm slot
  with 4 mm lead-in chamfers, oxblood panels inlaid flush, a press-release latch with an LED strip,
  and a sprung USB-C plug.
* **Devices:** a generic 304 × 212 × 15 laptop, a 75 % low-profile keyboard (84 keycaps fused into one
  solid), and an ambidextrous mouse lofted through 14 sections. Each device has its receiver coil(s).
* **Internals:** the compute board with vapor chamber, fin stack and blower, the PSU, three Qi2 coils on
  ferrite shields, and the dock PCB.

Masses use real densities. Solid envelopes of hollow devices (laptop, keyboard, mouse, PSU, boards)
use the effective densities listed in `build.py`, and each such part's `mass_note` in `scene.json`
says so.

## Verification (`verify.py`)

1. Every part's bounding box is checked against the SPEC envelope numbers (±0.6 mm), along with the
   display chord, the forward offset of the outer edges, and the latch size.
2. Interference: boolean intersection volume ≤ 0.5 mm³ for every overlapping pair of parts in the stow
   pose, the work and standalone poses, each `dock_sequence` step, and the laptop part-way out (10, 40
   and 80 mm).
3. Every STEP is re-imported, checking solid counts and volumes against the model (to 0.1 %). An XCAF
   read checks that every part is named and every solid carries its material colour. Each STL is
   checked as a valid binary file.
4. `scene.json` is checked against the SPEC shape, including that every file in the files index
   exists with exactly the listed byte size.
5. GLB nodes, extras, pivots, primitive modes, `TEXCOORD_0` on the screen, and file-size budgets.

Separately (not in the repo), both GLBs pass the Khronos `gltf-validator` with 0 errors and 0
warnings.
