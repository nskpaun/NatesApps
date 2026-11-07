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
| `build.py` | Builds all parts and writes everything in `export/`: GLBs and `scene.json` in app axes, STEP and STL rotated once into Z-up CAD axes (`to_cad_axes`), then calls `drawings.py`. |
| `drawings.py` | Drawing sheets: exact hidden-line projections (CadQuery SVG exporter / OCC HLR), A3 layout, dimensions, parts list, title block, top-view DXF, PNG rasters. |
| `stepfile.py` | Makes OCC-written STEP files reproducible (fixed timestamp, canonical order of the colour/style block). |
| `verify.py` | Checks the deliverables (see "Verification" below). |
| `requirements.txt` | `cadquery==2.8.0` (brings OCP 7.9, numpy, ezdxf, Pillow). |

## Deliverables (`export/`)

| Path | Contents |
|---|---|
| `model/station.glb` | glTF 2.0, metres. One node per part (`node.name` = part id, translation = pivot, no rotation/scale), `extras {group, material, internal}`, PBR materials named by material key. Tessellated per B-rep face, so normals are smooth within a face and crisp across edges. `display_screen` carries `TEXCOORD_0`: one 5120 × 1440 canvas split across the two panels (left u 0→0.5 outer edge → seam, right u 0.5→1; v 0 = top). |
| `model/station-edges.glb` | Same nodes; each mesh is one `LINES` primitive of the part's B-rep edges (seam and degenerate edges dropped). |
| `model/scene.json` | Params, bounds, materials (with a one-line `spec` of the finish), groups (with names and descriptions, pivots, mass, volume), parts (with explode vectors, bbox, mass, and a `mass_note` where an effective density is used), poses (`stow`, `work`, `standalone`; the keyboard and mouse carry `via` waypoints so they lift clear of the rim before sliding out), `dock_sequence`, dimension callouts (length labels measured between their end points), the `screen` block, the files index with real byte sizes, and the drawing index. |
| `files/night-array-assembly.step` | Full assembly, AP214, mm, **Z-up**, stow pose. Nested by group (`NA-display`, `NA-stand`, …); every part named by its id; every solid coloured by its material. |
| `files/parts/<group>.step` | One coloured, multi-solid STEP per group (mm, Z-up, named parts). |
| `files/parts/<group>.stl` | One binary STL per group (mm, Z-up). |
| `files/drawings/<group>.svg` | A3 drawing sheet: top / front / right side (third-angle; the CAD Top, Front and Right views of the Z-up files) + isometric, overall dimensions, parts list, title block. Ivory and amber linework on a transparent background (made for the app's dark `#15110F` panel). |
| `files/drawings/<group>-top.dxf` | Top-view outline, layer `OUTLINE`, mm, in the STEP's XY plane (x right, y away from the user), so it overlays the STEP seen from the top. |
| `drawings/<group>.png` | The sheet rasterised with headless Chromium, 2000 × 1414 px, transparent. |

Groups, in order: `display`, `stand`, `base`, `dock`, `laptop`, `keyboard`, `mouse`,
`deskmat`, `internals`. `dock_latch` + `dock_latch_led` form the `dock_latch` sub-group
pivot (it moves −z by 3 mm in the `release` dock step).

## Rebuild

```sh
cd night-array/cad
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt   # once
.venv/bin/python build.py            # wipes export/ and regenerates everything (about a minute)
.venv/bin/python verify.py           # geometry + file checks (~2.5 min); exit code 1 on any failure
```

* `build.py --only glb|step|drawings` regenerates one stage (no wipe). `--out DIR` writes somewhere
  else, which is how reproducibility is checked: `build.py --out /tmp/na && diff -r export /tmp/na`.
  `verify.py --export DIR` checks such a build before it replaces `export/`; `--fast` skips the
  sampled paths (laptop lift, stow ↔ work waypoints, explode).
* Rasterising the PNG sheets needs Node 22 with the `playwright` package and its Chromium.
  `drawings.py` adds the global module dirs (`/usr/local/lib/node_modules_global`,
  `/opt/node22/lib/node_modules`) to `NODE_PATH`; set `NODE_PATH` yourself if Playwright lives elsewhere.
* Everything is deterministic: two builds produce identical bytes for all 49 files. STEP needs help for
  that. OCC writes the colour/style entities in pointer-hash order, so `stepfile.py` sorts that block
  and renumbers it without touching the geometry entities. DXF metadata (dates, GUIDs) is fixed through
  ezdxf's fixed-metadata mode.

## Opening the files

The STEP and STL files are **Z-up, in mm**, the convention of FreeCAD, Onshape, current Fusion and every
slicer, so they open standing upright on the desk plane (z = 0) with no rotation. +X runs left to right as
you sit at the station, +Z is up and the user side faces −Y: the standard *Front* view (looking along +Y)
looks at the side you sit at, *Top* looks down on it and *Right* looks in from the dock side. The GLB stays
Y-up (glTF's convention; see "Coordinates and units").

* **FreeCAD** (0.21+ / 1.0): *File → Open* `night-array-assembly.step`. Under *Preferences →
  Import-Export → STEP* choose an import mode that keeps the assembly tree (Assembly or LinkGroup).
  Parts arrive named by id (`base_shell`, `dock_cradle`, …) under one node per group, coloured by
  material, in mm. View → Standard views → Front (key `1`) faces the user side.
* **Autodesk Fusion**: upload the STEP through the Data Panel, or use *Insert → Insert Mesh/CAD* in
  an open design. You get one component per group with one body per solid, plus colours. Fusion's
  default modeling orientation is Z up, so it stands upright as exported. An install still set to Y up
  (*Preferences → General → Default modeling orientation*) shows it lying on its back; switch the
  preference to Z up and start a new design.
* **Onshape**: *Import* (the upload arrow in the Documents page or a document's tab bar) and pick the
  STEP. Leave "Import as a single part studio" off to get an Assembly with the group/part tree, or turn
  it on for one Part Studio holding all 58 solids. Colours come through as part appearances. The view
  cube's *Front* faces the user side.
* **Per-group files**: `files/parts/<group>.step` opens the same way. The STLs are mesh-only (binary,
  mm, Z-up) for slicers and viewers. A slicer (PrusaSlicer, Bambu Studio, OrcaSlicer, Cura) shows each
  group upright and drops it onto its bed. The coordinates in each file are the group's own place on
  the desk (the display group spans z 153–520, for example), so per-group files imported into one CAD
  document line up with each other and with the assembly.
* **Blender / any glTF viewer**: open `model/station.glb` (Y-up metres, stands upright). Its nodes
  are the parts, and `extras` carry group, material and the internal flag. Blender's glTF importer
  converts Y-up to its own Z-up with the same mapping the STEP/STL use, so in Blender the GLB and the
  STLs (default axes, Up = Z, imported at scale 0.001 to get metres) line up.

## Coordinates and units

App/glTF space is metres, +X right, +Y up, +Z toward the user. The desk is y = 0, x = 0 is the centre
of the base slab, z = 0 is the base's depth centre. `params.py` and `model.py` work in these axes (in mm),
and `model/station.glb`, `model/station-edges.glb` and `model/scene.json` (pivots, poses, explode
vectors, dims, bounds) stay in them: everything the app and the viewer read is Y-up.

The CAD exchange files are rotated once on export (`build.to_cad_axes`, +90° about +X, set as an exact
matrix so no rounding noise gets in):

    CAD (x, y, z) = app (x, −z, y)        a scene.json point (x, y, z) m  →  (1000 x, −1000 z, 1000 y) mm

| File | X | Y | Z | Units |
|---|---|---|---|---|
| `station.glb`, `station-edges.glb`, `scene.json` | right | up | toward the user | m (`params` in mm) |
| STEP (assembly and per group), STL | right | away from the user | up | mm |
| `<group>-top.dxf` (top view) | right | away from the user | – | mm |

The DXF is the top view in the STEP's own XY plane, (x, y) = (x_app, −z_app). The SVG sheets are
third-angle: TOP is the CAD Top view (x right, y up the sheet, so the user side faces down toward
FRONT); FRONT looks at the user side (x right, z up); RIGHT SIDE looks in from +X (y to the right, z up,
the user side on its left, next to FRONT); ISOMETRIC looks from the front, right and above.
Everything is exported in the stow pose (laptop docked, keyboard and mouse in their pockets).

## How the model is built (short tour)

* **Display:** two 27" QHD panels (active area 596.7 × 335.7 mm each), toed in 10° about a vertical axis
  at x = 0, z = −62. Each facet is modelled once in a local "facet frame" (u along the panel away from
  the seam, w = panel normal) and placed with `place_facet()`, which rotates it, moves it to the seam
  axis, trims it at x = 0 and mirrors it for the left panel. The 14 mm gap between the active areas is
  covered by a 4 mm titanium mullion. `display_glass` is each stripped monitor's LCD module: the 2 mm
  black front plus a 10 mm module body behind it. The 2 mm VESA plates bolt to the module backs, on
  arms from a 36 × 38 mm hollow steel post; the monitors' own scaler/power boards sit on standoffs
  behind the arms. The shared titanium rim and the faceted graphite rear shroud (16 mm thin rim zone,
  vents, keel, VESA hub) follow the same frame.
* **Stand:** a hollow trapezoid neck (320 → 180 mm, 4.8° rearward lean) from planar half-space
  cuts, filleted. `NIGHT ARRAY` is inlaid in titanium (CadQuery `text`), and an amber light bar sits on
  the front face 22 mm below the display, low enough to show under its overhang from the seat.
* **Base:** a 1.29 m titanium tray with a 16 mm rim, a deck recessed to y = 30 (graphite liner with a
  titanium reveal), and keyboard and mouse pockets with floors at y = 16. Soft-touch polymer pads
  (non-metallic, so Qi2 passes) sit over non-metallic coil windows. The shell is hollow, with mounting bosses. Rear I/O, exhaust grille and AC
  inlet are on the back face, with an amber under-glow and charge indicators at the front.
* **Dock:** a swept side profile (spline, 120 mm at the back down to 60 at the front), a 20 mm slot
  with 4 mm lead-in chamfers, oxblood panels inlaid flush, a press-release latch with an LED strip,
  and a sprung USB-C plug.
* **Devices:** a generic 304 × 212 × 15 laptop, a 75 % low-profile keyboard (84 keycaps fused into one
  solid), and an ambidextrous mouse lofted through 14 sections. Each device has its receiver coil(s).
* **Internals:** the compute board with vapor chamber, fin stack and blower, the PSU, three Qi2 coils on
  ferrite shields, and the dock PCB.

Masses use real densities. Solid envelopes of hollow or composite devices (laptop, keyboard, mouse,
LCD modules, charging pads, PSU, boards, coils) use the effective densities listed in `build.py`, and
each such part's `mass_note` in `scene.json` says so.

## Verification (`verify.py`)

1. Every part's bounding box is checked against the SPEC envelope numbers (±0.6 mm), along with the
   display chord, the forward offset of the outer edges, and the latch size.
2. Interference: boolean intersection volume ≤ 0.5 mm³ for every overlapping pair of parts in the stow
   pose, the work and standalone poses, each `dock_sequence` step, and along the paths between them:
   the laptop part-way out (10, 40 and 80 mm), the keyboard and mouse along their `via` waypoints
   (8 samples per segment, desk mat shown), and the explode slider at 0.1 … 0.9 in the stow and work
   poses. Two kinds of pair are expected to cross while exploding and are left out by name: the base
   shell and the dock cradle have closed floors, so lifting them off the internals that stay on the
   desk passes the floor through those parts.
3. Every STEP is re-imported, checking solid counts and volumes against the model (to 0.1 %). An XCAF
   read checks that every part is named and every solid carries its material colour. Axes: the expected
   boxes are the fresh (app-axes) B-rep's mapped to CAD (x, −z, y) inside `verify.py`, independently
   of `build.to_cad_axes`, and every group STEP and every named part in the STEPs (with its assembly
   placements) must match them to 0.01 mm; the assembly must stand on z = 0 with the screen at
   z 172–507.7, the keyboard at y −122…−2 (user side toward −Y) and x unchanged. Each STL must be a valid
   binary file whose box matches the mapped model box to within its tessellation deflection, whose
   enclosed volume matches the B-rep to 1 % (a mirrored or inside-out mesh comes out negative), and
   whose stored facet normals follow the triangle winding. A Y-up, rotated-the-wrong-way or mirrored
   export fails these checks; solid counts and volumes alone could not tell.
4. `scene.json` is checked against the SPEC shape, including that every file in the files index
   exists with exactly the listed byte size, and against a fresh model build: `params` equals
   `params.py`, every part's bbox, volume, mass and explode vector match, the pose waypoints and dock
   lifts match `params.poses_mm`, and every length label is within 1 mm of the distance between its
   end points (`seam` and `panel_active_w` are nominal along-facet values).
5. GLB nodes, extras, pivots, primitive modes, `TEXCOORD_0` on the screen, each node's mesh bounds
   against the fresh B-rep (within 0.6 mm, the coarsest tessellation), and file-size budgets.

Separately (not in the repo), both GLBs pass the Khronos `gltf-validator` with 0 errors and 0
warnings.
