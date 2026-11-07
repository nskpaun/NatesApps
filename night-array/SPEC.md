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
      model/station.glb         triangles, one node per part (app renderer + external viewers)   Y-up, m
      model/station-edges.glb   B-rep feature edges as LINES, one node per part                   Y-up, m
      model/scene.json          parts, groups, poses, explode vectors, dims, files index, params  Y-up, m
      files/night-array-assembly.step                                                             Z-up, mm
      files/parts/<groupId>.step        one STEP per group (multi-solid, coloured)                Z-up, mm
      files/parts/<groupId>.stl         one binary STL per group                                  Z-up, mm
      files/drawings/<groupId>.svg      drawing sheet (3 views + iso + title block)               mm
      files/drawings/<groupId>-top.dxf  2D top-view outline                                       CAD XY, mm
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
* CAD (`params.py`, `model.py`) works in **mm** in the same axes (Y up). Everything the app and the viewer read stays
  in them: `model/station.glb`, `model/station-edges.glb` and `model/scene.json` are **Y-up, metres** (`params` in mm).
* **CAD exchange files are Z-up, mm** (so they open upright in FreeCAD, Onshape, current Fusion and every slicer):
  the STEP files (assembly and per group) and the STLs are rotated once on export, **+90° about +X**:
  `CAD (x, y, z) = app (x, −z, y)`. Up (+Y app) → +Z, the user side (+Z app) → −Y (so the CAD *Front* view, looking
  along +Y, faces the user side), +X unchanged, desk at z = 0. A `scene.json` point (x, y, z) m is
  (1000 x, −1000 z, 1000 y) mm in the STEP.
* The 2D files use the same CAD axes: the top-view DXF is (x_CAD, y_CAD) = (x_app, −z_app), mm; the SVG sheets
  (mm on A3, third-angle) show the CAD *Top*, *Front* and *Right* views plus an isometric.
* The exported assembly is in the **stow pose** (laptop docked, keyboard & mouse in their charging pockets).

## 2. Geometry (mm, app axes). CAD owns the details; these are the envelope numbers everyone relies on.

| Group | Part id | Material | Notes |
|---|---|---|---|
| `base` | `base_shell` | titanium | Main slab x∈[-640,650], z∈[-150,150], y∈[0,36]. Plan corner R40, soft top-edge fillet. 16 mm perimeter rim at y=36; inner deck recessed to y=30. Keyboard pocket 376×136 (x×z) centred (-90, 62), floor y=16. Mouse pocket 82×134 centred (250, 62), floor y=16. Rear I/O cut-outs on the back face (left side). |
| `base` | `deck_liner` | graphite | Inlaid deck liner, 1 mm, flush with the deck (y∈[29,30]), 1.2 mm titanium reveal. |
| `base` | `tray_pad_kb` | graphite | Soft-touch charging pad filling the keyboard pocket floor, y∈[16,18]. Device rests on y=18. Non-metallic (soft-touch PU over a glass-fibre carrier, so Qi2 passes; `graphite` is its colour): mass from an effective density of 1.2 g/cm³. |
| `base` | `tray_pad_mouse` | graphite | Same for mouse pocket, y∈[16,18]. |
| `base` | `base_glow` | amber_led | Thin under-glow strip, front bottom edge, x∈[-560,560], z≈148, y∈[2,5]. |
| `base` | `kb_charge_led` | amber_led | 30×2 mm indicator on the keyboard pocket's front lip (x=-90). |
| `base` | `mouse_charge_led` | amber_led | 16×2 mm indicator on the mouse pocket's front lip (x=250). |
| `base` | `base_feet` | rubber | Recessed feet strips (do not lift the base: base still sits at y=0). |
| `stand` | `neck` | graphite | Trapezoid neck: bottom width 320, top width 180, y∈[36,156], z∈[-140,-70], slight rearward lean. Joins display back. |
| `stand` | `neck_light` | amber_led | Light bar on the neck's front face just below the display, ~150×5×3, y≈126–131 (low enough to clear the display's overhang, so it shows from the seat). |
| `stand` | `neck_badge` | titanium | Inlaid "NIGHT ARRAY" lettering on the neck front face (CadQuery `text`). |
| `display` | `display_screen` | screen | **Dual 27" display (design decision — replaces the old single ultrawide).** Two off-the-shelf 27" QHD IPS monitors (2560×1440 each, active area 596.7 × 335.7 mm), stripped of their plastic housings and mounted side by side. Each panel is **toed in 10°** toward the user about a vertical axis through the seam at x=0, z=-62 (front surface at the seam), so the outer edges come forward (left facet runs along (−cos10°, 0, +sin10°) from the seam, right facet along (+cos10°, 0, +sin10°)). The visible seam between the two active areas is **14 mm** (7 mm each side of x=0). Active areas y∈[172,507.7], 0.3 mm proud of the bezel faces. One part, two facets. **Must carry TEXCOORD_0** (glTF convention, v 0 = top edge, 1 = bottom): the left panel maps u 0→0.5 (outer-left edge → seam), the right panel u 0.5→1 (seam → outer-right edge) — i.e. one 5120×1440 canvas split exactly like an OS spans two displays; the seam has no pixels. |
| `display` | `display_glass` | glass_black | The two stripped monitors' LCD modules with their black front faces / bezels, one facet per panel, from the seam out to 7+596.7+9 mm along each facet; height 360.7 (y∈[156,516.7]: 16 mm chin, 9 mm top). 2 mm black front plus the 10 mm module body behind it (12 mm deep, w∈[-12,0] along the facet normal; the body stops 1.5 mm short of the outer edge). Two solids, one part. Mass from an effective density (solid envelope of the modules). |
| `display` | `display_seam` | titanium | "The honest seam": a 4 mm wide titanium mullion running the full height of the glass at x=0, slightly proud, covering the joint between the two panels' inner borders. |
| `display` | `display_frame` | titanium | Shared shroud front rim (~3 mm) that wraps the outer edges of both panels (hides their outer bezels) and follows the 10° fold at the seam. |
| `display` | `display_back` | graphite | Shared rear shroud following both facets (~45 mm deep behind the panel faces; 16 mm thin rim zone, inner wall 1.5 mm behind the modules), vent slots, central spine cover (keel) with the VESA hub where the neck joins. |
| `display` | `display_spine` | steel | **internal: true.** Steel mounting spine with two 2 mm VESA 100 plates angled ±10°, one bolted to the back of each module, on arms from a 36×38 rectangular hollow post that stands on the neck. |
| `display` | `display_boards` | pcb | **internal: true.** Each monitor's own scaler + power board, kept as-is and mounted on standoffs behind the spine arms (two solids, one part). |
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

Overall display width ≈ 1214 mm (chord; 1 218 mm over the titanium frame, the `display_w` dim), outer edges ≈ 106 mm forward of the seam. Story: "the pixels of a 49-inch
super-ultrawide (5120×1440) for the price of two good mainstream 27s; a dead panel is a cheap swap; your OS already knows
what to do with two displays — snap a window to each half". The seam is part of the deal, so it is celebrated, not hidden.

Internal parts (`internal: true`) are hidden in the `studio` style and shown in `xray`, `cad`(optional), exploded and section views.

### Material keys (fixed list — every part uses exactly one)
`titanium` (primary metal; recoloured by the finish selector), `graphite`, `oxblood`, `glass_black`, `screen`,
`keycap`, `rubber`, `amber_led` (emissive), `copper`, `pcb`, `ferrite`, `laptop_alu`, `felt`, `steel`.

## 3. Files written by CAD

### Exchange files (`files/`)
* `night-array-assembly.step`: STEP AP214, **mm, Z-up** (section 1), stow pose. One assembly node per group (`NA-<groupId>`),
  every part named by its part id, every solid coloured by its material's `color`.
* `parts/<groupId>.step` (same, one group), `parts/<groupId>.stl` (binary, mm, Z-up), `drawings/<groupId>.svg` (A3 sheet,
  third-angle), `drawings/<groupId>-top.dxf` (top-view outline, layer `OUTLINE`, CAD XY, mm).
* Builds are byte-reproducible (fixed STEP/DXF stamps, canonical STEP colour block).

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
  // optional per material: "color" (sRGB hex), "metallic", "roughness", "density_g_cm3", "spec" (one-line finish text),
  // "emissive": true  (CAD writes all of them for every material; "emissive" only on amber_led)
  "groups": [
    { "id": "base", "name": "Base & charging trays", "summary": "one line", "description": "2–4 sentences",
      "parts": ["base_shell", "tray_pad_kb", ...],
      "pivot": [x,y,z],                  // metres, world space, stow pose
      "bbox_mm": [w, h, d], "mass_g": 0, "volume_cm3": 0,
      "materials": ["titanium", "graphite", "amber_led"] }
    // groups, in this order: display, stand, base, dock, laptop, keyboard, mouse, deskmat, internals
    // optional: "subgroups": { "dock_latch": { "parts": ["dock_latch", "dock_latch_led"], "pivot": [x,y,z] } } (dock)
  ],
  "parts": [
    { "id": "base_shell", "group": "base", "name": "Base shell", "material": "titanium", "internal": false,
      "explode": [dx,dy,dz],             // metres, offset at explode = 1
      "bbox_mm": [w,h,d], "volume_cm3": 0, "mass_g": 0 }
    // optional: "density_g_cm3" (the density used; CAD writes it on every part), "mass_note" (why it is an effective
    // density), "solids" (when > 1)
  ],
  "poses": {                              // per-GROUP delta transforms relative to the stow (CAD) pose
    "stow":       { "deskmat": { "hidden": true } },
    "work":       { "keyboard": { "t": [0, -0.015, 0.298], "via": [[0, 0.03, 0], [0, 0.03, 0.2]] },
                    "mouse":    { "t": [0.04, -0.015, 0.298], "via": [[0, 0.03, 0], [0.04, 0.03, 0.2]] } },
    "standalone": { "keyboard": {"t": [...], "via": [...]}, "mouse": {"t": [...], "via": [...]}, "laptop": { "hidden": true } }
  },
  // "t" = translation in metres, "r" = rotation in degrees [rx,ry,rz] about the group pivot (optional), "hidden" optional.
  // "via" (optional) = waypoints, same frame as "t", that the group passes through in order on its way from the stow pose
  // to this pose (play them reversed going back to stow). The keyboard and mouse lift 30 mm clear of the 36 mm rim, slide
  // forward until their back edge is past the base front (z = +200 mm), then set down on the mat; a straight line from
  // stow to "t" would run through the titanium rim. Animate each segment in turn (same timing for both groups).
  "dock_sequence": [                       // laptop / dock_latch deltas for each step
    { "step": "align",   "title": "Align",               "caption": "Guide into the open cradle",       "laptop": { "t": [0, 0.07, 0] } },
    { "step": "lower",   "title": "Lower",               "caption": "Seat the laptop onto the connector", "laptop": { "t": [0, 0, 0] } },
    { "step": "release", "title": "Press-release & lift", "caption": "Press to release, then lift out",  "laptop": { "t": [0, 0, 0] }, "dock_latch": { "t": [0, 0, -0.003] } },
    { "step": "lift",    "title": "Lift out",            "caption": "Laptop free; compute stays in the base", "laptop": { "t": [0, 0.16, 0] } }
  ],
  // dock_latch is a sub-group pivot: parts dock_latch + dock_latch_led move together under the name "dock_latch".
  "dims": [ { "id": "overall_w", "label": "1\u00a0415 mm", "a": [-0.64, 0, 0.15], "b": [0.775, 0, 0.15], "dir": [0, 0, 1] } ],
  // labels group thousands with a no-break space (U+00A0, written as-is in the file).
  // dims: measured points (metres, stow pose) + "dir" = which way to offset the dimension line. Include at least:
  // overall width, base depth, overall height, display width, one panel's active width, the seam, work offset 150 mm (pose "work"; add "pose": "work").
  // Length labels are the distance between "a" and "b"; only "seam" and "panel_active_w" carry nominal along-facet text.
  // CAD also writes "dock_h" and "base_h".
  "screen": { "part": "display_screen", "layout": "dual", "panels": 2, "panel_inch": 27, "panel_active_mm": [596.7, 335.7],
              "resolution_each": [2560, 1440], "seam_mm": 14, "toe_in_deg": 10, "seam_axis": [0, 0, -0.062],
              "canvas": [5120, 1440], "active_y_mm": [172, 507.7], "uv": "..." },   // last three optional
  "files": [                              // 38 entries; "bytes" = the file's real size
    { "id": "assembly-step", "group": null, "format": "STEP", "label": "Full assembly", "path": "files/night-array-assembly.step", "bytes": 0 },
    { "id": "assembly-glb",  "group": null, "format": "GLB",  "label": "Full assembly", "path": "model/station.glb", "bytes": 0 },
    { "id": "base-step",     "group": "base", "format": "STEP", "label": "Base & charging trays", "path": "files/parts/base.step", "bytes": 0 },
    { "id": "base-stl", ... "format": "STL" }, { "id": "base-svg", ... "format": "SVG" }, { "id": "base-dxf", ... "format": "DXF" }
    // per group, in group order: <id>-step, <id>-stl, <id>-svg ("<name> drawing"), <id>-dxf ("<name> top view")
  ],
  "drawings": { "base": "drawings/base.png", ... },
  "tagline": "Your hardware. Your OS.",   // optional
  "mass_note": "..."                      // optional: how the masses were estimated
}
```
Masses use real densities (titanium 4.43, aluminium 2.70, steel 7.85, copper 8.96, ABS/PBT 1.05–1.3, glass 2.5, felt 0.3, pcb 1.85, ferrite 4.8, rubber 1.2 g/cm³). Assume shells are solid unless you model them hollow; a concept-level number is fine but say so in the description.
A part whose solid stands for a hollow or composite device (laptop, keyboard, mouse, the LCD modules, the soft-touch pads, PSU, boards, coils) uses an effective density instead, and its `parts[]` entry says so in `mass_note`.

## 4. Viewer (three.js) — the live CAD renderer

Served from APK assets through `androidx.webkit.WebViewAssetLoader` at
`https://appassets.androidplatform.net/assets/viewer/index.html`, so `../model/station.glb` resolves to the model.
Bundle is a single classic (IIFE) script `viewer.js` (no ES-module script tags, no network, no CDN).

### Initial state
`index.html?state=<URL-encoded JSON ViewerState>` — applied before the first frame (no flash of the default state).
The page keeps its background transparent and its canvas hidden until that first frame (`ready`), so the app's still
underneath shows through until then.

### ViewerState (Kotlin → JS), applied with `NA.setState(partial)`
`partial` is an object or a JSON string; it merges into the current state, invalid values and unknown keys are ignored,
and the call returns the full state (`NA.getState()` returns it too). Defaults are the same in the Kotlin `ViewerState`,
the viewer (`viewer/src/state.js`) and the stills' base state (`viewer/tools/render_stills.mjs`), so still → live
doesn't shift.
```jsonc
{
  "mode": "work" | "stow" | "standalone",           // default "work". Animates groups to scene.json poses, through each pose's
                                                     // "via" waypoints (reversed going back to stow); the laptop lifts out in standalone
  "style": "studio" | "cad" | "xray" | "blueprint", // default "studio". studio = PBR night scene; cad = matte grey + black B-rep edges on light bg;
                                                     // xray = translucent shells, internals visible; blueprint = edges only, dark navy + grid
  "finish": "titanium" | "graphite" | "oxblood",    // default "titanium". Recolours material `titanium` (Neutral Titanium / Charcoal Graphite / Brushed Oxblood)
  "amber": 0.0..1.0,                                 // default 0.8. Amber lighting intensity (0 = off; LEDs + bloom + bounce light)
  "explode": 0.0..1.0,                               // default 0. Along the scene.json explode vectors
  "section": null | { "axis": "x" | "z", "t": 0.0..1.0 },  // default null. Clipping plane position across the bounds (hatched caps)
  "dims": false,                                     // default false. Dimension overlay (scene.json dims)
  "autorotate": false,                               // default false
  "isolate": null | "groupId",                       // default null. Show only this group (others fade out), frame it; a group the
                                                     // pose hides (laptop in standalone, desk mat in stow) is shown at its rest place
  "selected": null | "groupId",                      // default null. Highlight
  "quality": "high" | "balanced" | "battery",        // default "high". Pixel ratio + pixel budget, shadows, MSAA, bloom, desk reflection
  "cinematic": false                                 // default false. Slow orbiting camera, no picking ("Night shift")
}
```
### Commands (Kotlin → JS)
* `NA.camera("hero"|"front"|"top"|"side"|"back"|"dock"|"trays"|"display")` — animated camera move.
* `NA.dock("align"|"lower"|"release"|"lift"|"play"|"reset")` — a single step moves the laptop / `dock_latch` to that
  `dock_sequence` step (`reset` = back to the stow state: laptop seated, latch at rest) without events. `play` frames the `dock` camera (unless cinematic) and runs
  align (0 s) → lower (1.5 s) → release (3.05 s) → lift (3.9 s) → reset (5.5 s), posting a `dockStep` event as each step
  starts; **`done` is posted when the reset motion starts** (the laptop going back into the cradle is not "lift" any more),
  and that motion ends at about 6.7 s. A step or `play` sent meanwhile takes over.
* `NA.frame("groupId")` — animated camera framing of a group.
* All functions are safe to call before the model has loaded: calls are queued and applied before the first frame
  (they jump instead of animating). A queued `play` waits for the first frame: its steps and events are timed from then.

### Events (JS → Kotlin)
`window.NightArrayHost.post(JSON.stringify(evt))` — if `NightArrayHost` is absent (desktop browser), `console.log` instead.
* `{ "type": "ready" }` — once, after the first frame with the model is drawn.
* `{ "type": "pick", "group": "keyboard" | null }` — a tap (moves < 8 px, lifts within 350 ms; never a drag or long press)
  on a part; null = tapped empty space. Finger taps get target expansion for groups smaller than 44 dp on screen.
* `{ "type": "dockStep", "step": "align" | "lower" | "release" | "lift" | "done" }` — only from `play` (see above).
* `{ "type": "error", "message": "..." }` — no WebGL2, no half-float render targets, model failed to load, WebGL context
  lost for good.

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
