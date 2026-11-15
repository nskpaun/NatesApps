# Spark 2.4 for moving splats: what works, verified in a browser

Everything the request needs can be done in the viewer with Spark 2.4.0 as installed: no new library and no model. I ran each technique on the real `garage-shapes` splat (876,941 splats, SH degree 1) in a throwaway page; all of them compiled with no console or generator errors and held the 100 fps cap in an 800x600 pane.

No project files were changed (`git status` shows only the untracked `.claude/`). The test page is at `/private/tmp/claude-501/-Users-rose-NatesApps--claude-worktrees-local-ai-mesh-processing-30d48e/21f9bc40-38be-4264-aecd-a3d9e7cb7f9f/scratchpad/sparktest/test.js` (its local server is stopped).

Sources: `dist/types/*.d.ts` and `dist/spark.module.js` in `thread/viewer/node_modules/@sparkjsdev/spark`, plus sparkjs.dev docs (reachable; they confirm the modifier order, `updateVersion()` and the sort-lag note).

## Three traps to know first

- **Spark's own clock stays at 0 in this viewer.** `SparkRenderer` only advances its timer when one is passed in (`ownsTimer = !!options.timer`). Measured: `mesh.context.time`, `SplatMesh.dynoTime` and `onFrame`'s `time` were all 0 after 450 frames; with `new SparkRenderer({ renderer, timer: new THREE.Timer() })` they advanced. Either pass a timer or drive your own `dyno.dynoFloat` from the render loop (I did the latter).
- **A time uniform alone does not redraw anything.** Without `mesh.updateVersion()` each frame, the animated scene was frozen (0 changed pixels, 0 sorts). `mesh.needsUpdate = true` is the same call. Changing an Object3D transform, or an SDF's values, bumps the version automatically.
- **After assigning a modifier or skinning, call `mesh.updateGenerator()`** so the shader graph is rebuilt.

## How Spark draws several splat objects

- Every `SplatGenerator` in the scene (a `SplatMesh` is one) is written into one shared buffer and sorted in **one global sort**, so separate meshes interleave correctly by depth.
- When any generator's version changes, all visible generators are regenerated on the GPU that frame, then depth is read back and sorted in a worker. The sort is asynchronous and can lag a frame or two behind motion (docs say the same).
- Each generator's slot is rounded up to 2,048 splats, and each costs one GPU pass per frame.

| Test (on the 877k-splat garage) | fps | sorts per second |
|---|---|---|
| Static scene | 100 | 0 (nothing to re-sort) |
| Whole-scene modifier animated every frame | 100 | 86 to 92 |
| 50 extra 12-splat meshes moving | 100 | 82 |
| 400 extra 12-splat meshes moving | 100 | 50 |

The pane was hidden while measuring, so treat fps as approximate; the 100 looks like a frame cap, not the ceiling. For many small things, use one procedural generator, not hundreds of meshes.

## Order of operations inside a SplatMesh

From `constructGenerator`:

1. fetch splat (with SH colour)
2. `skinning`
3. `objectModifiers` (object space; here that is file units, not metres)
4. mesh transform (uniform scale, rotation, translation)
5. `recolor` / `opacity`
6. `SplatEdit`s (world space; this is where doorway erasers act)
7. `worldModifiers` (world space, metres)

Consequences for composing with `main.js`:

- **Metres:** `loadPart` puts the splat under `inner` with scale `1/metre` (3.9x for the garage), and stitching moves `outer`. Motion written as an `objectModifier` or skinning in file units survives stitching unchanged; multiply metre values by `p.metre`. A `worldModifier` needs world coordinates recomputed per stitched placement.
- **Doorways:** the erasers are global `SplatEdit`s and hit every `SplatMesh` with `editable: true` (the default). Motion from skinning or object modifiers is erased if it enters a doorway box; motion from world modifiers is tested at its rest position. Pass `editable: false` for a split-out mover that should ignore them. Plain `SplatGenerator` particles are never affected by edits.
- **Night mode:** the `pre`/`lit` meshes and the Rapier trimesh do not move with the splats. A moved object would be lit and shadowed, and collided with, at its rest position. Movers need their own mesh piece under the same moving group and a kinematic Rapier body; small sways can be ignored.
- **Mode switch and cleanup:** `apply()` toggles `p.splat.visible` only, and `disposePart` disposes `p.splat` only. Extra meshes and generators need to be added to both. `SplatMesh.dispose()` also disposes its `PackedSplats`, so a shared one must be disposed once.
- **Blur:** `setBlur` is unaffected.

## Technique 1: per-splat motion in a region (wind, swing)

`GsplatModifier` is a dyno block from `{ gsplat }` to `{ gsplat }`. The Gsplat GLSL struct has `center`, `flags`, `scales`, `index`, `quaternion`, `rgba`. `quatVec`, `quatQuat`, `isGsplatActive` and `PI` are available in every program.

Rotate everything inside a box about a pivot axis (verified: the centre car swung as a pendulum):

```js
const uTime = dyno.dynoFloat(0);            // set uTime.value in the render loop
const mod = dyno.dynoBlock({ gsplat: dyno.Gsplat }, { gsplat: dyno.Gsplat }, ({ gsplat }) => {
  const d = new dyno.Dyno({
    inTypes: { gsplat: dyno.Gsplat, t: "float", bmin: "vec3", bmax: "vec3", pivot: "vec3", axis: "vec3", amp: "float", freq: "float" },
    outTypes: { gsplat: dyno.Gsplat },
    inputs: { gsplat, t: uTime, bmin: dyno.dynoVec3(min), bmax: dyno.dynoVec3(max), pivot: dyno.dynoVec3(pivot),
              axis: dyno.dynoVec3(axis), amp: dyno.dynoFloat(0.35), freq: dyno.dynoFloat(2) },
    statements: ({ inputs, outputs }) => dyno.unindentLines(`
      ${outputs.gsplat} = ${inputs.gsplat};
      if (isGsplatActive(${inputs.gsplat}.flags)) {
        vec3 p = ${inputs.gsplat}.center;
        if (all(greaterThanEqual(p, ${inputs.bmin})) && all(lessThanEqual(p, ${inputs.bmax}))) {
          float a = ${inputs.amp} * sin(${inputs.freq} * ${inputs.t});
          vec4 rq = vec4(${inputs.axis} * sin(0.5 * a), cos(0.5 * a));
          ${outputs.gsplat}.center = ${inputs.pivot} + quatVec(rq, p - ${inputs.pivot});
          ${outputs.gsplat}.quaternion = quatQuat(rq, ${inputs.gsplat}.quaternion);
        }
      }`),
  });
  return { gsplat: d.outputs.gsplat };
});
mesh.objectModifier = mod; mesh.updateGenerator();
// each frame: uTime.value = t; mesh.updateVersion();
```

Wind sway from stock nodes only (verified as a `worldModifier`; a sphere falloff, displacement growing with height): `dyno.splitGsplat(gsplat).outputs` gives `center, x, y, z, rgba, ...`; combine with `dyno.sub/add/mul/sin/max/length/smoothstep`, `dyno.combine({ vectorType: "vec3", x, y, z })`, `dyno.dynoConst("float", v)`, and return `dyno.combineGsplat({ gsplat, center })`. Hash helpers for noise: `dyno.hashFloat/hashVec3(value)`.

There is no built-in smooth noise; sums of sines keyed on position were enough.

Limit: every region adds uniforms and branches to one shader. For many moving regions, use technique 2.

## Technique 2: SplatSkinning (best fit for "the layout model picks what moves")

Per-splat bone indices and weights live in a texture, so region membership of any shape is decided once on the CPU (for example from the blockout's object boxes), and one shader handles up to 256 independently moving parts.

```js
const sk = new SplatSkinning({ mesh, numSplats: mesh.packedSplats.numSplats, numBones: 4 });
for (let b = 0; b < 4; b++) sk.setRestQuatPos(b, new THREE.Quaternion(), new THREE.Vector3());
mesh.packedSplats.forEachSplat((i, centre) => {
  const k = weightFor(centre);                              // 0..1, e.g. ramp with distance from the pivot
  sk.setSplatBones(i, new THREE.Vector4(0, 1, 0, 0), new THREE.Vector4(1 - k, k, 0, 0));
});
sk.skinTexture.needsUpdate = true; mesh.skinning = sk; mesh.updateGenerator();
// each frame, rotation rq about pivot c:
sk.setBoneQuatPos(1, rq, c.clone().sub(c.clone().applyQuaternion(rq)));
sk.updateBones();                                           // also bumps the mesh version
```

- Verified: 49,614 car splats on bone 1 swung at 100 fps, with hard and with soft (height-ramped) weights.
- From the source, a bone applies `p' = R·p + (pos − restPos)`, a rotation about the object origin, not about the bone position. That is why the translation above is `c − R·c`. I confirmed the maths in the code and that the corrected form looks right; I did not separately measure the naive form's error.
- Weights are 8-bit; up to 4 bones per splat; dual-quaternion mode only for ordinary meshes (linear blend needs `covSplats`).
- A soft weight ramp gives bending (a branch, a flag) for free.

## Technique 3: split an object out and move it as its own mesh (cars driving by)

There is no "load a subset of a PLY" option. Load once into `PackedSplats`, then copy rows.

```js
const all = new PackedSplats({ url }); await all.initialized;
// pick indices with all.forEachSplat((i, centre) => ...), then for each side:
const cap = utils.getTextureSize(count).maxSplats;          // array must be padded to a multiple of 2048
const arr = new Uint32Array(cap * 4), sh1 = new Uint32Array(cap * 2);
// copy all.packedArray rows (4 words per splat) and all.extra.sh1 rows (2 words per splat)
const part = new PackedSplats({ packedArray: arr, numSplats: count, extra: { sh1 }, splatEncoding: all.splatEncoding });
const mover = new SplatMesh({ packedSplats: part, editable: false });
holder.add(mover);   // then animate holder.position / rotation as normal three.js
```

- Verified: the car (49,614 splats) split out with SH1 kept and driven along a path by a plain transform; no `updateVersion()` needed. Split took well under a second.
- `PackedSplats.extractSplats(indices, false)` also exists but drops SH (it goes through `getSplat`/`pushSplat`).
- `mesh.numSplats` reads 0 until the first rendered frame for a mesh built from `packedSplats`; use `packedSplats.numSplats`.
- **Visible problem:** where the car had stood there is a dark smear, because training never saw the platform under it. A mover that leaves its spot needs the background painted without it, or the mover trained or placed separately. This is a pipeline matter, not a viewer one.
- Packed centres are 16-bit floats (about 4 mm at garage scale); unchanged from today.

## Technique 4: SplatEdit displacement

`new SplatEditSdf({ type: SplatEditSdfType.BOX, opacity: 1, color: white })` with `sdf.displace.set(x, y, z)` inside a `SplatEdit` (MULTIPLY) shifts every splat in the SDF. Verified: the car slid 1.5 m back and forth.

- Translation only, world space, no rotation; SDF types are ALL, PLANE, SPHERE, BOX, ELLIPSOID, CYLINDER, CAPSULE, INFINITE_CONE.
- Good for a quick nudge; skinning or splitting is better for real motion.

## Technique 5: small procedural splats at run time (bees, falling leaves)

One `SplatGenerator` whose graph computes each splat from `index` and time, with no data at all. Verified with 60 wandering dots (and the stock `generators.snowBox` uses the same pattern for falling particles).

```js
const tf = new SplatTransformer(), uT = dyno.dynoFloat(0);
const g = new SplatGenerator({
  numSplats: 60,
  generator: dyno.dynoBlock({ index: "int" }, { gsplat: dyno.Gsplat }, ({ index }) => {
    const d = new dyno.Dyno({ inTypes: { index: "int", t: "float" }, outTypes: { gsplat: dyno.Gsplat },
      inputs: { index, t: uT }, globals: () => [dyno.defineGsplat],
      statements: ({ inputs, outputs }) => [/* GLSL: set .flags = GSPLAT_FLAG_ACTIVE, .index, .center, .scales, .quaternion, .rgba */] });
    return { gsplat: tf.applyGsplat(d.outputs.gsplat) };
  }),
  update: () => { uT.value = now; tf.update(g); g.updateVersion(); },
});
scene.add(g);
```

- `generators.snowBox({ box, numSplats, fallDirection, fallVelocity, wanderScale, color1, color2, anisoScale, minY, ... })` returns `{ snow, ...uniforms }` and is a ready-made falling-leaf or drifting-pollen field; its fall offset uses `deltaTime`, so it needs the timer fix above. I read its code but did not run it.
- Hand-built tiny meshes also work: `new PackedSplats()` then `pushSplat(center, scales, quaternion, opacity, color)`, or `new SplatMesh({ constructSplats: (splats) => ... })`; one `PackedSplats` can back many `SplatMesh` instances (verified with 50 and 400).
- Keep each index's position continuous between frames, because the sort lags.

## Not verified

- Motion inside a stitched world, in night mode, or with the stitch editor open: reasoned from the code only.
- Frame rate with the pane visible at full window size, and with several worlds loaded at once.
- SH shading on splats rotated by a modifier or skinning: the view direction is not rotated with them, so a strongly rotated part keeps its rest-pose highlights. SH here is degree 1, so I expect it to be minor. A split-out mesh moved by its transform is handled correctly.
- `snowBox`, `covSplats`/linear-blend skinning, `ExtSplats` (32-bit centres) and LOD paths were read, not run.
- `SplatMesh` nested as a child of another `SplatMesh`: I kept movers as siblings under a group.