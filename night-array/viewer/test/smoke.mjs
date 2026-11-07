// Smoke test of the viewer contract (SPEC.md section 4) through the real bundle, served like the APK serves it.
//   node test/smoke.mjs        (run `node build.mjs` first; `npm test` does both)
import { chromium } from 'playwright';
import { startServer } from './serve.mjs';

const GL_ARGS = ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'];
const VIEW = { width: 390, height: 520 };

let failures = 0;
const ok = (cond, msg) => {
  console.log(`${cond ? 'ok  ' : 'FAIL'} ${msg}`);
  if (!cond) failures++;
};

// Pretend to be the app: a NightArrayHost bridge that records events.
const HOST = () => {
  window.__events = [];
  window.NightArrayHost = { post: (s) => window.__events.push(JSON.parse(s)) };
};

async function open(browser, srv, { state = {}, init = [], route = null } = {}) {
  const page = await browser.newPage({ viewport: VIEW, deviceScaleFactor: 1 });
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  for (const fn of init) await page.addInitScript(fn);
  if (route) await page.route(route.match, route.handler);
  await page.goto(`${srv.viewerUrl}?state=${encodeURIComponent(JSON.stringify(state))}`, { waitUntil: 'commit' });
  return { page, errors };
}

const waitEvent = (page, type, timeout = 120000) =>
  page.waitForFunction((t) => (window.__events || []).some((e) => e.type === t), type, { timeout, polling: 100 });

const srv = await startServer(0);
const browser = await chromium.launch({ args: GL_ARGS });
try {
  // 1. transparent until ready, queued calls, ready event, initial state
  {
    const { page, errors } = await open(browser, srv, {
      state: { mode: 'stow', finish: 'graphite', amber: 0.4, quality: 'balanced' },
      init: [HOST, () => {
        document.addEventListener('DOMContentLoaded', () => {
          window.NA.setState({ finish: 'oxblood' });
          window.NA.camera('dock');
          window.NA.setState('{"amber": 0.6}');
        });
      }],
    });
    await page.waitForFunction(() => !!document.querySelector('#stage canvas'), null, { timeout: 30000 });
    const before = await page.evaluate(() => ({
      ready: window.NA.ready,
      opacity: getComputedStyle(document.querySelector('#stage canvas')).opacity,
      htmlBg: getComputedStyle(document.documentElement).backgroundColor,
      bodyBg: getComputedStyle(document.body).backgroundColor,
      standalone: document.documentElement.classList.contains('standalone-page'),
    }));
    ok(!before.ready && before.opacity === '0', `canvas hidden before ready (opacity ${before.opacity})`);
    ok(/rgba\(0, 0, 0, 0\)|transparent/.test(before.htmlBg) && /rgba\(0, 0, 0, 0\)|transparent/.test(before.bodyBg) && !before.standalone,
      `page background transparent in the app (${before.htmlBg} / ${before.bodyBg})`);
    if (!before.ready) {
      const shot = await page.screenshot({ omitBackground: true, clip: { x: 0, y: 0, width: 4, height: 4 } });
      ok(shot.length > 0, 'pre-ready screenshot taken (transparent page)');
    }
    await waitEvent(page, 'ready');
    const after = await page.evaluate(() => ({
      events: window.__events.map((e) => e.type),
      state: window.NA.getState(),
      cam: window.NA._viewer.cameraName,
      timings: window.NA._viewer.timings,
    }));
    ok(after.events.filter((t) => t === 'ready').length === 1, `exactly one ready event (${after.events.join(',')})`);
    ok(after.state.mode === 'stow' && after.state.quality === 'balanced', '?state= applied (mode stow, quality balanced)');
    ok(after.state.finish === 'oxblood' && after.state.amber === 0.6, 'setState before load merged (finish oxblood, amber 0.6 from JSON string)');
    ok(after.cam === 'dock', `camera command queued before load ran (${after.cam})`);
    console.log('     timings', JSON.stringify(after.timings));
    await page.waitForTimeout(800);
    const opacity = await page.evaluate(() => getComputedStyle(document.querySelector('#stage canvas')).opacity);
    ok(opacity === '1', `canvas faded in after ready (opacity ${opacity})`);

    // partial merge + validation
    const merged = await page.evaluate(() => window.NA.setState({ explode: 2, mode: 'bogus', dims: true, nope: 1 }));
    ok(merged.explode === 1 && merged.mode === 'stow' && merged.dims === true && !('nope' in merged), 'setState clamps, ignores invalid and unknown keys');
    await page.evaluate(() => window.NA.setState({ explode: 0, dims: false }));

    // render on demand: idle = no frames (work mode: in stow the charge LEDs breathe, which does render)
    await page.evaluate(() => { window.NA.setState({ mode: 'work' }); return window.NA.idle(30000); });
    const f0 = await page.evaluate(() => window.NA._viewer.renderer.info.render.frame);
    await page.waitForTimeout(1500);
    const f1 = await page.evaluate(() => window.NA._viewer.renderer.info.render.frame);
    ok(f1 === f0, `no frames while idle (${f0} -> ${f1})`);

    // camera presets all resolve
    const cams = await page.evaluate(async () => {
      const out = {};
      for (const c of ['hero', 'front', 'top', 'side', 'back', 'dock', 'trays', 'display']) {
        window.NA.camera(c);
        window.NA._viewer.tweens.finishAll();
        out[c] = window.NA._viewer.camera.position.toArray().every(Number.isFinite) && window.NA._viewer.camera.position.y > 0;
      }
      return out;
    });
    ok(Object.values(cams).every(Boolean), `all camera presets land above the desk ${JSON.stringify(cams)}`);

    // frame(group)
    const framed = await page.evaluate(() => {
      window.NA.frame('mouse');
      window.NA._viewer.tweens.finishAll();
      const v = window.NA._viewer;
      return v.camera.position.distanceTo(v.controls.target);
    });
    ok(framed > 0.1 && framed < 1.2, `frame('mouse') moves in close (${framed.toFixed(2)} m)`);

    // pause on hidden
    const paused = await page.evaluate(async () => {
      window.NA.setState({ autorotate: true });
      await new Promise((r) => setTimeout(r, 300));
      Object.defineProperty(document, 'hidden', { configurable: true, get: () => true });
      document.dispatchEvent(new Event('visibilitychange'));
      const v = window.NA._viewer;
      const a = v.renderer.info.render.frame;
      await new Promise((r) => setTimeout(r, 1200));
      const b = v.renderer.info.render.frame;
      Object.defineProperty(document, 'hidden', { configurable: true, get: () => false });
      document.dispatchEvent(new Event('visibilitychange'));
      window.NA.setState({ autorotate: false });
      return { a, b };
    });
    ok(paused.a === paused.b, `no frames while document.hidden (${paused.a} -> ${paused.b})`);

    // context loss + restore
    const ctx = await page.evaluate(async () => {
      const v = window.NA._viewer;
      const ext = v.renderer.getContext().getExtension('WEBGL_lose_context');
      if (!ext) return 'no-ext';
      ext.loseContext();
      await new Promise((r) => setTimeout(r, 300));
      const lost = v.contextLost;
      ext.restoreContext();
      await new Promise((r) => setTimeout(r, 300));
      await window.NA.idle(60000);
      return { lost, restored: !v.contextLost, frame: v.renderer.info.render.frame };
    });
    ok(ctx === 'no-ext' || (ctx.lost && ctx.restored), `webglcontextlost/restored handled ${JSON.stringify(ctx)}`);
    ok(errors.length === 0, `no page errors (${errors.slice(0, 3).join(' | ')})`);
    await page.close();
  }

  // 2. picking + dock sequence events
  {
    const { page, errors } = await open(browser, srv, { state: { mode: 'stow' }, init: [HOST] });
    await waitEvent(page, 'ready');
    await page.evaluate(() => { window.NA._capture(true); window.NA.camera('hero'); window.NA._viewer.tweens.finishAll(); });
    // tap the middle of the base (project its centre to the screen)
    const pt = await page.evaluate(() => {
      const v = window.NA._viewer;
      const p = v.model.groups.get('base').node.getWorldPosition(new v.camera.position.constructor());
      p.x = -0.45; // front rim of the base, left of the pockets
      p.y = 0.036;
      p.z = 0.143;
      p.project(v.camera);
      return { x: (p.x + 1) / 2 * innerWidth, y: (1 - p.y) / 2 * innerHeight };
    });
    await page.mouse.click(pt.x, pt.y);
    await page.mouse.click(5, 5);
    await page.waitForTimeout(300);
    const picks = await page.evaluate(() => window.__events.filter((e) => e.type === 'pick'));
    ok(picks.length === 2 && picks[0].group === 'base' && picks[1].group === null, `tap picks: ${JSON.stringify(picks)}`);
    // a drag is not a pick
    await page.mouse.move(200, 300);
    await page.mouse.down();
    await page.mouse.move(260, 300, { steps: 5 });
    await page.mouse.up();
    await page.waitForTimeout(200);
    const picks2 = await page.evaluate(() => window.__events.filter((e) => e.type === 'pick').length);
    ok(picks2 === 2, 'drag does not emit pick');

    await page.evaluate(() => window.NA.dock('play'));
    await page.waitForFunction(() => window.__events.some((e) => e.type === 'dockStep' && e.step === 'done'), null, { timeout: 60000, polling: 100 });
    const steps = await page.evaluate(() => window.__events.filter((e) => e.type === 'dockStep').map((e) => e.step));
    ok(steps.join(',') === 'align,lower,release,lift,done', `dock play emits ${steps.join(',')}`);
    const latch = await page.evaluate(() => {
      window.NA.dock('release');
      window.NA._viewer.tweens.finishAll();
      const v = window.NA._viewer;
      const z = v.model.movables.get('dock_latch').node.position.z;
      window.NA.dock('reset');
      window.NA._viewer.tweens.finishAll();
      return { pressed: z, rest: v.model.movables.get('dock_latch').node.position.z };
    });
    ok(Math.abs(latch.pressed - latch.rest + 0.003) < 1e-6, `dock_latch sub-group moves -3 mm on release (${JSON.stringify(latch)})`);
    ok(errors.length === 0, `no page errors (${errors.slice(0, 3).join(' | ')})`);
    await page.close();
  }

  // 3. no WebGL2 -> error event + friendly message, page stays transparent
  {
    const { page } = await open(browser, srv, {
      init: [HOST, () => {
        const orig = HTMLCanvasElement.prototype.getContext;
        HTMLCanvasElement.prototype.getContext = function (type, ...a) { return type === 'webgl2' ? null : orig.call(this, type, ...a); };
      }],
    });
    await waitEvent(page, 'error', 30000);
    const r = await page.evaluate(() => ({
      evt: window.__events.find((e) => e.type === 'error'),
      msg: !document.getElementById('msg').hidden && document.getElementById('msg').textContent,
      ready: window.__events.some((e) => e.type === 'ready'),
      queued: window.NA.camera('hero'),
    }));
    ok(r.evt && /WebGL2/.test(r.evt.message) && !r.ready, `no WebGL2 -> error event "${r.evt && r.evt.message}"`);
    ok(!!r.msg, `friendly message shown: "${(r.msg || '').slice(0, 60)}..."`);
    await page.close();
  }

  // 4. model fails to load -> error event
  {
    const { page } = await open(browser, srv, {
      init: [HOST],
      route: { match: /station\.glb$/, handler: (route) => route.fulfill({ status: 404, body: 'nope' }) },
    });
    await waitEvent(page, 'error', 60000);
    const evt = await page.evaluate(() => window.__events.find((e) => e.type === 'error'));
    ok(!!evt, `missing model -> error event "${evt && evt.message}"`);
    await page.close();
  }

  // 5. desktop browser (no host) logs events to the console
  {
    const page = await browser.newPage({ viewport: VIEW });
    const logs = [];
    page.on('console', (m) => logs.push(m.text()));
    await page.goto(srv.viewerUrl, { waitUntil: 'commit' });
    await page.waitForFunction(() => window.NA && window.NA.ready, null, { timeout: 120000, polling: 200 });
    ok(logs.some((l) => l.includes('"type":"ready"')), 'without NightArrayHost, ready is console.logged');
    await page.close();
  }
} finally {
  await browser.close();
  await srv.close();
}
console.log(failures ? `\n${failures} FAILED` : '\nall passed');
process.exit(failures ? 1 : 0);
