# Outdoor places: smallest general change (read-only study)

Nothing in the project was edited, and no image model, trainer or Ollama was run. The only experiment was a CPU depth-map render in the scratchpad, so every claim about how the painter or trainer reacts is unverified.

## Recommendation

Keep the box, but split it into two boxes when the layout says `"setting": "outdoor"`:

- **Play area**: today's `room [W, H, D]`. Objects, cameras, `fit()`, `free()` and the viewer's footprint keep using it unchanged.
- **Shell**: `B.ROOM` grown by a margin M of about 20 m on each side and 20 m high. Face 1 becomes ground, faces 0/2/3/5 a painted backdrop, face 4 sky.

Three things make this work:

1. The painter's depth map shows the backdrop and sky as pure black (infinitely far), while re-projection still uses the shell.
2. Sky above the painted band becomes one soft sky colour, not the "lightened ceiling" formula.
3. The viewer draws a sky dome of that same colour behind the splats as a back-stop, and outdoor worlds get no collider walls or doorways.

Every change is gated on the flag, so existing worlds behave exactly as now. It is roughly 60 to 80 lines across six files.

## Why not the alternatives

- **Bigger shell with nothing else changed.** Measured on a 14 x 12 m play area with a 20 m margin: the backdrop comes out at grey 0 to 24 of 255 with a visible vignette and corner crease, after the percentile stretch and `** 0.6` in `chisel_ring.py` 103-106. A depth ControlNet is likely to read that as a faint, huge wall, so you would get a hangar. With the proposed map the backdrop is exactly 0, ground runs 63 to 255 and objects 145 to 250. Comparison picture (indoor, shell as today, proposed): `/private/tmp/claude-501/-Users-rose-NatesApps--claude-worktrees-local-ai-mesh-processing-30d48e/21f9bc40-38be-4264-aecd-a3d9e7cb7f9f/scratchpad/outdoor/cmp.png`
- **Sky dome only, no sky in the splat.** msplat 1.1.4 has no mask or alpha input; `TrainingConfig` exposes only `bg_color`. Sky pixels in training views with no geometry behind them would become floaters. A later option is to fill unpainted sky with a key colour and set `cfg.bg_color` to match, so the trainer makes no sky splats and the dome shows through. That depends on how msplat uses `bg_color`, which I did not test.

## Indoor assumptions found, and the change for each

### `thread/llm_boxes.py`
- **Line 29** ("of an indoor space") and **line 31** (schema): add `"setting": "indoor" | "outdoor"` and `"surround"`, a phrase of at most 10 words for what is seen in the distance. Say that outdoors "room" means the patch of ground you can walk on, "wall" means an edge of that patch, and "height" is the tallest thing.
- **Line 36** ("Use these for ordinary rooms") and **line 43** (room sizes, "add the window"): add an outdoor size hint of 10 to 16 m. Tell the model to put large boundary things (hedges, fences, house fronts, tree rows) on the edges with the existing `wall` placement. Add one outdoor example beside lines 45-66.
- **Line 138**: clamps are 3 to 24 m and height 2.4 to 9. Outdoors keep the 24 m maximum, because picture detail is the limit, and allow height 3 to 12 so trees are not cut at line 170.
- **Line 160**: skip `window` furniture outdoors.
- **Line 201**: write `setting` and `surround` into `boxes.json`. Anything other than the exact string "outdoor" means indoor.
- **Line 170** (for the motion work): `base` is discarded and everything is forced to the floor, so nothing can hover yet.

### `thread/chisel_ring.py`
- **Lines 16-17**: `OUT = world.get("setting") == "outdoor"`, then `B.ROOM = ((-M, 0, -M), (RW + M, M, RD + M))` when outdoors. `spike/blockout.py` needs no change: `trace` (115-120) only needs the camera inside `ROOM`, and face ids 0 to 5 keep their meaning.
- **Lines 68, 75, 84-96**: cameras use RW/RH/RD, so they stay in the play area. No change.
- **Lines 103-106**: outdoors set `inv = 0` where `sid` is 0, 2, 3, 4 or 5, and use `lo = 0` instead of the 1st percentile.
- **Lines 147-148**: "A bare stretch of wall and floor." and "interior photo" become, outdoors, `f"outdoor photo, {style}. {what}"` with "An open stretch of ground." as the empty case. Append `f" Beyond: {surround}, under an open sky."` only when backdrop faces fill more than about 5% of that view, so downward views do not get sky painted on the ground.
- **Line 231**: add setting, margin and surround to `meta` only when outdoors, as is done for `shapes` on line 233, so old worlds are not repainted.
- **`carry_over` (201-222)**: works on the shell as it is, so neighbouring views share one backdrop.

### `thread/consistent.py`
- **Lines 74, 146-147**: the "top third of the walls" test uses `C.RH`. Outdoors, sample the sky colour from painted backdrop pixels in the top band of the paint.
- **Lines 160-166**: outdoors skip the `flat_ceiling` formula (0.6 x wall colour + 0.4 x white) and set `mean[4]` to that sky colour.
- **Lines 169-178**: nearest-cell fill would stretch the top row of paint up the backdrop as vertical streaks, and the 8-cell blur is only 24 cm. Outdoors, blend the fill on faces 0/2/3/5 towards the sky colour over about 8 m above the highest painted cell, so the shell's top edges show no seam.
- **Line 133**: 3 cm cells over a 20 m shell are about 11 million cells, 0.4 GB of sums and counts (1.1 GB at 40 m). Fine as it is.
- **Lines 38-41**: the upward rings aim at `C.RH`, which works as a pitch target. No change.

### `thread/blockout_mesh.py`
- **Line 39**: the inverted room box is the walls, floor and ceiling of both the mesh and the collider. Outdoors replace it with a ground slab only (play area plus about 6 m). Otherwise night mode lights walls 20 m away and balls bounce off invisible ones.
- **Line 47**: add `setting` and `sky` (the RGB above) to `_metre.json`.

### `thread/pipeline.py`
- **Lines 122-124**: copy `setting` and `sky` into the scenes entry.

### `thread/viewer/main.js`
- **Near 46-48**: add a sky dome, built like `back`: a BackSide sphere with `depthWrite: false` and a low `renderOrder`, following the camera as line 343 does, coloured from `def.sky`. It fills holes if the trainer drops large sky splats, and it is where moving clouds or day and night could go later.
- **Lines 113, 124**: add `p.open = def.setting === "outdoor"` and use a 1 m tessellation edge for open worlds.
- **Lines 160 and 390**: exclude open parts in `findDoors` and `snapFlush`, so no doorways are cut into a park.
- **Line 275**: the safety net sits 5 cm below the floor. Outdoors put its top at y = 0 so balls roll off the slab onto it. The `ballStats.onNet` test hook then counts those balls.
- **Lines 36-38, 284**: the lamp reaches 14 m. Night outdoors works through `back` dimming everything without mesh, but a sun or moon light would be a later addition.
- **Camera**: orbit is unclamped. Outdoors clamp `orbit.target` to the play area plus a few metres, or the flat backdrop gives itself away.

### Smaller places
- **`thread/viewer/index.html` 58-66**: the copy says "room".
- **`thread/server.py` 118-121**: optionally pass an Auto / Indoors / Outdoors choice as `WORLD_SETTING`, because the 9B model may misjudge.
- **`thread/shapes.py`**: uses `room` only for fitting and facing (335-382). No change needed.
- **`README.md`**: the Known limits section needs the limits below.

## How the layout model says indoor or outdoor

One enum field, `setting`, beside `room`, chosen by the model as it chooses box or cylinder, plus the free-text `surround`. No keyword matching in code. A missing or malformed value means indoor.

## Honest limits

- **The backdrop is a flat painted surround about 20 m out.** There is no parallax between distant layers, and walking towards it shows it is flat.
- **Sky above about 20° is one plain colour.** Ring views top out at 19.6° elevation (measured), so there are no clouds overhead. Four extra upward painted views would fix that for about 4 minutes more.
- **Far ground smears.** One pixel row covers 7 cm of ground at 10 m, 27 cm at 20 m and 1.1 m at 40 m. This is the README's "large halls are weak" problem again, so keep M near 20 m and let boundary objects hide the far ground.
- **Still a flat, rectangular patch.** No hills, kerbs or slopes.

## Risks, most likely first

1. **The painter fills black areas with mid-ground things** (extra trees, people, lamp posts). Those get projected onto the shell 20 m back and slide against the ground as you move. One painted view, about a minute, would show this.
2. **Foliage spills past its outline** more than furniture does. The 16 px `HALO` (line 114) may be too small for tree crowns, which would stamp them onto the backdrop.
3. **The hard step at the horizon** (ground grey about 63 dropping to 0) may be painted as a wall or ledge. If so, fade the ground to black over its last few metres.
4. **The trainer with a shell 5 to 10 times the camera spread**: possible floaters in plain sky, culled large splats, or a far clip. One 10,000-step run would show it. The dome covers holes but not floaters.
5. **Stitching an outdoor world to rooms**: the park's ground splats lie in the same plane as a neighbouring room's floor, and its shell encloses the neighbours. Unhandled; suggest leaving outdoor worlds out of doorway logic and documenting it.
6. **The 9B model's habits**: it may keep writing windows or room-sized footprints outdoors. The clamps and one outdoor example are the guard.
