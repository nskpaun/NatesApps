// Build-step renders of the LEGO pocket-section base (headless Chromium + three.js from night-array/viewer/node_modules).
//
//   node night-array/kit/lego/render_lego.mjs            (make_lego_base.py runs this unless --no-render)
//
// Reads bricks.json next to this file and writes steps/step-XX.png (build so far, newest step highlighted),
// overview.png (assembled, keyboard + mouse ghosted), exploded.png and floor-plan.png (top view of the floor layer
// with the pads, Magic Tag and devices outlined).
import { createRequire } from 'node:module';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const viewer = path.resolve(here, '../../viewer');
const req = createRequire(path.join(viewer, 'package.json'));
let chromium;
try { ({ chromium } = req('playwright')); } catch { ({ chromium } = createRequire('/opt/node-tools/node_modules/')('playwright')); }
const THREE_DIR = path.join(viewer, 'node_modules/three');
const stepsDir = path.join(here, 'steps');
fs.mkdirSync(stepsDir, { recursive: true });
const W = 1600, H = 900;

const PAGE = `<!doctype html><html><head><meta charset="utf-8"><style>html,body{margin:0;background:#eeece8}</style>
<script type="importmap">{"imports":{"three":"/three/build/three.module.js"}}</script>
</head><body><script type="module">
import * as THREE from 'three';
const W = ${W}, H = ${H};
const r = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
r.setSize(W, H); r.outputColorSpace = THREE.SRGBColorSpace;
document.body.appendChild(r.domElement);
const scene = new THREE.Scene(); scene.background = new THREE.Color('#eeece8');
scene.add(new THREE.HemisphereLight(0xffffff, 0x77736b, 1.7));
const d1 = new THREE.DirectionalLight(0xffffff, 1.6); d1.position.set(-300, 700, 500); scene.add(d1);
const d2 = new THREE.DirectionalLight(0xffffff, 0.6); d2.position.set(500, 300, -400); scene.add(d2);
const doc = await (await fetch('/data/bricks.json')).json();
const [SX, SY, SZ] = doc.size_mm;
const C = new THREE.Vector3(SX / 2, SZ / 2, SY / 2);           // three: X = x, Y = z (up), Z = y (toward the viewer)
const cam = new THREE.PerspectiveCamera(22, W / H, 1, 20000);
const root = new THREE.Group(); scene.add(root);
const boxGeo = new THREE.BoxGeometry(1, 1, 1);
const edgeGeo = new THREE.EdgesGeometry(boxGeo);
const studGeo = new THREE.CylinderGeometry(2.4, 2.4, 1.7, 14); studGeo.translate(0, 0.85, 0);
const HL = new THREE.Color('#ff8a00');
const BG = new THREE.Color('#eeece8');
const maxStep = Math.max(...doc.bricks.map(b => b.step));
function look(az, el, dist, t) {
  const a = az * Math.PI / 180, e = el * Math.PI / 180;
  cam.up.set(0, 1, 0);
  cam.position.set(t.x + dist * Math.sin(a) * Math.cos(e), t.y + dist * Math.sin(e), t.z + dist * Math.cos(a) * Math.cos(e));
  cam.lookAt(t);
}
function clear() { while (root.children.length) root.remove(root.children[0]); }
function addBox(b, colour, opts = {}) {
  const g = 0.18;                                             // visual gap per side so the seams read
  const m = new THREE.Mesh(boxGeo, new THREE.MeshStandardMaterial({ color: colour, roughness: 0.55, metalness: 0,
    transparent: (opts.opacity ?? 1) < 1, opacity: opts.opacity ?? 1, depthWrite: (opts.opacity ?? 1) >= 1,
    emissive: opts.emissive || 0x000000, emissiveIntensity: opts.emissive ? 0.25 : 0 }));
  m.scale.set(b.sx - 2 * g, b.sz - 0.05, b.sy - 2 * g);
  m.position.set(b.x + b.sx / 2, (b.z + (opts.dz || 0)) + b.sz / 2, b.y + b.sy / 2);
  root.add(m);
  if (opts.edges !== false) {
    const e = new THREE.LineSegments(edgeGeo, new THREE.LineBasicMaterial({ color: opts.edgeColor || 0x000000,
      transparent: true, opacity: opts.edgeOpacity ?? 0.45 }));
    e.scale.copy(m.scale); e.position.copy(m.position); root.add(e);
  }
}
// bricks: list of {b, colour, opts}; studs on every non-tile top cell that no other shown part covers
function addBricks(list) {
  const covered = new Set();
  for (const { b, opts } of list) {
    const z = Math.round((b.z + (opts.dz || 0)) * 10);
    for (let x = b.x; x < b.x + b.sx - 1; x += 8) for (let y = b.y; y < b.y + b.sy - 1; y += 8) covered.add(x + ',' + y + ',' + z);
  }
  const studs = [];
  for (const it of list) {
    addBox(it.b, it.colour, it.opts);
    if (it.b.kind === 'tile') continue;
    const zt = Math.round((it.b.z + it.b.sz + (it.opts.dz || 0)) * 10);
    for (let x = it.b.x; x < it.b.x + it.b.sx - 1; x += 8) for (let y = it.b.y; y < it.b.y + it.b.sy - 1; y += 8)
      if (!covered.has(x + ',' + y + ',' + zt)) studs.push([x + 4, (zt / 10), y + 4, it.colour, it.opts]);
  }
  if (!studs.length) return;
  const im = new THREE.InstancedMesh(studGeo, new THREE.MeshStandardMaterial({ roughness: 0.5, metalness: 0 }), studs.length);
  const mtx = new THREE.Matrix4();
  studs.forEach((s, i) => { mtx.makeTranslation(s[0], s[1], s[2]); im.setMatrixAt(i, mtx); im.setColorAt(i, s[3]); });
  root.add(im);
}
function colourFor(b, step, mode) {
  const c = new THREE.Color(b.color_hex);
  if (mode === 'step' && b.step < step) c.lerp(BG, 0.6);
  return c;
}
function refsFor(step, ghostDevices, dzOf) {
  for (const rf of doc.reference) {
    if (rf.kind === 'device' || rf.kind === 'tag') {
      if (ghostDevices) addBox(rf, new THREE.Color(rf.kind === 'tag' ? rf.color_hex : '#7fa7d6'), { opacity: 0.28, edgeColor: 0x1a1a1a, edgeOpacity: 0.8, dz: dzOf ? dzOf(11) : 0 });
    } else if (rf.step <= step) {
      const isNew = rf.step === step;
      addBox(rf, new THREE.Color(rf.color_hex), { edgeColor: isNew ? 0xff6a00 : 0x333333,
        edgeOpacity: 0.9, dz: dzOf ? dzOf(rf.step) : 0 });
    }
  }
}
window.render = (view, step) => {
  clear();
  if (view === 'step') {
    const list = doc.bricks.filter(b => b.step <= step).map(b => ({ b, colour: colourFor(b, step, 'step'),
      opts: b.step === step ? { edgeColor: 0xff7a00, edgeOpacity: 1 } : { edgeOpacity: 0.25 } }));
    addBricks(list);
    refsFor(step, false);
    look(-24, 44, 1080, new THREE.Vector3(C.x, 8, C.z + 10));
  }
  if (view === 'overview') {
    addBricks(doc.bricks.map(b => ({ b, colour: new THREE.Color(b.color_hex), opts: { edgeOpacity: 0.3 } })));
    refsFor(99, true);
    look(-24, 36, 1060, new THREE.Vector3(C.x, 15, C.z + 10));
  }
  if (view === 'exploded') {
    const dz = s => (s - 1) * 36;
    addBricks(doc.bricks.map(b => ({ b, colour: new THREE.Color(b.color_hex), opts: { edgeOpacity: 0.3, dz: dz(b.step) } })));
    refsFor(5, false, dz);
    look(-24, 34, 1750, new THREE.Vector3(C.x, 170, C.z));
  }
  if (view === 'plan') {                                      // floor layer from above, pads + devices outlined
    addBricks(doc.bricks.filter(b => b.step <= 7).map(b => ({ b, colour: new THREE.Color(b.color_hex), opts: { edgeOpacity: 0.35 } })));
    for (const rf of doc.reference) {
      if (rf.kind === 'foam' || rf.kind === 'cable') continue;
      const lift = { ...rf, z: 30 + (rf.kind === 'pad' ? 0 : rf.kind === 'device' ? 2 : 4), sz: 0.5 };
      addBox(lift, new THREE.Color(rf.kind === 'pad' ? '#ffffff' : rf.kind === 'tag' ? '#d03030' : '#4a90d9'),
        { opacity: rf.kind === 'pad' ? 0.45 : 0.25, edgeColor: rf.kind === 'pad' ? 0xffffff : 0x1060c0, edgeOpacity: 1 });
    }
    cam.up.set(0, 0, -1);
    cam.position.set(C.x, 1000, C.z + 0.01); cam.lookAt(C.x, 0, C.z);
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
  if (u === '/data/bricks.json') f = path.join(here, 'bricks.json');
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
const n = await page.evaluate(() => window.maxStep);
for (let s = 1; s <= n; s++) save(path.join(stepsDir, `step-${String(s).padStart(2, '0')}.png`), await page.evaluate(s => window.render('step', s), s));
for (const v of ['overview', 'exploded']) save(path.join(here, v + '.png'), await page.evaluate(v => window.render(v, 0), v));
save(path.join(here, 'floor-plan.png'), await page.evaluate(() => window.render('plan', 0)));
await browser.close(); server.close();
