// Renders the stills listed in SPEC.md section 4 with the viewer itself: the real bundle, served the way the APK
// serves it, in headless Chromium. Each still is drawn supersampled at 'high' quality, downsampled in the page (2D
// canvas, high-quality smoothing) and saved as JPEG into android/app/src/main/assets/renders/.
//
//   node tools/render_stills.mjs                 every still (run `node build.mjs` first; `npm run stills` does both)
//   node tools/render_stills.mjs hero part-      only stills whose name contains "hero" or "part-"
//   options: --ss 2      supersampling factor (1 = quick look while tuning)
//            --out DIR   write somewhere else (e.g. a scratch folder) instead of the app's assets
//            --q 0.85    JPEG quality
import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { startServer } from '../test/serve.mjs';

const here = path.dirname(fileURLToPath(import.meta.url));
const RENDERS = path.resolve(here, '../../android/app/src/main/assets/renders');
const GL_ARGS = ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'];

const WIDE = [1600, 900];
const SQUARE = [900, 900];

const BASE_STATE = {
  mode: 'work', style: 'studio', finish: 'titanium', amber: 0.8, explode: 0, section: null, dims: false,
  autorotate: false, isolate: null, selected: null, quality: 'high', cinematic: false,
};

// Camera specs extend the viewer's presets (src/cameras.js): az/el in degrees, fit = what to frame, pad = free margin,
// lift/shift = where the framed content sits, fov = vertical lens angle (stills use a longer lens than the live view).
const HERO = { preset: 'hero', az: -23, el: 13, fov: 21, pad: 0.1, lift: 0.02 };
const DOCK = { preset: 'dock', az: 33, el: 14, fov: 22, pad: 0.08, lift: 0.0, fit: { groups: ['dock', 'laptop'], reach: true }, minDistance: 0.3 };
// the finishes: the whole station from the dock side, where the titanium (base rim, cradle, frame) catches the light
const FINISH = { preset: 'hero', az: 48, el: 14, fov: 20, pad: 0.03, lift: 0.0 };
const LIT = 1.12; // studio stills sit a touch brighter than the live view (which leaves room for the app's chrome)

/** The SPEC list (wide stills). part-<group>.jpg are added from scene.json's groups at run time. */
export const STILLS = [
  { name: 'hero-work', state: { mode: 'work' }, camera: HERO, exposure: LIT },
  { name: 'hero-stow', state: { mode: 'stow' }, camera: { ...HERO, el: 16 }, exposure: LIT },
  { name: 'hero-standalone', state: { mode: 'standalone' }, camera: HERO, exposure: LIT },
  // align and lower share one camera (framing the laptop's whole travel); release moves in on the lit press-release
  // latch. All three are centred on the dock: the app crops them to narrow portrait cards.
  { name: 'dock-align', state: { mode: 'stow' }, dock: 'align', camera: DOCK, exposure: LIT },
  { name: 'dock-lower', state: { mode: 'stow' }, dock: 'lower', camera: DOCK, exposure: LIT },
  { name: 'dock-release', state: { mode: 'stow' }, dock: 'release', exposure: LIT,
    camera: { ...DOCK, az: 30, el: 12, pad: 0.1, fit: { groups: ['dock'] }, minDistance: 0.2 } },
  // both pockets from above, devices charging
  { name: 'trays', state: { mode: 'stow' }, camera: { preset: 'trays', az: -14, el: 60, fov: 22, pad: 0.08, lift: 0.08 }, exposure: LIT },
  { name: 'display', state: { mode: 'work' }, camera: { preset: 'display', az: -20, el: 7, fov: 20, pad: 0.05, lift: 0.0 }, exposure: LIT },
  { name: 'cad', state: { mode: 'work', style: 'cad' }, camera: { ...HERO, az: -32, el: 24, pad: 0.08, lift: 0 } },
  { name: 'xray', state: { mode: 'work', style: 'xray' }, camera: { ...HERO, az: -26, el: 20, pad: 0.08, lift: 0 } },
  { name: 'exploded', state: { mode: 'stow', explode: 1 }, camera: { ...HERO, az: -26, el: 18, pad: 0.03, fov: 20, lift: 0 }, exposure: 1.2 },
  { name: 'blueprint', state: { mode: 'work', style: 'blueprint' }, camera: { ...HERO, az: -34, el: 26, pad: 0.08, lift: 0 } },
  // a cut through the keyboard pocket: shell profile, pad, coil and the keyboard itself, seen square on
  { name: 'section', state: { mode: 'stow', section: { axis: 'x', t: 0.31 } }, exposure: LIT,
    camera: { ...HERO, az: -70, el: 14, pad: 0.02, fov: 20, lift: 0, fit: { groups: ['base', 'keyboard', 'internals'], internal: true, section: 0.3 } } },
  { name: 'finish-titanium', state: { mode: 'work', finish: 'titanium' }, camera: FINISH, exposure: LIT },
  { name: 'finish-graphite', state: { mode: 'work', finish: 'graphite' }, camera: FINISH, exposure: LIT },
  { name: 'finish-oxblood', state: { mode: 'work', finish: 'oxblood' }, camera: FINISH, exposure: LIT },
  // Night shift: low, from the dock side, amber up (the live cinematic camera orbits at about this height)
  { name: 'night', state: { mode: 'stow', amber: 1 }, camera: { ...HERO, az: 34, el: 6, fov: 24, pad: -0.02, lift: -0.01 }, exposure: 0.95 },
  { name: 'amber-off', state: { mode: 'work', amber: 0 }, camera: HERO, exposure: LIT },
];

// Art direction for the isolated-group stills (any group scene.json adds later gets the default view).
const PART_VIEW = {
  default: { az: -30, el: 24 },
  display: { az: -52, el: 8, pad: 0.05 },
  stand: { az: -34, el: 16 },
  base: { az: -40, el: 34, pad: 0.05 },
  dock: { az: 38, el: 22 },
  laptop: { az: 50, el: 14 },
  keyboard: { az: -30, el: 32, pad: 0.08, exposure: 1.2 },
  mouse: { az: -36, el: 28, pad: 0.2 },
  deskmat: { az: -40, el: 34, pad: 0.05, exposure: 1.6 },
  internals: { az: -58, el: 52, pad: 0.03 },
};
// groups that only exist (or only make sense) on the desk in work mode
const PART_MODE = { deskmat: 'work', keyboard: 'work', mouse: 'work' };

function partStills(groups) {
  return groups.map((g) => {
    const { exposure, ...v } = { pad: 0.1, ...PART_VIEW.default, ...(PART_VIEW[g.id] || {}) };
    const internal = g.id === 'internals'; // SPEC: the internals still is the x-ray view
    return {
      name: `part-${g.id}`,
      size: SQUARE,
      state: { mode: PART_MODE[g.id] || 'stow', isolate: g.id, style: internal ? 'xray' : 'studio' },
      camera: { preset: 'hero', fov: 24, lift: 0.0, ...v, fit: { groups: [g.id], internal }, minDistance: 0.1 },
      exposure: internal ? 1 : exposure || LIT,
    };
  });
}

/**
 * Renders `stills` ([{ name, state, camera, dock?, size?, exposure? }]) into outDir. Loads the viewer once per frame size.
 * Returns the number of failures.
 */
export async function renderStills(stills, { outDir = RENDERS, ss = 2, quality = 0.85, log = console.log } = {}) {
  fs.mkdirSync(outDir, { recursive: true });
  const srv = await startServer(0);
  const browser = await chromium.launch({ args: GL_ARGS });
  let failed = 0;
  try {
    const bySize = new Map();
    for (const s of stills) {
      const key = (s.size || WIDE).join('x');
      if (!bySize.has(key)) bySize.set(key, []);
      bySize.get(key).push(s);
    }
    for (const [key, list] of bySize) {
      const [w, h] = key.split('x').map(Number);
      const page = await browser.newPage({ viewport: { width: w, height: h }, deviceScaleFactor: 1 });
      const msgs = [];
      page.on('console', (m) => { if (m.type() === 'error' || m.type() === 'warning') msgs.push(`${m.type()}: ${m.text()}`); });
      page.on('pageerror', (e) => msgs.push(`pageerror: ${e.message}`));
      const first = { ...BASE_STATE, ...list[0].state };
      await page.goto(`${srv.viewerUrl}?state=${encodeURIComponent(JSON.stringify(first))}`, { waitUntil: 'commit' });
      await page.waitForFunction(() => window.NA && (window.NA.ready || window.NA.error), null, { timeout: 240000, polling: 250 });
      const err = await page.evaluate(() => window.NA.error);
      if (err) throw new Error(`viewer failed: ${err}`);
      await page.evaluate(async (ss) => {
        const v = window.NA._viewer;
        window.NA._capture(true); // no LED breathing: every frame is final
        v.forcePixelRatio = ss; // supersample; the page box-filters it back down below
        v.resize(true);
        await window.NA.idle(60000);
      }, ss);
      for (const still of list) {
        const t1 = Date.now();
        const res = await page.evaluate(async ({ still, base, w, h, quality }) => {
          const NA = window.NA, v = NA._viewer;
          NA.dock('reset');
          NA.setState({ ...base, ...still.state });
          v.tweens.finishAll();
          v.fader.finishAll();
          if (still.dock) {
            NA.dock(still.dock);
            v.tweens.finishAll();
          }
          const cam = v.stillCamera(still.camera);
          v.renderer.toneMappingExposure = still.exposure || 1;
          v.requestRender();
          await NA.idle(120000);
          // one more frame: shadow map, contact shadow and desk reflection have all caught up with the final layout
          v.renderer.shadowMap.needsUpdate = true;
          v.stage.contact.dirty = true;
          v.render();
          const c = document.createElement('canvas');
          c.width = w;
          c.height = h;
          const g = c.getContext('2d');
          g.imageSmoothingEnabled = true;
          g.imageSmoothingQuality = 'high';
          g.drawImage(v.canvas, 0, 0, w, h); // same task as the render, so the WebGL drawing buffer is still intact
          const info = v.renderer.info.render;
          v.renderer.toneMappingExposure = 1;
          return { url: c.toDataURL('image/jpeg', quality), cam, calls: info.calls, tris: info.triangles };
        }, { still, base: BASE_STATE, w, h, quality });
        const file = path.join(outDir, `${still.name}.jpg`);
        const buf = Buffer.from(res.url.split(',')[1], 'base64');
        if (buf.length < 8000) {
          failed++;
          log(`FAIL ${still.name}: suspiciously small JPEG (${buf.length} B)`);
        }
        fs.writeFileSync(file, buf);
        log(`${still.name}.jpg ${w}x${h} ${(buf.length / 1024).toFixed(0)} KiB ${((Date.now() - t1) / 1000).toFixed(1)} s`);
      }
      for (const m of msgs) if (!/parallel_shader_compile|GPU stall|swiftshader|GL_CLOSE_PATH|ReadPixels/i.test(m)) log('   ' + m.slice(0, 300));
      await page.close();
    }
  } finally {
    await browser.close();
    await srv.close();
  }
  return failed;
}

/** Every still the SPEC lists, with the part-<group> stills built from scene.json's groups. */
export function allStills() {
  const sceneJson = JSON.parse(fs.readFileSync(path.resolve(here, '../../cad/export/model/scene.json'), 'utf8'));
  return [...STILLS, ...partStills(sceneJson.groups || [])];
}

async function main() {
  const args = process.argv.slice(2);
  const opt = (k, d) => { const i = args.indexOf(k); return i >= 0 ? args.splice(i, 2)[1] : d; };
  const ss = Number(opt('--ss', 2));
  const outDir = path.resolve(opt('--out', RENDERS));
  const quality = Number(opt('--q', 0.85));
  const filters = args.filter((a) => !a.startsWith('--'));
  const list = allStills().filter((s) => !filters.length || filters.some((f) => s.name.includes(f)));
  const t0 = Date.now();
  const failed = await renderStills(list, { outDir, ss, quality });
  console.log(`${failed ? failed + ' FAILED, ' : ''}${list.length} stills in ${((Date.now() - t0) / 1000).toFixed(0)} s -> ${outDir}`);
  process.exit(failed ? 1 : 0);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((e) => {
    console.error(e);
    process.exit(1);
  });
}
