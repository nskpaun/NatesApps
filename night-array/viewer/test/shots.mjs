// Visual check: renders a set of views through the real bundle (served like the APK serves it) and writes
// PNGs to an output folder.  node test/shots.mjs <outDir> [filter] [--portrait|--landscape|--both]
// Each shot: { name, state, camera, dock, frame, w, h }.
import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';
import { startServer } from './serve.mjs';

const GL_ARGS = ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'];

const SIZES = { portrait: [390, 520], landscape: [844, 390] };

export const SHOTS = [
  { name: 'work-hero', state: { mode: 'work' }, camera: 'hero' },
  { name: 'stow-hero', state: { mode: 'stow' }, camera: 'hero' },
  { name: 'standalone-hero', state: { mode: 'standalone' }, camera: 'hero' },
  { name: 'work-front', state: { mode: 'work' }, camera: 'front' },
  { name: 'stow-dock', state: { mode: 'stow' }, camera: 'dock' },
  { name: 'stow-trays', state: { mode: 'stow' }, camera: 'trays' },
  { name: 'work-display', state: { mode: 'work' }, camera: 'display' },
  { name: 'work-top', state: { mode: 'work' }, camera: 'top' },
  { name: 'work-side', state: { mode: 'work' }, camera: 'side' },
  { name: 'stow-back', state: { mode: 'stow' }, camera: 'back' },
  { name: 'finish-graphite', state: { mode: 'work', finish: 'graphite' }, camera: 'hero' },
  { name: 'finish-oxblood', state: { mode: 'work', finish: 'oxblood' }, camera: 'hero' },
  { name: 'amber-off', state: { mode: 'work', amber: 0 }, camera: 'hero' },
  { name: 'dock-align', state: { mode: 'stow' }, camera: 'dock', dock: 'align' },
];

const DEFAULTS = { mode: 'work', style: 'studio', finish: 'titanium', amber: 0.8, explode: 0, section: null, dims: false, autorotate: false, isolate: null, selected: null, quality: 'high', cinematic: false };

/** Loads the viewer once per viewport size and walks through the shots (state + camera jump, then screenshot). */
export async function shoot({ outDir, filter = null, sizes = ['portrait', 'landscape'], dpr = 2, log = console.log, extra = [], shots = null, fresh = false }) {
  fs.mkdirSync(outDir, { recursive: true });
  const srv = await startServer(0);
  const browser = await chromium.launch({ args: GL_ARGS });
  const results = [];
  const list = (shots || [...SHOTS, ...extra]).filter((s) => !filter || s.name.includes(filter));
  try {
    for (const sz of sizes) {
      const [w, h] = SIZES[sz] || sz;
      let page = null;
      const msgs = [];
      for (const shot of list) {
        if (!page || fresh || shot.w || shot.dpr) {
          if (page) await page.close();
          page = await browser.newPage({ viewport: { width: shot.w || w, height: shot.h || h }, deviceScaleFactor: shot.dpr || dpr });
          page.on('console', (m) => msgs.push(`${m.type()}: ${m.text()}`));
          page.on('pageerror', (e) => msgs.push(`pageerror: ${e.message}`));
          const url = `${srv.viewerUrl}?state=${encodeURIComponent(JSON.stringify({ ...DEFAULTS, ...(shot.state || {}) }))}`;
          await page.goto(url, { waitUntil: 'commit' });
          await page.waitForFunction(() => window.NA && (window.NA.ready || window.NA.error), null, { timeout: 180000, polling: 200 });
          await page.waitForTimeout(700); // css fade-in
        }
        const t0 = Date.now();
        const err = await page.evaluate(async (shot) => {
          const NA = window.NA;
          if (NA.error) return NA.error;
          const v = NA._viewer;
          NA._capture(true);
          NA.dock('reset');
          NA.setState({ ...shot.defaults, ...(shot.state || {}) });
          v.tweens.finishAll();
          if (shot.dock) NA.dock(shot.dock);
          v.tweens.finishAll();
          NA.camera(shot.camera || 'hero');
          if (shot.frame) NA.frame(shot.frame);
          v.tweens.finishAll();
          v.requestRender();
          await NA.idle(60000);
          return null;
        }, { ...shot, defaults: DEFAULTS });
        const file = path.join(outDir, `${shot.name}-${typeof sz === 'string' ? sz : `${w}x${h}`}.png`);
        await page.screenshot({ path: file });
        results.push({ file, ms: Date.now() - t0, err });
        log(`${path.basename(file)} ${Date.now() - t0} ms${err ? ' ERROR ' + err : ''}`);
      }
      for (const m of msgs) if (/error|warn/i.test(m) && !/parallel_shader_compile|GPU stall|swiftshader/i.test(m)) log('   ' + m.slice(0, 300));
      if (page) await page.close();
    }
  } finally {
    await browser.close();
    await srv.close();
  }
  return results;
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const args = process.argv.slice(2);
  const outDir = args[0] || 'shots';
  const filter = args[1] && !args[1].startsWith('--') ? args[1] : null;
  const sizes = args.includes('--portrait') ? ['portrait'] : args.includes('--landscape') ? ['landscape'] : ['portrait', 'landscape'];
  await shoot({ outDir, filter, sizes });
}
