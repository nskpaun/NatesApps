# Nate's Worlds: implementation plan for moving outdoor scenes with sound

All paths are under `/Users/rose/NatesApps/.claude/worktrees/local-ai-mesh-processing-30d48e/local-worlds`. Nothing was edited or run in this phase; I only read code and the Spark source.

## 0. Decision

**Base design: the risk-first one**, with its mesh movers replaced by a route none of the three proposed but all the findings support: **train twice, split offline**.

- **Things that leave their spot** (`swing`, `spin`, `bob`, `path`):
  - They stay in the painted blockout, as today.
  - `consistent.py` writes two training sets from the same paintings: one with them (today's output) and one without, where the ground and wall behind are filled by the existing `fill_tex`.
  - Both sets are trained.
  - A new `movers.py` copies each mover's splats out of the first PLY, and the viewer moves them as their own `SplatMesh`.
- **Why this route:**
  - The mover is a splat like the room, so no look mismatch (the risk design's top worry).
  - The ground under it is trained fill, not a hole or flat discs (the simplest design's top worry).
  - It needs neither `bg_color` training nor painting an object alone (the quality design's two unverified gates).
- **Cost:** about 2 to 3 extra minutes per world with such movers. This is an estimate from the measured 71 s training and 57 s re-projection.
- **Sway** stays in the room splat via `SplatSkinning` in the viewer.
- **Tiny flyers and falling bits** are procedural `SplatGenerator`s.
- **Outdoor** is the 20 m shell from the outdoor study.
- **Audio** is the finished `audio.js`.

**Cut from this build:**
- separate painting or training of movers on a plain backdrop
- vertex-coloured mesh movers
- sprite billboards
- `snowBox`
- stitching outdoor worlds with doorways
- a second layout question
- a local music model (later option; needs your approval because it is a new download)

## 1. Disputed claims, checked in the code

| Claim | Finding | Consequence |
|---|---|---|
| Motion inside `objects` changes the shapes checksum | True. `shapes.stamp` (`thread/shapes.py:34`) and `thread/pipeline.py:84` hash `[room, objects]` only. | Motion goes in a top-level `motions` list keyed by object index. No checksum code changes. |
| Paint meta might hash `boxes.json` | False. `thread/chisel_ring.py:231` hashes views, room, paint size, style, chain, file and shapes. | Editing motion never repaints. Outdoor keys are added to `meta` only when outdoor. |
| `yaw = atan2(dx, dz)` points a piece's front along travel | True. `to_world` (`thread/llm_boxes.py:113-115`) maps local +v to `(sin yaw, cos yaw)`. | Use it for `path`. |
| A car's front will face travel | Only its long axis is guaranteed. `place()` (`thread/shapes.py:347-353`) may pick turns (1, 3) and then chooses by aim. | The car lies along the road but may drive tail-first. Stated as a limit. |
| A hanging piece's shape would drop to the floor | False. `support()` (`thread/shapes.py:95`) starts from the box's own underside. | Honouring `base` for movers is safe. |
| Everything is forced to the floor | True (`thread/llm_boxes.py:170`). | A swing frame cannot be built from pieces. Add one general static shape, `arch` (two posts and a top beam). |
| Bone transform is `p' = R·p + (pos − restPos)` | True (`setBoneQuatPos`, `spark.module.js:13337`), dual-quaternion mode. | Rotation about pivot c uses translation `c − R·c`. Sway uses rotation bones about the base, so partial weights bend about the same point. |
| The shell needs changes in `spike/blockout.py` | False. `trace` labels faces by the nearest `ROOM` plane, and `free()` and the cameras use `RW`/`RD`. | No file in `spike/` is touched. |
| Pass B needs new hole-fill logic | False. `fill_tex` (`thread/consistent.py:169-185`) covers it. | Two real catches: `B.visible` reads the global `B.PRIMS` and must keep the full list, and the halo penalty is soft and covers shapes only. Both are handled in section 3. |
| PLY layout | 27 float32 per splat (xyz, normals, 3 dc, 9 rest, opacity, 3 scale, 4 rot). | Splitting is a numpy row copy; no Gaussian maths. |
| `style` is in the scene entry | False. | `pipeline.py` adds it; audio seeds from it. |

## 2. Data contract

Every new key is optional. A world without them behaves exactly as today.

### 2a. `boxes.json` (written by `llm_boxes.py`)

All positions are in room metres.

```json
{"request": "...", "room": [14, 6, 12],
 "objects": [{"name": "tree", "prims": [...]},
             {"name": "swing frame", "prims": [...3 boxes...], "open": true},
             {"name": "swing seat", "prims": [{"shape": "box", "c": [7, 0.55, 6], "h": [0.25, 0.05, 0.12], "yaw": 0}]},
             {"name": "car", "prims": [...], "yaw": 1.5708}],
 "setting": "outdoor", "surround": "rows of trees and distant houses",
 "wind": {"strength": 0.5, "from": 250},
 "mood": {"feel": "bright", "energy": 0.5, "time": "day"},
 "motions": [
  {"i": 0, "type": "sway", "amount": 0.6, "stiff": 0.35, "phase": 0.13, "sound": "rustle"},
  {"i": 2, "type": "swing", "pivot": 2.3, "axis": "depth", "angle": 20, "period": 2.9, "phase": 0.4, "sound": "creak"},
  {"i": 3, "type": "path", "points": [[1.5, 1.2], [12.5, 1.2]], "speed": 3, "mode": "loop", "pause": 4, "phase": 0, "sound": "rumble"}],
 "effects": [
  {"type": "wander", "label": "bees", "at": [3, 5], "radius": 1.2, "height": [0.4, 1.4], "count": 12, "size": 0.02, "speed": 1.2, "colours": ["#d8a520", "#3a2a10"], "sound": "buzz"},
  {"type": "drift", "label": "leaves", "at": [7, 9], "radius": 4, "height": [0, 5], "count": 120, "size": 0.05, "fall": 0.6, "colours": ["#c9682a", "#8a9a3a"], "sound": "none"}]}
```

Motion primitives and clamps:

| type | parameters | clamps and defaults | how it is shown |
|---|---|---|---|
| `sway` | `amount`, `stiff` | amount 0..1 (0.6); stiff 0..0.8 (0.35) | skinned in the room splat |
| `swing` | `pivot` (m above ground), `axis` ("depth" or "width": the piece's own direction it swings along), `angle`, `period` | angle 4..30° (20); period default 2π√(L/9.8), clamp 1.5..6 s | lifted |
| `spin` | `axis` ("up", "width", "depth"), `period` | 1..60 s (8) | lifted |
| `bob` | `height`, `period` | 0.02..0.3 m (0.1); 1.5..8 s (3) | lifted |
| `path` | `points` (2..4 `[x, z]`), `speed`, `mode` ("loop" or "back"), `pause` | speed 0.2..8 m/s (3); pause 0..30 s; indoors forced to "back" | lifted |

- `sound` is one of `rustle | buzz | rumble | creak | chirp | none`. Default by type: sway rustle, swing creak, path rumble, wander buzz, others none.
- `mood.feel` is one of `calm, warm, bright, dreamy, playful, mysterious, melancholy, eerie`.
- Effects clamps:
  - at most 4 effects
  - wander: count 1..40, size 0.01..0.3, radius 0.3..6, speed 0.2..4
  - drift: count 10..400, size 0.01..0.15, fall 0..2
- `setting` is outdoor only for the exact string "outdoor".
- Caps: at most 40 motions, of which at most 12 lifted.
- `phase` is 0..1 and distinct per ring or corner copy.

### 2b. Interface from `chisel_ring.py` (implementer A) to `consistent.py`, `movers.py`, `blockout_mesh.py` (implementer B)

Module attributes:
- `C.OUT`: bool, outdoor.
- `C.MARGIN`: 20.0 outdoors, else 0. `B.ROOM` is already grown.
- `C.SURROUND`: string.
- `C.LIFT`: sorted list of object indices whose motion type is swing, spin, bob or path.
- `C.halo(sid, also=(), px=HALO)`: as today, plus the objects in `also`, with band width `px`. Called with no extras it is identical to today.

### 2c. Files written by implementer B in `WORLD/gen_c/`

- `lifted.json`: `[3, 5]`. Written by `consistent.py`; the objects actually removed from the bare set.
- `sky.json`: `[r, g, b]`, 0..1, outdoor only.
- `mover_NNN.ply`, `mover_NNN.glb`, `mover_NNN_collider.glb`, and `movers.json`. Written by `movers.py`. All three files per mover are in the with-movers training's file frame.

### 2d. Scene entry in `thread/scenes.json` (B writes, C reads)

`gen_c_metre.json` gains the keys below and `pipeline.py` copies them. File names become URL paths like `ply`.

```json
{"...today's keys...": 0, "style": "sunny spring park, soft morning light",
 "fromRoom": [16 numbers, row-major 4x4: room metres -> gen_c file units, mirror included],
 "setting": "outdoor", "sky": [0.62, 0.75, 0.90], "surround": "...",
 "wind": {"strength": 0.5, "from": 250}, "mood": {"feel": "bright", "energy": 0.5, "time": "day"},
 "effects": [ ...as in boxes.json... ],
 "movers": [
  {"i": 0, "name": "tree", "type": "sway", "render": "skin",
   "box": {"c": [3, 2.5, 9], "h": [1.5, 2.5, 1.5], "yaw": 0}, "amount": 0.6, "stiff": 0.35, "phase": 0.13, "sound": "rustle"},
  {"i": 2, "name": "swing seat", "type": "swing", "render": "splat",
   "box": {"c": [7, 0.55, 6], "h": [0.25, 0.05, 0.12], "yaw": 0}, "pivot": [7, 2.3, 6], "axis": "depth", "angle": 20, "period": 2.9, "phase": 0.4, "sound": "creak",
   "ply": "/worlds/x/gen_c/mover_002.ply", "mesh": "/worlds/x/gen_c/mover_002.glb", "collider": "/worlds/x/gen_c/mover_002_collider.glb",
   "fromRoom": [16 numbers: room metres -> THIS ply's file units], "splats": 5210}]}
```

- `box` is the yaw-oriented bounds in room metres: mesh bounds when the object has a shape, else prim bounds.
- A `path` mover also carries `points` as `[x, z]` in room metres, plus `speed`, `mode`, `pause`.
- A lifted mover whose split failed is omitted from `movers`, left in the static mesh, and stays static. Motion can never fail a world.

## 3. Work split by file ownership

Three implementers, no shared file. `spike/blockout.py` and `thread/train_scene.py` are not touched.

### Implementer A: layout and painting

Owns `thread/llm_boxes.py`, `thread/shapes.py`, `thread/chisel_ring.py`, `README.md`, and new `thread/tests/test_layout.py`.

**`llm_boxes.py`**
- Prompt (lines 29-66):
  - Add `setting`, `surround`, `wind`, `mood`, `effects`, and an optional `motion` and `sound` per piece.
  - Outdoor wording: "room" is the patch of ground you can walk on, 10 to 16 m; big boundary things go on edges with `wall`; height is the tallest thing.
  - Rule: the moving part is its own piece. A hanging part has `base` above the ground and hangs under an `arch` piece.
  - Rule: small or thin moving things (insects, birds, falling leaves, petals, snow) are effects, never pieces.
  - Rule: a travelling piece has size `[width, height, length]` and a clear strip along its points.
  - One outdoor example using sway, arch plus swing, path, wander and drift.
  - `num_ctx` 8192.
- New static shape `arch`, size `[width, height, depth]`: two 0.12 m posts and a 0.12 m beam. The object gets `"open": true`.
- `expand`:
  - Outdoors: height clamp 3..12, no `window`.
  - Line 170: honour `base` only for pieces with motion swing, spin or bob, clamped to room height minus piece height.
  - `path`: place at `points[0]`, yaw `atan2(dx, dz)` of the first segment, forced into the object's `yaw`. Drop the motion if the length is under 1 m.
  - Shrink a swing's angle so its arc stays 0.1 m clear of the ground.
  - Validate motions into `info["motions"]`, with `i = len(objs)` taken before the append; drop those with `i >= 80`.
  - Validate `effects`, `wind`, `mood`.
  - A malformed motion or effect is dropped and the piece is kept.
  - Environment variable `WORLD_SETTING` (indoor or outdoor) overrides the model.
- Line 201 already dumps `**info`.

**`shapes.py`**
- `plan` skips objects with `"open"`, so posts stay posts.
- `plan` ranks kinds that have a motion first.
- No checksum change.

**`chisel_ring.py`**
- Lines 16-17: `OUT`, `MARGIN`, `SURROUND`, the shell `B.ROOM`, and `LIFT` from `world.get("motions")`.
- `prep` (103-106): outdoors `inv = 0` where `sid` is 0, 2, 3, 4 or 5, and `lo = 0`.
- Prompt (147-148): `outdoor photo, {style}. {what}`, plus ` Beyond: {surround}, under an open sky.` when backdrop faces fill more than 5% of the view. The empty case becomes "An open stretch of ground."
- `halo(sid, also=(), px=HALO)`.
- `meta` gains setting, margin and surround only when outdoor.

**`tests/test_layout.py`** (no model)
- An old canned layout gives byte-identical `room` and `objects` to the current code.
- Every primitive clamps.
- A path piece's yaw is right.
- Ring copies have distinct phases.
- Malformed motion is dropped and the piece kept.
- `prep` on a copy of `thread/worlds/garage-shapes` gives identical depth PNG hashes.

**`README.md`**: the new features and the limits in section 6.

### Implementer B: movers, assembly, builds

Owns `thread/consistent.py`, new `thread/movers.py`, `thread/blockout_mesh.py`, `thread/pipeline.py`, `thread/server.py`, `thread/scenes.json` entries and the test worlds.

**`consistent.py`**
- Wrap everything after the pool (lines 133-198) in `write(results, out, bare)`. With no lifted movers it is called once and the output must be byte-identical to today's. Check this on the garage.
- When `C.LIFT` is non-empty:
  - First call writes `{D}/{name}_m` (today's content).
  - Set a module flag and start a second pool. In its `render`:
    - trace targets with `B.PRIMS`/`C.PRIM_OBJ` filtered to exclude lifted objects;
    - restore the full list around the `B.visible` call;
    - treat source pixels inside `C.halo(ssid, also=C.LIFT, px=49)` as never a source for room faces.
  - Second call writes `{D}/{name}_c` (bare), with init points from it.
  - Write `lifted.json`.
  - Any exception in the second pass: write `{name}_c` as today, `lifted.json` = `[]`.
- Outdoors:
  - Sky colour from painted backdrop pixels in the top band; `mean[4]` = sky; skip `flat_ceiling`.
  - Blend backdrop fill towards sky over 8 m above the highest painted cell.
  - Write `sky.json`.

**`movers.py`** (new, `thread/.venv`), run as `movers.py gen_c gen_m`
- Fit the with-movers transform from `gen_m/cams.json` and `gen_m_scene.json` (the same Umeyama fit as `blockout_mesh.py:10-19`).
- Map `gen_m.ply` centres to room metres.
- Per lifted object keep splats that are all of:
  - within 5 cm of its mesh (trimesh or open3d distance; box test for box objects)
  - with y > 0.02 m
  - with longest axis under 0.3 m
  - not near-transparent.
- Copy those rows unchanged to `mover_NNN.ply` with the same header.
- Export `mover_NNN.glb` (at most 20,000 faces) and `mover_NNN_collider.glb` (at most 500 faces) with the same transform and winding flip as `blockout_mesh.py:43-44`.
- Write `movers.json`.
- A mover with fewer than 300 splats is skipped.

**`blockout_mesh.py`**
- Leave out of both static GLBs the objects listed in `movers.json`.
- Outdoors: replace the inverted box (line 39) with a ground slab (play area plus 6 m, top at y = 0, 0.2 m thick).
- Line 47: add `fromRoom` and the section 2d keys. Sway movers get `render: "skin"`.

**`pipeline.py`**
- After training `gen_c`, when `lifted.json` is non-empty: stage "lifting out the moving things", train `gen_m` with the same arguments, then run `movers.py`. Both are soft: failure leaves a static world.
- Line 124: copy the new keys, and add `style`.

**`server.py`**
- Pass `body.get("setting")` as `WORLD_SETTING`.
- `/api/stitch` refuses a world whose `setting` is outdoor, with a plain message.

### Implementer C: viewer and audio

Owns `thread/viewer/main.js`, new `thread/viewer/motion.js`, new `thread/viewer/audio.js`, `thread/viewer/index.html`.

**`audio.js`**
- Copy unchanged from `/private/tmp/claude-501/-Users-rose-NatesApps--claude-worktrees-local-ai-mesh-processing-30d48e/21f9bc40-38be-4264-aecd-a3d9e7cb7f9f/scratchpad/audio/audio.js`.
- The scratchpad can be cleared by a reboot, so copy it first.

**`motion.js`**: exports `setupMotion(p, ctx)`, `stepMotion(p, T, w)`, `disposeMotion(p)`, `setMotionVisible(p, mode, night)`.
- One helper: `roomToOuter = p.inner.matrix × fromRoom`. It is the only place that knows about the mirror.
- **Skin movers**
  - One `SplatSkinning` per part: bone 0 at rest, 3 bones per sway object (a lean, and two flutter clumps chosen by a 25 cm position hash).
  - Membership once, via `packedSplats.forEachSplat`, through the inverse of `fromRoom`:
    - inside the box grown 8 cm
    - y > 0.03
    - more than 4 cm from an indoor wall
    - nearest box wins.
  - Weight is a ramp above `stiff`, to the power 1.5.
  - Then `mesh.skinning = sk; mesh.updateGenerator()`.
  - Per frame: rotate about the base point with translation `c − R·c`, then `sk.updateBones()`.
- **Splat movers**
  - `new SplatMesh({ url: ply, editable: false })` inside a `fix` group (matrix `roomToOuter × inverse(mover.fromRoom)`, re-based on the pivot) inside an animated group under `p.outer`.
  - The same group holds the GLB as a night `pre`/`lit` pair and a wireframe.
  - Swings whose pivot is more than 0.3 m above the piece get two thin dark cylinders from pivot to piece.
  - A Rapier `kinematicPositionBased` body with a convex hull from the collider GLB (cuboid of `box` as fallback), posed before `phys.step()`.
  - `path`: centripetal Catmull-Rom by arc length, heading from the tangent.
    - "loop" outdoors extends 12 m past both ends, fades `opacity` over the last 3 m, waits `pause`, restarts.
    - "back" eases at the ends.
- **Effects**
  - One `SplatGenerator` per effect under `p.outer`, using the verified custom-`Dyno` pattern (index and time in, `defineGsplat`, `SplatTransformer.applyGsplat`).
  - Positions are a pure function of index and `T`. Opacity fades at the drift wrap.
  - The same formula in JS for index 0 gives the sound position.

**`main.js`**
- Own clock `T` (dt capped at 0.1 s). Spark's clock is 0 in this viewer.
- Test hooks: `window.motion = { set(t), pause(b), stats }`.
- Call the four `motion.js` functions from `load`, the loop, `apply()` and `disposePart`. Add mover wires to `drop()`.
- Outdoor:
  - sky dome from `def.sky`, built like `back`
  - `p.open` excluded from `findDoors` (160) and `snapFlush` (390)
  - 1 m tessellation
  - safety net top at y = 0
  - orbit target clamped to the play area plus 3 m.
- Audio:
  - `detachAll`, `setMood({...def.mood, name, style, setting})` and `attach` per mover and effect in `load` (at most 12 emitters; the 6 largest sways)
  - `setWind(w)` and `update(camera)` after render, with the same `w = gust(T, seed, strength)` that drives sway
  - `setNight` in the night handler
  - `stop()` in `enterStitch`.

**`index.html`**
- Sound checkbox (the click that starts audio), a volume slider, a Motion checkbox.
- An Auto / Indoors / Outdoors select in the prompt pane, sent as `setting`.
- Copy that no longer says only "room".

## 4. Order of work and hand-offs

The GPU (painter, trainer, Hunyuan3D, Ollama) is used by one process at a time, in this order: B, then A, then B.

1. **Start, in parallel, no GPU**
   - A: `llm_boxes.py` and the tests.
   - C: copy `audio.js`, wire audio, sky dome, clock.
   - B: copy `thread/worlds/garage-shapes` to `thread/worlds/garage-motion`.
     - Hand-add `motions` (sway on corner car 0, spin on the centre car, path on a corner car) and two `effects`.
     - Update `blockout_mesh.py` and register "Garage (motion test)" with skin movers and effects only.
     - **Hand-off 1 (B to C):** that entry; C builds sway and effects on it.
2. **A delivers the `chisel_ring.py` interface** (`OUT`, `MARGIN`, `LIFT`, `halo`). **Hand-off 2 (A to B).**
3. **B, GPU: mover gate on the garage**
   - Run `consistent.py` (both passes), two trainings and `movers.py`. No painting; about 5 minutes.
   - **Hand-off 3 (B to C):** the entry now has splat movers.
   - Gate: with the car away, the rest spot shows soft floor, not a dark smear; the mover has no torn halves.
   - If it fails: widen the halo band and loosen or tighten the 5 cm rule. If it still fails: lifted movers stay static, and say so.
4. **A, GPU: layout and outdoor gates**
   - Five sentences through Ollama: park, street, garden, a room with a ceiling fan, a plain bedroom that must come out static.
   - Then `prep` plus ONE painted outdoor view; look at it.
   - Fallbacks, in order:
     1. fade the ground to black over its last metres
     2. "open empty horizon" in the prompt
     3. boundary pieces on every edge
     4. a 4 m margin diorama.
5. **B, GPU: the full acceptance build** (section 5), about 25 to 30 minutes.
6. **C runs the acceptance checks in the Browser pane.** Then a human listens to the audio.

**Cut lines if time runs short, in order:** `bob`, the setting select, the orbit clamp, Catmull-Rom (straight two-point paths only), `spin`.

## 5. Acceptance test

Build from the app, Standard detail:
- **Layout:** "A small park on a breezy day: two big leafy trees at the back, a swing set in the middle with one seat hanging from it, a flower bed on the left with bees buzzing around it, leaves blowing down from the trees, a bench on the right, and a road along the front edge where a car drives past."
- **Style:** "sunny spring park, fresh green grass, soft morning light"

What must be observed. Screenshots use `window.motion.set(t)` at three times, from four off-centre eyes per mover: high oblique, low grazing, behind, and side-on at the motion's extreme. None of them on a training-ring position.

1. **Layout:** `boxes.json` has `setting: outdoor`, two `sway`, one `arch` plus a `swing` piece with base above 0, one `path`, one `wander`, one `drift`, a `mood`. No object name appears in code.
2. **Outdoors:**
   - No ceiling or walls.
   - Sky dome colour matches the painted sky.
   - No wall or ledge at the horizon.
   - From each edge of the play area, no sky floaters.
   - Balls roll off the slab and are counted by `ballStats.onNet`.
3. **Foliage:** between two times, crown pixels change, the trunk base moves less than 1 px, and pixels outside all mover boxes change by under 1%.
4. **Swing:**
   - The seat and its two ropes rock about the beam.
   - The frame stays still.
   - No second seat is left behind.
   - Dropped balls are pushed by it.
5. **Insects and leaves:**
   - Small blobs of the effect colours move continuously across 10 consecutive frames with no popping.
   - They vanish in mesh and collider modes.
   - Buzz is audible only within about a metre.
6. **Car:**
   - It travels the road, fades out past the edge, and returns after the pause.
   - With it away, the rest spot's brightness is within 20% of the ground beside it.
   - It hides and is hidden by trees correctly.
   - Balls on the road are pushed.
   - In night mode its shadow follows it and none stays at the rest spot.
7. **Music and sound:**
   - Silent until the Sound box is ticked.
   - Then pads and bells fade in over about 4 s.
   - Wind sound rises with the same gusts that move the trees.
   - A rumble passes with the car; a creak at swing reversals.
   - Sound suspends when the window is hidden.
   - A human confirms it is pleasant.
8. **No regressions:**
   - Every existing entry in `thread/scenes.json` loads with no console errors.
   - `garage-shapes` shows 0 sorts per second when idle and unchanged screenshots.
   - 40 balls dropped indoors give `onNet == 0`.
   - `consistent.py` output for a world with no lifted movers is byte-identical.
   - Existing `boxes.json` stamps are unchanged.
9. **Speed:** `motion.stats` shows at least 60 fps with the pane visible at full size.

## 6. Limits to tell the user

- **Outdoors is a flat painted surround** about 20 m away with plain sky above roughly 20°. There are no hills or clouds overhead, and far ground is soft. Outdoor worlds cannot be stitched to rooms yet.
- **Trees are solid painted shapes.** Clumps of the crown bend in the wind, but sky never shows through leaves and single leaves do not flutter. The falling-leaf effect supplies that impression.
- **The swing is the weakest part.** The seat is a small painted plank with ropes drawn by the viewer, and the frame is plain posts. The painter may draw its own chains, which then stay on the background.
- **The car slides rigidly.**
  - Its wheels do not turn.
  - It may travel tail-first.
  - It follows the road only if the layout model left one clear.
  - The ground where it was painted is a soft filled patch, and a painted contact shadow may stay there.
  - The side of it that faced away from every painted view is one flat colour.
- **Bees and leaves are small coloured blobs,** not modelled creatures. They pass through objects and are unlit at night.
- **Night mode:** swaying foliage is lit at its rest position.
- **The layout model decides what moves.** It can tag the wrong piece or misjudge indoor versus outdoor; the Indoors/Outdoors choice overrides the latter.
- **Build time** grows by an estimated 2 to 3 minutes for worlds with a swinging or travelling thing. This has not been measured.
- **Music is synthesised in the browser.** So far it has been measured, not heard. It has not been run in the app's WebKit view. Levels may differ by a few dB there, and the reverb may need shortening.
- **Not yet verified until the gates in section 4 pass:**
  - outdoor painting
  - training with a far shell
  - the split mover's look
  - motion inside stitched worlds
  - frame rate at full window size.
- **Later option, needs your approval:** a local music model to pre-render a loop per world. That is a new model download.
