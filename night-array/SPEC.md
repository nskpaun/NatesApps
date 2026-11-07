# Night Array — build contract

This file is the single contract between the three parts of the project. If code and this file
disagree, fix the code (or, if the contract itself is wrong, update this file in the same change).

```
night-array/
  SPEC.md                 this file
  cad/                    CAD pipeline (Python + CadQuery)          — owner: CAD
    requirements.txt      cadquery==2.8.0
    params.py             every dimension, in mm (single source of truth)
    model.py              parametric solids, one function per part
    build.py              runs everything → cad/export/
    export/               COMMITTED output (deliverable CAD files + app model)
      model/station.glb         triangles, one node per part (app renderer + external viewers)
      model/station-edges.glb   B-rep feature edges as LINES, one node per part
      model/scene.json          parts, groups, poses, explode vectors, dims, files index, params
      files/night-array-assembly.step
      files/parts/<groupId>.step        one STEP per group (multi-solid, coloured)
      files/parts/<groupId>.stl         one binary STL per group (mm)
      files/drawings/<groupId>.svg      drawing sheet (3 views + iso + title block)
      files/drawings/<groupId>-top.dxf  2D top-view outline
      drawings/<groupId>.png            rasterised drawing sheet for in-app viewing
  viewer/                 live renderer (three.js 0.170.0, bundled with esbuild) — owner: VIEWER
    package.json, src/*.js, index.html, build.mjs, test/*.mjs, tools/render_stills.mjs
    → writes android/app/src/main/assets/viewer/{index.html,viewer.js,LICENSES.txt}
    → writes android/app/src/main/assets/renders/*.jpg   (stills rendered by this same viewer)
  android/                Kotlin + Jetpack Compose app           — owner: ANDROID
    app/build.gradle.kts adds `../../cad/export` as an extra assets srcDir, so APK assets are:
      viewer/…  renders/…  model/…  files/…  drawings/…  concept/board.jpg
```

Never write outside your own directories (plus the two asset dirs the viewer owns).

## 1. Coordinate system & units

* **App / glTF space:** metres, **+Y up**, **+X right**, **+Z toward the user (front)**. Right-handed.
* Origin: desk surface is `y = 0`; `x = 0` is the centre of the main base slab; `z = 0` is the front-to-back centre of the base.
* CAD (`params.py`) works in **mm** in the same axes (Y up). CadQuery default is Z-up: either model in Y-up
  directly or rotate once on export. STEP/STL/DXF/SVG files are in **mm**; GLB is in **m**.
* The exported assembly is in the **stow pose** (laptop docked, keyboard & mouse in their charging pockets).

## 2. Geometry (mm, app axes). CAD owns the details; these are the envelope numbers everyone relies on.

| Group | Part id | Material | Notes |
|---|---|---|---|
| `base` | `base_shell` | titanium | Main slab x∈[-640,650], z∈[-150,150], y∈[0,36]. Plan corner R40, soft top-edge fillet. 16 mm perimeter rim at y=36; inner deck recessed to y=30. Keyboard pocket 376×136 (x×z) centred (-90, 62), floor y=16. Mouse pocket 82×134 centred (250, 62), floor y=16. Rear I/O cut-outs on the back face (left side). |
| `base` | `tray_pad_kb` | graphite | Soft-touch charging pad filling the keyboard pocket floor, y∈[16,18]. Device rests on y=18. |
| `base` | `tray_pad_mouse` | graphite | Same for mouse pocket, y∈[16,18]. |
| `base` | `base_glow` | amber_led | Thin under-glow strip, front bottom edge, x∈[-560,560], z≈148, y∈[2,5]. |
| `base` | `kb_charge_led` | amber_led | 30×2 mm indicator on the keyboard pocket's front lip (x=-90). |
| `base` | `mouse_charge_led` | amber_led | 16×2 mm indicator on the mouse pocket's front lip (x=250). |
| `base` | `base_feet` | rubber | Recessed feet strips (do not lift the base: base still sits at y=0). |
| `stand` | `neck` | graphite | Trapezoid neck: bottom width 320, top width 180, y∈[36,156], z∈[-140,-70], slight rearward lean. Joins display back. |
| `stand` | `neck_light` | amber_led | Light bar along the neck's top-front edge, ~150×5×3, y≈148–153. |
| `stand` | `neck_badge` | titanium | Inlaid "NIGHT ARRAY" lettering on the neck front face (CadQuery `text`). |
| `display` | `display_screen` | screen | **Dual 27" display (design decision — replaces the old single ultrawide).** Two off-the-shelf 27" QHD IPS monitors (2560×1440 each, active area 596.7 × 335.7 mm), stripped of their plastic housings and mounted side by side. Each panel is **toed in 10°** toward the user about a vertical axis through the seam at x=0, z=-62 (front surface at the seam), so the outer edges come forward (left facet runs along (−cos10°, 0, +sin10°) from the seam, right facet along (+cos10°, 0, +sin10°)). The visible seam between the two active areas is **14 mm** (7 mm each side of x=0). Active areas y∈[172,507.7], 0.3 mm proud of the bezel faces. One part, two facets. **Must carry TEXCOORD_0** (glTF convention, v 0 = top edge, 1 = bottom): the left panel maps u 0→0.5 (outer-left edge → seam), the right panel u 0.5→1 (seam → outer-right edge) — i.e. one 5120×1440 canvas split exactly like an OS spans two displays; the seam has no pixels. |
| `display` | `display_glass` | glass_black | The two monitors' black front faces / bezels, one facet per panel, from the seam out to 7+596.7+9 mm along each facet; height 360.7 (y∈[156,516.7]: 16 mm chin, 9 mm top). ~2 mm thick. Two solids, one part. |
| `display` | `display_seam` | titanium | "The honest seam": a 4 mm wide titanium mullion running the full height of the glass at x=0, slightly proud, covering the joint between the two panels' inner borders. |
| `display` | `display_frame` | titanium | Shared shroud front rim (~3 mm) that wraps the outer edges of both panels (hides their outer bezels) and follows the 10° fold at the seam. |
| `display` | `display_back` | graphite | Shared rear shroud following both facets (~45 mm deep behind the panel faces), vent slots, central spine cover with the VESA hub where the neck joins. |
| `display` | `display_spine` | steel | **internal: true.** Steel mounting spine with two VESA 100 plates angled ±10°, one per monitor. |
| `display` | `display_boards` | pcb | **internal: true.** Each monitor's own scaler + power board, kept as-is and mounted on the spine (two solids, one part). |
| `dock` | `dock_cradle` | titanium | Right wing x∈[650,775], z∈[-130,130]. Side profile: ~120 tall at the back, sweeping down to ~60 at the front (concave curve). Laptop slot 20 wide (x∈[712,732]), z∈[-112,112], floor y=24, lead-in chamfers. |
| `dock` | `dock_panels` | oxblood | 2 mm accent panels on the outer (+x) face and front face of the cradle. |
| `dock` | `dock_latch` | graphite | Press-release button on the cradle's front face, right side, ~34×22×14, y≈18–40. Its own sub-group pivot so it can be pressed (moves −z ~3 mm). |
| `dock` | `dock_latch_led` | amber_led | 26×3 strip on top of the latch button (moves with it). |
| `dock` | `dock_connector` | steel | Sprung USB-C plug standing up from the slot floor at z≈-60. |
| `laptop` | `laptop_body` | laptop_alu | Generic laptop, 304 (y, standing) × 212 (z) × 15 (x), R6 edges, lid seam groove, standing on its left side in the slot: x∈[714.5,729.5], y∈[24,328], z∈[-106,106]. Hinge edge faces −z. |
| `keyboard` | `keyboard_body` | graphite | 360 (x) × 120 (z), low wedge 9 mm front → 13 mm back, R8 corners. Stow: centred (-90, 62), bottom at y=18. |
| `keyboard` | `keyboard_keys` | keycap | ~75 % layout keycaps fused as one solid (unit 18.5 mm). |
| `mouse` | `mouse_shell` | graphite | 66 (x) × 118 (z) × 38 (y) ergonomic ambidextrous shell. Stow: centred (250, 62), bottom y=18. |
| `mouse` | `mouse_wheel` | rubber | Scroll wheel. |
| `mouse` | `mouse_glow` | amber_led | Amber accent strip at the mouse's rear. |
| `deskmat` | `deskmat` | felt | 820 × 3 × 300, centred (60, 0–3, 385). Only visible in `work` / `standalone` poses. |
| `internals` | `compute_board` | pcb | Mainboard in the base, x∈[-600,-300], z∈[-120,110], y≈4–6. "Compute stays in the base." |
| `internals` | `compute_heatsink` | steel | Vapor chamber + fin stack on the board, y≈6–22. |
| `internals` | `compute_fan` | graphite | Slim blower. |
| `internals` | `psu` | graphite | Internal power supply, x∈[330,470]. |
| `internals` | `qi_coil_kb` | copper | Two flat Qi2 coils under the keyboard pad (x=-170 and x=-10, z=62), y≈12–15. One part (two solids). |
| `internals` | `qi_coil_mouse` | copper | One coil under the mouse pad (250, 62). |
| `internals` | `ferrite_kb`, `ferrite_mouse` | ferrite | Shield plates under the coils, y≈10–12. |
| `internals` | `dock_board` | pcb | Dock PCB under the cradle. |
| `internals` | `keyboard_coil`, `mouse_coil` | copper | Receiver coils inside the keyboard / mouse. **These belong to groups `keyboard` / `mouse`** (so they move with them) but are flagged `internal: true`. |

Overall display width ≈ 1214 mm (chord), outer edges ≈ 106 mm forward of the seam. Story: "the pixels of a 49-inch
super-ultrawide (5120×1440) for the price of two good mainstream 27s; a dead panel is a cheap swap; your OS already knows
what to do with two displays — snap a window to each half". The seam is part of the deal, so it is celebrated, not hidden.

Internal parts (`internal: true`) are hidden in the `studio` style and shown in `xray`, `cad`(optional), exploded and section views.

### Material keys (fixed list — every part uses exactly one)
`titanium` (primary metal; recoloured by the finish selector), `graphite`, `oxblood`, `glass_black`, `screen`,
`keycap`, `rubber`, `amber_led` (emissive), `copper`, `pcb`, `ferrite`, `laptop_alu`, `felt`, `steel`.

## 3. Files written by CAD

### `model/station.glb`
* glTF 2.0 binary. One **top-level node per part**, `node.name == partId`. Node `translation` = the part's pivot
  in the stow pose (metres); mesh vertices are local to that node. No rotation/scale on nodes (bake it).
* Pivot = bottom-centre of the part's bounding box, except groups that animate use the group pivot from scene.json.
* Each mesh has one primitive: POSITION, NORMAL (per-B-rep-face smooth, so B-rep face boundaries are crisp),
  indices (uint32 allowed), and `material` whose `name == materialKey` with a reasonable pbrMetallicRoughness so the
  GLB looks right in external viewers too. `display_screen` also has TEXCOORD_0.
* `extras` on each node: `{ "group": "...", "material": "...", "internal": bool }`.
* Must pass `gltf-validator` with zero errors.

### `model/station-edges.glb`
* Same node names and translations; each mesh is a single `LINES` primitive (mode 1) of the part's B-rep edges
  (discretised, ≤ 0.25 mm chord error on small parts is fine; keep the file < 6 MB).

### `model/scene.json`
```jsonc
{
  "version": 1,
  "units": "m",
  "name": "Night Array — Work & Stow",
  "params": { /* the full params.py dict, mm */ },
  "bounds": { "min": [x,y,z], "max": [x,y,z] },                // stow pose, metres
  "materials": { "titanium": { "label": "Neutral Titanium" }, ... },  // every key from the list above
  "groups": [
    { "id": "base", "name": "Base & charging trays", "summary": "one line", "description": "2–4 sentences",
      "parts": ["base_shell", "tray_pad_kb", ...],
      "pivot": [x,y,z],                  // metres, world space, stow pose
      "bbox_mm": [w, h, d], "mass_g": 0, "volume_cm3": 0,
      "materials": ["titanium", "graphite", "amber_led"] }
    // groups, in this order: display, stand, base, dock, laptop, keyboard, mouse, deskmat, internals
  ],
  "parts": [
    { "id": "base_shell", "group": "base", "name": "Base shell", "material": "titanium", "internal": false,
      "explode": [dx,dy,dz],             // metres, offset at explode = 1
      "bbox_mm": [w,h,d], "volume_cm3": 0, "mass_g": 0 }
  ],
  "poses": {                              // per-GROUP delta transforms relative to the stow (CAD) pose
    "stow":       { "deskmat": { "hidden": true } },
    "work":       { "keyboard": { "t": [0, -0.015, 0.298] }, "mouse": { "t": [0.04, -0.015, 0.298] } },
    "standalone": { "keyboard": {"t": [...]}, "mouse": {"t": [...]}, "laptop": { "hidden": true } }
  },
  // "t" = translation in metres, "r" = rotation in degrees [rx,ry,rz] about the group pivot (optional), "hidden" optional.
  "dock_sequence": [                       // laptop / dock_latch deltas for each step
    { "step": "align",   "title": "Align",               "caption": "Guide into the open cradle",       "laptop": { "t": [0, 0.14, 0] } },
    { "step": "lower",   "title": "Lower",               "caption": "Seat the laptop onto the connector", "laptop": { "t": [0, 0, 0] } },
    { "step": "release", "title": "Press-release & lift", "caption": "Press to release, then lift out",  "laptop": { "t": [0, 0, 0] }, "dock_latch": { "t": [0, 0, -0.003] } },
    { "step": "lift",    "title": "Lift out",            "caption": "Laptop free; compute stays in the base", "laptop": { "t": [0, 0.16, 0] } }
  ],
  // dock_latch is a sub-group pivot: parts dock_latch + dock_latch_led move together under the name "dock_latch".
  "dims": [ { "id": "overall_w", "label": "1 474 mm", "a": [x,y,z], "b": [x,y,z], "dir": [0,1,0] } ],
  // dims: measured points (metres, stow pose) + "dir" = which way to offset the dimension line. Include at least:
  // overall width, base depth, overall height, display width, one panel's active width, the seam, work offset 150 mm (pose "work"; add "pose": "work").
  "screen": { "part": "display_screen", "layout": "dual", "panels": 2, "panel_inch": 27, "panel_active_mm": [596.7, 335.7],
              "resolution_each": [2560, 1440], "seam_mm": 14, "toe_in_deg": 10, "seam_axis": [0, 0, -0.062] },
  "files": [
    { "id": "assembly-step", "group": null, "format": "STEP", "label": "Full assembly", "path": "files/night-array-assembly.step", "bytes": 0 },
    { "id": "assembly-glb",  "group": null, "format": "GLB",  "label": "Full assembly", "path": "model/station.glb", "bytes": 0 },
    { "id": "base-step",     "group": "base", "format": "STEP", "label": "Base & charging trays", "path": "files/parts/base.step", "bytes": 0 },
    { "id": "base-stl", ... "format": "STL" }, { "id": "base-svg", ... "format": "SVG" }, { "id": "base-dxf", ... "format": "DXF" }
  ],
  "drawings": { "base": "drawings/base.png", ... }
}
```
Masses use real densities (titanium 4.43, aluminium 2.70, steel 7.85, copper 8.96, ABS/PBT 1.05–1.3, glass 2.5, felt 0.3, pcb 1.85, ferrite 4.8, rubber 1.2 g/cm³). Assume shells are solid unless you model them hollow; a concept-level number is fine but say so in the description.

## 4. Viewer (three.js) — the live CAD renderer

Served from APK assets through `androidx.webkit.WebViewAssetLoader` at
`https://appassets.androidplatform.net/assets/viewer/index.html`, so `../model/station.glb` resolves to the model.
Bundle is a single classic (IIFE) script `viewer.js` (no ES-module script tags, no network, no CDN).

### Initial state
`index.html?state=<URL-encoded JSON ViewerState>` — applied before the first frame (no flash of the default state).

### ViewerState (Kotlin → JS), applied with `NA.setState(obj)`; partial objects merge into the current state
```jsonc
{
  "mode": "work" | "stow" | "standalone",           // animates groups to scene.json poses
  "style": "studio" | "cad" | "xray" | "blueprint", // studio = PBR night scene; cad = matte grey + black B-rep edges on light bg;
                                                     // xray = translucent shells, internals visible; blueprint = edges only, dark navy + grid
  "finish": "titanium" | "graphite" | "oxblood",    // recolours material `titanium` (Neutral Titanium / Charcoal Graphite / Brushed Oxblood)
  "amber": 0.0..1.0,                                 // amber lighting intensity (0 = off; LEDs + bloom + bounce light)
  "explode": 0.0..1.0,
  "section": null | { "axis": "x" | "z", "t": 0.0..1.0 },  // clipping plane position across the bounds
  "dims": false,                                     // dimension overlay
  "autorotate": false,
  "isolate": null | "groupId",                       // show only this group (others hidden), frame it
  "selected": null | "groupId",                      // highlight
  "quality": "high" | "balanced" | "battery",        // pixel ratio, shadows, bloom
  "cinematic": false                                 // slow orbiting camera, no picking ("Night shift")
}
```
### Commands (Kotlin → JS)
* `NA.camera("hero"|"front"|"top"|"side"|"back"|"dock"|"trays"|"display")` — animated camera move.
* `NA.dock("align"|"lower"|"release"|"lift"|"play"|"reset")` — `play` runs align → lower → release → lift → reset, emitting `dockStep` events.
* `NA.frame("groupId")` — animated camera framing of a group.
* All functions are safe to call before the model has loaded (queue them).

### Events (JS → Kotlin)
`window.NightArrayHost.post(JSON.stringify(evt))` — if `NightArrayHost` is absent (desktop browser), `console.log` instead.
* `{ "type": "ready" }` — after the first frame with the model is drawn.
* `{ "type": "pick", "group": "keyboard" | null }` — tap (not drag) on a part; null = tapped empty space.
* `{ "type": "dockStep", "step": "align" | "lower" | "release" | "lift" | "done" }`
* `{ "type": "error", "message": "..." }` — e.g. WebGL2 unavailable, model failed to load.

### Stills (rendered by the viewer itself, headless Chromium, written to `android/app/src/main/assets/renders/`)
JPEG, 1600×900 unless noted. The app must tolerate any of these being missing.
`hero-work.jpg`, `hero-stow.jpg`, `hero-standalone.jpg`, `dock-align.jpg`, `dock-lower.jpg`, `dock-release.jpg`,
`trays.jpg` (charging pockets close-up), `display.jpg` (the dual panels + seam close-up), `cad.jpg`, `xray.jpg`, `exploded.jpg`, `blueprint.jpg`, `section.jpg`,
`finish-titanium.jpg`, `finish-graphite.jpg`, `finish-oxblood.jpg`, `night.jpg` (cinematic), `amber-off.jpg`,
and `part-<groupId>.jpg` (900×900, isolated group, studio style) for every group except `internals` (use xray style for that one).

## 5. Android app

* Package `com.natesapps.nightarray`, app name **Night Array**, minSdk 26, targetSdk/compileSdk 36, Kotlin + Compose,
  same Gradle/AGP/Compose versions as `ackoff/android`. Extra deps: `androidx.webkit:webkit`.
* Tabs: **Explore** (hero, modes, feature stories, docking sequence, materials, design principles, the original concept board,
  Night shift), **Studio** (live renderer + Compose controls), **Files** (CAD library: assembly + per group: render,
  drawing, specs, Share / Save for STEP, STL, GLB, SVG, DXF), **Specs** (spec sheet, bill of materials from scene.json, desk-fit check).
* One WebView instance, owned above the navigation, re-used by Studio and Night shift. Until `ready` arrives (or forever on
  Robolectric / if `error` arrives) the Studio shows the matching still from `renders/` underneath.
* Palette (also used by the viewer's background): bg `#0C0A09`, panel `#15110F`, panel2 `#1E1915`, line `#2E2621`,
  ink `#F2EAE1`, muted `#A39A90`, amber `#F2A04A`, amberSoft `#3A2614`, titanium `#BDB2A4`, oxblood `#7A2E2A`, graphite `#3A3735`.
  Headings: light weight, uppercase, wide letter spacing (like the concept board). Tagline: serif italic "Your hardware. Your OS."
