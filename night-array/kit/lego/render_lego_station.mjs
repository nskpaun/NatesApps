// Renders of the LEGO Night Array station (headless Chromium + three.js from night-array/viewer/node_modules).
// Adapted from render_lego_dock.mjs (same page / server / stud / slope approach); adds curved and inverted slopes,
// monitors, stands, a desk, section-coloured exploded view and a section cut through a neck.
//
//   node night-array/kit/lego/render_lego_station.mjs [dir]     (make_lego_station.py runs this unless --no-render)
//
// Reads <dir>/bricks.json (default: station/ next to this file) and writes <dir>/overview.png (front 3/4, like the
// concept image: screens dark, keyboard + mouse lifted out in front), back.png, exploded-sections.png,
// section-neck.png (cut through the left pole) and steps/step-XX.png (build so far, newest step highlighted).
import { createRequire } from 'node:module';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const dir = path.resolve(process.argv[2] || path.join(here, 'station'));
const only = process.argv[3] || '';
const viewer = path.resolve(here, '../../viewer');
const req = createRequire(path.join(viewer, 'package.json'));
let chromium;
try { ({ chromium } = req('playwright')); } catch { ({ chromium } = createRequire('/opt/node-tools/node_modules/')('playwright')); }
const THREE_DIR = path.join(viewer, 'node_modules/three');
const stepsDir = path.join(dir, 'steps');
fs.mkdirSync(stepsDir, { recursive: true });
const W = 1800, H = 1000;

const PAGE = `<!doctype html><html><head><meta charset="utf-8"><style>html,body{margin:0;background:#eeece8}</style>
<script type="importmap">{"imports":{"three":"/three/build/three.module.js"}}</script>
</head><body><script type="module">
import * as THREE from 'three';
const W = ${W}, H = ${H};
const r = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
r.setSize(W, H); r.outputColorSpace = THREE.SRGBColorSpace; r.localClippingEnabled = true;
document.body.appendChild(r.domElement);
const scene = new THREE.Scene(); scene.background = new THREE.Color('#eeece8');
scene.add(new THREE.HemisphereLight(0xffffff, 0x8a857c, 1.7));
const d1 = new THREE.DirectionalLight(0xffffff, 1.5); d1.position.set(-700, 1100, 1300); scene.add(d1);
const d2 = new THREE.DirectionalLight(0xffffff, 0.6); d2.position.set(900, 500, -900); scene.add(d2);
const doc = await (await fetch('/data/bricks.json')).json();
const [SX, SY, SZ] = doc.size_mm;
const pcam = new THREE.PerspectiveCamera(22, W / H, 10, 40000);
let cam = pcam;
const root = new THREE.Group(); scene.add(root);
const boxGeo = new THREE.BoxGeometry(1, 1, 1);
const edgeGeo = new THREE.EdgesGeometry(boxGeo);
const studGeo = new THREE.CylinderGeometry(2.4, 2.4, 1.7, 10); studGeo.translate(0, 0.85, 0);
const cylGeo = new THREE.CylinderGeometry(0.5, 0.5, 1, 28);
const BG = new THREE.Color('#eeece8');
const maxStep = Math.max(...doc.bricks.map(b => b.step), ...doc.reference.map(f => f.step || 0));
let clip = [];
function look(az, el, dist, t) {
  cam = pcam;
  const a = az * Math.PI / 180, e = el * Math.PI / 180;
  cam.up.set(0, 1, 0);
  cam.position.set(t.x + dist * Math.sin(a) * Math.cos(e), t.y + dist * Math.sin(e), t.z + dist * Math.cos(a) * Math.cos(e));
  cam.lookAt(t);
}
function clear() { while (root.children.length) root.remove(root.children[0]); }
function mat(colour, opts) {
  return new THREE.MeshStandardMaterial({ color: colour, roughness: opts.rough ?? 0.55, metalness: opts.metal ?? 0,
    side: THREE.DoubleSide, transparent: (opts.opacity ?? 1) < 1, opacity: opts.opacity ?? 1,
    depthWrite: (opts.opacity ?? 1) >= 1, clippingPlanes: opts.noclip ? [] : clip });
}
function edges(geo, m, opts) {
  const e = new THREE.LineSegments(geo, new THREE.LineBasicMaterial({ color: opts.edgeColor || 0x000000,
    transparent: true, opacity: opts.edgeOpacity ?? 0.45, clippingPlanes: opts.noclip ? [] : clip }));
  e.matrixAutoUpdate = m.matrixAutoUpdate; e.matrix.copy(m.matrix);
  e.scale.copy(m.scale); e.position.copy(m.position); root.add(e);
}
// model frame (x right, y toward the user, z up) -> three (x, z, y); o = offset [dx, dy, dz]
function addBox(b, colour, opts = {}) {
  const g = opts.gap ?? 0.18, o = opts.off || [0, 0, 0];
  const m = new THREE.Mesh(opts.cyl ? cylGeo : boxGeo, mat(colour, opts));
  m.scale.set(Math.max(b.sx - 2 * g, 0.05), Math.max(b.sz - 0.05, 0.05), Math.max(b.sy - 2 * g, 0.05));
  m.position.set(b.x + b.sx / 2 + o[0], b.z + o[2] + b.sz / 2, b.y + b.sy / 2 + o[1]);
  root.add(m);
  if (opts.edges !== false && !opts.cyl) edges(edgeGeo, m, opts);
}
const wedgeCache = {};
function addSlope(b, colour, opts = {}) {
  const g = 0.18, s = b.slope, o = opts.off || [0, 0, 0], z0 = b.z + o[2];
  const alongX = s.down === '+x' || s.down === '-x';
  const L = (alongX ? b.sx : b.sy) - 2 * g, Wd = (alongX ? b.sy : b.sx) - 2 * g, Hh = b.sz - 0.05;
  const key = [L, Wd, Hh, s.curved ? 'c' : s.inverted ? 'i' : s.high_mm].join(',');
  let geo = wedgeCache[key];
  if (!geo) {
    const sh = new THREE.Shape();
    if (s.inverted) {
      sh.moveTo(0, 0); sh.lineTo(0, Hh); sh.lineTo(L, Hh); sh.lineTo(L, Hh - 1.6); sh.lineTo(s.high_mm - g, 0); sh.lineTo(0, 0);
    } else if (s.curved) {
      sh.moveTo(0, 0); sh.lineTo(0, Hh); sh.lineTo(s.high_mm, Hh);
      for (let i = 1; i <= 8; i++) { const t = i / 8; sh.lineTo(s.high_mm + (L - s.high_mm) * t, s.lip_mm + (Hh - s.lip_mm) * Math.cos(t * Math.PI / 2)); }
      sh.lineTo(L, 0); sh.lineTo(0, 0);
    } else {
      sh.moveTo(0, 0); sh.lineTo(0, Hh); sh.lineTo(s.high_mm - g, Hh); sh.lineTo(L, s.lip_mm); sh.lineTo(L, 0); sh.lineTo(0, 0);
    }
    geo = wedgeCache[key] = new THREE.ExtrudeGeometry(sh, { depth: Wd, bevelEnabled: false });
  }
  const m = new THREE.Mesh(geo, mat(colour, opts));
  const M = new THREE.Matrix4();
  const X = (v) => new THREE.Vector3(...v);
  const bx = b.x + o[0], by = b.y + o[1];
  let p;
  // shape x = along the fall line (from the high end), shape y = up, extrusion = across
  if (s.down === '+y') { M.makeBasis(X([0, 0, 1]), X([0, 1, 0]), X([1, 0, 0])); p = [bx + g, z0, by + g]; }
  if (s.down === '-y') { M.makeBasis(X([0, 0, -1]), X([0, 1, 0]), X([1, 0, 0])); p = [bx + g, z0, by + b.sy - g]; }
  if (s.down === '+x') { M.makeBasis(X([1, 0, 0]), X([0, 1, 0]), X([0, 0, 1])); p = [bx + g, z0, by + g]; }
  if (s.down === '-x') { M.makeBasis(X([-1, 0, 0]), X([0, 1, 0]), X([0, 0, 1])); p = [bx + b.sx - g, z0, by + g]; }
  M.setPosition(...p);
  m.matrixAutoUpdate = false; m.matrix.copy(M); root.add(m);
  const eg = wedgeCache[key + 'e'] || (wedgeCache[key + 'e'] = new THREE.EdgesGeometry(geo, 25));
  const e = new THREE.LineSegments(eg, new THREE.LineBasicMaterial({ color: opts.edgeColor || 0x000000, transparent: true,
    opacity: opts.edgeOpacity ?? 0.45, clippingPlanes: clip }));
  e.matrixAutoUpdate = false; e.matrix.copy(M); root.add(e);
}
function studsOf(b) {
  if (b.kind === 'tile') return [];
  if (b.part === '15573') return [[b.x + b.sx / 2, b.y + b.sy / 2]];
  const pts = [];
  for (let x = b.x + 4; x < b.x + b.sx; x += 8) for (let y = b.y + 4; y < b.y + b.sy; y += 8) pts.push([x, y]);
  if (b.kind !== 'slope') return pts;
  if (b.slope.curved) return [];
  if (b.slope.inverted) return pts;
  const d = b.slope.down;
  return pts.filter(([x, y]) => d === '+y' ? y < b.y + 8 : d === '-y' ? y > b.y + b.sy - 8 : d === '+x' ? x < b.x + 8 : x > b.x + b.sx - 8);
}
function addBricks(list) {
  const covered = new Set();
  for (const { b, opts } of list) {
    const o = opts.off || [0, 0, 0];
    const z = Math.round((b.z + o[2]) * 10);
    for (let x = b.x + 4; x < b.x + b.sx; x += 4) for (let y = b.y + 4; y < b.y + b.sy; y += 4)
      covered.add(Math.round(x + o[0]) + ',' + Math.round(y + o[1]) + ',' + z);
  }
  const studs = [];
  for (const it of list) {
    const o = it.opts.off || [0, 0, 0];
    if (it.b.kind === 'slope') addSlope(it.b, it.colour, it.opts); else addBox(it.b, it.colour, it.opts);
    if (it.opts.nostuds) continue;
    const zt = Math.round((it.b.z + it.b.sz + o[2]) * 10);
    for (const [x, y] of studsOf(it.b)) if (!covered.has(Math.round(x + o[0]) + ',' + Math.round(y + o[1]) + ',' + zt)) studs.push([x + o[0], zt / 10, y + o[1], it.colour]);
  }
  if (!studs.length) return;
  const im = new THREE.InstancedMesh(studGeo, new THREE.MeshStandardMaterial({ roughness: 0.5, metalness: 0, clippingPlanes: clip }), studs.length);
  const mtx = new THREE.Matrix4();
  studs.forEach((s, i) => { mtx.makeTranslation(s[0], s[1], s[2]); im.setMatrixAt(i, mtx); im.setColorAt(i, s[3]); });
  root.add(im);
}
function desk(yFront = SY + 420) {
  const d = { x: -260, y: 0, z: -28, sx: SX + 520, sy: yFront, sz: 28 };
  addBox(d, new THREE.Color('#6b4a36'), { gap: 0, edgeOpacity: 0.25, rough: 0.8 });
}
const REF_STYLE = {
  monitor: { rough: 0.6 }, screen: { rough: 0.25, edges: false }, stand: { rough: 0.45, metal: 0.4 },
  bar: { rough: 0.35, metal: 0.6 }, hardware: { metal: 0.5 }, electronics: {}, pad: {}, foam: {}, felt: { opacity: 0.9 },
  cable: {}, tag: {}, plug: {}, device: { rough: 0.4 }, core: { rough: 0.7, edgeOpacity: 0.3 },
};
// refs: which = function(ref) -> null (skip) | {off, opacity, hi}
function refs(which) {
  for (const rf of doc.reference) {
    const w = which(rf);
    if (!w) continue;
    const st = REF_STYLE[rf.kind] || {};
    let col = new THREE.Color(rf.color_hex);
    if (rf.kind === 'device' && /MacBook/.test(rf.name)) col = new THREE.Color('#aeb4bb');
    addBox(rf, col, { ...st, gap: 0, off: w.off, opacity: w.opacity ?? st.opacity ?? 1, cyl: rf.shape === 'cyl',
      edgeColor: w.hi ? 0xff6a00 : 0x222222, edgeOpacity: w.hi ? 0.95 : 0.5, metal: /MacBook/.test(rf.name) ? 0.5 : st.metal });
  }
}
const isDesk = rf => /keyboard\\)|mouse\\)/.test(rf.name) && rf.kind === 'device';
const C = new THREE.Vector3(SX / 2, SZ / 2, SY / 2);
window.render = (view, step) => {
  clear(); clip.length = 0;
  const full = (o = {}) => doc.bricks.map(b => ({ b, colour: new THREE.Color(b.color_hex), opts: { edgeOpacity: 0.28, ...o } }));
  if (view === 'step') {
    const list = doc.bricks.filter(b => b.step <= step).map(b => {
      const c = new THREE.Color(b.color_hex); if (b.step < step) c.lerp(BG, 0.22);
      return { b, colour: c, opts: b.step === step ? { edgeColor: 0xff7a00, edgeOpacity: 1 } : { edgeOpacity: 0.2 } };
    });
    addBricks(list); desk();
    refs(rf => (rf.step || 99) <= step && !(rf.kind === 'device' && step < 16) ? { hi: rf.step === step } : null);
    const top = Math.max(60, ...doc.bricks.filter(b => b.step <= step).map(b => b.z + b.sz),
      ...doc.reference.filter(f => (f.step || 99) <= step).map(f => f.z + f.sz));
    look(-14, 27, 2350 + top * 1.3, new THREE.Vector3(C.x, top * 0.4, SY * 0.5));
  }
  if (view === 'overview') {
    addBricks(full()); desk();
    refs(rf => {
      if (rf.kind === 'tag') return null;
      if (isDesk(rf)) return { off: [/keyboard/.test(rf.name) ? -40 : 150, SY - rf.y + 70 + (/mouse/.test(rf.name) ? 20 : 0), -rf.z] };
      return {};
    });
    look(-6, 11, 2750, new THREE.Vector3(C.x, 230, SY * 0.6));
  }
  if (view === 'back') {
    addBricks(full()); desk();
    refs(rf => rf.kind === 'tag' ? null : {});
    look(180 + 24, 16, 2900, new THREE.Vector3(C.x, 235, SY * 0.4));
  }
  if (view === 'exploded') {
    const OFF = { base: [0, 0, 0], pockets: [0, 0, 150], dock: [260, 0, 60], necks: [0, 0, 300], frame: [0, 0, 460] };
    addBricks(doc.bricks.map(b => ({ b, colour: new THREE.Color(b.color_hex), opts: { edgeOpacity: 0.28, off: OFF[b.section] } })));
    refs(rf => {
      if (['stand', 'hardware', 'monitor', 'screen'].includes(rf.kind)) return { off: [0, -520, 0] };
      if (rf.kind === 'bar') return { off: [0, 0, 460 + (rf.z > 300 ? 110 : -110)] };
      if ((rf.kind === 'pad' || rf.kind === 'electronics') && rf.step === 4) return { off: [0, 0, 70] };
      return null;
    });
    look(-24, 24, 4500, new THREE.Vector3(C.x + 120, 430, SY * 0.1));
  }
  if (view === 'section') {
    const pole = doc.reference.find(f => f.shape === 'cyl');
    const px = pole.x + pole.sx / 2;
    clip.push(new THREE.Plane(new THREE.Vector3(1, 0, 0), -px));     // keep x >= pole centre, look from -x
    const ocam = new THREE.OrthographicCamera(-1, 1, 1, -1, -8000, 8000);
    const hgt = 640, w = hgt * W / H, cy = 150, cz = 245;
    Object.assign(ocam, { left: -w / 2, right: w / 2, top: hgt / 2, bottom: -hgt / 2 });
    ocam.position.set(px - 3000, cz, cy); ocam.up.set(0, 1, 0); ocam.lookAt(px, cz, cy);
    ocam.updateProjectionMatrix();
    addBricks(doc.bricks.filter(b => b.x < px + 520).map(b => ({ b, colour: new THREE.Color(b.color_hex), opts: { edgeOpacity: 0.5 } })));
    desk(700);
    refs(rf => rf.x > px + 520 || rf.kind === 'tag' || /right|laptop|MacBook/.test(rf.name) && rf.x > px + 400 ? null : {});
    cam = ocam;
  }
  r.render(scene, cam);
  return r.domElement.toDataURL('image/png');
};
window.maxStep = maxStep;
window.ready = true;
</script></body></html>`;

const server = http.createServer((rq, res) => {
  const u = decodeURIComponent(rq.url.split('?')[0]);
  if (u === '/') { res.writeHead(200, { 'content-type': 'text/html' }); return res.end(PAGE); }
  let f = null;
  if (u.startsWith('/three/')) f = path.join(THREE_DIR, u.slice(7));
  if (u === '/data/bricks.json') f = path.join(dir, 'bricks.json');
  if (!f || !fs.existsSync(f)) { res.writeHead(404); return res.end(); }
  res.writeHead(200, { 'content-type': f.endsWith('.js') ? 'text/javascript' : 'application/json' });
  fs.createReadStream(f).pipe(res);
});
await new Promise(r => server.listen(0, r));
const browser = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
const page = await browser.newPage({ viewport: { width: W, height: H } });
page.on('pageerror', e => console.error('page error:', e.message));
page.on('console', m => { if (m.type() === 'error') console.error('page:', m.text()); });
await page.goto(`http://127.0.0.1:${server.address().port}/`);
await page.waitForFunction(() => window.ready === true, null, { timeout: 180000 });
const save = (file, url) => { fs.writeFileSync(file, Buffer.from(url.split(',')[1], 'base64')); console.log('wrote', path.relative(process.cwd(), file)); };
const VIEWS = { overview: 'overview.png', back: 'back.png', exploded: 'exploded-sections.png', section: 'section-neck.png' };
for (const [v, f] of Object.entries(VIEWS)) {
  if (only && !only.split(',').includes(v)) continue;
  save(path.join(dir, f), await page.evaluate(v => window.render(v, 0), v));
}
if (!only || only.split(',').includes('steps')) {
  const n = await page.evaluate(() => window.maxStep);
  for (let s = 1; s <= n; s++) save(path.join(stepsDir, `step-${String(s).padStart(2, '0')}.png`), await page.evaluate(s => window.render('step', s), s));
}
await browser.close(); server.close();
