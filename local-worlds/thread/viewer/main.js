import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { TransformControls } from "three/addons/controls/TransformControls.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { SplatMesh, SparkRenderer } from "@sparkjsdev/spark";
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
const S = {}; // current scene state
window.S = S; window.THREE = THREE; window.camera = camera; window.orbit = orbit;

const lamp = new THREE.PointLight(0xffc27a, 1, 0, 2);
lamp.castShadow = true; lamp.shadow.mapSize.set(1024, 1024); lamp.shadow.bias = -0.002; lamp.shadow.normalBias = 0.02;
const bulb = new THREE.Mesh(new THREE.SphereGeometry(1, 16, 12), new THREE.MeshBasicMaterial({ color: 0xffe0a8 }));
lamp.add(bulb); lamp.visible = false; scene.add(lamp);
const ambient = new THREE.AmbientLight(0x6f7fb8, 0.22); ambient.visible = false; scene.add(ambient);
const drag = new TransformControls(camera, renderer.domElement);
drag.attach(lamp); drag.addEventListener("dragging-changed", (e) => (orbit.enabled = !e.value));
const dragHelper = drag.getHelper(); dragHelper.visible = false; drag.enabled = false; scene.add(dragHelper);

async function load(def) {
  if (!def) return;
  status(`loading ${def.name}…`); S.ready = false;
  if (S.world) scene.remove(S.world, S.back);
  for (const b of S.balls ?? []) scene.remove(b.mesh);
  const world = new THREE.Group();
  world.quaternion.setFromUnitVectors(new THREE.Vector3(...def.up).normalize(), new THREE.Vector3(0, 1, 0));
  scene.add(world);
  const splat = new SplatMesh({ url: def.ply });
  world.add(splat);
  const [vis, col] = await Promise.all([gltf.loadAsync(def.mesh), gltf.loadAsync(def.collider)]);
  const visGeo = vis.scene.getObjectByProperty("isMesh", true).geometry;
  const colGeo = col.scene.getObjectByProperty("isMesh", true).geometry;
  visGeo.computeVertexNormals();
  const flat = new THREE.Mesh(visGeo, new THREE.MeshBasicMaterial({ vertexColors: true, side: THREE.DoubleSide }));
  const wire = new THREE.Mesh(colGeo, new THREE.MeshBasicMaterial({ color: 0x35d0ff, wireframe: true }));
  // night mode: depth prepass, then a lit white pass multiplied over the splat (ambient + lamp, with shadows)
  const pre = new THREE.Mesh(visGeo, new THREE.MeshBasicMaterial({ colorWrite: false, transparent: true, side: THREE.DoubleSide }));
  const lit = new THREE.Mesh(visGeo, new THREE.MeshStandardMaterial({ color: 0xffffff, flatShading: !!def.flat, roughness: 1, metalness: 0, side: THREE.DoubleSide,
    shadowSide: THREE.DoubleSide, transparent: true, depthWrite: false, depthFunc: THREE.EqualDepth,
    // multiply the splat underneath by the light arriving at the surface, so splat detail survives
    blending: THREE.CustomBlending, blendEquation: THREE.AddEquation, blendSrc: THREE.DstColorFactor, blendDst: THREE.ZeroFactor }));
  pre.renderOrder = 9; lit.renderOrder = 10; lit.castShadow = true; lit.receiveShadow = true;
  // where the mesh has holes, dim the splat to ambient level so unlit patches do not glow
  const back = new THREE.Mesh(new THREE.SphereGeometry(1, 24, 16), new THREE.MeshBasicMaterial({ color: 0x1a1d2b, side: THREE.BackSide, transparent: true,
    depthWrite: false, blending: THREE.CustomBlending, blendEquation: THREE.AddEquation, blendSrc: THREE.DstColorFactor, blendDst: THREE.ZeroFactor }));
  back.renderOrder = 9.5; back.frustumCulled = false; S.back = back; scene.add(back);
  world.add(flat, wire, pre, lit);
  world.updateMatrixWorld(true);
  // physics from the collider mesh, in world space
  const pos = colGeo.attributes.position, v = new THREE.Vector3(), verts = new Float32Array(pos.count * 3);
  const box = new THREE.Box3();
  for (let i = 0; i < pos.count; i++) { v.fromBufferAttribute(pos, i).applyMatrix4(world.matrixWorld); v.toArray(verts, i * 3); box.expandByPoint(v); }
  // robust room height: ignore stray geometry above the ceiling and below the floor
  const ys = Array.from({ length: pos.count }, (_, i) => verts[i * 3 + 1]).sort((a, b) => a - b);
  const floorY = ys[Math.floor(ys.length * 0.04)], ceilY = ys[Math.floor(ys.length * 0.96)];
  const metre = def.metre ?? (ceilY - floorY) / (def.heightMetres ?? 2.4);
  const phys = new RAPIER.World({ x: 0, y: -9.8 * metre, z: 0 });
  phys.createCollider(RAPIER.ColliderDesc.trimesh(verts, new Uint32Array(colGeo.index.array)));
  // safety net: a flat floor just under the reconstructed one, for holes in the mesh
  phys.createCollider(RAPIER.ColliderDesc.cuboid(1000, 0.05 * metre, 1000).setTranslation(0, floorY - 0.1 * metre, 0));
  Object.assign(S, { def, world, splat, flat, wire, pre, lit, phys, metre, balls: [], box, floorY });
  // start where the photos were taken, looking the way the first camera looked
  const c = new THREE.Vector3(...(def.eye ?? def.center)).applyMatrix4(world.matrixWorld);
  const f = new THREE.Vector3(...def.forward).applyQuaternion(world.quaternion).normalize();
  camera.position.copy(c); camera.near = 0.02 * metre; camera.far = 200 * metre; camera.updateProjectionMatrix();
  orbit.target.copy(c).addScaledVector(f, 1.2 * metre); orbit.update();
  lamp.position.copy(c).addScaledVector(f, 0.7 * metre).add(new THREE.Vector3(0.25 * metre, 0.15 * metre, 0));
  lamp.intensity = (def.lamp ?? 1.6) * metre * metre; lamp.shadow.normalBias = 0.06 * metre; lamp.shadow.bias = -0.004; lamp.shadow.radius = 4; lamp.shadow.camera.near = 0.05 * metre; lamp.shadow.camera.far = 12 * metre;
  bulb.scale.setScalar(0.04 * metre); drag.setSize(0.6);
  await splat.initialized;
  apply();
  S.ready = true;
  status(`${def.name}: ${def.note ?? ""} | drag to look, scroll to move`);
  document.title = "Nate\u2019s Worlds";
}

function apply() {
  if (!S.world) return;
  const mode = document.querySelector("input[name=mode]:checked").value, night = $("#night").checked;
  S.splat.visible = mode === "splat"; S.flat.visible = mode === "mesh"; S.wire.visible = mode === "collider";
  S.lit.material.vertexColors = mode === "mesh"; S.lit.material.needsUpdate = true; ambient.visible = night;
  S.flat.visible = mode === "mesh" && !night; S.lit.material.blending = mode === "mesh" ? THREE.NormalBlending : THREE.CustomBlending;
  S.pre.visible = S.lit.visible = night && mode !== "collider";
  S.back.visible = night && mode === "splat"; lamp.visible = night; dragHelper.visible = night; drag.enabled = night;
}
document.querySelectorAll("input[name=mode]").forEach((r) => r.addEventListener("change", apply));
$("#night").addEventListener("change", apply);

const ballGeo = new THREE.SphereGeometry(1, 20, 14);
const ray = new THREE.Raycaster();
function drop(n = 25) {
  if (!S.world) return 0;
  const m = S.metre; let made = 0;
  for (let tries = 0; made < n && tries < n * 8; tries++) {
    // aim at a random point in the lower middle of the view and spawn just above the surface found there
    ray.setFromCamera(new THREE.Vector2((Math.random() - 0.5) * 1.2, (Math.random() - 0.75) * 0.9), camera);
    const wasVisible = S.wire.visible; S.wire.visible = true;
    const hit = ray.intersectObject(S.wire, false)[0]; S.wire.visible = wasVisible;
    if (!hit || hit.distance > 4 * m) continue;
    const r = (0.035 + Math.random() * 0.025) * m;
    const p = hit.point.clone().addScaledVector(ray.ray.direction, -0.15 * m).add(new THREE.Vector3(0, (0.25 + Math.random() * 0.4) * m, 0));
    const body = S.phys.createRigidBody(RAPIER.RigidBodyDesc.dynamic().setTranslation(p.x, p.y, p.z).setCcdEnabled(true).setLinearDamping(0.1).setAngularDamping(0.3));
    S.phys.createCollider(RAPIER.ColliderDesc.ball(r).setRestitution(0.5).setFriction(0.7).setDensity(1), body);
    const col = new THREE.Color().setHSL(Math.random(), 0.75, 0.55);
    const mesh = new THREE.Mesh(ballGeo, new THREE.MeshStandardMaterial({ color: col, emissive: col, emissiveIntensity: 0.55, roughness: 0.4 }));
    mesh.scale.setScalar(r); mesh.castShadow = true; scene.add(mesh); S.balls.push({ body, mesh, spawnY: p.y }); made++;
  }
  return made;
}
$("#drop").addEventListener("click", () => drop());
window.drop = drop;

renderer.setAnimationLoop(() => {
  if (S.phys) {
    S.phys.step();
    for (const b of S.balls) { const t = b.body.translation(); b.mesh.position.set(t.x, t.y, t.z); }
    window.ballStats = { n: S.balls.length, onNet: S.balls.filter((b) => b.body.translation().y < S.floorY).length };
  }
  orbit.update();
  if (S.back) { S.back.position.copy(camera.position); S.back.scale.setScalar(camera.far * 0.5); }
  renderer.render(scene, camera);
});

let defs = [];
async function refreshScenes(select) {
  defs = await (await fetch("/scenes.json", { cache: "no-store" })).json();
  const sel = $("#scene"), keep = select ?? sel.value;
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

