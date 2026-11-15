// motion.js: things that move in a world. Three kinds, all driven by one time value T (seconds) so any moment can be shown again:
//   skin    sway: splats of the room itself bend about the base of their box, or of their stretch of a long box (SplatSkinning, decided once per splat)
//   splat   swing, spin, bob, path: a piece split out of the room as its own splat, with its own mesh and a kinematic collider
//   effects wander, drift: small blobs made on the GPU from an index and T, no data
// Every part degrades: a mover or effect that cannot be set up is skipped with a console warning and the world stays as it was.
import * as THREE from "three";
import { SplatMesh, SplatSkinning, SplatGenerator, SplatTransformer, dyno } from "@sparkjsdev/spark";

const TAU = Math.PI * 2, UP = new THREE.Vector3(0, 1, 0), Q0 = new THREE.Quaternion(), V0 = new THREE.Vector3();
const clamp = (x, a, b) => Math.min(b, Math.max(a, x));
const num = (v, d) => (v != null && Number.isFinite(+v) ? +v : d);
const mod = (a, n) => ((a % n) + n) % n;
const LIFTED = new Set(["swing", "spin", "bob", "path"]);
const SOUNDS = new Set(["rustle", "buzz", "rumble", "creak", "chirp"]);
const DEFAULT_SOUND = { sway: "rustle", swing: "creak", path: "rumble", wander: "buzz" };
const soundOf = (m) => (SOUNDS.has(m.sound) ? m.sound : m.sound == null ? DEFAULT_SOUND[m.type] : null);
const okBox = (b) => b && Array.isArray(b.c) && Array.isArray(b.h) && [...b.c, ...b.h].length === 6 && [...b.c, ...b.h].every(Number.isFinite);
const warn = (what, e) => console.warn(`motion: ${what} skipped:`, e?.message ?? e);

// Room metres -> the part's `outer` frame (metres, floor at y = 0, centred). The only place that knows the room is mirrored in z.
export function roomToOuter(p) {
  const f = p.def.fromRoom; p.inner.updateMatrix();
  if (Array.isArray(f) && f.length === 16 && f.every(Number.isFinite)) return p.inner.matrix.clone().multiply(new THREE.Matrix4().set(...f));
  return new THREE.Matrix4().set(1, 0, 0, -p.roomW / 2, 0, 1, 0, 0, 0, 0, -1, p.roomD / 2, 0, 0, 0, 1);   // entries without fromRoom
}
// A rotation given in one frame, as the same rotation seen through `mat` (which may scale and mirror; flip is the sign of its determinant).
const qv = new THREE.Vector3();
function toFrame(q, mat, flip) {
  const s = qv.set(q.x, q.y, q.z).length(); if (s < 1e-9) return q.identity();
  qv.transformDirection(mat).multiplyScalar(s * flip); return q.set(qv.x, qv.y, qv.z, q.w);
}
// A box's own width and depth directions in room axes (the same convention as the layout: depth is (sin yaw, cos yaw)).
const boxAxis = (yaw, which) => (which === "width" ? new THREE.Vector3(Math.cos(yaw), 0, -Math.sin(yaw)) : new THREE.Vector3(Math.sin(yaw), 0, Math.cos(yaw)));

// ---- sway: skinning inside the room splat ---------------------------------------------------------------------------
function setupSkin(p, M, list) {
  const src = p.splat.packedSplats ?? p.splat.splats, n = src?.numSplats ?? src?.getNumSplats?.() ?? 0;
  if (!n || typeof src.forEachSplat !== "function") throw new Error("the splat has no data to read");
  list = list.slice(0, 85);                                    // three bones per pivot, 256 at most
  let spare = 85 - list.length, bones = 1;
  const toRoom = M.R.clone().invert().multiply(p.inner.matrix), toFile = toRoom.clone().invert();
  const boxes = list.map((m, k) => {
    const b = m.box, yaw = num(b.yaw, 0), stiff = clamp(num(m.stiff, 0.35), 0, 0.8), H = 2 * b.h[1];
    // a box much longer than it is tall would tip like a seesaw about one point, so it gets a row of pivots along its length and each splat blends the two nearest
    const long = b.h[0] >= b.h[2] ? 0 : 1, hl = b.h[long ? 2 : 0], cs = clamp(H, 1, 3), nc = 1 + Math.min(spare, 2 * hl > 1.5 * cs ? Math.ceil(2 * hl / cs) : 0), cw = 2 * hl / Math.max(1, nc - 1);
    spare -= nc - 1;
    const along = boxAxis(yaw, long ? "depth" : "width"), reach = Math.hypot(nc > 1 ? cw / 2 : hl, b.h[long ? 0 : 2]);     // how far a splat can be from its pivot, sideways
    const cells = Array.from({ length: nc }, (_, j) => ({ bone: bones + 3 * j, base: new THREE.Vector3(b.c[0], b.c[1] - b.h[1], b.c[2]).addScaledVector(along, nc > 1 ? j * cw - hl : 0).applyMatrix4(toFile) }));
    bones += 3 * nc;
    return { m, cells, long, hl, cw, cx: b.c[0], cy: b.c[1], cz: b.c[2], hu: b.h[0] + 0.08, hy: b.h[1] + 0.08, hv: b.h[2] + 0.08, cos: Math.cos(yaw), sin: Math.sin(yaw),
      y0: b.c[1] - b.h[1], H: Math.max(H, 0.05), stiff, amount: clamp(num(m.amount, 0.6), 0, 1), phase: num(m.phase, 0), n: 0,
      size: clamp(Math.sqrt(2.5 / Math.max(H, 0.1)), 0.7, 2) * Math.min(1, Math.max(H, 0.05) / reach) };       // the full turn only where the pivot is nearer than the thing is tall
  });
  const sk = new SplatSkinning({ mesh: p.splat, numSplats: n, numBones: bones });
  for (let b = 0; b < sk.numBones; b++) sk.setRestQuatPos(b, Q0, V0);
  for (let i = 0; i < n; i++) sk.skinData[i * 4] = 255;        // every splat fully on bone 0, which never moves (all-zero weights would divide by zero)
  const room = p.def.room, walls = !p.open && Array.isArray(room) && room.length === 3, v = new THREE.Vector3(), bi = new THREE.Vector4(), wt = new THREE.Vector4();
  let moved = 0;
  src.forEachSplat((i, centre) => {
    v.copy(centre).applyMatrix4(toRoom);
    if (!(v.y > 0.03)) return;                                 // the ground stays
    if (walls && (v.x < 0.04 || v.x > room[0] - 0.04 || v.z < 0.04 || v.z > room[2] - 0.04 || v.y > room[1] - 0.04)) return;   // so do walls and ceiling
    let best = null, bd = 1, s = 0;
    for (const b of boxes) {
      const dx = v.x - b.cx, dz = v.z - b.cz, lu = dx * b.cos - dz * b.sin, lv = dx * b.sin + dz * b.cos, d = Math.max(Math.abs(lu) / b.hu, Math.abs(v.y - b.cy) / b.hy, Math.abs(lv) / b.hv);
      if (d <= bd) { bd = d; best = b; s = b.long ? lv : lu; }
    }
    if (!best) return;
    const k = clamp(((v.y - best.y0) / best.H - best.stiff) / (1 - best.stiff), 0, 1) ** 1.5;   // nothing below `stiff`, more towards the top
    if (k < 1 / 255) return;
    // two clumps, by which 25 cm cell the splat is in, flutter on their own on top of the lean
    const cell = Math.imul(Math.floor(v.x * 4), 73856093) ^ Math.imul(Math.floor(v.y * 4), 19349663) ^ Math.imul(Math.floor(v.z * 4), 83492791), f = 0.5 * k;
    const C = best.cells, q = clamp((s + best.hl) / best.cw, 0, C.length - 1), a = Math.min(Math.floor(q), Math.max(0, C.length - 2)), t = q - a;   // between pivots a and a + 1
    bi.set(0, C[a].bone, C[Math.round(q)].bone + 1 + ((cell >>> 7) & 1), C[Math.min(a + 1, C.length - 1)].bone); wt.set(1 - k, k * (1 - f) * (1 - t), k * f, k * (1 - f) * t);
    sk.setSplatBones(i, bi, wt); best.n++; moved++;
  });
  sk.skinTexture.needsUpdate = true;
  p.splat.skinning = sk; p.splat.updateGenerator();
  M.skin = { sk, boxes, toFile, flip: Math.sign(toFile.determinant()) || 1 };
  M.stats.sway = boxes.length; M.stats.skinned = moved;
  for (const b of boxes) {
    if (!b.n) warn(`sway on "${b.m.name ?? b.m.i}"`, "no splats inside its box");
    const kind = soundOf(b.m); if (!kind || !b.n) continue;
    const ear = new THREE.Object3D(); ear.position.set(b.cx, b.cy + (b.hy - 0.08) / 2, b.cz).applyMatrix4(M.R); p.outer.add(ear); M.extras.push(ear);
    M.sounds.push({ obj: ear, kind, type: "sway", size: b.hu * b.hy * b.hv });
  }
}
const qa = new THREE.Quaternion(), qb = new THREE.Quaternion(), qc = new THREE.Quaternion(), ax = new THREE.Vector3(), tv = new THREE.Vector3();
function setBone(S, b, k, q) {                 // q turns about each pivot's base point, in room axes
  toFrame(q, S.toFile, S.flip);
  for (const c of b.cells) S.sk.setBoneQuatPos(c.bone + k, q, tv.copy(c.base).applyQuaternion(q).negate().add(c.base));   // a bone turns about the file origin, so shift by c - R·c
}
function stepSkin(M, T, w) {
  const S = M.skin;
  for (const b of S.boxes) {
    const ph = TAU * b.phase, A = b.amount * b.size;
    const lean = A * (0.07 * w + 0.045 * w * Math.sin(TAU * 0.31 * T + ph) + 0.006 * Math.sin(TAU * 0.17 * T + 3 * ph));
    for (let j = 0; j < 2; j++) {
      ax.copy(M.leanAxis).applyAxisAngle(UP, j ? -1.1 : 1.1);
      qb.setFromAxisAngle(ax, A * (0.02 + 0.08 * w) * Math.sin(TAU * (j ? 1.31 : 0.83) * T + ph + 2.3 * j));
      qc.setFromAxisAngle(UP, A * (0.015 + 0.06 * w) * Math.sin(TAU * 0.57 * T + 2 * ph + 3.1 * j));
      setBone(S, b, 1 + j, qb.premultiply(qc).multiply(qa.setFromAxisAngle(M.leanAxis, lean)));   // twist, flutter, lean
    }
    setBone(S, b, 0, qa.setFromAxisAngle(M.leanAxis, lean));
  }
  S.sk.updateBones();                          // also tells Spark the splat changed
}

// ---- lifted movers: own splat, own mesh, kinematic body --------------------------------------------------------------
function geoOf(g) { return g?.scene.getObjectByProperty("isMesh", true)?.geometry ?? null; }
async function setupLift(p, M, m, ctx) {
  if (!okBox(m.box)) throw new Error("no box");
  if (!m.ply) throw new Error("no splat file");
  if (!(Array.isArray(m.fromRoom) && m.fromRoom.length === 16 && m.fromRoom.every(Number.isFinite))) throw new Error("no fromRoom");
  const b = m.box, yaw = num(b.yaw, 0), c = new THREE.Vector3(...b.c);
  const piv = m.type === "path" ? new THREE.Vector3(c.x, 0, c.z)
    : Array.isArray(m.pivot) && m.pivot.length === 3 && m.pivot.every(Number.isFinite) ? new THREE.Vector3(...m.pivot)
    : m.type === "swing" && Number.isFinite(m.pivot) ? new THREE.Vector3(c.x, m.pivot, c.z) : c.clone();
  const rest = piv.clone().applyMatrix4(M.R), mid = c.clone().applyMatrix4(M.R).sub(rest);          // mid: the box centre seen from the pivot
  const dir = (v) => v.transformDirection(M.R);
  const grp = new THREE.Group(), fix = new THREE.Group();
  grp.position.copy(rest); fix.matrixAutoUpdate = false;
  fix.matrix.makeTranslation(-rest.x, -rest.y, -rest.z).multiply(M.R).multiply(new THREE.Matrix4().set(...m.fromRoom).invert()); fix.matrixWorldNeedsUpdate = true;
  const splat = new SplatMesh({ url: m.ply, editable: false });       // not editable: doorway erasers leave it alone
  fix.add(splat); grp.add(fix); grp.visible = false; p.outer.add(grp);
  const L = { m, grp, fix, splat, rest, geos: [], mats: [], gone: false, op: 1, lastT: null };
  const toss = () => { p.outer.remove(grp); splat.dispose(); for (const g of L.geos) g.dispose(); for (const x of L.mats) x.dispose(); };
  const [sp, vis, col] = await Promise.allSettled([splat.initialized, m.mesh ? ctx.gltf.loadAsync(m.mesh) : null, m.collider ? ctx.gltf.loadAsync(m.collider) : null]);
  const visGeo = vis.status === "fulfilled" ? geoOf(vis.value) : null, colGeo = (col.status === "fulfilled" ? geoOf(col.value) : null) ?? visGeo;
  for (const g of new Set([visGeo, colGeo])) if (g) L.geos.push(g);
  if (M.dead) return toss();
  if (sp.status === "rejected") { toss(); throw sp.reason ?? new Error("its splat could not be loaded"); }
  if (!visGeo) warn(`the mesh of "${m.name ?? m.i}"`, vis.reason ?? "no mesh in the file");

  // meshes, like a part's own: flat view, collider wireframe, night pair
  if (visGeo) {
    if (!visGeo.attributes.color) visGeo.setAttribute("color", new THREE.BufferAttribute(new Float32Array(visGeo.attributes.position.count * 3).fill(0.62), 3));
    L.flat = new THREE.Mesh(visGeo, new THREE.MeshNormalMaterial({ flatShading: true, side: THREE.DoubleSide }));
    L.pre = new THREE.Mesh(visGeo, new THREE.MeshBasicMaterial({ colorWrite: false, transparent: true, side: THREE.DoubleSide }));
    L.lit = new THREE.Mesh(visGeo, new THREE.MeshStandardMaterial({ color: 0xffffff, flatShading: true, roughness: 1, metalness: 0, side: THREE.DoubleSide,
      shadowSide: THREE.DoubleSide, transparent: true, depthWrite: false, depthFunc: THREE.EqualDepth,
      blending: THREE.CustomBlending, blendEquation: THREE.AddEquation, blendSrc: THREE.DstColorFactor, blendDst: THREE.ZeroFactor }));
    L.pre.renderOrder = 9; L.lit.renderOrder = 10; L.lit.castShadow = true; L.lit.receiveShadow = true;
    fix.add(L.flat, L.pre, L.lit); L.mats.push(L.flat.material, L.pre.material, L.lit.material);
  }
  if (colGeo) { L.wire = new THREE.Mesh(colGeo, new THREE.MeshBasicMaterial({ color: 0xffb035, wireframe: true })); fix.add(L.wire); L.mats.push(L.wire.material); }
  L.ear = new THREE.Object3D(); L.ear.position.copy(mid); grp.add(L.ear);                           // where its sound comes from

  // how it moves
  const flip = M.flip;
  if (m.type === "swing") {
    const along = m.axis === "width" ? "width" : "depth", turn = along === "width" ? "depth" : "width";   // swings along one of its directions, so turns about the other
    L.axis = dir(boxAxis(yaw, turn)); L.angle = THREE.MathUtils.degToRad(clamp(num(m.angle, 20), 1, 45)) * flip;
    L.period = clamp(num(m.period, TAU * Math.sqrt(Math.max(0.2, piv.y - c.y) / 9.8)), 0.5, 20);
    const top = mid.clone(); top.y += b.h[1];
    if (-top.y > 0.3) {                      // hangs well below its pivot: two thin lines from the pivot line down to the piece
      const half = (turn === "width" ? b.h[0] : b.h[2]) * 0.8, mat = new THREE.MeshBasicMaterial({ color: 0x2b2622 }); L.mats.push(mat); L.ropes = [];
      for (const s of [-1, 1]) {
        const a = L.axis.clone().multiplyScalar(s * half), e = top.clone().add(a), len = e.distanceTo(a), geo = new THREE.CylinderGeometry(0.012, 0.012, len, 6);
        const rope = new THREE.Mesh(geo, mat); rope.position.copy(a).lerp(e, 0.5); rope.quaternion.setFromUnitVectors(UP, e.clone().sub(a).normalize());
        grp.add(rope); L.ropes.push(rope); L.geos.push(geo);
      }
    }
  } else if (m.type === "spin") {
    L.axis = m.axis === "width" || m.axis === "depth" ? dir(boxAxis(yaw, m.axis)) : UP.clone(); L.period = clamp(num(m.period, 8), 0.5, 120) * flip;
  } else if (m.type === "bob") {
    L.height = clamp(num(m.height, 0.1), 0, 0.5); L.period = clamp(num(m.period, 3), 0.5, 20);
  } else if (m.type === "path") {
    const pts = (Array.isArray(m.points) ? m.points : []).filter((q) => Array.isArray(q) && Number.isFinite(q[0]) && Number.isFinite(q[1])).slice(0, 8)
      .map((q) => new THREE.Vector3(q[0], 0, q[1]).applyMatrix4(M.R));
    const curve = pts.length > 1 ? new THREE.CatmullRomCurve3(pts, false, "centripetal") : null, len = curve ? curve.getLength() : 0;
    if (len > 0.5) {                         // by arc length, so the speed is even
      const h0 = pts[1].clone().sub(pts[0]).setY(0).normalize();                                     // the piece was placed facing along the first stretch
      L.path = { curve, len, from: pts[0], yaw0: Math.atan2(h0.x, h0.z), t0: curve.getTangentAt(0), t1: curve.getTangentAt(1), end: curve.getPointAt(1),
        speed: clamp(num(m.speed, 3), 0.05, 20), pause: clamp(num(m.pause, 0), 0, 60), loop: m.mode === "loop" && !!p.open };
      // the strip it travels, for whoever wants to keep out of its way: points along it, and how far it reaches to each side
      const P = L.path, side = h0.clone().cross(UP);
      L.lane = { pts: curve.getSpacedPoints(Math.ceil(len / 0.3)), r: Math.abs(dir(boxAxis(yaw, "width")).dot(side)) * b.h[0] + Math.abs(dir(boxAxis(yaw, "depth")).dot(side)) * b.h[2] + 0.7 };
      if (P.loop) for (let s = 0.3; s <= 12; s += 0.3) L.lane.pts.push(P.from.clone().addScaledVector(P.t0, -s), P.end.clone().addScaledVector(P.t1, s));
    } else warn(`the path of "${m.name ?? m.i}"`, "too short; it stays where it is");
  }

  L.lane ??= { pts: [rest.clone().add(mid)], r: Math.hypot(b.h[0], b.h[2]) + (m.type === "swing" ? Math.sin(Math.abs(L.angle)) * Math.max(0, piv.y - c.y + b.h[1]) : 0) + 0.5 };
  // collider: the piece's hull (a box of its bounds if that fails), carried by a body the motion places each step
  const src = colGeo?.attributes.position, pts = src ? new Float32Array(src.count * 3) : null;
  if (pts) for (let i = 0; i < src.count; i++) tv.fromBufferAttribute(src, i).applyMatrix4(fix.matrix).toArray(pts, i * 3);
  const R = ctx.RAPIER, depth = dir(boxAxis(yaw, "depth"));
  const desc = (pts && R.ColliderDesc.convexHull(pts)) ?? R.ColliderDesc.cuboid(b.h[0], b.h[1], b.h[2]).setTranslation(mid.x, mid.y, mid.z).setRotation(new THREE.Quaternion().setFromAxisAngle(UP, Math.atan2(depth.x, depth.z)));
  pose(L, M.T); p.outer.updateMatrixWorld(true); grp.matrixWorld.decompose(wp, wq, ws);
  L.body = ctx.phys.createRigidBody(R.RigidBodyDesc.kinematicPositionBased().setTranslation(wp.x, wp.y, wp.z).setRotation(wq));
  L.col = ctx.phys.createCollider(desc.setFriction(0.7).setRestitution(0.2), L.body);
  L.lastT = M.T; grp.visible = true;
  M.lifts.push(L); M.stats.lifted = M.lifts.length; show(M, L);
  const kind = soundOf(m); if (kind) M.sounds.push({ obj: L.ear, kind, type: m.type, size: b.h[0] * b.h[1] * b.h[2] });
}
const wp = new THREE.Vector3(), wq = new THREE.Quaternion(), ws = new THREE.Vector3(), pp = new THREE.Vector3(), pt = new THREE.Vector3();
// Place a lifted mover for time T. A pure function of T, so any moment can be shown again.
function pose(L, T) {
  const m = L.m, g = L.grp, ph = num(m.phase, 0); let op = 1;
  if (m.type === "swing") g.quaternion.setFromAxisAngle(L.axis, L.angle * Math.sin(TAU * (T / L.period + ph)));
  else if (m.type === "spin") g.quaternion.setFromAxisAngle(L.axis, TAU * mod(T / L.period + ph, 1));
  else if (m.type === "bob") g.position.copy(L.rest).y += L.height * Math.sin(TAU * (T / L.period + ph));
  else if (L.path) {
    const P = L.path, c = P.curve;
    if (P.loop) {                            // comes in from 12 m before the first point, leaves 12 m past the last, waits, starts again
      const ext = 12, run = (P.len + 2 * ext) / P.speed, cyc = run + P.pause, u = mod(T + ph * cyc, cyc), d = Math.min(u, run) * P.speed - ext;
      const fade = clamp(1.2 * P.speed, 3, 8);                 // fades in and out over 1.2 s (3 to 8 m), slowly at first and at last, so it never pops
      op = u >= run ? 0 : smooth(0, fade, d + ext) * smooth(0, fade, P.len + ext - d);
      if (d < 0) { pp.copy(P.from).addScaledVector(P.t0, d); pt.copy(P.t0); }
      else if (d > P.len) { pp.copy(P.end).addScaledVector(P.t1, d - P.len); pt.copy(P.t1); }
      else { c.getPointAt(d / P.len, pp); c.getTangentAt(d / P.len, pt); }
    } else {                                 // there and back, easing at both ends and keeping its facing
      const tt = P.len * Math.PI / (2 * P.speed), cyc = 2 * (tt + P.pause), u = mod(T + ph * cyc, cyc);
      const f = u < tt ? u / tt : u < tt + P.pause ? 1 : u < 2 * tt + P.pause ? 1 - (u - tt - P.pause) / tt : 0, s = clamp((1 - Math.cos(Math.PI * f)) / 2, 0, 1);
      c.getPointAt(s, pp); c.getTangentAt(s, pt);
    }
    g.position.copy(pp);                     // its own centre rides on the route, on the room's ground (the group's origin is the middle of its box, at ground level)
    g.quaternion.setFromAxisAngle(UP, Math.atan2(pt.x, pt.z) - P.yaw0);      // heading only: it never pitches or rolls
  }
  L.op = op;
}
function show(M, L) {
  const mode = M.mode ?? "splat", night = !!M.night, here = L.op > 0.5;      // a faded-out piece is neither lit nor solid
  L.gone = !here;
  L.splat.opacity = L.op; L.splat.visible = mode === "splat" && L.op > 0.01;
  if (L.flat) {
    L.flat.visible = mode === "mesh" && !night && here; L.pre.visible = L.lit.visible = night && mode !== "collider" && here;
    const mat = L.lit.material, vc = mode === "mesh", bl = vc ? THREE.NormalBlending : THREE.CustomBlending;
    if (mat.vertexColors !== vc || mat.blending !== bl) { mat.vertexColors = vc; mat.blending = bl; mat.needsUpdate = true; }
  }
  if (L.wire) L.wire.visible = mode === "collider" && here;
  for (const r of L.ropes ?? []) r.visible = mode !== "collider" && here;
}
function stepLift(p, M, L, T) {
  const was = L.gone, jump = L.lastT == null || Math.abs(T - L.lastT) > 0.25; L.lastT = T;
  pose(L, T); show(M, L);
  if (!L.body) return;
  L.grp.updateWorldMatrix(true, false); L.grp.matrixWorld.decompose(wp, wq, ws);
  // a jump in time (or coming back from hidden) is not a push: place the body there outright
  if (jump || was) { L.body.setTranslation(wp, true); L.body.setRotation(wq, true); }
  L.body.setNextKinematicTranslation(wp); L.body.setNextKinematicRotation(wq);
  if (was !== L.gone) L.col.setEnabled(!L.gone);
}

// ---- effects: small blobs from an index and the time ------------------------------------------------------------------
// The same arithmetic in GLSL and in JS (integers, so they agree exactly): random number k of blob i, in 0..1.
// lsWander and lsDrift say where blob i is at time t; the blobs and their night glow both use them.
const FX_GLSL = `
float lsRand(int i, int k) {
  uint x = uint(i) * 747796405u + uint(k) * 2891336453u + 12345u;
  x ^= x >> 16u; x *= 2246822519u; x ^= x >> 13u; x *= 3266489917u; x ^= x >> 16u;
  return float(x >> 8u) / 16777216.0;
}
vec4 lsQmul(vec4 a, vec4 b) { return vec4(a.w * b.xyz + b.w * a.xyz + cross(a.xyz, b.xyz), a.w * b.w - dot(a.xyz, b.xyz)); }
vec3 lsWander(int i, float t, vec3 at, vec3 ext, vec3 par) {
  float r1 = lsRand(i, 1), r2 = lsRand(i, 2), r3 = lsRand(i, 3), r4 = lsRand(i, 4), r5 = lsRand(i, 5), r6 = lsRand(i, 6);
  float om = par.x / ext.x * (0.6 + 0.8 * r1), k = 6.2831853;
  return at + vec3(ext.x, ext.y, ext.x) * vec3(
    0.55 * sin(om * t + k * r2) + 0.30 * sin(om * 1.7 * t + k * r3) + 0.15 * sin(om * 3.1 * t + k * r4),
    0.5 + 0.5 * (0.60 * sin(om * 0.8 * t + k * r5) + 0.40 * sin(om * 2.3 * t + k * r6)),
    0.55 * sin(om * 1.13 * t + k * r4) + 0.30 * sin(om * 1.9 * t + k * r5) + 0.15 * sin(om * 2.7 * t + k * r2));
}
vec3 lsDrift(int i, float t, vec3 at, vec3 ext, vec3 par, vec3 wind, float rise, out float ph) {
  float r1 = lsRand(i, 1), r2 = lsRand(i, 2), r3 = lsRand(i, 3), r4 = lsRand(i, 4), r5 = lsRand(i, 5), r6 = lsRand(i, 6), k = 6.2831853;
  float per = ext.y / (par.y * (0.7 + 0.6 * r1)), an = k * r3, rr = ext.x * sqrt(r4), wob = 0.25 * min(1.0, ext.x);
  ph = fract(t / per + r2);
  vec3 c = at + vec3(rr * cos(an), ext.y * mix(1.0 - ph, ph, rise), rr * sin(an));
  c.x += wind.x * (ph - 0.5) + wob * sin(1.3 * t * (0.6 + r5) + k * r6);
  c.z += wind.z * (ph - 0.5) + wob * cos(1.1 * t * (0.6 + r6) + k * r5);
  return c;
}
vec3 lsColour(int i, float n, vec3 c1, vec3 c2, vec3 c3) {
  int ci = int(floor(lsRand(i, 7) * n));
  return (ci == 0 ? c1 : (ci == 1 ? c2 : c3)) * (0.85 + 0.3 * lsRand(i, 8));
}
// how bright a glowing blob is just now, 0..1: a slow pulse of its own; 1 when nothing glows
float lsPulse(int i, float t, float glow) { return mix(1.0, 0.62 + 0.38 * sin(t * (1.2 + 1.6 * lsRand(i, 9)) + 6.2831853 * lsRand(i, 8)), glow); }`;
function rand(i, k) {
  let x = (Math.imul(i, 747796405) + Math.imul(k, 2891336453) + 12345) | 0;
  x ^= x >>> 16; x = Math.imul(x, 2246822519); x ^= x >>> 13; x = Math.imul(x, 3266489917); x ^= x >>> 16;
  return (x >>> 8) / 16777216;
}
const fract = (x) => x - Math.floor(x), smooth = (a, b, x) => { const t = clamp((x - a) / (b - a), 0, 1); return t * t * (3 - 2 * t); };
// Where blob i is at time t, in the part's outer frame. Must match lsWander and lsDrift above line for line.
function fxPos(F, i, t, out) {
  const r = (k) => rand(i + F.seed, k);
  if (F.type === "wander") {
    const om = F.speed / F.radius * (0.6 + 0.8 * r(1)), a = (k) => TAU * r(k);
    return out.set(
      F.at.x + F.radius * (0.55 * Math.sin(om * t + a(2)) + 0.30 * Math.sin(om * 1.7 * t + a(3)) + 0.15 * Math.sin(om * 3.1 * t + a(4))),
      F.at.y + F.H * (0.5 + 0.5 * (0.60 * Math.sin(om * 0.8 * t + a(5)) + 0.40 * Math.sin(om * 2.3 * t + a(6)))),
      F.at.z + F.radius * (0.55 * Math.sin(om * 1.13 * t + a(4)) + 0.30 * Math.sin(om * 1.9 * t + a(5)) + 0.15 * Math.sin(om * 2.7 * t + a(2))));
  }
  const per = F.H / (F.fall * (0.7 + 0.6 * r(1))), ph = fract(t / per + r(2)), an = TAU * r(3), rr = F.radius * Math.sqrt(r(4)), wob = 0.25 * Math.min(1, F.radius);
  return out.set(
    F.at.x + rr * Math.cos(an) + F.wind.x * (ph - 0.5) + wob * Math.sin(1.3 * t * (0.6 + r(5)) + TAU * r(6)),
    F.at.y + F.H * (F.rise ? ph : 1 - ph),
    F.at.z + rr * Math.sin(an) + F.wind.z * (ph - 0.5) + wob * Math.cos(1.1 * t * (0.6 + r(6)) + TAU * r(5)));
}
// Each blob is one splat. An effect that can glow has a second splat per blob (index n and up): a wide faint halo, drawn only while it glows.
// look = (opacity, glow 0..1, 1 when it rises instead of falling); sizes differ from blob to blob by a quarter either way.
const FX_BODY = {
  wander: (I, O) => `{
    int n = ${I.n}, i = ${I.index} % n + ${I.seed};
    bool halo = ${I.index} >= n;
    float t = ${I.t}, glow = ${I.look}.y, size = ${I.ext}.z * (0.75 + 0.5 * lsRand(i, 10)), pulse = lsPulse(i, t, glow);
    vec3 col = lsColour(i, ${I.par}.z, ${I.c1}, ${I.c2}, ${I.c3});
    ${O.gsplat}.flags = (halo && glow < 0.01) ? 0u : GSPLAT_FLAG_ACTIVE;
    ${O.gsplat}.index = ${I.index};
    ${O.gsplat}.center = lsWander(i, t, ${I.at}, ${I.ext}, ${I.par});
    ${O.gsplat}.scales = size * (halo ? vec3(3.5) : vec3(1.0, 0.7, 1.0));
    ${O.gsplat}.quaternion = vec4(0.0, 0.0, 0.0, 1.0);
    ${O.gsplat}.rgba = vec4(halo ? col : mix(col, vec3(1.0), 0.3 * glow), ${I.look}.x * (halo ? 0.22 * glow * pulse : 1.0));
  }`,
  drift: (I, O) => `{
    int n = ${I.n}, i = ${I.index} % n + ${I.seed};
    bool halo = ${I.index} >= n;
    float t = ${I.t}, glow = ${I.look}.y, size = ${I.ext}.z * (0.75 + 0.5 * lsRand(i, 10)), pulse = lsPulse(i, t, glow), k = 6.2831853, ph = 0.0;
    float r3 = lsRand(i, 3), r4 = lsRand(i, 4), r5 = lsRand(i, 5), r6 = lsRand(i, 6), r11 = lsRand(i, 11);
    vec3 c = lsDrift(i, t, ${I.at}, ${I.ext}, ${I.par}, ${I.wind}, ${I.look}.z, ph);
    vec3 col = lsColour(i, ${I.par}.z, ${I.c1}, ${I.c2}, ${I.c3});
    float turn = t * (0.4 + 0.9 * r5) + k * r6;
    float rock = (0.35 + 0.9 * r11) * sin(t * (1.6 + 2.2 * r3) + k * r4);
    vec3 ax = normalize(vec3(r3 - 0.5, 0.0, r4 - 0.5) + vec3(0.001, 0.0, 0.0));
    float fade = smoothstep(0.0, 0.08, ph) * (1.0 - smoothstep(0.9, 1.0, ph));
    ${O.gsplat}.flags = (halo && glow < 0.01) ? 0u : GSPLAT_FLAG_ACTIVE;
    ${O.gsplat}.index = ${I.index};
    ${O.gsplat}.center = c;
    ${O.gsplat}.scales = size * (halo ? vec3(3.0) : vec3(1.0, 0.25, 0.7));
    ${O.gsplat}.quaternion = lsQmul(vec4(0.0, sin(0.5 * turn), 0.0, cos(0.5 * turn)), vec4(ax * sin(0.5 * rock), cos(0.5 * rock)));
    ${O.gsplat}.rgba = vec4(halo ? col : mix(col, vec3(1.0), 0.3 * glow), ${I.look}.x * fade * (halo ? 0.22 * glow * pulse : 1.0));
  }`,
};
// Night mode multiplies the picture down to the lamp's light, blobs included, so a glowing effect is drawn once more there as points of light added on top.
const GLOW_VERT = (wander) => `
uniform float t, vh; uniform int seed; uniform vec3 at, ext, par, wind, look, c1, c2, c3;
varying vec4 vCol;
${FX_GLSL}
void main() {
  int i = gl_VertexID + seed; float ph = 0.5;
  vec3 c = ${wander ? "lsWander(i, t, at, ext, par)" : "lsDrift(i, t, at, ext, par, wind, look.z, ph)"};
  vec4 mv = modelViewMatrix * vec4(c, 1.0);
  gl_Position = projectionMatrix * mv;
  gl_PointSize = clamp(projectionMatrix[1][1] * vh * 0.5 * 14.0 * ext.z * (0.75 + 0.5 * lsRand(i, 10)) / max(0.05, -mv.z), 3.0, 96.0);
  vCol = vec4(lsColour(i, par.z, c1, c2, c3), look.x * lsPulse(i, t, 1.0) * ${wander ? "1.0" : "smoothstep(0.0, 0.08, ph) * (1.0 - smoothstep(0.9, 1.0, ph))"});
}`;
const GLOW_FRAG = `
varying vec4 vCol;
void main() {
  vec2 q = 2.0 * gl_PointCoord - 1.0; float a = exp(-4.5 * dot(q, q)) - 0.011;
  if (a <= 0.0) discard;
  gl_FragColor = vec4(vCol.rgb * vCol.a * a * 0.9, 1.0);
}`;
// "#rrggbb" as the numbers stored in a splat (display values, not converted to linear)
function colour(s) { const m = /^#?([0-9a-f]{6})$/i.exec(String(s).trim()); if (!m) return null; const n = parseInt(m[1], 16); return new THREE.Vector3((n >> 16) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255); }
const v2 = new THREE.Vector2();
function setupEffect(p, M, e, k) {
  if (!e || !FX_BODY[e.type]) throw new Error(`unknown type ${e?.type}`);
  const wander = e.type === "wander", at = new THREE.Vector3(num(e.at?.[0], p.roomW / 2), 0, num(e.at?.[1], p.roomD / 2)).applyMatrix4(M.R);
  let lo = Math.max(0, num(e.height?.[0], wander ? 0.4 : 0)), hi = num(e.height?.[1], lo + (wander ? 1 : 3)); if (hi < lo) [lo, hi] = [hi, lo];
  const cols = (Array.isArray(e.colours) ? e.colours : []).map(colour).filter(Boolean).slice(0, 3); if (!cols.length) cols.push(new THREE.Vector3(0.8, 0.8, 0.75));
  const F = { type: e.type, seed: 1 + k * 4099, at: at.setY(at.y + lo), H: Math.max(hi - lo, 0.05), radius: clamp(num(e.radius, wander ? 1.2 : 4), 0.3, wander ? 6 : 12),
    n: Math.round(wander ? clamp(num(e.count, 12), 1, 40) : clamp(num(e.count, 120), 10, 400)), size: clamp(num(e.size, wander ? 0.02 : 0.05), 0.01, wander ? 0.3 : 0.15),
    speed: clamp(num(e.speed, 1.2), 0.2, 4), fall: Math.max(0.02, clamp(Math.abs(num(e.fall, 0.6)), 0, 2)), rise: !wander && (e.rise === true || num(e.fall, 0) < 0),   // a negative fall (or "rise": true) goes up: sparks, bubbles, smoke
    opacity: clamp(num(e.opacity, 0.95), 0.05, 1), wind: new THREE.Vector3(), drawn: null };
  // what gives off light: said outright ("glow": true or false), else small blobs of a bright, strong colour (a firefly or a spark, not dust, snow or a leaf)
  // (the guess is made only in a world painted at dusk or at night: by day a bee or a small orange leaf is not a light, in night mode either)
  F.glows = typeof e.glow === "boolean" ? e.glow : M.dusk > 0 && F.size <= 0.04 && cols.some((c) => { const hi = Math.max(c.x, c.y, c.z); return hi >= 0.8 && hi - Math.min(c.x, c.y, c.z) >= 0.45 * hi; });
  F.wind.copy(M.windDir).multiplyScalar(Math.min(F.radius, M.windStrength * F.H));      // how far the wind carries a blob over one fall
  const u = F.u = { t: dyno.dynoFloat(0), seed: dyno.dynoInt(F.seed), n: dyno.dynoInt(F.n), at: dyno.dynoVec3(F.at.clone()), ext: dyno.dynoVec3(new THREE.Vector3(F.radius, F.H, F.size * 0.4)),
    par: dyno.dynoVec3(new THREE.Vector3(F.speed, F.fall, cols.length)), wind: dyno.dynoVec3(F.wind.clone()), look: dyno.dynoVec3(new THREE.Vector3(F.opacity, 0, F.rise ? 1 : 0)),
    c1: dyno.dynoVec3(cols[0]), c2: dyno.dynoVec3(cols[1] ?? cols[0]), c3: dyno.dynoVec3(cols[2] ?? cols[0]) };
  const tf = new SplatTransformer(), body = FX_BODY[e.type];
  const gen = new SplatGenerator({
    numSplats: F.glows ? 2 * F.n : F.n,
    generator: dyno.dynoBlock({ index: "int" }, { gsplat: dyno.Gsplat }, ({ index }) => {
      const d = new dyno.Dyno({
        inTypes: { index: "int", seed: "int", n: "int", t: "float", at: "vec3", ext: "vec3", par: "vec3", wind: "vec3", look: "vec3", c1: "vec3", c2: "vec3", c3: "vec3" }, outTypes: { gsplat: dyno.Gsplat },
        inputs: { index, ...u }, globals: () => [dyno.defineGsplat, FX_GLSL], statements: ({ inputs, outputs }) => body(inputs, outputs).split("\n"),
      });
      return { gsplat: tf.applyGsplat(d.outputs.gsplat) };
    }),
    // redraw only when the time or the part's placement changed, so a paused world costs nothing
    update: () => { u.t.value = M.T; const moved = tf.update(gen); if (moved || F.drawn !== M.T) { F.drawn = M.T; gen.updateVersion(); } },
  });
  F.gen = gen; gen.visible = (M.mode ?? "splat") === "splat"; p.outer.add(gen); M.fx.push(F); M.stats.effects = M.fx.length;
  if (F.glows) try {               // the points of light for night mode: the same places, worked out again on the GPU
    const geo = new THREE.BufferGeometry(); geo.setAttribute("position", new THREE.BufferAttribute(new Float32Array(F.n * 3), 3));
    const un = { t: { value: 0 }, vh: { value: 1000 }, seed: { value: F.seed } }; for (const key of ["at", "ext", "par", "wind", "look", "c1", "c2", "c3"]) un[key] = { value: u[key].value };
    const mat = new THREE.ShaderMaterial({ uniforms: un, vertexShader: GLOW_VERT(wander), fragmentShader: GLOW_FRAG, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending });
    F.lights = new THREE.Points(geo, mat); F.lights.frustumCulled = false; F.lights.renderOrder = 11; F.lights.visible = false;
    F.lights.onBeforeRender = (r) => { un.t.value = M.T; un.vh.value = r.getDrawingBufferSize(v2).y; };
    p.outer.add(F.lights);
  } catch (err) { warn(`the glow of "${e.label ?? e.type}"`, err); F.lights = null; }
  const kind = soundOf(e);
  if (kind) { const v = new THREE.Vector3(); M.sounds.push({ obj: () => fxPos(F, 0, M.T, v).applyMatrix4(p.outer.matrixWorld).toArray(), kind, type: e.type, size: F.radius }); }
}

// ---- the four calls main.js makes -------------------------------------------------------------------------------------
// ctx: { RAPIER, phys, gltf, T }. Resolves once every mover has loaded or been skipped. Returns p.motion, or null when the world has nothing that moves.
export async function setupMotion(p, ctx) {
  const d = p.def, movers = (Array.isArray(d.movers) ? d.movers : []).filter((m) => m && typeof m === "object"), effects = (Array.isArray(d.effects) ? d.effects : []).slice(0, 4);
  if (!movers.length && !effects.length) return null;
  const M = p.motion = { dead: false, T: num(ctx.T, 0), w: null, mode: null, night: false, dusk: d.mood?.time === "night" ? 1 : d.mood?.time === "dusk" ? 0.6 : 0, skin: null, lifts: [], fx: [], extras: [], sounds: [],
    stats: { sway: 0, skinned: 0, lifted: 0, effects: 0, skipped: [] }, get wires() { return M.lifts.filter((L) => L.wire && !L.gone).map((L) => L.wire); },
    get lanes() { return M.lifts.map((L) => L.lane); } };      // where lifted pieces go, in the part's outer frame: { pts, r }
  const skip = (what, e) => { M.stats.skipped.push(what); warn(what, e); };
  M.R = roomToOuter(p); M.flip = Math.sign(M.R.determinant()) || 1;
  // wind: `from` is a compass bearing in the room's own axes (0 = from +z, 90 = from +x); it blows the other way
  const from = THREE.MathUtils.degToRad(num(d.wind?.from, 270));
  M.windRoom = new THREE.Vector3(-Math.sin(from), 0, -Math.cos(from)); M.windDir = M.windRoom.clone().transformDirection(M.R);
  M.windStrength = clamp(num(d.wind?.strength, p.open ? 0.35 : 0.2), 0, 1);
  M.leanAxis = new THREE.Vector3().crossVectors(UP, M.windRoom).normalize();           // turning about this tips the top downwind (room axes)
  const sways = movers.filter((m) => m.type === "sway" && m.render === "skin" && (okBox(m.box) || skip(`sway on "${m.name ?? m.i}"`, "no box")));
  if (sways.length) try { setupSkin(p, M, sways); } catch (e) { skip("sway", e); if (p.splat.skinning) { p.splat.skinning = null; p.splat.updateGenerator(); } M.skin = null; }
  effects.forEach((e, k) => { try { setupEffect(p, M, e, k); } catch (err) { skip(`effect "${e?.label ?? e?.type ?? k}"`, err); } });
  const lifted = movers.filter((m) => m.render === "splat" && LIFTED.has(m.type)).slice(0, 12);
  for (const m of movers) if (!sways.includes(m) && !lifted.includes(m) && !(m.type === "sway" && m.render === "skin")) skip(`"${m.name ?? m.i}" (${m.type}, ${m.render ?? "no render"})`, "nothing to move it with; it stays still");
  await Promise.all(lifted.map((m) => setupLift(p, M, m, ctx).catch((e) => { if (!M.dead) skip(`"${m.name ?? m.i}" (${m.type})`, e); })));
  return M.dead ? null : M;
}
// Call before the physics step. T in seconds, w the wind in 0..1. Does nothing when neither changed.
export function stepMotion(p, T, w = 0) {
  const M = p.motion; if (!M || M.dead || (T === M.T && w === M.w)) return;
  M.T = T; M.w = w;
  if (M.skin) stepSkin(M, T, w);
  for (const L of M.lifts) stepLift(p, M, L, T);
}
export function setMotionVisible(p, mode, night) {
  const M = p.motion; if (!M || M.dead) return;
  M.mode = mode; M.night = night;
  for (const L of M.lifts) show(M, L);
  for (const F of M.fx) {                                       // blobs are splats only: no mesh, no collider
    F.gen.visible = mode === "splat";
    const glow = F.glows ? (night ? 1 : M.dusk) : 0;            // things that give off light glow in a world painted at dusk or at night, and in night mode
    if (F.u.look.value.y !== glow) { F.u.look.value.y = glow; F.drawn = null; }
    if (F.lights) F.lights.visible = night && mode === "splat";
  }
}
// Release everything setupMotion made for this part (bodies go with the physics world). Safe on a part with no motion, and while loads are still running.
export function disposeMotion(p) {
  const M = p.motion; if (!M) return;
  M.dead = true; p.motion = null;
  if (M.skin) { p.splat.skinning = null; M.skin.sk.skinTexture.dispose(); M.skin.sk.boneTexture.dispose(); }
  for (const L of M.lifts) { p.outer.remove(L.grp); L.splat.dispose(); for (const g of L.geos) g.dispose(); for (const x of L.mats) x.dispose(); }
  for (const F of M.fx) { p.outer.remove(F.gen); if (F.lights) { p.outer.remove(F.lights); F.lights.geometry.dispose(); F.lights.material.dispose(); } }
  for (const o of M.extras) p.outer.remove(o);
  M.lifts = []; M.fx = []; M.sounds = []; M.skin = null;
}
