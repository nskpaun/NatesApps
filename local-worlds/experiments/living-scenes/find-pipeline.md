Study of the prompt pipeline for moving parts (read-only; nothing in the project was edited, no model, trainer or Ollama was run). All paths are under /Users/rose/NatesApps/.claude/worktrees/local-ai-mesh-processing-30d48e/local-worlds. Numbers marked "measured" come from CPU-only reads of thread/worlds/garage-shapes; anything about msplat's behaviour with a plain backdrop is read from its type stubs, not run.

## Short answers

- (a) The object index in boxes.json is already the one ID every stage shares, so a `motion` field on the object rides through untouched; only three places need to pass it on (llm_boxes.py:175, blockout_mesh.py:47, pipeline.py:124).
- (b) Membership can be computed exactly, because the trainer-frame transform is recovered to 1.8e-7. On the garage, 80-90% of an object's splats lie within 5 cm of its mesh, with a 5-9% opaque fringe 5-15 cm out. Splitting one trained splat is workable for small motion, not for something that drives away.
- (c) There is essentially no trusted paint behind or under an object (about 1% of the floor under a corner car). consistent.py can render the room without movers and a small mover-only set with modest changes. The main training run took 71 s, so an extra small run should be well under a minute (not measured).
- (d) Thin, hanging, tiny or see-through things are dropped or flattened at six separate points; they should bypass the blockout and be drawn by the viewer.

## (a) Carrying a motion description to the viewer

The object index `oi` in `boxes.json["objects"]` is the ID at every stage:
- `shapes/placed/NNN.npz` (thread/shapes.py:7, written at 415)
- `plan.json["objects"]["i"]` (shapes.py:215-216)
- `PRIM_OBJ` (thread/chisel_ring.py:47-49)
- surface id `6 + oi` (spike/blockout.py:127; thread/consistent.py:13-14)

Steps:
1. **Layout model.** Add an optional `"motion"` to the piece schema in thread/llm_boxes.py:34, with a small closed set of primitives chosen the way `shape` is chosen today. A workable set:
   - `sway`: bends about its base in wind (amplitude, period).
   - `swing`: pendulum about a pivot at the top (axis, angle, period).
   - `path`: travels between two `[u, v]` points (speed, loop or back-and-forth).
   - `wander`: count, radius, height, speed around a point.
   - `spin` and `bob`.
2. **Validation.** `expand()` (llm_boxes.py:134-178) clamps the numbers as it does sizes, converts `[u, v]` fractions to metres like `placements()` (77-111), and attaches the result at line 175, where the object is appended as `{"name", "prims", yaw}`. Ring and corner copies each get it; a per-copy phase should be added. Line 201 writes it to boxes.json.
3. **Layout checksum.** `shapes.stamp` hashes the whole `objects` list (shapes.py:32-34, mirrored at thread/pipeline.py:84), so motion inside objects changes the checksum. That is harmless for new worlds, and old worlds have no motion key.
4. **Into the scene entry.** thread/blockout_mesh.py is the only place holding the similarity transform (lines 10-16) and it writes `gen_c_metre.json` (line 47). Add a `movers` list there: object index, motion, pivot and box in room metres, and per-mover file names. pipeline.py:124 copies named keys from that file into the entry, so add `"movers"` to that tuple.
5. **Viewer.** `loadPart(def)` (thread/viewer/main.js:103-127) receives the entry. Stitched worlds reference rooms by name (thread/server.py:99-103, main.js:253), so movers come along if attached under `p.inner` or `p.outer`.

Coordinate conversion, verified on the garage (fitted R is the identity, t and s only): a room point (x, y, z) lands in the viewer's `outer` frame at (x − RW/2, y, −(z − RD/2)). z is mirrored (blockout_mesh.py:6, 43), so yaw angles flip sign.

Blockers that sit in this same path:
- **Everything is forced to the floor.** llm_boxes.py:170 sets `base = 0.0`, ignoring the model's `base`. Nothing can hang or fly: a swing seat, a tree canopy above its trunk, a bee.
- **Tiny pieces are dropped before line 175.** Line 161 drops labels matching `TINY` (line 75) and anything with a footprint under 0.12 m. A `wander` piece must be diverted before that `continue` into a separate `effects` list that never enters `B.PRIMS`.
- **Static mesh and collider include every object.** blockout_mesh.py:41-45 concatenates all prims into one mesh; main.js:109 takes the first mesh and main.js:266-272 makes one static trimesh. A mover would leave an invisible collider and a night-mode shading ghost (main.js:136-141) where it started. Movers need their own GLB and a kinematic Rapier body.

## (b) Which splats belong to which object

**The transform is exact.** blockout_mesh.py:10-19 fits trainer camera centres (`gen_c_scene.json` poses) to blockout cameras (`cams.json`, consistent.py:198). Logged fit error is 1.8e-7, scale 0.2564. So `room = S · Rᵀ((x_file − t)/s)` maps every splat centre into room metres, where the boxes and `placed/NNN.npz` meshes live. `R` and `t` are not saved today (only metre, centre, floor), so the assignment belongs in blockout_mesh.py or a sibling step.

**Tightness, measured** on gen_c.ply (876,941 splats, 12 x 10 m room):

| Object | Splats within 5 cm of mesh | Within 2 cm | Opaque fringe 5-15 cm out, above floor | Within 5 cm of mesh and under 3 cm above floor |
|---|---|---|---|---|
| Centre car (on platform) | 49,956 | 39,706 | 2,857 | 0 |
| Corner cars (each) | 9,570-10,483 | 5,885-6,521 | 954-1,493 | 193-335 |

- Splat size: median 2.6 cm on the longest axis, 99th percentile 9.7 cm; only 4-34 splats per car are larger than 15 cm.
- 18.5% of all splats lie more than 5 cm outside the room box (floaters behind walls). They are irrelevant here but show the splat is not clean.
- The fringe is the object's paint spilling past its outline (the reason for `HALO`, chisel_ring.py:114-121). It would either stay behind as a ghost or travel as fuzz.
- At a floor contact, splats within about 3 cm are a coin toss between object and floor.

**Three ways to act on membership** (the Spark 2.4 types are in thread/viewer/node_modules/@sparkjsdev/spark/dist/types):
1. **Split offline.** Python reads the PLY (plain float32 records), writes `room.ply` plus `mover_k.ply`, and the viewer loads each as its own `SplatMesh` in a `THREE.Group` at the pivot. This is the simplest and fits today's `loadPart`.
2. **One splat with bones.** `SplatSkinning` (SplatSkinning.d.ts: `setSplatBones`, `setBoneQuatPos`) takes a per-splat bone index from a sidecar file. I did not verify that Spark's splat order equals PLY order.
3. **GPU sway.** `objectModifier` (SplatMesh.d.ts:35, 152) displaces splats inside an object's box by a sine weighted by height above the base. It needs no membership file and no hole filling, since nothing leaves its place.

**Limit of all three:** the splats under and behind the mover were never trained (see c). Splitting is fine for sway and small swings, and wrong for anything that travels.

## (c) What is behind a mover, and training room and mover separately

**There is almost no paint there today.** Measured from the saved source-view depth files (18 painted views, 3 cm cells, point-sampled so slightly low):

| Area | Seen by any painted view | Seen outside the 16 px halo band |
|---|---|---|
| Floor under a corner car's footprint | 30-32% | 1% |
| Footprint plus 30 cm | 44-45% | 9-14% |
| Left wall behind corner car 0, below its roof | 36% | 3% |

- In the ~115 re-rendered training views the hidden floor is never rendered at all: target rays stop on the object (consistent.py:80-82), so the trained splat has a hole or stretched neighbours there.
- The painter also bakes the object's contact shadow into the surrounding floor, which would stay when a car drives off.
- The fill that would cover the hole already exists: consistent.py:169-178 builds a complete texture per room face (nearest painted cell, then a 24 cm blur). It is applied only to pixels a target ray reaches (179-185).

**Static room without movers, with small changes to consistent.py:**
- Trace target views with a prim list that excludes movers; keep the full list for the source side. `B.trace` and `B.visible` read the global `B.PRIMS` (blockout.py:122, 141), so they need a prim-list argument or a swap around the calls at consistent.py:80-82 and 114.
- No new logic is needed for the hole. The source test at consistent.py:107-108 requires `ssid == sid`, so pixels where the source saw the mover fail and fall through to `fill_tex`.
- Extend `C.halo` (chisel_ring.py:116-121, which covers generated shapes only) to box movers.
- Result: a soft, plausible floor patch, not real paint. Good under a swing or tree; visibly blurry along a whole road a car has left.
- Better for `path` movers: leave them out of the painted blockout entirely, so the room is painted empty there (real paint, no baked shadow), and paint the mover on its own.

**Mover-only views:**
- From today's room paintings: render about 24-40 cameras on a ring and dome around the mover's box, tracing only its prims, taking colour only where `sid == 6 + oi`, backdrop elsewhere. Write a second COLMAP folder as lines 187-197 do, sampling init points only on the mover (191-192). This costs seconds of ray casting and no painting. The side facing the wall has no paint and gets the surface's mean colour (consistent.py:157-161).
- For movers left out of the room: a short depth-guided ring of 4-6 views of the mesh alone on the backdrop, at about 55 s per view (job2.log), or less at a smaller size.

**Can msplat train on a plain or transparent background?**
- No alpha or mask support is visible: the compiled module has no such strings, and the only relevant setting is `TrainingConfig.bg_color` (site-packages/msplat/_core.pyi:24, default magenta 0.613, 0.010, 0.398).
- So "transparent" means painting the backdrop exactly `bg_color`. The renderer composites onto that colour, so empty space needs no Gaussians.
- thread/train_scene.py can already set it: `--set bg_color=r,g,b` (lines 15, 72-74 handle list fields).
- Not run, so unverified. Plan to prune afterwards by dropping splats more than about 5 cm from the known mesh.
- `keep_crs` exists (pyi:20) and might stop the re-centre and re-scale, also unverified. It is not needed: the same camera-fit trick as blockout_mesh.py:10-16 recovers each mover's transform.

**Time:**
- Main training run: 71 s (file times 12:37:57 to 12:39:08) for 114 views at 1024x768, 10,000 steps, 877k splats.
- consistent.py for 114 views: about 57 s.
- An extra mover run (about 30 views, 3,000-4,000 steps, tens of thousands of splats) should be roughly 20-40 s. This is an estimate, not measured.
- With the default `num_downscales 2, resolution_schedule 3000`, a 3,000-step run never reaches full resolution (train_scene.py:59-61); pass `--downscales 0`.
- Copies of one kind can share one mover splat only if they share paint; today each copy takes paint from different room views.

**Cheaper alternative for rigid movers:** skip the second training and show the mover as its generated mesh with baked vertex colours in three.js. Splat detail on objects is only about 2.6 cm, which a 60k-face mesh (shapes.py:21) roughly matches. It animates trivially, has an exact collider and shades properly in night mode. The catch is a slightly different look from the splat room.

## (d) Where thin or see-through things break today

1. **Layout drops them.**
   - llm_boxes.py:43 tells the model "only large solid shapes".
   - Line 161 drops fabric and light labels and anything under 0.12 m.
   - Lines 146-148 clamp radius to at least 0.08 m and width to at least 0.1 m.
   - Line 170 puts everything on the floor.
   - Chains, ropes, twigs and bees never reach boxes.json; a canopy becomes a floor-to-top block.
2. **Shapes are solid hulls.**
   - shapes.py:20 and 171 leave anything thinner than 0.15 m as a box.
   - `cut_out` uses a binary opening and erosion (shapes.py:290, 295) and keeps see-through gaps only above 0.02% of the picture (289), so chains and leaf gaps close up.
   - Hunyuan3D returns a watertight blob: a tree is a lollipop.
3. **Depth guidance cannot show them.** Training focal is 804 px at 1024 wide, so a 1 cm chain at 4 m is about 2 px in the depth map and under 2 px at the 768 paint size. That is below what the painter resolves, so it is ignored or painted fatter, off the geometry.
4. **Small surfaces get no paint.** consistent.py:31 disowns any surface seen in fewer than 400 px. If that holds in every view, it falls to the flat mean or overall colour (157-161). A 3 cm bee at 3 m is about 8 px across, so it becomes a flat blob.
5. **Opacity is baked in.** Every training pixel is the first opaque hit of a ray (blockout.py:122-131). Sky can never show through leaves, the canopy edge is the hull's hard edge, and paint spilling past the outline is discarded as halo (consistent.py:99-102).
6. **Outdoors.**
   - blockout.py:115 assumes the camera is inside a closed box.
   - Faces 0-5 are always wall, floor and ceiling.
   - consistent.py:162-166 flattens an unpainted ceiling to a lightened wall colour.
   - chisel_ring.py:148 hard-codes "interior photo"; llm_boxes.py:29 says "indoor space".
   - Height is clamped to 2.4-9 m (llm_boxes.py:138).
   - An outdoor scene can only be a painted diorama box (walls as distant scenery, ceiling as sky) unless those are changed.

**Consequence for thin, small or see-through movers:** keep them out of the blockout, painting and training, and have the viewer draw them.
- Chains and ropes: thin three.js cylinders between a pivot and a seat.
- Bees, leaves, butterflies: billboards. shapes.py:241-297 already produces an RGBA cut-out of one object on a plain backdrop (`KIND.rgba.png`, 512x512 with alpha, about 31 s each on the garage), which is a ready sprite with no new model.
- Foliage sway: the `objectModifier` displacement from (b) over the canopy's splats. It moves nothing out of place, so it exposes no hole.