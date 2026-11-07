// Quick preview renders of a CAD build (cad/export or a module scratch dir) in headless Chromium + three.js.
//
//   node cad/tools/preview.mjs <build dir> [view ...] [--w 1600 --h 1000] [--pose work]
//
// <build dir> holds model/station.glb, model/station-edges.glb and model/scene.json.  Views (default: all):
//   hero    front-left, above, internal parts hidden (the look)          back    rear three-quarter
//   top     plan view (internal shown faint)                            front   straight on
//   xray    hero camera, shells translucent, internals solid            dock    the right wing close-up
//   section cut at x = -203 (keyboard Qi pad) looking from +x           zsection cut at z = -138 (posts) from the front
//   side    from +x, shells translucent
// Writes <build dir>/preview/<view>.png.  three.js comes from viewer/node_modules (npm install there once).
import { createRequire } from 'node:module';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
// playwright: the viewer's copy, else the global one
const req = createRequire(path.resolve(here, '../../viewer/package.json'));
let chromium;
try { ({ chromium } = req('playwright')); } catch { ({ chromium } = createRequire('/opt/node22/lib/node_modules/')('playwright')); }
const THREE_DIR = path.resolve(here, '../../viewer/node_modules/three');
const args = process.argv.slice(2);
const opt = (k, d) => { const i = args.indexOf('--' + k); if (i < 0) return d; const v = args[i + 1]; args.splice(i, 2); return v; };
const W = +opt('w', 1600), H = +opt('h', 1000), POSE = opt('pose', 'stow');
const dir = path.resolve(args.shift() || path.resolve(here, '../export'));
const ALL = ['hero', 'back', 'top', 'front', 'xray', 'dock', 'section', 'zsection', 'side'];
const views = args.length ? args : ALL;
const outDir = path.join(dir, 'preview');
fs.mkdirSync(outDir, { recursive: true });

const PAGE = `<!doctype html><html><head><meta charset="utf-8"><style>html,body{margin:0;background:#1b1c1e}</style>
<script type="importmap">{"imports":{"three":"/three/build/three.module.js","three/addons/":"/three/examples/jsm/"}}</script>
</head><body><script type="module">
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
const W = ${W}, H = ${H};
const r = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
r.setSize(W, H); r.localClippingEnabled = true; r.outputColorSpace = THREE.SRGBColorSpace;
r.toneMapping = THREE.ACESFilmicToneMapping; r.toneMappingExposure = 1.15;
document.body.appendChild(r.domElement);
const scene = new THREE.Scene(); scene.background = new THREE.Color('#1b1c1e');
scene.add(new THREE.HemisphereLight(0xfff4e8, 0x302820, 1.5));
const d1 = new THREE.DirectionalLight(0xffffff, 2.2); d1.position.set(-1.5, 2.5, 2.5); scene.add(d1);
const d2 = new THREE.DirectionalLight(0xffe0c0, 1.0); d2.position.set(2, 1, -2); scene.add(d2);
const sc = await (await fetch('/model/scene.json')).json();
const load = (u) => new Promise((res, rej) => new GLTFLoader().load(u, res, undefined, rej));
const [g, ge] = await Promise.all([load('/model/station.glb'), load('/model/station-edges.glb')]);
const info = Object.fromEntries(sc.parts.map(p => [p.id, p]));
const mats = sc.materials;
const nodes = {}, edges = {};
g.scene.traverse(o => { if (o.isMesh) { const id = o.parent && o.parent.name && info[o.parent.name] ? o.parent.name : o.name; nodes[id] = o; } });
ge.scene.traverse(o => { if (o.isLineSegments || o.isLine) { const id = o.parent && o.parent.name && info[o.parent.name] ? o.parent.name : o.name.replace(/_edges$/, ''); edges[id] = o; } });
for (const [id, m] of Object.entries(nodes)) {
  const p = info[id]; const md = mats[p.material] || {};
  m.material = new THREE.MeshStandardMaterial({ color: new THREE.Color(md.color || '#888'), metalness: Math.min(md.metallic ?? 0, 0.6),
    roughness: Math.max(md.roughness ?? 0.5, 0.35), emissive: md.emissive ? new THREE.Color(md.color) : new THREE.Color(0), emissiveIntensity: md.emissive ? 1.5 : 0,
    side: THREE.DoubleSide });
}
for (const e of Object.values(edges)) e.material = new THREE.LineBasicMaterial({ color: 0x000000, transparent: true, opacity: 0.35 });
scene.add(g.scene); scene.add(ge.scene);
// pose
const pose = sc.poses[${JSON.stringify(POSE)}] || {};
for (const [gid, d] of Object.entries(pose)) {
  for (const pid of (sc.groups.find(x => x.id === gid) || { parts: [] }).parts) {
    for (const o of [nodes[pid], edges[pid]]) { if (!o) continue; const n = o.parent && info[o.parent.name] ? o.parent : o;
      if (d.hidden) n.visible = false; if (d.t) n.position.add(new THREE.Vector3(...d.t)); }
  }
}
const cam = new THREE.PerspectiveCamera(22, W / H, 0.01, 50);
const b = sc.bounds; const c = new THREE.Vector3((b.min[0] + b.max[0]) / 2, (b.min[1] + b.max[1]) / 2, (b.min[2] + b.max[2]) / 2);
function setVis(mode) {
  for (const [id, m] of Object.entries(nodes)) {
    const p = info[id]; const md = mats[p.material] || {};
    const internal = p.internal; const shell = !internal && p.kind === 'printed';
    m.material.transparent = false; m.material.opacity = 1; m.material.depthWrite = true; m.visible = true;
    if (edges[id]) edges[id].visible = true;
    if (mode === 'studio' && internal) { m.visible = false; if (edges[id]) edges[id].visible = false; }
    if (mode === 'xray' && (shell || ['monitor_housings', 'display_screen', 'laptop_body'].includes(id))) {
      m.material.transparent = true; m.material.opacity = 0.18; m.material.depthWrite = false; }
    if (pose[p.group] && pose[p.group].hidden) { m.visible = false; if (edges[id]) edges[id].visible = false; }
  }
}
function clip(planes) {
  for (const m of Object.values(nodes)) m.material.clippingPlanes = planes;
  for (const e of Object.values(edges)) e.material.clippingPlanes = planes;
}
function look(az, el, dist, target, fov = 22) {
  cam.fov = fov; cam.updateProjectionMatrix();
  const a = az * Math.PI / 180, e = el * Math.PI / 180;
  cam.position.set(target.x + dist * Math.sin(a) * Math.cos(e), target.y + dist * Math.sin(e), target.z + dist * Math.cos(a) * Math.cos(e));
  cam.lookAt(target);
}
window.render = (view) => {
  clip([]); setVis(view === 'xray' || view === 'side' ? 'xray' : (view === 'hero' || view === 'front' || view === 'back' || view === 'dock') ? 'studio' : 'all');
  const T = c.clone();
  if (view === 'hero') look(-28, 16, 3.3, T);
  if (view === 'xray') look(-28, 22, 3.3, T);
  if (view === 'back') look(150, 18, 3.3, T);
  if (view === 'front') look(0, 4, 3.6, T);
  if (view === 'top') { look(0, 89.5, 3.9, new THREE.Vector3(c.x, 0, c.z)); }
  if (view === 'side') look(90, 6, 4.0, T, 16);
  if (view === 'dock') look(35, 16, 1.6, new THREE.Vector3(0.68, 0.12, 0.0));
  if (view === 'section') { clip([new THREE.Plane(new THREE.Vector3(-1, 0, 0), -0.203)]); look(90, 8, 1.3, new THREE.Vector3(-0.2, 0.05, 0.0), 24); }
  if (view === 'zsection') { clip([new THREE.Plane(new THREE.Vector3(0, 0, 1), 0.138)]); look(0, 6, 3.6, new THREE.Vector3(0, 0.2, -0.14), 24); }
  r.render(scene, cam);
  return r.domElement.toDataURL('image/png');
};
window.ready = true;
</script></body></html>`;

const server = http.createServer((req, res) => {
  const u = decodeURIComponent(req.url.split('?')[0]);
  let f = null;
  if (u === '/' || u === '/index.html') { res.writeHead(200, { 'content-type': 'text/html' }); return res.end(PAGE); }
  if (u.startsWith('/three/')) f = path.join(THREE_DIR, u.slice(7));
  if (u.startsWith('/model/')) f = path.join(dir, 'model', u.slice(7));
  if (!f || !fs.existsSync(f)) { res.writeHead(404); return res.end(); }
  const type = f.endsWith('.js') ? 'text/javascript' : f.endsWith('.json') ? 'application/json' : 'application/octet-stream';
  res.writeHead(200, { 'content-type': type }); fs.createReadStream(f).pipe(res);
});
await new Promise(r => server.listen(0, r));
const port = server.address().port;
const browser = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
const page = await browser.newPage({ viewport: { width: W, height: H } });
page.on('console', m => { if (m.type() === 'error') console.error('page:', m.text()); });
page.on('pageerror', e => console.error('page error:', e.message));
await page.goto(`http://127.0.0.1:${port}/`);
await page.waitForFunction(() => window.ready === true, null, { timeout: 120000 });
for (const v of views) {
  const url = await page.evaluate((v) => window.render(v), v);
  fs.writeFileSync(path.join(outDir, v + '.png'), Buffer.from(url.split(',')[1], 'base64'));
  console.log('wrote', path.join(outDir, v + '.png'));
}
await browser.close(); server.close();
