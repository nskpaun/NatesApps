import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { TransformControls } from "three/addons/controls/TransformControls.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { SplatMesh, SparkRenderer, SplatEdit, SplatEditSdf, SplatEditSdfType, SplatEditRgbaBlendMode } from "@sparkjsdev/spark";
import RAPIER from "rapier";
import { createAudio, gust, hash } from "./audio.js";
import { createFly } from "./fly.js";
import { setupMotion, stepMotion, disposeMotion, setMotionVisible } from "./motion.js";

const $ = (s) => document.querySelector(s), clamp = (x, a, b) => Math.min(b, Math.max(a, x));
const status = (t) => ($("#status").textContent = t);
const S = { parts: [], balls: [] }; // current world
const E = { on: false, parts: new Map(), sel: null, markers: [], seq: 0 };   // stitch editor (further down)
const renderer = new THREE.WebGLRenderer({ antialias: false, preserveDrawingBuffer: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2)); renderer.setSize(innerWidth, innerHeight);
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
document.body.appendChild(renderer.domElement);
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(65, innerWidth / innerHeight, 0.01, 100);
// The trainer (msplat) adds 0.3 px² to every splat's screen footprint with no opacity change; Spark's default (blurAmount) dims small splats instead.
const spark = new SparkRenderer({ renderer, preBlurAmount: 0.3, blurAmount: 0 }); scene.add(spark);
const orbit = new OrbitControls(camera, renderer.domElement);
const fly = createFly(camera, renderer.domElement, orbit);
const setFly = () => fly.setEnabled($("#walk").checked && !E.on);        // walking camera everywhere but the stitch editor
setFly();
// Training focal length in pixels: stored by newer builds; invented rooms are painted 1024 px wide at 65° across; unknown for old photo worlds.
const trainFocal = (def) => def.focal > 0 ? def.focal : def.kind === "prompt" || def.flat ? (def.width > 0 ? def.width : 1024) / 2 / Math.tan(THREE.MathUtils.degToRad(32.5)) : null;
// Scale the 0.3 from training pixels to screen pixels (area, so focal ratio squared); 0.3 as is when no part's focal is known.
const blurFor = (viewFocal, focals) => { const k = focals.filter((f) => f > 0).map((f) => (viewFocal / f) ** 2); return 0.3 * (k.length ? k.reduce((a, b) => a + b) / k.length : 1); };
function setBlur() {
  const viewFocal = renderer.getDrawingBufferSize(new THREE.Vector2()).y / 2 / Math.tan(THREE.MathUtils.degToRad(camera.fov / 2));
  spark.preBlurAmount = blurFor(viewFocal, (E.on ? [...E.parts.values()] : S.parts).map((p) => trainFocal(p.def)));
}
addEventListener("resize", () => { renderer.setPixelRatio(Math.min(devicePixelRatio, 2)); renderer.setSize(innerWidth, innerHeight); camera.aspect = innerWidth / innerHeight; camera.updateProjectionMatrix(); setBlur(); });

await RAPIER.init();
const gltf = new GLTFLoader();
window.S = S; window.THREE = THREE; window.camera = camera; window.orbit = orbit; window.scene = scene; window.renderer = renderer; window.fly = fly;

const lamp = new THREE.PointLight(0xffc27a, 1, 0, 2);
lamp.castShadow = true; lamp.shadow.mapSize.set(1024, 1024); lamp.shadow.bias = -0.004; lamp.shadow.normalBias = 0.06; lamp.shadow.radius = 4;
lamp.shadow.camera.near = 0.05; lamp.shadow.camera.far = 14;
const bulb = new THREE.Mesh(new THREE.SphereGeometry(0.04, 16, 12), new THREE.MeshBasicMaterial({ color: 0xffe0a8 }));
lamp.add(bulb); lamp.visible = false; scene.add(lamp);
const ambient = new THREE.AmbientLight(0x6f7fb8, 0.22); ambient.visible = false; scene.add(ambient);
const drag = new TransformControls(camera, renderer.domElement);
drag.attach(lamp); drag.setSize(0.6); drag.addEventListener("dragging-changed", (e) => (orbit.enabled = !e.value));
const dragHelper = drag.getHelper(); dragHelper.visible = false; drag.enabled = false; scene.add(dragHelper);
// where meshes have holes, dim the splat to ambient level so unlit patches do not glow in night mode
const back = new THREE.Mesh(new THREE.SphereGeometry(1, 24, 16), new THREE.MeshBasicMaterial({ color: 0x1a1d2b, side: THREE.BackSide, transparent: true,
  depthWrite: false, blending: THREE.CustomBlending, blendEquation: THREE.AddEquation, blendSrc: THREE.DstColorFactor, blendDst: THREE.ZeroFactor }));
back.renderOrder = 9.5; back.frustumCulled = false; back.visible = false; scene.add(back);
// outdoors: one sky colour behind everything, so a gap in the splats shows sky and not black
const sky = new THREE.Mesh(back.geometry, new THREE.MeshBasicMaterial({ side: THREE.BackSide, depthWrite: false, depthTest: false, fog: false }));
sky.renderOrder = -10; sky.frustumCulled = false; sky.visible = false; scene.add(sky);
// Motion and sound. T is the world's own clock in seconds (Spark's stays at 0 here); everything that moves is a function of it.
const audio = createAudio({ volume: +$("#volume").value });
const clock = { T: 0, paused: false, last: performance.now(), w: 0, fps: 0, frames: 0, sorts: 0, sortsPerSec: 0, lastSort: 0, since: performance.now(), windAt: 0 };

const DOOR = { w: 1.0, h: 2.1 };

// Split triangles until no edge is longer than maxEdge. Rapier smooths ball contacts across the seams of a flat surface only where the
// triangles are small next to the room: with two triangles per floor, measured 17-40 of 400 rolling balls still got kicked at the diagonal; with these, 0.
function tessellate(geo, maxEdge) {
  const g = geo.index ? geo.toNonIndexed() : geo, p = g.attributes.position, out = [];
  const stack = [];
  for (let i = 0; i < p.count; i += 3) stack.push([new THREE.Vector3().fromBufferAttribute(p, i), new THREE.Vector3().fromBufferAttribute(p, i + 1), new THREE.Vector3().fromBufferAttribute(p, i + 2)]);
  while (stack.length) {
    const [a, b, c] = stack.pop(), ab = a.distanceTo(b), bc = b.distanceTo(c), ca = c.distanceTo(a), mx = Math.max(ab, bc, ca);
    if (mx <= maxEdge) { out.push(a, b, c); continue; }
    if (mx === ab) { const m = a.clone().lerp(b, 0.5); stack.push([a, m, c], [m, b, c]); }
    else if (mx === bc) { const m = b.clone().lerp(c, 0.5); stack.push([a, b, m], [a, m, c]); }
    else { const m = c.clone().lerp(a, 0.5); stack.push([a, b, m], [m, b, c]); }
  }
  return out;
}
// Triangles of a geometry as a flat list of points (three per triangle).
function trisOf(geo) {
  const p = (geo.index ? geo.toNonIndexed() : geo).attributes.position, out = [];
  for (let i = 0; i < p.count; i++) out.push(new THREE.Vector3().fromBufferAttribute(p, i));
  return out;
}
// Split a convex polygon where dist(point) changes sign: [the part with dist <= 0, the part with dist > 0]. Keeps the winding.
function splitPoly(poly, dist) {
  const neg = [], pos = [];
  for (let i = 0; i < poly.length; i++) {
    const a = poly[i], b = poly[(i + 1) % poly.length], da = dist(a), db = dist(b);
    (da <= 0 ? neg : pos).push(a);
    if ((da <= 0) !== (db <= 0)) { const m = a.clone().lerp(b, da / (da - db)); neg.push(m); pos.push(m.clone()); }
  }
  return [neg, pos];
}
// What is left of a triangle once the region where every dist is <= 0 has been cut out of it, as triangles (same winding).
function cutHole(tri, dists) {
  const out = [], ab = new THREE.Vector3(), ac = new THREE.Vector3(); let inside = tri;
  for (const dist of dists) {
    const [inn, outside] = splitPoly(inside, dist);
    for (let k = 1; k < outside.length - 1; k++)
      if (ab.subVectors(outside[k], outside[0]).cross(ac.subVectors(outside[k + 1], outside[0])).lengthSq() > 1e-12) out.push(outside[0], outside[k], outside[k + 1]);   // skip slivers
    inside = inn; if (inside.length < 3) break;
  }
  return out;
}
function geometryFrom(tris, grey = 0.62) {
  const g = new THREE.BufferGeometry(), pos = new Float32Array(tris.length * 3);
  tris.forEach((v, i) => v.toArray(pos, i * 3));
  g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  g.setAttribute("color", new THREE.BufferAttribute(new Float32Array(tris.length * 3).fill(grey), 3));
  g.computeVertexNormals(); return g;
}

// One world, normalised: metres, y up, floor at y = 0, centred on its footprint. `outer` is what stitching moves.
async function loadPart(def) {
  const outer = new THREE.Group(), inner = new THREE.Group(); outer.add(inner); scene.add(outer);
  const splat = new SplatMesh({ url: def.ply }); inner.add(splat);
  let vis, col;
  try { [vis, col] = await Promise.all([gltf.loadAsync(def.mesh), gltf.loadAsync(def.collider)]); }
  catch (e) { scene.remove(outer); splat.dispose(); throw e; }
  let visGeo = vis.scene.getObjectByProperty("isMesh", true).geometry, colGeo = col.scene.getObjectByProperty("isMesh", true).geometry;
  const q = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(...def.up).normalize(), new THREE.Vector3(0, 1, 0));
  const pos = colGeo.attributes.position, v = new THREE.Vector3(), xs = [], ys = [], zs = [];
  for (let i = 0; i < pos.count; i++) { v.fromBufferAttribute(pos, i).applyQuaternion(q); xs.push(v.x); ys.push(v.y); zs.push(v.z); }
  const isRoom = def.kind === "prompt" || def.flat;          // exact box room from a blockout
  const open = isRoom && def.setting === "outdoor";          // a patch of ground under the sky: no walls, no doorways
  const pct = (arr, f) => arr.slice().sort((a, b) => a - b)[Math.floor((arr.length - 1) * f)];
  const lo = isRoom ? 0 : 0.04, hi = isRoom ? 1 : 0.96;
  // Newer builds store the floor height and the footprint centre [x, z] in file units; older worlds get an estimate from the collider.
  // With a centre, (x, floor, z) is a point of the file and is turned upright like the mesh; alone, floor is the height along `up`.
  const mid = def.centre ? v.set(def.centre[0], def.floor ?? 0, def.centre[1]).applyQuaternion(q) : null;
  const floorY = mid && def.floor != null ? mid.y : def.floor ?? pct(ys, lo), metre = def.metre ?? (pct(ys, hi) - floorY) / (def.heightMetres ?? 2.4);
  const cx = mid ? mid.x : (pct(xs, lo) + pct(xs, hi)) / 2, cz = mid ? mid.z : (pct(zs, lo) + pct(zs, hi)) / 2;
  inner.quaternion.copy(q); inner.scale.setScalar(1 / metre); inner.position.set(-cx / metre, -floorY / metre, -cz / metre);
  // footprint in metres: exact for invented rooms, estimated for photo worlds
  const roomW = isRoom ? (def.room?.[0] ?? 4) : (pct(xs, hi) - pct(xs, lo)) / metre, roomD = isRoom ? (def.room?.[2] ?? 4) : (pct(zs, hi) - pct(zs, lo)) / metre;
  if (isRoom) { visGeo = colGeo = geometryFrom(tessellate(colGeo, (open ? 1 : roomW * roomD > 60 ? 0.5 : 0.25) * metre)); }
  else visGeo.computeVertexNormals();
  return { def, outer, inner, splat, visGeo, colGeo, isRoom, open, roomW, roomD, metre };
}

// Meshes for a part: flat view, collider wireframe, and the night-mode pair (depth prepass + lit pass multiplied over the splat).
function buildMeshes(p) {
  for (const k of ["flat", "wire", "pre", "lit"]) if (p[k]) { p.inner.remove(p[k]); p[k].material.dispose(); }
  // an invented room's mesh has no colours of its own: shade it by which way each face points, so its shapes can be read
  p.flat = new THREE.Mesh(p.visGeo, p.isRoom ? new THREE.MeshNormalMaterial({ flatShading: true, side: THREE.DoubleSide })
    : new THREE.MeshBasicMaterial({ vertexColors: true, side: THREE.DoubleSide }));
  p.wire = new THREE.Mesh(p.colGeo, new THREE.MeshBasicMaterial({ color: 0x35d0ff, wireframe: true }));
  p.pre = new THREE.Mesh(p.visGeo, new THREE.MeshBasicMaterial({ colorWrite: false, transparent: true, side: THREE.DoubleSide }));
  p.lit = new THREE.Mesh(p.visGeo, new THREE.MeshStandardMaterial({ color: 0xffffff, flatShading: p.isRoom, roughness: 1, metalness: 0, side: THREE.DoubleSide,
    shadowSide: THREE.DoubleSide, transparent: true, depthWrite: false, depthFunc: THREE.EqualDepth,
    blending: THREE.CustomBlending, blendEquation: THREE.AddEquation, blendSrc: THREE.DstColorFactor, blendDst: THREE.ZeroFactor }));
  p.pre.renderOrder = 9; p.lit.renderOrder = 10; p.lit.castShadow = true; p.lit.receiveShadow = true;
  p.inner.add(p.flat, p.wire, p.pre, p.lit);
}

// Doorways: where two invented rooms have walls touching, find the overlap and return a box to cut through both.
// The four walls of a room in world space: outward normal n, centre c, direction along the wall t, and length len.
function wallsOf(p) {
  return [[1, 0], [-1, 0], [0, 1], [0, -1]].map(([nx, nz]) => {
    const n = new THREE.Vector3(nx, 0, nz).applyAxisAngle(new THREE.Vector3(0, 1, 0), p.outer.rotation.y);
    return { n, c: p.outer.position.clone().addScaledVector(n, (nx ? p.roomW : p.roomD) / 2), t: new THREE.Vector3(-n.z, 0, n.x), len: nx ? p.roomD : p.roomW };
  });
}
// For two facing walls: the gap between them and the stretch where they overlap (as an interval along a.t from a.c).
function facing(a, b) {
  if (a.n.dot(b.n) > -0.985) return null;
  const d = b.c.clone().sub(a.c), gap = d.dot(a.n), along = d.dot(a.t);
  const lo = Math.max(-a.len / 2, along - b.len / 2), hi = Math.min(a.len / 2, along + b.len / 2);
  return { gap, lo, hi };
}
function findDoors(parts) {
  const doors = [], rooms = parts.filter((p) => p.isRoom && !p.open);
  for (let i = 0; i < rooms.length; i++) for (let j = i + 1; j < rooms.length; j++)
    for (const a of wallsOf(rooms[i])) for (const b of wallsOf(rooms[j])) {
      const f = facing(a, b);
      if (!f || f.gap < -0.15 || f.gap > 0.6 || f.hi - f.lo < DOOR.w + 0.4) continue;    // touching (or nearly) with room for a door
      const centre = a.c.clone().addScaledVector(a.t, (f.lo + f.hi) / 2).addScaledVector(a.n, f.gap / 2);
      // depth: just past both walls (for the editor's marker); walls: the two wall planes to cut, one per room
      doors.push({ centre, yaw: Math.atan2(a.n.x, a.n.z), depth: Math.abs(f.gap) + 0.2, walls: [{ part: rooms[i], n: a.n, c: a.c }, { part: rooms[j], n: b.n, c: b.c }] });
    }
  return doors;
}
// The door rectangle on a wall as three cutting functions (negative inside): two jambs and the lintel. No bottom, so the floor is never touched.
function doorDists(d) {
  const tx = Math.cos(d.yaw), tz = -Math.sin(d.yaw), along = (w) => (w.x - d.centre.x) * tx + (w.z - d.centre.z) * tz;
  return [(w) => -along(w) - DOOR.w / 2, (w) => along(w) - DOOR.w / 2, (w) => w.y - DOOR.h];
}
const REACH = 0.35;   // how far into a room (from its wall) a doorway is cleared of furniture, in the collider and in the splats
const wallDist = (wall, w) => (w.x - wall.c.x) * wall.n.x + (w.z - wall.c.z) * wall.n.z - (wall.off ?? 0);   // outward distance from the wall
const onWall = (wall, w) => Math.abs(wallDist(wall, w)) < 0.02;
const triArea = (a, b, c) => b.clone().sub(a).cross(c.clone().sub(a)).length() / 2;
// Where a wall really is, as an offset along its normal from where the footprint puts it: the biggest flat sheet within 0.4 m.
// (The footprint centre of an older world is an estimate and can be a few decimetres out when a piece pokes through a wall.)
function wallOffset(wall, tris) {
  const bins = new Map(), s = (w) => (w.x - wall.c.x) * wall.n.x + (w.z - wall.c.z) * wall.n.z; let best = 0, most = 0;
  for (let i = 0; i < tris.length; i += 3) {
    const a = s(tris[i]);
    if (Math.abs(a) > 0.4 || Math.abs(s(tris[i + 1]) - a) > 1e-3 || Math.abs(s(tris[i + 2]) - a) > 1e-3) continue;
    const k = Math.round(a * 100), sum = (bins.get(k) ?? [0, 0]); sum[0] += triArea(tris[i], tris[i + 1], tris[i + 2]); sum[1] += a * triArea(tris[i], tris[i + 1], tris[i + 2]);
    bins.set(k, sum); if (sum[0] > most) { most = sum[0]; best = sum[1] / sum[0]; }
  }
  return best;
}
// Cut the doorways out of this room. Triangles lying on the wall are clipped exactly against the door rectangle, so jambs and lintel are
// straight; anything else of this room standing in the opening (a shelf or window placed on that wall) is clipped away up to REACH from the
// wall. The floor and furniture beside the door are untouched.
function carve(p, doors) {
  p.outer.updateMatrixWorld(true);
  const toWorld = p.inner.matrixWorld, toLocal = toWorld.clone().invert(), old = new Set([p.visGeo, p.colGeo]);
  let tris = trisOf(p.colGeo).map((v) => v.applyMatrix4(toWorld));
  for (const d of doors) for (const wall of d.walls) {
    if (wall.part !== p) continue;
    wall.off = wallOffset(wall, tris);
    const rect = doorDists(d), prism = [...rect, (w) => -REACH - wallDist(wall, w), (w) => wallDist(wall, w) - REACH], next = [];
    for (let i = 0; i < tris.length; i += 3) {
      const t = [tris[i], tris[i + 1], tris[i + 2]], dists = t.every((w) => onWall(wall, w)) ? rect : prism;
      // whole triangles are kept as they are when they lie on the floor or fully to one side of the opening
      next.push(...(t.every((w) => w.y < 0.03) || dists.some((f) => t.every((w) => f(w) > 0)) ? t : cutHole(t, dists)));
    }
    tris = next;
  }
  p.visGeo = p.colGeo = geometryFrom(tris.map((v) => v.clone().applyMatrix4(toLocal)));   // clone: cut pieces share corner points
  for (const g of old) g.dispose();
}
// Hide the splats in a doorway: one box per room, from REACH inside its wall to just past the middle of the gap, from just above the
// floor (so the floor stays) to the lintel. Each box sits on its own wall, so a room turned a few degrees still loses the right patch.
function eraseDoor(d) {
  for (const wall of d.walls) {
    const out = Math.max(0, wallDist(wall, d.centre)) + 0.05, at = d.centre.clone().addScaledVector(wall.n, (out - REACH) / 2 - wallDist(wall, d.centre));
    eraseBox(at.setY((DOOR.h + 0.03) / 2), Math.atan2(wall.n.x, wall.n.z), DOOR.w / 2, (DOOR.h - 0.03) / 2, (out + REACH) / 2, 0.02);
  }
}
function clearEdits() { for (const e of S.edits ?? []) scene.remove(e); S.edits = []; }
function eraseBox(centre, yaw, halfX, halfY, halfZ, softEdge = 0.03) {     // hide splats inside a box
  const edit = new SplatEdit({ rgbaBlendMode: SplatEditRgbaBlendMode.MULTIPLY, softEdge });
  const sdf = new SplatEditSdf({ type: SplatEditSdfType.BOX, opacity: 0 });
  sdf.position.copy(centre); sdf.rotation.y = yaw; sdf.scale.set(halfX, halfY, halfZ);
  edit.add(sdf); scene.add(edit); S.edits.push(edit);
}

// Take a part out of the scene and release its splat data, geometries (visGeo and colGeo can be the same one) and materials.
function disposePart(p) {
  disposeMotion(p);
  scene.remove(p.outer); p.splat.dispose();
  for (const g of new Set([p.visGeo, p.colGeo])) g.dispose();
  for (const k of ["flat", "wire", "pre", "lit", "outline"]) p[k]?.material.dispose();
  p.outline?.geometry.dispose();
}
function clearWorld() {
  for (const p of S.parts) disposePart(p);
  for (const b of S.balls) { scene.remove(b.mesh); b.mesh.material.dispose(); }      // the sphere geometry is shared, keep it
  S.phys?.free();                                                                   // Rapier's memory is not garbage collected
  clearEdits(); S.parts = []; S.balls = []; S.phys = null; S.net = null; S.world = null; S.ready = false;
  S.wind = null; S.bound = null; S.zones = null; S.sky = false; tour.path = null; S.emitters = 0; sky.visible = false; orbit.maxDistance = Infinity; audio.detachAll();
}

// Balls no longer bump on the seams between triangles of a flat surface. The two-sided variant keeps contacts on the back of a triangle,
// so a patch of a reconstructed mesh that faces the wrong way still holds a ball.
// Rapier's FIX_INTERNAL_EDGES flag is deliberately not used: it makes triangles one-sided, and in a browser test
// 14 of 40 balls then rolled out through the walls of an invented room (0 of 40 without it).
const TRI_FLAGS = undefined;
let loadSeq = 0;   // each load() takes a number; a load that is no longer the newest gives up and cleans up after itself
async function load(def) {
  if (!def || E.on) return;                 // the stitch editor owns the scene while it is open; it loads the chosen world when it closes
  const my = ++loadSeq;
  status(`loading ${def.name}…`); clearWorld();
  const specs = def.parts ? def.parts.map((s) => ({ ...s, def: defs.find((d) => d.name === s.ref) })).filter((s) => s.def) : [{ def, x: 0, z: 0, rot: 0 }];
  if (!specs.length) return status(`${def.name}: its rooms no longer exist`);
  const got = await Promise.allSettled(specs.map(async (s) => { const p = await loadPart(s.def); p.outer.position.set(s.x, 0, s.z); p.outer.rotation.y = s.rot; return p; }));
  const parts = got.filter((r) => r.status === "fulfilled").map((r) => r.value), failed = got.find((r) => r.status === "rejected");
  if (my !== loadSeq || failed) {
    parts.forEach(disposePart);
    if (my === loadSeq) { status(`${def.name} could not be loaded`); console.error(failed.reason); }
    return;
  }
  S.parts = parts; setBlur();
  const doors = def.parts ? findDoors(S.parts) : [];
  S.doors = doors;
  const phys = new RAPIER.World({ x: 0, y: -9.8, z: 0 });
  for (const p of S.parts) {
    if (p.isRoom && doors.length) carve(p, doors);
    buildMeshes(p); p.outer.updateMatrixWorld(true);
    const g = p.colGeo.index ? p.colGeo.toNonIndexed() : p.colGeo, pos = g.attributes.position, verts = new Float32Array(pos.count * 3), v = new THREE.Vector3();
    for (let i = 0; i < pos.count; i++) v.fromBufferAttribute(pos, i).applyMatrix4(p.inner.matrixWorld).toArray(verts, i * 3);
    phys.createCollider(RAPIER.ColliderDesc.trimesh(verts, Uint32Array.from({ length: pos.count }, (_, i) => i), TRI_FLAGS));
  }
  doors.forEach(eraseDoor);
  // safety net: a flat floor just under the real one, for holes in reconstructed meshes
  // outdoors it is also the ground around the slab: a ball that rolls off lands on it and is counted. Its top is 5 cm down, so a ball resting on the ground does not touch it
  const out = S.parts.find((p) => p.open);
  const net = phys.createCollider(RAPIER.ColliderDesc.cuboid(1000, 0.05, 1000).setTranslation(0, -0.1, 0));
  Object.assign(S, { def, world: S.parts[0].outer, phys, net, metre: 1, floorY: 0 });
  if (out) {     // keep the eye near the play area: the far surround is a flat painting
    S.bound = { x: out.outer.position.x, z: out.outer.position.z, hx: out.roomW / 2 + 3, hz: out.roomD / 2 + 3, hy: Math.max(3, out.def.room?.[1] ?? 6) }; orbit.maxDistance = 8;
    const c = out.def.sky; S.sky = Array.isArray(c) && c.length === 3 && c.every(Number.isFinite);
    if (S.sky) sky.material.color.setRGB(c[0], c[1], c[2], THREE.SRGBColorSpace);
  }
  else if (S.parts.every((p) => p.isRoom && Array.isArray(p.def.room) && p.def.room.length === 3 && p.def.room.every((v) => v > 0))) {
    // invented rooms: where a walking eye may be. Each room's box, 0.25 m in from walls and ceiling, and a short box through each doorway
    S.zones = [...S.parts.map((p) => ({ x: p.outer.position.x, z: p.outer.position.z, yaw: p.outer.rotation.y, hx: Math.max(0.05, p.roomW / 2 - 0.25), hz: Math.max(0.05, p.roomD / 2 - 0.25), y0: Math.min(0.3, p.def.room[1] / 2), y1: Math.max(p.def.room[1] / 2, p.def.room[1] - 0.25) })),
      ...doors.map((d) => ({ x: d.centre.x, z: d.centre.z, yaw: d.yaw, hx: DOOR.w / 2 - 0.2, hz: d.depth / 2 + 0.45, y0: 0.3, y1: DOOR.h - 0.25 }))];
    for (const z of S.zones) { z.cos = Math.cos(z.yaw); z.sin = Math.sin(z.yaw); }
  }
  // start where the first part's photos were taken (or its first generated view)
  const p0 = S.parts[0], d0 = p0.def;
  const c = new THREE.Vector3(...(d0.eye ?? d0.center)).applyMatrix4(p0.inner.matrixWorld);
  const f = new THREE.Vector3(...d0.forward).applyQuaternion(p0.inner.getWorldQuaternion(new THREE.Quaternion())).normalize();
  camera.position.copy(c); camera.near = 0.02; camera.far = 200; camera.updateProjectionMatrix();
  orbit.target.copy(c).addScaledVector(f, 1.2); orbit.update();
  lamp.position.copy(c).addScaledVector(f, 0.7).add(new THREE.Vector3(0.25, 0.15, 0));
  lamp.intensity = def.lamp ?? (def.parts ? 5 : 1.6);
  try { await Promise.all(parts.map((p) => p.splat.initialized)); }
  catch (e) { if (my === loadSeq) { clearWorld(); status(`${def.name} could not be loaded`); console.error(e); } return; }
  if (my !== loadSeq) return;               // a newer load has already cleared this world
  // moving things and sound. Both are optional extras: a failure here leaves a still, silent world
  await Promise.all(parts.map((p) => setupMotion(p, { RAPIER, phys, gltf, T: clock.T }).catch((e) => console.warn("motion: skipped for", p.def.name, e))));
  if (my !== loadSeq) return;
  const wd = parts.find((p) => p.def.wind)?.def.wind, sways = parts.some((p) => p.motion?.stats.sway);
  S.wind = { seed: hash(def.name), strength: Math.min(1, Math.max(0, Number.isFinite(+wd?.strength) ? +wd.strength : out ? 0.35 : sways ? 0.2 : 0)) };
  audio.setMood({ ...d0.mood, name: def.name, style: d0.style, setting: out ? "outdoor" : "indoor", night: $("#night").checked || undefined });   // undefined: let the mood's own time of day decide
  // at most 12 sounds: everything that travels or flies first, then the largest swaying things (6 at most)
  const sounds = parts.flatMap((p) => p.motion?.sounds ?? []), big = (a, b) => b.size - a.size;
  const picked = [...sounds.filter((s) => s.type !== "sway").sort(big).slice(0, 12), ...sounds.filter((s) => s.type === "sway").sort(big).slice(0, 6)].slice(0, 12);
  for (const s of picked) audio.attach(s.obj, s.kind);
  S.emitters = picked.length;
  if ($("#sound").checked && !audio.running) audio.start();
  apply();
  S.ready = true;
  const doorNote = def.parts ? ` | ${S.parts.length} rooms, ${doors.length} doorway${doors.length === 1 ? "" : "s"}` : "";
  status(`${def.name}: ${def.note ?? ""}${doorNote} | ${fly.enabled ? "W A S D to move, drag to look" : "drag to orbit, scroll to zoom"}`);
  document.title = "Prometheus Worlds";
}

function apply() {
  if (!S.world) return;
  const mode = document.querySelector("input[name=mode]:checked").value, night = $("#night").checked;
  for (const p of S.parts) {
    p.splat.visible = mode === "splat"; p.flat.visible = mode === "mesh" && !night; p.wire.visible = mode === "collider";
    p.lit.material.vertexColors = mode === "mesh"; p.lit.material.blending = mode === "mesh" ? THREE.NormalBlending : THREE.CustomBlending; p.lit.material.needsUpdate = true;
    p.pre.visible = p.lit.visible = night && mode !== "collider";
    setMotionVisible(p, mode, night);
  }
  sky.visible = !!S.sky && mode === "splat";
  ambient.visible = night; back.visible = night && mode === "splat"; lamp.visible = night; dragHelper.visible = night; drag.enabled = night;
}
document.querySelectorAll("input[name=mode]").forEach((r) => r.addEventListener("change", apply));
$("#night").addEventListener("change", () => { apply(); audio.setNight($("#night").checked || undefined); });
// ticking Sound is the click the browser needs before it lets a page play anything
$("#sound").addEventListener("change", (e) => (e.target.checked ? audio.start() : audio.stop()));
$("#volume").addEventListener("input", (e) => audio.setVolume(+e.target.value));

const ballGeo = new THREE.SphereGeometry(1, 20, 14);
const ray = new THREE.Raycaster();
function drop(n = 25) {
  if (!S.world) return 0;
  let made = 0; const wires = S.parts.flatMap((p) => [p.wire, ...(p.motion?.wires ?? [])]);
  for (let tries = 0; made < n && tries < n * 8; tries++) {
    // aim at a random point in the lower middle of the view and spawn just above the surface found there
    ray.setFromCamera(new THREE.Vector2((Math.random() - 0.5) * 1.2, (Math.random() - 0.75) * 0.9), camera);
    const hit = ray.intersectObjects(wires, false)[0];
    if (!hit || hit.distance > 9) continue;
    const r = 0.035 + Math.random() * 0.025;
    const p = hit.point.clone().addScaledVector(ray.ray.direction, -0.15).add(new THREE.Vector3(0, 0.25 + Math.random() * 0.4, 0));
    const body = S.phys.createRigidBody(RAPIER.RigidBodyDesc.dynamic().setTranslation(p.x, p.y, p.z).setCcdEnabled(true).setLinearDamping(0.1).setAngularDamping(0.3));
    const ballCol = S.phys.createCollider(RAPIER.ColliderDesc.ball(r).setRestitution(0.5).setFriction(0.7).setDensity(1), body);
    const col = new THREE.Color().setHSL(Math.random(), 0.75, 0.55);
    const mesh = new THREE.Mesh(ballGeo, new THREE.MeshStandardMaterial({ color: col, emissive: col, emissiveIntensity: 0.55, roughness: 0.4 }));
    mesh.scale.setScalar(r); mesh.castShadow = true; scene.add(mesh); S.balls.push({ body, col: ballCol, mesh, onNet: false }); made++;
  }
  return made;
}
$("#drop").addEventListener("click", () => drop());
window.drop = drop;

// test hook: how many balls there are and how many fell through the collider onto the safety net (a ball counts once it has touched the net)
Object.defineProperty(window, "ballStats", { get: () => ({ n: S.balls.length, onNet: S.balls.filter((b) => b.onNet).length }) });
// test hooks: motion.set(t) shows the world at time t and holds it there; motion.pause(false) lets time run again
window.motion = {
  set(t) { clock.T = Number.isFinite(+t) ? +t : 0; clock.paused = true; },
  pause(b = true) { clock.paused = !!b; },
  get stats() {
    return { t: clock.T, paused: clock.paused || !$("#motionOn").checked, wind: clock.w, fps: Math.round(clock.fps), sorts: clock.sortsPerSec, sound: audio.running, emitters: S.emitters ?? 0,
      parts: S.parts.map((p) => (p.motion ? { name: p.def.name, ...p.motion.stats } : null)) };
  },
};
renderer.setAnimationLoop(() => {
  if (document.hidden) return;              // nothing to show: leave the GPU alone
  const now = performance.now(), dt = Math.min(0.1, (now - clock.last) / 1000); clock.last = now;
  if (!clock.paused && $("#motionOn").checked) clock.T += dt;
  clock.frames++; if (spark.lastSortTime !== clock.lastSort) { clock.lastSort = spark.lastSortTime; clock.sorts++; }
  if (now - clock.since >= 1000) { const k = 1000 / (now - clock.since); clock.fps = clock.frames * k; clock.sortsPerSec = Math.round(clock.sorts * k); clock.frames = clock.sorts = 0; clock.since = now; }
  // one wind value for the swaying and for the wind sound
  const w = clock.w = S.wind?.strength > 0 ? gust(clock.T, S.wind.seed, S.wind.strength) : 0;
  for (const p of S.parts) if (p.motion) try { stepMotion(p, clock.T, w); } catch (e) { console.warn("motion: stopped for", p.def.name, e); disposeMotion(p); }
  if (S.phys) {
    S.phys.step();
    for (const b of S.balls) {
      const t = b.body.translation(); b.mesh.position.set(t.x, t.y, t.z);
      if (!b.onNet) S.phys.contactPair(S.net, b.col, (m) => { if (m.numContacts() > 0) b.onNet = true; });
    }
  }
  if ($("#tour").checked && S.ready && !E.on) tourStep(dt);
  else { fly.update(dt); if (!E.on) keepIn(dt); }
  orbit.update();
  back.position.copy(camera.position); back.scale.setScalar(camera.far * 0.5);
  sky.position.copy(camera.position); sky.scale.setScalar(camera.far * 0.5);
  renderer.render(scene, camera);
  if (audio.running) {
    if (now - clock.windAt > 100) { clock.windAt = now; audio.setWind(w); }      // ten times a second is plenty for a slow curve
    audio.update(camera);
  }
});

// Keep the eye in the world. Walking outdoors: inside the play area, at least 0.3 m above the ground. Walking in invented rooms: inside the
// rooms (S.zones), so W A S D cannot pass a wall into the void. Both are soft: the eye is eased back, most of the way each frame, and is never
// left more than 0.2 m out. Orbiting outdoors: the point orbited stays in the play area, and the eye above the ground.
const zv = new THREE.Vector3(), zb = new THREE.Vector3();
function nearestInside(zones, e, out) {
  let best = Infinity;
  for (const z of zones) {
    const dx = e.x - z.x, dz = e.z - z.z, u = clamp(dx * z.cos - dz * z.sin, -z.hx, z.hx), v = clamp(dx * z.sin + dz * z.cos, -z.hz, z.hz);   // in the zone's own axes
    zv.set(z.x + u * z.cos + v * z.sin, clamp(e.y, z.y0, z.y1), z.z - u * z.sin + v * z.cos);
    const d = zv.distanceToSquared(e); if (d < best) { best = d; out.copy(zv); }
  }
  return out;
}
function keepIn(dt) {
  const b = S.bound, e = camera.position, t = orbit.target, soft = 1 - Math.exp(-dt * 30);
  if (fly.enabled && (b || S.zones)) {
    if (b) zb.set(clamp(e.x, b.x - b.hx, b.x + b.hx), clamp(e.y, 0.4, Math.max(0.4, b.hy)), clamp(e.z, b.z - b.hz, b.z + b.hz)); else nearestInside(S.zones, e, zb);
    const d = zb.distanceTo(e); if (d < 1e-5) return;
    zb.sub(e).multiplyScalar(Math.max(soft, 1 - 0.2 / d)); if (b && e.y + zb.y < 0.3) zb.y = 0.3 - e.y;      // the ground itself is firm
    e.add(zb); t.add(zb);
  } else if (b) {
    const x = clamp(t.x, b.x - b.hx, b.x + b.hx), y = clamp(t.y, 0, b.hy), z = clamp(t.z, b.z - b.hz, b.z + b.hz);
    if (x !== t.x || y !== t.y || z !== t.z) { e.x += x - t.x; e.y += y - t.y; e.z += z - t.z; t.set(x, y, z); }
    if (e.y < 0.3) e.y += (0.3 - e.y) * soft;
  }
}

// Tour: a slow glide round one part of the world at eye height, looking at its middle. Any key, or a click, drag or scroll on the picture, hands the camera back.
const tour = { path: null };
const stopTour = () => { if ($("#tour").checked) { $("#tour").checked = false; tour.path = null; } };
function tourPlan() {
  const far = (p) => p.outer.position.distanceToSquared(camera.position), tv = new THREE.Vector3();
  const holds = (p) => { p.outer.updateMatrixWorld(true); tv.copy(camera.position).applyMatrix4(p.outer.matrixWorld.clone().invert()); return Math.abs(tv.x) <= p.roomW / 2 && Math.abs(tv.z) <= p.roomD / 2; };
  const p = S.parts.find(holds) ?? S.parts.reduce((a, b) => (far(b) < far(a) ? b : a));   // the part the eye is in, or else the nearest
  p.outer.updateMatrixWorld(true);
  const room = p.isRoom && Array.isArray(p.def.room) ? p.def.room : null, closed = room && !p.open, hx = p.roomW / 2, hz = p.roomD / 2, margin = p.open ? 0.5 : 0.7;
  const eye = new THREE.Vector3(...(p.def.eye ?? p.def.center ?? [0, 0, 0])).applyMatrix4(p.inner.matrixWorld).y - p.outer.position.y;
  const y = Math.min(clamp(Number.isFinite(eye) ? eye : 1.5, 1.1, 1.8), closed ? Math.max(0.4, room[1] - 0.5) : 9), toWorld = p.outer.matrixWorld;
  let cx = 0, cz = 0, ex = hx, ez = hz;      // the ring's middle and half-size in the part's frame: the room's, unless something travels through its middle
  const at = (a, f, out) => out.set(cx + Math.max(0.15 * ex, Math.min(f * ex, ex - margin)) * Math.cos(a), y, cz + Math.max(0.15 * ez, Math.min(f * ez, ez - margin)) * Math.sin(a)).applyMatrix4(toWorld);
  const look = new THREE.Vector3(0, Math.max(0.3, y - 0.3), 0).applyMatrix4(toWorld);
  // is there room for an eye here? Look straight down from above (from under the ceiling in an invented room): what is found first must be well
  // below the eye. Nothing may stand within 1.5 m between the eye and the middle, so no piece fills the picture (or has the eye inside it),
  // nor within 0.5 m behind it or to either side
  const top = p.open ? y + 12 : closed ? room[1] - 0.06 : y + 0.4, skip = RAPIER.QueryFilterFlags.EXCLUDE_KINEMATIC | RAPIER.QueryFilterFlags.EXCLUDE_DYNAMIC, v = new THREE.Vector3(), d = new THREE.Vector3();
  const lanes = S.parts.flatMap((q) => (q.motion?.lanes ?? []).map((l) => ({ r2: l.r * l.r, pts: l.pts.map((x) => x.clone().applyMatrix4(q.outer.matrixWorld)) })));   // and it keeps off the strips where things travel or swing
  const inLane = (v) => lanes.some((l) => l.pts.some((x) => (x.x - v.x) ** 2 + (x.z - v.z) ** 2 < l.r2));
  const N = 72, TAU = Math.PI * 2, rings = [0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2];
  // a lane near the middle (a road down a street) leaves no ring round the middle that stays off it: the tour then goes round the middle
  // of the largest stretch of floor no lane crosses, and looks at that
  if (lanes.length && Array.from({ length: N }, (_, k) => rings.every((r) => inLane(at(k * TAU / N, r, v)))).filter(Boolean).length > N / 12) {
    const G = 32, cell = (i, j, out) => out.set((i + 0.5) / G * 2 * hx - hx, y, (j + 0.5) / G * 2 * hz - hz), free = [], seen = new Uint8Array(G * G); let best = [];
    for (let j = 0; j < G; j++) for (let i = 0; i < G; i++) free.push(!inLane(cell(i, j, v).applyMatrix4(toWorld)));
    for (let s = 0; s < G * G; s++) {
      if (!free[s] || seen[s]) continue;
      const grp = [], todo = [s]; seen[s] = 1;
      while (todo.length) { const q = todo.pop(), i = q % G, j = (q - i) / G; grp.push(q);
        for (const [a, b] of [[i - 1, j], [i + 1, j], [i, j - 1], [i, j + 1]]) { const n = b * G + a; if (a >= 0 && a < G && b >= 0 && b < G && free[n] && !seen[n]) { seen[n] = 1; todo.push(n); } } }
      if (grp.length > best.length) best = grp;
    }
    if (best.length) {
      const sum = best.reduce((o, q) => { cell(q % G, Math.floor(q / G), v); o.x += v.x; o.z += v.z; return o; }, { x: 0, z: 0 });
      cx = sum.x / best.length; cz = sum.z / best.length; ex = Math.max(0.5, hx - Math.abs(cx)); ez = Math.max(0.5, hz - Math.abs(cz));
      look.set(cx, Math.max(0.3, y - 0.3), cz).applyMatrix4(toWorld);
    }
  }
  const clear = (a, f) => {
    at(a, f, v); if (inLane(v)) return false;
    const far = d.subVectors(look, v).length(); d.divideScalar(far || 1);
    if (far > 0.3 && S.phys.castRay(new RAPIER.Ray(v, d), Math.min(1.5, 0.6 * far), true, skip)) return false;
    d.setY(0).normalize(); for (const [x, z] of [[-d.x, -d.z], [-d.z, d.x], [d.z, -d.x]]) if (S.phys.castRay(new RAPIER.Ray(v, { x, y: 0, z }), 0.5, true, skip)) return false;
    v.y += top - y;
    const hit = S.phys.castRay(new RAPIER.Ray(v, { x: 0, y: -1, z: 0 }), top + 1, true, skip);
    return !hit || (hit.timeOfImpact ?? hit.toi) > top - y + 0.4;
  };
  // per direction, the widest ring that is clear (and still clear a little further in); then smoothed, never outwards, so the glide has no corners
  let f = Array.from({ length: N }, () => 0.7);
  try { f = f.map((_, k) => rings.find((r) => clear(k * TAU / N, r) && clear(k * TAU / N, r - 0.06)) ?? 0.2); } catch (e) { console.warn("tour: could not look for a clear way round", e); }
  if (f.filter((r) => r > 0.2).length < N / 4) f = f.map(() => 0.6);       // next to nothing clear: more likely the test than the world
  const near = (g, k, fn) => fn(...[-3, -2, -1, 0, 1, 2, 3].map((j) => g[(k + j + N) % N]));
  f = f.map((_, k) => near(f, k, Math.min)); f = f.map((_, k) => near(f, k, (...q) => q.reduce((a, b) => a + b) / q.length));
  const local = camera.position.clone().applyMatrix4(toWorld.clone().invert()), a0 = Math.atan2((local.z - cz) / ez, (local.x - cx) / ex), a = Number.isFinite(a0) ? a0 : 0;
  // where the ring is at angle a: between the two nearest directions
  const ring = (a, out) => { const q = ((a / TAU) % 1 + 1) % 1 * N, k = Math.floor(q) % N; return at(a, f[k] + (f[(k + 1) % N] - f[k]) * (q - Math.floor(q)), out); };
  const dir = camera.getWorldDirection(new THREE.Vector3()), start = ring(a, new THREE.Vector3()), turn = dir.angleTo(v.subVectors(look, start));   // how far the eye has to turn to face the middle
  const yaw = Math.atan2(dir.x, dir.z);
  return { ring, look, a, w: TAU / 50, t: 0, blend: Math.max(2.5 + 2.5 * turn / Math.PI, 2 * start.distanceTo(camera.position)), from: camera.position.clone(), yaw0: yaw, yaw1: yaw, pitch0: Math.asin(clamp(dir.y, -1, 1)), at: start };
}
const tp = new THREE.Vector3(), tl = new THREE.Vector3();
function tourStep(dt) {
  const P = tour.path ??= tourPlan(); P.t += dt;
  // once round in 50 s, and never faster than 0.4 m/s where the ring is wide or changes width
  const da = P.w * dt, step = P.ring(P.a + da, tp).distanceTo(P.at); P.a += da * Math.min(1, 0.4 * dt / Math.max(step, 1e-6)); P.ring(P.a, P.at);
  const s = clamp(P.t / P.blend, 0, 1), ease = s * s * (3 - 2 * s);    // the first seconds: from where the eye was, and the way it faced, into the glide
  camera.position.lerpVectors(P.from, P.at, ease);
  tl.subVectors(P.look, P.at).normalize();                             // the way the glide looks from here
  if (ease < 1) {                                                      // turn to it as bearing and tilt, the bearing followed round so it never jumps
    const turn = Math.atan2(tl.x, tl.z) - P.yaw1; P.yaw1 += turn - Math.PI * 2 * Math.round(turn / (Math.PI * 2));
    const yaw = P.yaw0 + (P.yaw1 - P.yaw0) * ease, pitch = P.pitch0 + (Math.asin(clamp(tl.y, -1, 1)) - P.pitch0) * ease;
    tl.set(Math.sin(yaw) * Math.cos(pitch), Math.sin(pitch), Math.cos(yaw) * Math.cos(pitch));
  }
  orbit.target.copy(camera.position).addScaledVector(tl, 2);           // orbit.update() turns the camera to it
}
$("#tour").addEventListener("change", (e) => { tour.path = null; e.target.blur(); });
addEventListener("keydown", (e) => { if (!e.metaKey && !e.ctrlKey && !e.altKey && !["Shift", "Meta", "Control", "Alt", "CapsLock"].includes(e.key)) stopTour(); });
renderer.domElement.addEventListener("pointerdown", stopTour);
renderer.domElement.addEventListener("wheel", stopTour, { passive: true });

let defs = [];
async function refreshScenes(select) {
  defs = await (await fetch("/scenes.json", { cache: "no-store" })).json();
  const sel = $("#scene"), keep = select ?? sel.value;
  $("#stitch").disabled = defs.filter((d) => !d.parts).length < 2;
  sel.replaceChildren(...defs.map((d) => new Option(d.name, d.name)));
  if (!defs.length) { status("No worlds yet. Choose New world to build one from photos or a prompt."); return null; }
  sel.value = defs.find((d) => d.name === keep)?.name ?? defs[0].name;
  return defs.find((d) => d.name === sel.value);
}
$("#scene").addEventListener("change", (e) => load(defs.find((d) => d.name === e.target.value)));
const asked = new URLSearchParams(location.search);     // ?scene=Name opens that world, &tour=1 starts the tour: a link that shows a world hands-free
if (asked.get("tour") === "1") $("#tour").checked = true;
await load(await refreshScenes(asked.get("scene")));

// ---- New world: upload photos or send a prompt, then follow the job
const dlg = $("#dlg"); let tab = "photos";
function setTab(t) { tab = t; $("#tabPhotos").setAttribute("aria-selected", t === "photos"); $("#tabPrompt").setAttribute("aria-selected", t === "prompt"); $("#panePhotos").hidden = t !== "photos"; $("#panePrompt").hidden = t !== "prompt"; $("#err").textContent = ""; }
$("#walk").addEventListener("change", setFly); setFly();
$("#tabPhotos").addEventListener("click", () => setTab("photos")); $("#tabPrompt").addEventListener("click", () => setTab("prompt"));
$("#new").addEventListener("click", () => { $("#err").textContent = ""; dlg.showModal(); });
$("#dlgCancel").addEventListener("click", () => dlg.close());
const post = async (url, body, raw) => { const r = await fetch(url, { method: "POST", body: raw ? body : JSON.stringify(body) }); const j = await r.json(); if (!r.ok) throw new Error(j.error ?? r.statusText); return j; };
$("#dlgGo").addEventListener("click", async () => {
  const name = $("#wname").value.trim(), go = $("#dlgGo"); go.disabled = true;
  try {
    if (tab === "photos") {
      const files = [...$("#files").files];
      if (files.length < 8) throw new Error("Pick at least 8 photos (20 or more works much better).");
      const id = "photos-" + Date.now().toString(36);
      for (const [i, f] of files.entries()) { $("#err").textContent = `Copying photo ${i + 1} of ${files.length}…`; await post(`/api/upload?job=${id}&name=${encodeURIComponent(f.name)}`, f, true); }
      await post("/api/jobs", { type: "photos", id, name: name || "My photos" });
    } else {
      await post("/api/jobs", { type: "prompt", name: name || "Invented world", layout: $("#layout").value, style: $("#style").value, views: +$("#views").value, setting: $("#setting").value || undefined });
    }
    dlg.close(); poll();
  } catch (e) { $("#err").textContent = e.message; }
  go.disabled = false;
});
$("#jobCancel").addEventListener("click", () => post("/api/cancel", {}));

// ---- Stitch editor: drag worlds around from above, place them side by side, save as one bigger world
const mover = new TransformControls(camera, renderer.domElement);
mover.addEventListener("dragging-changed", (e) => { orbit.enabled = !e.value; if (!e.value && E.sel) { snapFlush(E.sel); showDoors(); } });
// when a room is dropped with a wall close to another room's wall, slide it so the two walls meet exactly
function snapFlush(p) {
  if (!p.isRoom || p.open) return;
  let best = null;
  for (const q of E.parts.values()) if (q !== p && q.isRoom && !q.open) for (const a of wallsOf(p)) for (const b of wallsOf(q)) {
    const f = facing(a, b);
    if (f && Math.abs(f.gap) < 0.9 && f.hi - f.lo > DOOR.w + 0.4 && (!best || Math.abs(f.gap) < Math.abs(best.gap))) best = { gap: f.gap, n: a.n };
  }
  if (best) p.outer.position.addScaledVector(best.n, best.gap);
}
mover.addEventListener("change", () => E.on && showDoors());
const moverHelper = mover.getHelper(); moverHelper.visible = false; mover.enabled = false; scene.add(moverHelper);
function setMoverMode() {
  const rot = document.querySelector("input[name=smode]:checked").value === "rotate", snap = $("#snap").checked;
  mover.setMode(rot ? "rotate" : "translate"); mover.showX = !rot; mover.showZ = !rot; mover.showY = rot;
  mover.setTranslationSnap(snap ? 0.25 : null); mover.setRotationSnap(snap ? Math.PI / 12 : null);
}
function outline(p, colour) {
  if (p.outline) { p.outer.remove(p.outline); p.outline.geometry.dispose(); p.outline.material.dispose(); }
  const hx = p.roomW / 2, hz = p.roomD / 2, pts = [[-hx, -hz], [hx, -hz], [hx, hz], [-hx, hz]].map(([x, z]) => new THREE.Vector3(x, 0.06, z));
  p.outline = new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints(pts), new THREE.LineBasicMaterial({ color: colour, depthTest: false }));
  p.outline.renderOrder = 20; p.outer.add(p.outline);
}
function select(p) {
  E.sel = p;
  for (const q of E.parts.values()) outline(q, q === p ? 0xffd43b : 0x66d9ff);
  if (p) { mover.attach(p.outer); moverHelper.visible = true; mover.enabled = true; } else { mover.detach(); moverHelper.visible = false; mover.enabled = false; }
}
function showDoors() {
  for (const mk of E.markers) { scene.remove(mk); mk.geometry.dispose(); mk.material.dispose(); } E.markers = [];
  const doors = findDoors([...E.parts.values()]);
  for (const d of doors) {
    const mk = new THREE.Mesh(new THREE.BoxGeometry(DOOR.w, DOOR.h, d.depth + 0.5), new THREE.MeshBasicMaterial({ color: 0x51cf66, transparent: true, opacity: 0.55, depthTest: false }));
    mk.position.copy(d.centre).setY(DOOR.h / 2); mk.rotation.y = d.yaw; mk.renderOrder = 21; scene.add(mk); E.markers.push(mk);
  }
  const n = E.parts.size;
  $("#stitchHint").textContent = n < 2 ? "Tick two or more worlds, then drag them next to each other." :
    `${n} worlds, ${doors.length} doorway${doors.length === 1 ? "" : "s"}. Invented rooms get a doorway (green) where their walls touch.`;
  $("#stitchSave").disabled = n < 2;
}
async function togglePart(def, box) {
  if (!box.checked) { const p = E.parts.get(def.name); if (p) { E.parts.delete(def.name); if (E.sel === p) select(null); disposePart(p); setBlur(); } return showDoors(); }
  status(`loading ${def.name}…`);
  const seq = E.seq; let p;
  try { p = await loadPart(def); } catch (e) { console.error(e); box.checked = false; return status(`${def.name} could not be loaded`); }
  // while it loaded: the editor was closed, the box was unticked, or a second tick already added this world
  if (seq !== E.seq || !box.checked || E.parts.has(def.name)) return disposePart(p);
  buildMeshes(p);
  p.flat.visible = p.pre.visible = p.lit.visible = false; p.wire.visible = false;
  const used = [...E.parts.values()].map((q) => q.outer.position.x);
  p.outer.position.set(used.length ? Math.max(...[...E.parts.values()].map((q) => q.outer.position.x + q.roomW / 2)) + p.roomW / 2 + 1 : 0, 0, 0);
  E.parts.set(def.name, p); setBlur(); select(p); showDoors(); status("Stitch: click a world to select it, then drag the arrows. Scroll to zoom.");
}
function enterStitch() {
  loadSeq++; clearWorld(); audio.stop(); E.on = true; $("#tour").checked = false; setFly(); E.seq++; $("#bar").hidden = true; $("#stitchBar").hidden = false; $("#night").checked = false; apply(); lamp.visible = false; dragHelper.visible = false; drag.enabled = false; back.visible = false; ambient.visible = false;
  $("#stitchList").replaceChildren(...defs.filter((d) => !d.parts && d.setting !== "outdoor").map((d) => {     // outdoor worlds cannot be stitched yet
    const l = document.createElement("label"), c = document.createElement("input"); c.type = "checkbox";
    c.addEventListener("change", () => togglePart(d, c)); l.append(c, d.name); return l;
  }));
  camera.position.set(4, 26, 6); orbit.target.set(4, 0, 0); orbit.update();
  eraseBox(new THREE.Vector3(0, 52.2, 0), 0, 500, 50, 500);       // hide everything above 2.2 m so rooms are visible from above
  setMoverMode(); showDoors(); status("Stitch: tick worlds to add them.");
}
function exitStitch() {
  select(null);                              // let go of the selected part before the parts are disposed
  for (const p of E.parts.values()) disposePart(p);
  for (const mk of E.markers) { scene.remove(mk); mk.geometry.dispose(); mk.material.dispose(); }
  E.parts.clear(); E.markers = []; E.on = false; setFly(); E.seq++; clearEdits();
  $("#bar").hidden = false; $("#stitchBar").hidden = true;
}
let downAt = null;
renderer.domElement.addEventListener("pointerdown", (e) => (downAt = [e.clientX, e.clientY]));
renderer.domElement.addEventListener("pointerup", (e) => {
  if (!E.on || !downAt || mover.dragging || Math.hypot(e.clientX - downAt[0], e.clientY - downAt[1]) > 4) return;
  const r = renderer.domElement.getBoundingClientRect();
  ray.setFromCamera(new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1), camera);
  const parts = [...E.parts.values()], hit = ray.intersectObjects(parts.map((p) => p.wire), false)[0];
  if (hit) select(parts.find((p) => p.wire === hit.object));
});
document.querySelectorAll("input[name=smode]").forEach((r) => r.addEventListener("change", setMoverMode));
$("#snap").addEventListener("change", setMoverMode);
$("#stitch").addEventListener("click", enterStitch);
$("#stitchCancel").addEventListener("click", async () => { exitStitch(); await load(await refreshScenes()); });
$("#stitchSave").addEventListener("click", async () => {
  const parts = [...E.parts.entries()].map(([ref, p]) => ({ ref, x: +p.outer.position.x.toFixed(3), z: +p.outer.position.z.toFixed(3), rot: +p.outer.rotation.y.toFixed(4) }));
  try {
    const j = await post("/api/stitch", { name: $("#stitchName").value.trim() || "Stitched world", parts });
    exitStitch(); await load(await refreshScenes(j.name));
  } catch (err) { $("#stitchHint").textContent = err.message; }
});
window.E = E; E.refresh = showDoors; E.snapFlush = snapFlush;

let polling = false, announced = null, watched = false;   // watched: this page saw the job running, so its result should be opened
async function poll() {
  if (polling) return; polling = true;
  for (;;) {
    let j; try { j = await (await fetch("/api/status", { cache: "no-store" })).json(); } catch { break; }   // plain file server: no jobs
    const box = $("#job"), mins = `${Math.floor(j.elapsed / 60)}:${String(j.elapsed % 60).padStart(2, "0")}`;
    if (j.state === "running") { watched = true;
      box.style.display = "block"; $("#jobCancel").hidden = false; $("#new").disabled = true;
      $("#jobTitle").textContent = `Building “${j.name}”`; $("#jobStage").textContent = `${j.stage} · ${mins}`; $("#jobLog").textContent = (j.log ?? []).at(-1) ?? "";
    } else {
      $("#new").disabled = false; $("#jobCancel").hidden = true;
      if (j.state === "done" && announced !== j.id && !watched) announced = j.id;   // finished before this page opened: do not jump to it
      if (j.state === "done" && announced !== j.id) { announced = j.id; box.style.display = "block"; $("#jobTitle").textContent = `“${j.name}” is ready`; $("#jobStage").textContent = `took ${mins}`; $("#jobLog").textContent = ""; await load(await refreshScenes(j.name)); }
      else if (j.state === "failed") { box.style.display = "block"; $("#jobTitle").textContent = `“${j.name}” could not be built`; $("#jobStage").textContent = j.error ?? ""; $("#jobLog").textContent = ""; }
      else if (j.state === "cancelled") { box.style.display = "block"; $("#jobTitle").textContent = `“${j.name}” was cancelled`; $("#jobStage").textContent = ""; $("#jobLog").textContent = ""; }
      if (j.state !== "running") break;
    }
    await new Promise((r) => setTimeout(r, 1500));
  }
  polling = false;
}
poll();

