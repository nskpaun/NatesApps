# Night Array viewer

The live CAD renderer inside the Night Array app: a three.js page that shows the dual-27" battle station from
`cad/export/model/` in a warm night "studio", plus CAD, X-ray and blueprint styles, the three modes (work, stow,
standalone), the docking sequence, explode, a section plane, dimensions and picking. The same page renders the
still images the app shows before the live view is ready (`android/app/src/main/assets/renders/*.jpg`).

The contract with the CAD pipeline and the app is [`../SPEC.md`](../SPEC.md), section 4. Everything the CAD side
provides in `scene.json` (groups, parts, materials and their colour / metal / roughness hints, poses, explode
vectors, the dock sequence and the `dock_latch` sub-group pivot, dims, screen layout) is read from there, never
hard-coded.

## How it ships

`node build.mjs` bundles `src/` with esbuild into one classic IIFE script and writes, into the app's assets:

```
android/app/src/main/assets/viewer/index.html     the page (transparent until "ready")
android/app/src/main/assets/viewer/viewer.js      three.js 0.170.0 + the viewer, minified (budget 1.5 MB)
android/app/src/main/assets/viewer/LICENSES.txt   three.js licence + the example modules that are bundled
```

The app serves assets through `WebViewAssetLoader` at
`https://appassets.androidplatform.net/assets/viewer/index.html`, so the page loads `../model/station.glb`,
`../model/station-edges.glb` and `../model/scene.json` straight from the CAD export (the app's Gradle build adds
`cad/export` as an assets directory). No network, no CDN, no module scripts.

The page keeps its background transparent and its canvas at opacity 0 until the first frame with the model is
drawn, so the app's still image (underneath the WebView) shows through until then.

## API (Kotlin -> JS)

```js
NA.setState(partial)   // object or JSON string; merges into the current ViewerState, returns the full state
NA.getState()          // the current ViewerState
NA.camera(name)        // hero | front | top | side | back | dock | trays | display  (animated)
NA.dock(step)          // align | lower | release | lift | play | reset   ("play" runs the whole sequence)
NA.frame(groupId)      // animated framing of one group
```

All of them are safe to call before the model has loaded: calls are queued and applied before the first frame.
The initial state can also come from the URL: `index.html?state=<URL-encoded JSON>`.

ViewerState (defaults in `src/state.js`; invalid values and unknown keys are ignored):

| key | values | |
|---|---|---|
| `mode` | `work` `stow` `standalone` | keyboard and mouse travel between pockets and desk mat through the pose's `via` waypoints; the laptop lifts out in standalone |
| `style` | `studio` `cad` `xray` `blueprint` | cross-fades from a snapshot of the old frame |
| `finish` | `titanium` `graphite` `oxblood` | recolours material `titanium` |
| `amber` | 0..1 | LEDs, bloom and the amber practical lights |
| `explode` | 0..1 | scene.json explode vectors |
| `section` | `null` or `{ axis: "x" \| "z", t: 0..1 }` | clipping plane across the bounds, with hatched caps |
| `dims` | bool | scene.json dims as 3D dimension lines + labels |
| `autorotate` | bool | |
| `isolate` | `null` or group id | others fade out, the camera frames the group |
| `selected` | `null` or group id | highlight (rim glow / tint / amber edges, per style) |
| `quality` | `high` `balanced` `battery` | pixel ratio + pixel budget, shadow map, MSAA, bloom, desk reflection |
| `cinematic` | bool | slow orbiting camera, no picking (Night shift) |

## Events (JS -> Kotlin)

Sent with `window.NightArrayHost.post(JSON.stringify(evt))`, or `console.log` when there is no host:

```
{ "type": "ready" }                                  first frame with the model drawn
{ "type": "pick", "group": "keyboard" | null }       a tap (< 8 px, < 350 ms), never a drag; null = empty space
{ "type": "dockStep", "step": "align" | "lower" | "release" | "lift" | "done" }
{ "type": "error", "message": "..." }                no WebGL2, model failed to load, context lost for good
```

Hooks for the tests and the stills tool (the app doesn't use them): `NA.on(fn)` listens to the same events in the
page, `NA.idle(ms)` resolves once nothing is animating and a frame is drawn, `NA._capture(true)` stops the LED
breathing so every frame is final, and `NA.ready`, `NA.error`, `NA._viewer` expose the state. The stills tool
also uses `NA._viewer.stillCamera(spec)` (a preset framing with its own lens) and `forcePixelRatio`.

## Source map

| file | |
|---|---|
| `src/main.js` | entry: `window.NA`, `?state=`, the pre-load queue, WebGL2 check, error reporting |
| `src/state.js` | ViewerState defaults, validation, partial merge |
| `src/bridge.js` | events to `NightArrayHost` / console |
| `src/app.js` | the `Viewer`: boot, state application, mode choreography, dock sequence, cameras, picking, render-on-demand loop, context loss |
| `src/model.js` | scene.json + GLBs -> group / sub-group / part hierarchy, pose targets, bounds |
| `src/materials.js` | one physical material per scene.json key (hints + brushed / clearcoat extras), finish, amber |
| `src/stage.js` | the night set: room and city bokeh, desk with contact shadow and blurred reflection, environment, key / rim lights, amber practicals |
| `src/post.js` | quality tiers and the HDR -> bloom -> tone-mapping pipeline |
| `src/cameras.js` | presets, aspect-aware framing (`fitPoints`), orbiting camera moves |
| `src/screen.js` | the desktops painted onto the dual panels (one per mode), wake / sleep cross-fade |
| `src/styles.js` | cad / xray / blueprint materials, B-rep edge lines, grid, style cross-fade |
| `src/section.js` | clipping plane and stencil section caps |
| `src/dims.js` | dimension lines and labels |
| `src/highlight.js`, `src/fade.js` | selection highlight; node fades (isolate, desk mat, laptop) |
| `src/textures.js`, `src/util.js` | procedural textures; tweens, easing, helpers |

## Build, test, render stills

Dependencies are pinned (`three` 0.170.0, `esbuild` 0.24.0, `playwright` 1.63.0) and installed in `node_modules`.
The tests and the stills run the real bundle in headless Chromium with SwiftShader WebGL2
(`--use-gl=angle --use-angle=swiftshader --enable-unsafe-swiftshader`), served by `test/serve.mjs`, which maps
URLs the same way the APK merges its assets.

```sh
npm run build        # node build.mjs            -> android/app/src/main/assets/viewer/  (--dev: unminified + source map; never commit it)
npm test             # build + node test/smoke.mjs   (about 3 minutes on SwiftShader)
npm run stills       # build + node tools/render_stills.mjs -> android/app/src/main/assets/renders/  (about 6 minutes)
npm run serve        # node test/serve.mjs 8787, then open http://127.0.0.1:8787/assets/viewer/index.html
node test/shots.mjs <outDir> [filter] [--portrait|--landscape]   # visual check set (PNG, phone-sized viewports)
```

`test/smoke.mjs` pretends to be the app (a stub `NightArrayHost` that records events) and checks: the page stays
transparent until exactly one `ready`; `?state=` and calls made before load (setState, camera, dock, frame) are
applied; every mode x style renders without console or page errors; the keyboard and mouse pass through
scene.json's `via` waypoints (clear of the rim) both ways and land on their poses; explode, section (x and z),
dims, isolate and frame for every group, finish, amber 0/1 and the quality tiers; a tap on the keyboard picks `keyboard`, empty
space picks `null`, a drag or long press picks nothing; `dock play` emits align, lower, release, lift, done; all
camera presets; the render loop goes quiet when idle (no renders, no rAF callbacks for 2 s) and while the page
is hidden; context loss and restore; a phone (touch, `isMobile`, 390x844 at DPR 3) with finger taps, a one-finger
orbit and a pinch; and the error paths (no WebGL2, model missing, no host).

`tools/render_stills.mjs` renders every still SPEC.md section 4 lists: `hero-work`, `hero-stow`,
`hero-standalone`, `dock-align`, `dock-lower`, `dock-release`, `trays`, `display`, `cad`, `xray`, `exploded`,
`blueprint`, `section`, `finish-titanium`, `finish-graphite`, `finish-oxblood`, `night`, `amber-off` (1600x900)
and `part-<group>` (900x900, isolated, studio; `internals` in x-ray) for every group in scene.json. Each still is
drawn at 2x (`--ss`), filtered down in the page and encoded as JPEG (q 0.85, `--q`). `node tools/render_stills.mjs
hero dock` renders only matching names; `--out <dir>` writes elsewhere (handy while tuning). Camera framing for
each still lives at the top of the file and uses the same presets and fitting as the live view, with a longer
lens. The dock stills keep the cradle in the middle third because the app crops them to narrow portrait cards.
Re-render the stills whenever the CAD export or the look changes.

## Performance notes

- Render on demand: a frame is drawn only when something changes (input, a tween, a state change). At rest the
  loop stops completely (the smoke test checks for zero renders and zero rAF callbacks over 2 s). The one
  exception is the stow-mode charge LEDs, which breathe at about 15 fps (not on `battery`, not while the page is
  hidden).
- Pixel budget per tier (2.4 / 1.5 / 0.9 MP) on top of the pixel-ratio cap (2 / 1.5 / 1), so a DPR-3 phone does
  not render 9x the pixels.
- The shadow map (2048 PCF soft on `high`, 1024 on `balanced`, 512 PCF on `battery`) and the contact shadow are
  redrawn only when the layout changes, never while orbiting.
- Bloom (UnrealBloom) runs only in studio and x-ray, and not on `battery`. The desk reflection renders the station
  a second time into a reduced-size target (0.5x on `high`, 0.33x on `balanced`, off on `battery`).
- B-rep edges from `station-edges.glb` are drawn as fat lines only in the cad, x-ray and blueprint styles.
- `renderer.info.render` holds the totals of the last whole frame (it is reset once per frame, not per pass).

Measured on a phone-sized page (390x844 CSS px, DPR 3, work mode, hero camera); the model is 41 meshes and
98 k triangles, `viewer.js` is 865 KiB. "Layout" frames also redraw the shadow map and contact shadow.
SwiftShader times are CPU-rendered and only meaningful relative to each other.

| style / quality | canvas | draw calls (orbit / layout) | triangles (orbit / layout) | SwiftShader ms per frame |
|---|---|---|---|---|
| studio / high | 780x1688 | 79 / 142 | 167 k / 332 k | 1106 |
| studio / balanced | 585x1266 | 79 / 142 | 167 k / 332 k | 792 |
| studio / battery | 390x844 | 36 / 99 | 83 k / 249 k | 332 |
| cad / high | 780x1688 | 60 / 91 | 253 k / 336 k | 906 |
| xray / high | 780x1688 | 79 | 265 k | 903 |
| blueprint / high | 780x1688 | 87 | 423 k | 1009 |

On `high`, bloom is 13 draw calls and about 11 % of the frame; the desk reflection is 29 draw calls, 83 k
triangles and about 7 %. Most of the frame is the main pass (4x MSAA, half-float, physical materials). The fat
edge lines are what puts cad and blueprint above studio in triangles.

## Known limits

- Verified in headless SwiftShader only; real-device frame rates are untested.
- Section caps need watertight solids. The base, neck and display shells are hollow, so their caps are thin
  strips (tinted amber in studio so they still read).
- The style cross-fade copies the canvas into a raw RGB8 texture handed to three via `renderer.properties`;
  revisit if three is upgraded.
