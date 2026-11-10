// Renders of the LEGO laptop dock (headless Chromium + three.js from night-array/viewer/node_modules).
// Adapted from render_lego.mjs (same page / server / stud approach); adds slope wedges, one-stud jumpers,
// a tall camera framing and two section views through the plug.
//
//   node night-array/kit/lego/render_lego_dock.mjs [dir]      (make_lego_dock.py runs this unless --no-render)
//
// Reads <dir>/bricks.json (default: dock/ next to this file) and writes <dir>/steps/step-XX.png (build so far,
// newest step highlighted), overview.png (assembled, laptop ghosted), exploded.png, plug-section-side.png and
// plug-section-front.png (cut through the plug centre).
import { createRequire } from 'node:module';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const dir = path.resolve(process.argv[2] || path.join(here, 'dock'));
const viewer = path.resolve(here, '../../viewer');
const req = createRequire(path.join(viewer, 'package.json'));
let chromium;
try { ({ chromium } = req('playwright')); } catch { ({ chromium } = createRequire('/opt/node-tools/node_modules/')('playwright')); }
const THREE_DIR = path.join(viewer, 'node_modules/three');
const stepsDir = path.join(dir, 'steps');
fs.mkdirSync(stepsDir, { recursive: true });
const W = 1400, H = 1050;

const PAGE = `<!doctype html><html><head><meta charset="utf-8"><style>html,body{margin:0;background:#eeece8}</style>
<script type="importmap">{"imports":{"three":"/three/build/three.module.js"}}</script>
</head><body><script type="module">
import * as THREE from 'three';
const W = ${W}, H = ${H};
const r = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
r.setSize(W, H); r.outputColorSpace = THREE.SRGBColorSpace; r.localClippingEnabled = true;
document.body.appendChild(r.domElement);
const scene = new THREE.Scene(); scene.background = new THREE.Color('#eeece8');
scene.add(new THREE.HemisphereLight(0xffffff, 0x77736b, 1.6));
const d1 = new THREE.DirectionalLight(0xffffff, 1.5); d1.position.set(-500, 700, 400); scene.add(d1);
const d2 = new THREE.DirectionalLight(0xffffff, 0.6); d2.position.set(500, 300, -400); scene.add(d2);
const doc = await (await fetch('/data/bricks.json')).json();
const [SX, SY, SZ] = doc.size_mm;
const pcam = new THREE.PerspectiveCamera(24, W / H, 1, 20000);
let cam = pcam;
const root = new THREE.Group(); scene.add(root);
const boxGeo = new THREE.BoxGeometry(1, 1, 1);
const edgeGeo = new THREE.EdgesGeometry(boxGeo);
const studGeo = new THREE.CylinderGeometry(2.4, 2.4, 1.7, 14); studGeo.translate(0, 0.85, 0);
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
  return new THREE.MeshStandardMaterial({ color: colour, roughness: 0.55, metalness: 0, side: THREE.DoubleSide,
    transparent: (opts.opacity ?? 1) < 1, opacity: opts.opacity ?? 1, depthWrite: (opts.opacity ?? 1) >= 1,
    clippingPlanes: opts.noclip ? [] : clip });
}
function edges(geo, m, opts) {
  const e = new THREE.LineSegments(geo, new THREE.LineBasicMaterial({ color: opts.edgeColor || 0x000000,
    transparent: true, opacity: opts.edgeOpacity ?? 0.45, clippingPlanes: opts.noclip ? [] : clip }));
  e.matrixAutoUpdate = m.matrixAutoUpdate; e.matrix.copy(m.matrix);
  e.scale.copy(m.scale); e.position.copy(m.position); root.add(e);
}
function addBox(b, colour, opts = {}) {
  const g = opts.gap ?? 0.18;
  const m = new THREE.Mesh(boxGeo, mat(colour, opts));
  m.scale.set(Math.max(b.sx - 2 * g, 0.05), Math.max(b.sz - 0.05, 0.05), Math.max(b.sy - 2 * g, 0.05));
  m.position.set(b.x + b.sx / 2, (b.z + (opts.dz || 0)) + b.sz / 2, b.y + b.sy / 2);
  root.add(m);
  if (opts.edges !== false) edges(edgeGeo, m, opts);
}
// slope wedge: flat high row (high_mm) at the high end, falling to a lip at the low end
const wedgeCache = {};
function addSlope(b, colour, opts = {}) {
  const g = 0.18, s = b.slope, z0 = b.z + (opts.dz || 0);
  const alongX = s.down === '+x' || s.down === '-x';
  const L = (alongX ? b.sx : b.sy) - 2 * g, Wd = (alongX ? b.sy : b.sx) - 2 * g, Hh = b.sz - 0.05;
  const key = [L, Wd, Hh].join(',');
  let geo = wedgeCache[key];
  if (!geo) {
    const sh = new THREE.Shape();
    sh.moveTo(0, 0); sh.lineTo(0, Hh); sh.lineTo(s.high_mm - g, Hh); sh.lineTo(L, s.lip_mm); sh.lineTo(L, 0); sh.lineTo(0, 0);
    geo = wedgeCache[key] = new THREE.ExtrudeGeometry(sh, { depth: Wd, bevelEnabled: false });
  }
  const m = new THREE.Mesh(geo, mat(colour, opts));
  const M = new THREE.Matrix4();
  const X = (v) => new THREE.Vector3(...v);
  let o;
  if (s.down === '+y') { M.makeBasis(X([0, 0, 1]), X([0, 1, 0]), X([1, 0, 0])); o = [b.x + g, z0, b.y + g]; }
  if (s.down === '-y') { M.makeBasis(X([0, 0, -1]), X([0, 1, 0]), X([1, 0, 0])); o = [b.x + g, z0, b.y + b.sy - g]; }
  if (s.down === '+x') { M.makeBasis(X([1, 0, 0]), X([0, 1, 0]), X([0, 0, 1])); o = [b.x + g, z0, b.y + g]; }
  if (s.down === '-x') { M.makeBasis(X([-1, 0, 0]), X([0, 1, 0]), X([0, 0, 1])); o = [b.x + b.sx - g, z0, b.y + g]; }
  M.setPosition(...o);
  m.matrixAutoUpdate = false; m.matrix.copy(M); root.add(m);
  const eg = wedgeCache[key + 'e'] || (wedgeCache[key + 'e'] = new THREE.EdgesGeometry(geo, 20));
  const e = new THREE.LineSegments(eg, new THREE.LineBasicMaterial({ color: opts.edgeColor || 0x000000, transparent: true,
    opacity: opts.edgeOpacity ?? 0.45, clippingPlanes: clip }));
  e.matrixAutoUpdate = false; e.matrix.copy(M); root.add(e);
}
function studsOf(b) {
  if (b.kind === 'tile') return [];
  const pts = [];
  if (b.part === '15573') return [[b.x + b.sx / 2, b.y + b.sy / 2]];
  for (let x = b.x + 4; x < b.x + b.sx; x += 8) for (let y = b.y + 4; y < b.y + b.sy; y += 8) pts.push([x, y]);
  if (b.kind !== 'slope') return pts;
  const d = b.slope.down;
  return pts.filter(([x, y]) => d === '+y' ? y < b.y + 8 : d === '-y' ? y > b.y + b.sy - 8 : d === '+x' ? x < b.x + 8 : x > b.x + b.sx - 8);
}
function addBricks(list) {
  const covered = new Set();
  for (const { b, opts } of list) {
    const z = Math.round((b.z + (opts.dz || 0)) * 10);
    for (let x = b.x + 4; x < b.x + b.sx; x += 4) for (let y = b.y + 4; y < b.y + b.sy; y += 4) covered.add(Math.round(x) + ',' + Math.round(y) + ',' + z);
  }
  const studs = [];
  for (const it of list) {
    if (it.b.kind === 'slope') addSlope(it.b, it.colour, it.opts); else addBox(it.b, it.colour, it.opts);
    const zt = Math.round((it.b.z + it.b.sz + (it.opts.dz || 0)) * 10);
    for (const [x, y] of studsOf(it.b)) if (!covered.has(Math.round(x) + ',' + Math.round(y) + ',' + zt)) studs.push([x, zt / 10, y, it.colour]);
  }
  if (!studs.length) return;
  const im = new THREE.InstancedMesh(studGeo, new THREE.MeshStandardMaterial({ roughness: 0.5, metalness: 0, clippingPlanes: clip }), studs.length);
  const mtx = new THREE.Matrix4();
  studs.forEach((s, i) => { mtx.makeTranslation(s[0], s[1], s[2]); im.setMatrixAt(i, mtx); im.setColorAt(i, s[3]); });
  root.add(im);
}
function colourFor(b, step, mode) {
  const c = new THREE.Color(b.color_hex);
  if (mode === 'step' && b.step < step) c.lerp(BG, 0.55);
  return c;
}
function refs(step, { ghost = true, dzOf = null, highlight = true, laptopOpacity = 0.22, maxRefStep = 99 } = {}) {
  for (const rf of doc.reference) {
    if ((rf.step || 0) > maxRefStep && !(maxRefStep === 11.5 && !rf.name.startsWith('back liner'))) continue;
    if (rf.kind === 'device') {
      if (ghost) addBox(rf, new THREE.Color('#7fa7d6'), { opacity: laptopOpacity, edgeColor: 0x1a3a6a, edgeOpacity: 0.8,
        dz: dzOf ? dzOf(13) : 0, gap: 0 });
    } else if ((rf.step || 0) <= step) {
      const isNew = highlight && rf.step === step;
      addBox(rf, new THREE.Color(rf.color_hex), { edgeColor: isNew ? 0xff6a00 : 0x333333, edgeOpacity: 0.9,
        dz: dzOf ? dzOf(rf.step) : 0, gap: 0, opacity: rf.kind === 'felt' ? 0.85 : 1 });
    }
  }
}
const C = new THREE.Vector3(SX / 2, 0, SY / 2);
window.render = (view, step) => {
  clear(); clip.length = 0;
  if (view === 'step') {
    const list = doc.bricks.filter(b => b.step <= step).map(b => ({ b, colour: colourFor(b, step, 'step'),
      opts: b.step === step ? { edgeColor: 0xff7a00, edgeOpacity: 1 } : { edgeOpacity: 0.25 } }));
    addBricks(list);
    refs(step, { ghost: false });
    const top = Math.max(...doc.bricks.filter(b => b.step <= step).map(b => b.z + b.sz));
    look(-38, 34, 640 + top * 1.9, new THREE.Vector3(C.x, top * 0.42, C.z));
  }
  if (view === 'overview') {
    addBricks(doc.bricks.map(b => ({ b, colour: new THREE.Color(b.color_hex), opts: { edgeOpacity: 0.3 } })));
    refs(99, { ghost: true, highlight: false });
    look(-40, 20, 1180, new THREE.Vector3(C.x, 175, C.z + 10));
  }
  if (view === 'exploded') {
    const dz = s => (s - 1) * 28 + (s >= 7 ? 40 : 0) + (s >= 12 ? 40 : 0);
    addBricks(doc.bricks.map(b => ({ b, colour: new THREE.Color(b.color_hex), opts: { edgeOpacity: 0.3, dz: dz(b.step) } })));
    refs(12, { ghost: false, dzOf: dz, highlight: false, maxRefStep: 11 });
    look(-40, 24, 1450, new THREE.Vector3(C.x, 215, C.z));
  }
  if (view === 'section-side' || view === 'section-front') {
    const plug = doc.reference.find(f => f.name.startsWith('USB-C plug'));
    const px = plug.x + plug.sx / 2, py = plug.y + plug.sy / 2;
    const ocam = new THREE.OrthographicCamera(-1, 1, 1, -1, -5000, 5000);
    if (view === 'section-side') {
      clip.push(new THREE.Plane(new THREE.Vector3(1, 0, 0), -px));     // keep x >= plug centre, look from -x
      const w = 150, hgt = w * H / W, cx = 52, cz = 38;
      Object.assign(ocam, { left: -w / 2, right: w / 2, top: hgt / 2, bottom: -hgt / 2 });
      ocam.position.set(px - 1000, cz, cx); ocam.up.set(0, 1, 0); ocam.lookAt(px, cz, cx);
    } else {
      clip.push(new THREE.Plane(new THREE.Vector3(0, 0, -1), py));     // keep y <= plug centre, look from the front
      const w = 120, hgt = w * H / W, cx = 64, cz = 38;
      Object.assign(ocam, { left: -w / 2, right: w / 2, top: hgt / 2, bottom: -hgt / 2 });
      ocam.position.set(cx, cz, py + 1000); ocam.up.set(0, 1, 0); ocam.lookAt(cx, cz, py);
    }
    ocam.updateProjectionMatrix();
    addBricks(doc.bricks.map(b => ({ b, colour: new THREE.Color(b.color_hex), opts: { edgeOpacity: 0.5 } })));
    refs(99, { ghost: true, highlight: false, laptopOpacity: 0.35, maxRefStep: view === 'section-front' ? 11.5 : 99 });
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
const n = await page.evaluate(() => window.maxStep);
for (let s = 1; s <= n; s++) save(path.join(stepsDir, `step-${String(s).padStart(2, '0')}.png`), await page.evaluate(s => window.render('step', s), s));
for (const v of ['overview', 'exploded']) save(path.join(dir, v + '.png'), await page.evaluate(v => window.render(v, 0), v));
save(path.join(dir, 'plug-section-side.png'), await page.evaluate(() => window.render('section-side', 0)));
save(path.join(dir, 'plug-section-front.png'), await page.evaluate(() => window.render('section-front', 0)));
await browser.close(); server.close();
