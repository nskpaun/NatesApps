// Preview renders of the pocket-section POC (headless Chromium + three.js from night-array/viewer/node_modules).
//
//   node night-array/kit/poc/render_preview.mjs <build dir> <out dir>
//
// <build dir> holds scene.json + the assembly-position STLs that pocket_section.py writes.  Writes
// assembled.png, exploded.png, underside.png, section.png (cut through the keyboard pad) and detail.png (exploded
// keyboard carrier stack) to <out dir>.
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
const dir = path.resolve(process.argv[2] || path.join(here, 'build'));
const outDir = path.resolve(process.argv[3] || path.join(here, 'preview'));
fs.mkdirSync(outDir, { recursive: true });
const W = 1600, H = 1000;

const PAGE = `<!doctype html><html><head><meta charset="utf-8"><style>html,body{margin:0;background:#f2f1ee}</style>
<script type="importmap">{"imports":{"three":"/three/build/three.module.js","three/addons/":"/three/examples/jsm/"}}</script>
</head><body><script type="module">
import * as THREE from 'three';
import { STLLoader } from 'three/addons/loaders/STLLoader.js';
const W = ${W}, H = ${H};
const r = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
r.setSize(W, H); r.localClippingEnabled = true; r.outputColorSpace = THREE.SRGBColorSpace;
document.body.appendChild(r.domElement);
const scene = new THREE.Scene(); scene.background = new THREE.Color('#f2f1ee');
scene.add(new THREE.HemisphereLight(0xffffff, 0x8a8478, 1.6));
const d1 = new THREE.DirectionalLight(0xffffff, 1.9); d1.position.set(-300, -500, 700); scene.add(d1);
const d2 = new THREE.DirectionalLight(0xffffff, 0.8); d2.position.set(400, 600, -300); scene.add(d2);
const sc = await (await fetch('/build/scene.json')).json();
const loader = new STLLoader();
const items = [];
for (const p of sc.parts) {
  const g = await new Promise((res, rej) => loader.load('/build/' + p.file, res, undefined, rej));
  g.computeVertexNormals();
  const m = new THREE.Mesh(g, new THREE.MeshStandardMaterial({ color: p.color, roughness: 0.75, metalness: 0.0,
    side: THREE.DoubleSide, transparent: p.opacity < 1, opacity: p.opacity, flatShading: false }));
  const e = new THREE.LineSegments(new THREE.EdgesGeometry(g, 28), new THREE.LineBasicMaterial({ color: 0x000000, transparent: true, opacity: 0.35 }));
  const grp = new THREE.Group(); grp.add(m); grp.add(e); scene.add(grp);
  items.push({ p, grp, m, e });
}
const [b0, b1] = sc.bounds;
const C = new THREE.Vector3((b0[0] + b1[0]) / 2, (b0[1] + b1[1]) / 2, (b0[2] + b1[2]) / 2);
const cam = new THREE.PerspectiveCamera(24, W / H, 1, 20000); cam.up.set(0, 0, 1);
function look(az, el, dist, t) {   // az 0 = from the front (-y), positive = from the right
  const a = az * Math.PI / 180, e = el * Math.PI / 180;
  cam.position.set(t.x + dist * Math.sin(a) * Math.cos(e), t.y - dist * Math.cos(a) * Math.cos(e), t.z + dist * Math.sin(e));
  cam.lookAt(t);
}
function setup(explode, planes) {
  for (const it of items) {
    const k = explode ? 1 : 0;
    it.grp.position.set(...it.p.explode.map(v => v * k));
    it.m.material.clippingPlanes = planes; it.e.material.clippingPlanes = planes;
    it.m.material.opacity = it.p.opacity; it.m.material.transparent = it.p.opacity < 1;
  }
}
window.render = (view) => {
  if (view === 'assembled') { setup(false, []); look(-28, 30, 1350, C); }
  if (view === 'exploded') { setup(true, []); look(-30, 22, 1650, new THREE.Vector3(C.x, C.y, C.z - 50)); }
  if (view === 'underside') { setup(false, []); look(-20, -55, 1300, C); }
  if (view === 'section') {   // cut through the keyboard pad centre, looking from the front
    setup(false, [new THREE.Plane(new THREE.Vector3(0, 1, 0), -sc.section_y)]);
    look(-4, 3, 420, new THREE.Vector3(125, sc.section_y, 20));
  }
  if (view === 'detail') { setup(true, []); look(-35, 35, 620, new THREE.Vector3(55, 109, -150)); }
  r.render(scene, cam);
  return r.domElement.toDataURL('image/png');
};
window.ready = true;
</script></body></html>`;

const server = http.createServer((rq, res) => {
  const u = decodeURIComponent(rq.url.split('?')[0]);
  if (u === '/' ) { res.writeHead(200, { 'content-type': 'text/html' }); return res.end(PAGE); }
  let f = null;
  if (u.startsWith('/three/')) f = path.join(THREE_DIR, u.slice(7));
  if (u.startsWith('/build/')) f = path.join(dir, u.slice(7));
  if (!f || !fs.existsSync(f)) { res.writeHead(404); return res.end(); }
  res.writeHead(200, { 'content-type': f.endsWith('.js') ? 'text/javascript' : f.endsWith('.json') ? 'application/json' : 'application/octet-stream' });
  fs.createReadStream(f).pipe(res);
});
await new Promise(r => server.listen(0, r));
const browser = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
const page = await browser.newPage({ viewport: { width: W, height: H } });
page.on('pageerror', e => console.error('page error:', e.message));
page.on('console', m => { if (m.type() === 'error') console.error('page:', m.text()); });
await page.goto(`http://127.0.0.1:${server.address().port}/`);
await page.waitForFunction(() => window.ready === true, null, { timeout: 180000 });
for (const v of ['assembled', 'exploded', 'underside', 'section', 'detail']) {
  const url = await page.evaluate(v => window.render(v), v);
  fs.writeFileSync(path.join(outDir, v + '.png'), Buffer.from(url.split(',')[1], 'base64'));
  console.log('wrote', path.join(outDir, v + '.png'));
}
await browser.close(); server.close();
