import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { TransformControls } from "three/addons/controls/TransformControls.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { SplatMesh, SparkRenderer, SplatEdit, SplatEditSdf, SplatEditSdfType, SplatEditRgbaBlendMode } from "@sparkjsdev/spark";
import RAPIER from "rapier";

const $ = (s) => document.querySelector(s);
const status = (t) => ($("#status").textContent = t);
const renderer = new THREE.WebGLRenderer({ antialias: false, preserveDrawingBuffer: true });
renderer.setSize(innerWidth, innerHeight);
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
document.body.appendChild(renderer.domElement);
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(65, innerWidth / innerHeight, 0.01, 100);
scene.add(new SparkRenderer({ renderer }));
const orbit = new OrbitControls(camera, renderer.domElement);
addEventListener("resize", () => { renderer.setSize(innerWidth, innerHeight); camera.aspect = innerWidth / innerHeight; camera.updateProjectionMatrix(); });

await RAPIER.init();
const gltf = new GLTFLoader();
const S = { parts: [], balls: [] }; // current world
window.S = S; window.THREE = THREE; window.camera = camera; window.orbit = orbit; window.scene = scene; window.renderer = renderer;

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

const DOOR = { w: 1.0, h: 2.1 };

// Split triangles until no edge is longer than maxEdge, so pieces of big flat walls can be removed for doorways.
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
  const [vis, col] = await Promise.all([gltf.loadAsync(def.mesh), gltf.loadAsync(def.collider)]);
  let visGeo = vis.scene.getObjectByProperty("isMesh", true).geometry, colGeo = col.scene.getObjectByProperty("isMesh", true).geometry;
  const q = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(...def.up).normalize(), new THREE.Vector3(0, 1, 0));
  const pos = colGeo.attributes.position, v = new THREE.Vector3(), xs = [], ys = [], zs = [];
  for (let i = 0; i < pos.count; i++) { v.fromBufferAttribute(pos, i).applyQuaternion(q); xs.push(v.x); ys.push(v.y); zs.push(v.z); }
  const isRoom = def.kind === "prompt" || def.flat;          // exact box room from a blockout
  const pct = (arr, f) => arr.slice().sort((a, b) => a - b)[Math.floor((arr.length - 1) * f)];
  const lo = isRoom ? 0 : 0.04, hi = isRoom ? 1 : 0.96;
  const floorY = pct(ys, lo), metre = def.metre ?? (pct(ys, hi) - floorY) / (def.heightMetres ?? 2.4);
  const cx = (pct(xs, lo) + pct(xs, hi)) / 2, cz = (pct(zs, lo) + pct(zs, hi)) / 2;
  inner.quaternion.copy(q); inner.scale.setScalar(1 / metre); inner.position.set(-cx / metre, -floorY / metre, -cz / metre);
  // footprint in metres: exact for invented rooms, estimated for photo worlds
  const roomW = isRoom ? (def.room?.[0] ?? 4) : (pct(xs, hi) - pct(xs, lo)) / metre, roomD = isRoom ? (def.room?.[2] ?? 4) : (pct(zs, hi) - pct(zs, lo)) / metre;
  if (isRoom) { visGeo = colGeo = geometryFrom(tessellate(colGeo, (roomW * roomD > 60 ? 0.5 : 0.25) * metre)); }
  else visGeo.computeVertexNormals();
  return { def, outer, inner, splat, visGeo, colGeo, isRoom, roomW, roomD, metre };
}

// Meshes for a part: flat view, collider wireframe, and the night-mode pair (depth prepass + lit pass multiplied over the splat).
function buildMeshes(p) {
  for (const k of ["flat", "wire", "pre", "lit"]) if (p[k]) p.inner.remove(p[k]);
  p.flat = new THREE.Mesh(p.visGeo, new THREE.MeshBasicMaterial({ vertexColors: true, side: THREE.DoubleSide }));
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
  const doors = [], rooms = parts.filter((p) => p.isRoom);
  for (let i = 0; i < rooms.length; i++) for (let j = i + 1; j < rooms.length; j++)
    for (const a of wallsOf(rooms[i])) for (const b of wallsOf(rooms[j])) {
      const f = facing(a, b);
      if (!f || f.gap < -0.15 || f.gap > 0.6 || f.hi - f.lo < DOOR.w + 0.4) continue;    // touching (or nearly) with room for a door
      const centre = a.c.clone().addScaledVector(a.t, (f.lo + f.hi) / 2).addScaledVector(a.n, f.gap / 2);
      doors.push({ centre, yaw: Math.atan2(a.n.x, a.n.z), depth: f.gap + 0.7 });
    }
  return doors;
}
const inDoor = (d, w) => { const l = w.clone().sub(d.centre).applyAxisAngle(new THREE.Vector3(0, 1, 0), -d.yaw); return Math.abs(l.x) < DOOR.w / 2 && l.y < DOOR.h && l.y > -0.2 && Math.abs(l.z) < d.depth / 2; };
function carve(p, doors) {
  p.outer.updateMatrixWorld(true);
  const pos = p.colGeo.attributes.position, keep = [], a = new THREE.Vector3(), b = new THREE.Vector3(), c = new THREE.Vector3(), w = new THREE.Vector3();
  for (let i = 0; i < pos.count; i += 3) {
    a.fromBufferAttribute(pos, i); b.fromBufferAttribute(pos, i + 1); c.fromBufferAttribute(pos, i + 2);
    w.copy(a).add(b).add(c).divideScalar(3).applyMatrix4(p.inner.matrixWorld);
    if (!doors.some((d) => inDoor(d, w))) keep.push(a.clone(), b.clone(), c.clone());
  }
  p.visGeo = p.colGeo = geometryFrom(keep);
}
function clearEdits() { for (const e of S.edits ?? []) scene.remove(e); S.edits = []; }
function eraseBox(centre, yaw, halfX, halfY, halfZ) {     // hide splats inside a box
  const edit = new SplatEdit({ rgbaBlendMode: SplatEditRgbaBlendMode.MULTIPLY, softEdge: 0.03 });
  const sdf = new SplatEditSdf({ type: SplatEditSdfType.BOX, opacity: 0 });
  sdf.position.copy(centre); sdf.rotation.y = yaw; sdf.scale.set(halfX, halfY, halfZ);
  edit.add(sdf); scene.add(edit); S.edits.push(edit);
}

function clearWorld() {
  for (const p of S.parts) scene.remove(p.outer);
  for (const b of S.balls) scene.remove(b.mesh);
  clearEdits(); S.parts = []; S.balls = []; S.phys = null; S.world = null; S.ready = false;
}

async function load(def) {
  if (!def) return;
  status(`loading ${def.name}…`); clearWorld();
  const specs = def.parts ? def.parts.map((s) => ({ ...s, def: defs.find((d) => d.name === s.ref) })).filter((s) => s.def) : [{ def, x: 0, z: 0, rot: 0 }];
  if (!specs.length) return status(`${def.name}: its rooms no longer exist`);
  S.parts = await Promise.all(specs.map(async (s) => { const p = await loadPart(s.def); p.outer.position.set(s.x, 0, s.z); p.outer.rotation.y = s.rot; return p; }));
  const doors = def.parts ? findDoors(S.parts) : [];
  S.doors = doors;
  const phys = new RAPIER.World({ x: 0, y: -9.8, z: 0 });
  for (const p of S.parts) {
    if (p.isRoom && doors.length) carve(p, doors);
    buildMeshes(p); p.outer.updateMatrixWorld(true);
    const g = p.colGeo.index ? p.colGeo.toNonIndexed() : p.colGeo, pos = g.attributes.position, verts = new Float32Array(pos.count * 3), v = new THREE.Vector3();
    for (let i = 0; i < pos.count; i++) v.fromBufferAttribute(pos, i).applyMatrix4(p.inner.matrixWorld).toArray(verts, i * 3);
    phys.createCollider(RAPIER.ColliderDesc.trimesh(verts, Uint32Array.from({ length: pos.count }, (_, i) => i)));
  }
  for (const d of doors) eraseBox(d.centre.clone().setY(DOOR.h / 2), d.yaw, DOOR.w / 2, DOOR.h / 2 + 0.05, d.depth / 2);
  // safety net: a flat floor just under the real one, for holes in reconstructed meshes
  phys.createCollider(RAPIER.ColliderDesc.cuboid(1000, 0.05, 1000).setTranslation(0, -0.1, 0));
  Object.assign(S, { def, world: S.parts[0].outer, phys, metre: 1, floorY: 0 });
  // start where the first part's photos were taken (or its first generated view)
  const p0 = S.parts[0], d0 = p0.def;
  const c = new THREE.Vector3(...(d0.eye ?? d0.center)).applyMatrix4(p0.inner.matrixWorld);
  const f = new THREE.Vector3(...d0.forward).applyQuaternion(p0.inner.getWorldQuaternion(new THREE.Quaternion())).normalize();
  camera.position.copy(c); camera.near = 0.02; camera.far = 200; camera.updateProjectionMatrix();
  orbit.target.copy(c).addScaledVector(f, 1.2); orbit.update();
  lamp.position.copy(c).addScaledVector(f, 0.7).add(new THREE.Vector3(0.25, 0.15, 0));
  lamp.intensity = def.lamp ?? (def.parts ? 5 : 1.6);
  await Promise.all(S.parts.map((p) => p.splat.initialized));
  apply();
  S.ready = true;
  const doorNote = def.parts ? ` | ${S.parts.length} rooms, ${doors.length} doorway${doors.length === 1 ? "" : "s"}` : "";
  status(`${def.name}: ${def.note ?? ""}${doorNote} | drag to look, scroll to move`);
  document.title = "Nate’s Worlds";
}

function apply() {
  if (!S.world) return;
  const mode = document.querySelector("input[name=mode]:checked").value, night = $("#night").checked;
  for (const p of S.parts) {
    p.splat.visible = mode === "splat"; p.flat.visible = mode === "mesh" && !night; p.wire.visible = mode === "collider";
    p.lit.material.vertexColors = mode === "mesh"; p.lit.material.blending = mode === "mesh" ? THREE.NormalBlending : THREE.CustomBlending; p.lit.material.needsUpdate = true;
    p.pre.visible = p.lit.visible = night && mode !== "collider";
  }
  ambient.visible = night; back.visible = night && mode === "splat"; lamp.visible = night; dragHelper.visible = night; drag.enabled = night;
}
document.querySelectorAll("input[name=mode]").forEach((r) => r.addEventListener("change", apply));
$("#night").addEventListener("change", apply);

const ballGeo = new THREE.SphereGeometry(1, 20, 14);
const ray = new THREE.Raycaster();
function drop(n = 25) {
  if (!S.world) return 0;
  let made = 0; const wires = S.parts.map((p) => p.wire);
  for (let tries = 0; made < n && tries < n * 8; tries++) {
    // aim at a random point in the lower middle of the view and spawn just above the surface found there
    ray.setFromCamera(new THREE.Vector2((Math.random() - 0.5) * 1.2, (Math.random() - 0.75) * 0.9), camera);
    const hit = ray.intersectObjects(wires, false)[0];
    if (!hit || hit.distance > 9) continue;
    const r = 0.035 + Math.random() * 0.025;
    const p = hit.point.clone().addScaledVector(ray.ray.direction, -0.15).add(new THREE.Vector3(0, 0.25 + Math.random() * 0.4, 0));
    const body = S.phys.createRigidBody(RAPIER.RigidBodyDesc.dynamic().setTranslation(p.x, p.y, p.z).setCcdEnabled(true).setLinearDamping(0.1).setAngularDamping(0.3));
    S.phys.createCollider(RAPIER.ColliderDesc.ball(r).setRestitution(0.5).setFriction(0.7).setDensity(1), body);
    const col = new THREE.Color().setHSL(Math.random(), 0.75, 0.55);
    const mesh = new THREE.Mesh(ballGeo, new THREE.MeshStandardMaterial({ color: col, emissive: col, emissiveIntensity: 0.55, roughness: 0.4 }));
    mesh.scale.setScalar(r); mesh.castShadow = true; scene.add(mesh); S.balls.push({ body, mesh }); made++;
  }
  return made;
}
$("#drop").addEventListener("click", () => drop());
window.drop = drop;

renderer.setAnimationLoop(() => {
  if (S.phys) {
    S.phys.step();
    for (const b of S.balls) { const t = b.body.translation(); b.mesh.position.set(t.x, t.y, t.z); }
    window.ballStats = { n: S.balls.length, onNet: S.balls.filter((b) => b.body.translation().y < -0.02).length };
  }
  orbit.update();
  back.position.copy(camera.position); back.scale.setScalar(camera.far * 0.5);
  renderer.render(scene, camera);
});

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
await load(await refreshScenes(new URLSearchParams(location.search).get("scene")));

// ---- New world: upload photos or send a prompt, then follow the job
const dlg = $("#dlg"); let tab = "photos";
function setTab(t) { tab = t; $("#tabPhotos").setAttribute("aria-selected", t === "photos"); $("#tabPrompt").setAttribute("aria-selected", t === "prompt"); $("#panePhotos").hidden = t !== "photos"; $("#panePrompt").hidden = t !== "prompt"; $("#err").textContent = ""; }
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
      await post("/api/jobs", { type: "prompt", name: name || "Invented room", layout: $("#layout").value, style: $("#style").value, views: +$("#views").value });
    }
    dlg.close(); poll();
  } catch (e) { $("#err").textContent = e.message; }
  go.disabled = false;
});
$("#jobCancel").addEventListener("click", () => post("/api/cancel", {}));

// ---- Stitch editor: drag worlds around from above, place them side by side, save as one bigger world
const E = { on: false, parts: new Map(), sel: null, markers: [] };
const mover = new TransformControls(camera, renderer.domElement);
mover.addEventListener("dragging-changed", (e) => { orbit.enabled = !e.value; if (!e.value && E.sel) { snapFlush(E.sel); showDoors(); } });
// when a room is dropped with a wall close to another room's wall, slide it so the two walls meet exactly
function snapFlush(p) {
  if (!p.isRoom) return;
  let best = null;
  for (const q of E.parts.values()) if (q !== p && q.isRoom) for (const a of wallsOf(p)) for (const b of wallsOf(q)) {
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
  if (p.outline) p.outer.remove(p.outline);
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
  for (const mk of E.markers) scene.remove(mk); E.markers = [];
  const doors = findDoors([...E.parts.values()]);
  for (const d of doors) {
    const mk = new THREE.Mesh(new THREE.BoxGeometry(DOOR.w, DOOR.h, d.depth), new THREE.MeshBasicMaterial({ color: 0x51cf66, transparent: true, opacity: 0.55, depthTest: false }));
    mk.position.copy(d.centre).setY(DOOR.h / 2); mk.rotation.y = d.yaw; mk.renderOrder = 21; scene.add(mk); E.markers.push(mk);
  }
  const n = E.parts.size;
  $("#stitchHint").textContent = n < 2 ? "Tick two or more worlds, then drag them next to each other." :
    `${n} worlds, ${doors.length} doorway${doors.length === 1 ? "" : "s"}. Invented rooms get a doorway (green) where their walls touch.`;
  $("#stitchSave").disabled = n < 2;
}
async function togglePart(def, on) {
  if (!on) { const p = E.parts.get(def.name); if (p) { scene.remove(p.outer); E.parts.delete(def.name); if (E.sel === p) select(null); } return showDoors(); }
  status(`loading ${def.name}…`);
  const p = await loadPart(def); buildMeshes(p);
  p.flat.visible = p.pre.visible = p.lit.visible = false; p.wire.visible = false;
  const used = [...E.parts.values()].map((q) => q.outer.position.x);
  p.outer.position.set(used.length ? Math.max(...[...E.parts.values()].map((q) => q.outer.position.x + q.roomW / 2)) + p.roomW / 2 + 1 : 0, 0, 0);
  E.parts.set(def.name, p); select(p); showDoors(); status("Stitch: click a world to select it, then drag the arrows. Scroll to zoom.");
}
function enterStitch() {
  clearWorld(); E.on = true; $("#bar").hidden = true; $("#stitchBar").hidden = false; $("#night").checked = false; apply(); lamp.visible = false; dragHelper.visible = false; drag.enabled = false; back.visible = false; ambient.visible = false;
  $("#stitchList").replaceChildren(...defs.filter((d) => !d.parts).map((d) => {
    const l = document.createElement("label"), c = document.createElement("input"); c.type = "checkbox";
    c.addEventListener("change", () => togglePart(d, c.checked)); l.append(c, d.name); return l;
  }));
  camera.position.set(4, 26, 6); orbit.target.set(4, 0, 0); orbit.update();
  eraseBox(new THREE.Vector3(0, 52.2, 0), 0, 500, 50, 500);       // hide everything above 2.2 m so rooms are visible from above
  setMoverMode(); showDoors(); status("Stitch: tick worlds to add them.");
}
function exitStitch() {
  for (const p of E.parts.values()) scene.remove(p.outer);
  for (const mk of E.markers) scene.remove(mk);
  E.parts.clear(); E.markers = []; E.on = false; select(null); clearEdits();
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

let polling = false, announced = null;
async function poll() {
  if (polling) return; polling = true;
  for (;;) {
    let j; try { j = await (await fetch("/api/status", { cache: "no-store" })).json(); } catch { break; }   // plain file server: no jobs
    const box = $("#job"), mins = `${Math.floor(j.elapsed / 60)}:${String(j.elapsed % 60).padStart(2, "0")}`;
    if (j.state === "running") {
      box.style.display = "block"; $("#jobCancel").hidden = false; $("#new").disabled = true;
      $("#jobTitle").textContent = `Building “${j.name}”`; $("#jobStage").textContent = `${j.stage} · ${mins}`; $("#jobLog").textContent = (j.log ?? []).at(-1) ?? "";
    } else {
      $("#new").disabled = false; $("#jobCancel").hidden = true;
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

