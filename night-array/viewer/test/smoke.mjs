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
// Counts requestAnimationFrame calls (the render loop must go quiet when nothing changes).
const RAF_COUNTER = () => {
  window.__raf = 0;
  const raf = window.requestAnimationFrame.bind(window);
  window.requestAnimationFrame = (cb) => { window.__raf++; return raf(cb); };
};

/** Screen position (CSS px) of a group's visible bounds centre, optionally lifted to its top face. */
const groupPoint = (page, id, top = true) => page.evaluate(([id, top]) => {
  const v = window.NA._viewer;
  const b = v.model.bounds([id]);
  const c = b.getCenter(b.min.clone());
  if (top) c.y = b.max.y - 0.002;
  c.project(v.camera);
  const r = v.canvas.getBoundingClientRect();
  return { x: r.left + (c.x + 1) / 2 * r.width, y: r.top + (1 - c.y) / 2 * r.height };
}, [id, top]);
const picks = (page) => page.evaluate(() => window.__events.filter((e) => e.type === 'pick').map((e) => e.group));

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
      init: [HOST, RAF_COUNTER, () => {
        document.addEventListener('DOMContentLoaded', () => {
          window.NA.setState({ finish: 'oxblood' });
          window.NA.camera('dock');
          window.NA.dock('align');
          window.NA.frame('dock');
          window.NA.setState('{"amber": 0.6}');
          window.__preload = { ready: window.NA.ready, queued: window.NA.dock('lower') === true && window.NA.dock('align') === true };
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
    const pre = await page.evaluate(() => {
      const v = window.NA._viewer;
      const box = v.model.bounds(['dock']);
      const c = box.getCenter(box.min.clone());
      const out = { preload: window.__preload, dockStep: v.dockStep, framed: v.controls.target.distanceTo(c), dist: v.camera.position.distanceTo(v.controls.target) };
      window.NA.dock('reset');
      v.tweens.finishAll();
      return out;
    });
    ok(pre.preload && !pre.preload.ready && pre.preload.queued, `calls before load are accepted and queued ${JSON.stringify(pre.preload)}`);
    ok(pre.dockStep === 'align', `queued dock('align') applied (${pre.dockStep})`);
    ok(pre.framed < 0.12 && pre.dist < 1.2, `queued frame('dock') applied (target ${pre.framed.toFixed(3)} m from the dock, ${pre.dist.toFixed(2)} m away)`);
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
    await page.waitForTimeout(300);
    const f0 = await page.evaluate(() => [window.NA._viewer.renderer.info.render.frame, window.__raf]);
    await page.waitForTimeout(2000);
    const f1 = await page.evaluate(() => [window.NA._viewer.renderer.info.render.frame, window.__raf]);
    ok(f1[0] === f0[0] && f1[1] === f0[1], `idle: no renders and no rAF callbacks over 2 s (frames ${f0[0]} -> ${f1[0]}, rAF ${f0[1]} -> ${f1[1]})`);

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

  // 3. stage 2: modes, dock glow, styles, section, dims, highlight, isolate, picking rules
  {
    const { page, errors } = await open(browser, srv, { state: { mode: 'stow' }, init: [HOST] });
    await waitEvent(page, 'ready');
    // drive time by hand so mid-animation checks don't depend on SwiftShader's frame rate
    const r = await page.evaluate(() => {
      const NA = window.NA, v = NA._viewer, out = {};
      v.hidden = true; v.stopLoop();
      let T = 1e7;
      const step = (ms) => { T += ms; v.tweens.update(T); };
      const pos = (id) => v.model.movables.get(id).node.position.clone();
      step(0);
      // stow -> work: keyboard lifts over the rim, travels, lands on the mat; the mat fades in first
      const kb0 = pos('keyboard');
      NA.setState({ mode: 'work' });
      step(0);
      step(150);
      const mat = v.model.groups.get('deskmat').node;
      out.matFading = mat.visible && v.fader.isFading(mat);
      step(500);
      const kbMid = pos('keyboard');
      out.kbLifted = kbMid.y > kb0.y + 0.02;
      step(400);
      out.kbTravel = pos('keyboard').z > kb0.z + 0.05;
      v.tweens.finishAll();
      const kb1 = pos('keyboard');
      const pose = v.sj.poses.work.keyboard.t;
      out.kbLanded = Math.abs(kb1.z - (v.model.movables.get('keyboard').pivot.z + pose[2])) < 1e-6 && Math.abs(kb1.y - (v.model.movables.get('keyboard').pivot.y + pose[1])) < 1e-6;
      out.matShown = mat.visible && !v.fader.isFading(mat);
      out.matMaterialRestored = v.model.parts.get('deskmat').mesh.material === v.model.parts.get('deskmat').mesh.userData.studioMat;
      out.notCharging = !v.charging();
      // work -> stow: charging starts only after the devices land
      NA.setState({ mode: 'stow' });
      step(0); step(300);
      out.chargeWaits = !v.charging(performance.now());
      v.tweens.finishAll();
      out.matHidden = !mat.visible;
      v.chargeAt = 0;
      out.charging = v.charging();
      // standalone: laptop lifts out and is hidden; back in work it is seated again
      NA.setState({ mode: 'standalone' });
      step(0); step(600);
      const lap = v.model.movables.get('laptop');
      out.lapRising = lap.node.position.y > lap.pivot.y + 0.02 && lap.node.visible;
      v.tweens.finishAll();
      out.lapHidden = !lap.node.visible;
      NA.setState({ mode: 'work' });
      step(0); v.tweens.finishAll();
      out.lapBack = lap.node.visible && lap.node.position.distanceTo(v.laptopSeat) < 1e-6;
      // dock glow: seated -> connector glows; align -> not seated
      v.updateDockGlow(10);
      out.glowSeated = v.glow.seated && v.connectorMat.emissiveIntensity > 0;
      NA.dock('align'); v.tweens.finishAll(); v.updateDockGlow(10);
      out.glowLifted = !v.glow.seated && v.connectorMat.emissiveIntensity < 1e-3;
      NA.dock('lower'); v.tweens.finishAll(); v.updateDockGlow(0.016);
      out.flashOnSeat = v.glow.flash > 0.5;
      NA.dock('reset'); v.tweens.finishAll();
      // styles
      for (const st of ['cad', 'xray', 'blueprint', 'studio']) {
        NA.setState({ style: st }); v.tweens.finishAll();
        const lines = [...v.model.parts.values()].filter((p) => p.lineV && p.lineV.visible).length;
        const bgTex = !!(v.scene.background && v.scene.background.isTexture);
        const m = v.model.parts.get('base_shell').mesh.material.name;
        out[`style_${st}`] = { lines, bgTex, mat: m, desk: v.stage.desk.visible, grid: v.styles.grid.visible };
      }
      // section: clipping + caps on, then off
      NA.setState({ section: { axis: 'x', t: 0.5 } }); v.tweens.finishAll();
      const sm = v.model.parts.get('base_shell').mesh.material;
      out.sectionOn = v.section.active && v.section.cap.visible && !!sm.clippingPlanes && sm.clippingPlanes[0] === v.section.plane;
      const b = v.section.bounds;
      out.sectionPlane = Math.abs(-v.section.plane.constant - (b.min.x + b.max.x) / 2) < 1e-6;
      NA.setState({ section: { axis: 'z', t: 0.25 } }); v.tweens.finishAll();
      out.sectionZ = v.section.axis === 'z' && v.section.plane.normal.z === -1;
      NA.setState({ section: null }); step(0); v.tweens.finishAll();
      out.sectionOff = !v.section.active && !v.section.cap.visible && sm.clippingPlanes === null;
      // dims: work shows the work-offset dim; stow hides it; exploding hides all
      NA.setState({ mode: 'work', dims: true }); v.tweens.finishAll(); v.render();
      const shown = () => [...document.querySelectorAll('#labels .dim')].filter((e) => !e.classList.contains('hide')).map((e) => e.dataset.dim);
      out.dimsWork = shown();
      NA.setState({ mode: 'stow' }); v.tweens.finishAll(); v.render();
      out.dimsStow = shown();
      NA.setState({ explode: 0.6 }); v.tweens.finishAll(); v.render();
      out.dimsExploded = shown();
      NA.setState({ explode: 0, dims: false }); v.tweens.finishAll(); v.render();
      out.dimsOff = shown().length;
      // highlight
      NA.setState({ selected: 'keyboard' }); v.tweens.finishAll();
      out.rims = v.highlight.rims.length === v.model.groups.get('keyboard').parts.length && v.highlight.rims.every((r) => r.visible);
      NA.setState({ style: 'cad' }); v.tweens.finishAll();
      out.cadSelEdges = v.model.parts.get('keyboard_body').lineV.material === v.styles.lines.cad.sel;
      NA.setState({ style: 'studio', selected: null }); v.tweens.finishAll();
      out.rimsCleared = v.highlight.rims.length === 0;
      // isolate fades the others away and brings them back
      NA.setState({ isolate: 'mouse' }); step(0); step(200);
      out.isoFading = v.fader.active.size > 0;
      v.tweens.finishAll();
      out.isoHidden = [...v.model.groups.values()].filter((g) => g.id !== 'mouse').every((g) => !g.node.visible) && v.model.groups.get('mouse').node.visible;
      NA.setState({ isolate: null }); v.tweens.finishAll();
      out.isoBack = ['display', 'base', 'dock', 'keyboard'].every((id) => v.model.groups.get(id).node.visible);
      // style change cross-fades (not in capture mode)
      v.capture = false; v.hidden = false;
      NA.setState({ style: 'blueprint' });
      out.styleFade = v.styleFade.alpha > 0.9 && v.tweens.has('stylefade');
      v.tweens.finishAll();
      out.styleFadeDone = v.styleFade.alpha < 0.01;
      NA.setState({ style: 'studio' }); v.tweens.finishAll();
      v.requestRender();
      return out;
    });
    const bad = Object.entries(r).filter(([k, x]) => x === false).map(([k]) => k);
    ok(bad.length === 0, `mode choreography / dock glow / section / highlight / isolate checks ${bad.length ? 'FAILED: ' + bad.join(', ') : JSON.stringify(Object.keys(r).filter((k) => r[k] === true))}`);
    ok(r.style_cad.lines > 20 && r.style_cad.bgTex && /^cad-/.test(r.style_cad.mat) && !r.style_cad.desk && r.style_cad.grid, `cad style ${JSON.stringify(r.style_cad)}`);
    ok(r.style_xray.mat === 'xray-shell' && r.style_xray.bgTex && !r.style_xray.desk, `xray style ${JSON.stringify(r.style_xray)}`);
    ok(r.style_blueprint.lines > 20 && r.style_blueprint.mat === 'depth-only' && r.style_blueprint.grid, `blueprint style ${JSON.stringify(r.style_blueprint)}`);
    ok(r.style_studio.lines === 0 && r.style_studio.desk && !r.style_studio.grid, `studio style restored ${JSON.stringify(r.style_studio)}`);
    ok(r.dimsWork.includes('work_offset') && r.dimsWork.length >= 8, `dims in work: ${r.dimsWork.join(',')}`);
    ok(!r.dimsStow.includes('work_offset') && r.dimsStow.length === r.dimsWork.length - 1, `dims in stow drop the work-pose dim: ${r.dimsStow.join(',')}`);
    ok(r.dimsExploded.length === 0 && r.dimsOff === 0, 'dims hidden while exploded and when off');

    // a long press is not a tap; cinematic never picks
    await page.evaluate(() => { const v = window.NA._viewer; v.hidden = false; v.requestRender(); window.NA.camera('hero'); v.tweens.finishAll(); });
    const before = await page.evaluate(() => window.__events.filter((e) => e.type === 'pick').length);
    await page.mouse.move(195, 300);
    await page.mouse.down();
    await page.waitForTimeout(450);
    await page.mouse.up();
    await page.evaluate(() => window.NA.setState({ cinematic: true }));
    await page.mouse.click(195, 300);
    await page.evaluate(() => window.NA.setState({ cinematic: false }));
    await page.mouse.click(5, 5);
    await page.waitForTimeout(300);
    const picks = await page.evaluate(() => window.__events.filter((e) => e.type === 'pick').map((e) => e.group));
    ok(picks.length === before + 1 && picks[picks.length - 1] === null, `long press and cinematic taps don't pick (${picks.length - before} new pick)`);
    ok(errors.length === 0, `no page errors (${errors.slice(0, 3).join(' | ')})`);
    await page.close();
  }

  // 3b. contract sweep: every mode x style, explode, isolate + frame every group, finish, amber, quality, tap on the keyboard
  {
    const { page, errors } = await open(browser, srv, { state: { mode: 'work' }, init: [HOST] });
    await waitEvent(page, 'ready');
    const r = await page.evaluate(() => {
      const NA = window.NA, v = NA._viewer, out = {};
      NA._capture(true);
      const fin = () => { v.tweens.finishAll(); v.fader.finishAll(); v.tweens.finishAll(); };
      const inView = (box, minFill) => {
        const pts = [];
        for (let i = 0; i < 8; i++) pts.push(new v.camera.position.constructor(i & 1 ? box.max.x : box.min.x, i & 2 ? box.max.y : box.min.y, i & 4 ? box.max.z : box.min.z).project(v.camera));
        const xs = pts.map((p) => p.x), ys = pts.map((p) => p.y);
        const fill = Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys)) / 2;
        return pts.every((p) => Math.abs(p.x) <= 1.02 && Math.abs(p.y) <= 1.02) && fill >= minFill;
      };
      // every mode x style draws
      out.combos = [];
      for (const mode of ['work', 'stow', 'standalone']) {
        for (const style of ['studio', 'cad', 'xray', 'blueprint']) {
          const st = NA.setState({ mode, style });
          fin();
          v.render();
          const i = v.renderer.info.render;
          out.combos.push({ mode, style, ok: st.mode === mode && st.style === style && i.calls > 10 && i.triangles > 1000, calls: i.calls, tris: i.triangles });
        }
      }
      NA.setState({ mode: 'work', style: 'studio' });
      fin();
      // explode follows scene.json's vectors
      const ep = [...v.model.parts.values()].filter((p) => p.explode.lengthSq() > 1e-6);
      NA.setState({ explode: 1 });
      fin();
      out.explode1 = ep.length > 10 && ep.every((p) => p.node.position.distanceTo(p.rest.clone().add(p.explode)) < 1e-6);
      NA.setState({ explode: 0.5 });
      fin();
      out.explodeHalf = ep.every((p) => p.node.position.distanceTo(p.rest.clone().addScaledVector(p.explode, 0.5)) < 1e-6);
      NA.setState({ explode: 0 });
      fin();
      out.explode0 = ep.every((p) => p.node.position.distanceTo(p.rest) < 1e-6);
      // stow <-> work follows scene.json's "via" waypoints: lift clear of the rim, slide out, set down (reversed going back)
      out.via = {};
      {
        v.hidden = true;
        v.stopLoop();
        let T = 2e7;
        const step = (ms) => { T += ms; v.tweens.update(T); };
        NA.setState({ mode: 'stow' });
        fin();
        for (const [to, from] of [['work', 'stow'], ['stow', 'work']]) {
          const tracks = {};
          NA.setState({ mode: to });
          step(0);
          for (let ms = 0; ms < 3000; ms += 16) {
            step(16);
            for (const id of ['keyboard', 'mouse']) {
              const mv = v.model.movables.get(id);
              (tracks[id] = tracks[id] || []).push(mv.node.position.clone().sub(mv.pivot));
            }
          }
          fin();
          for (const id of ['keyboard', 'mouse']) {
            const pose = v.sj.poses[to === 'stow' ? from : to][id];
            const via = (pose && pose.via) || [];
            const tr = tracks[id];
            const near = (w) => Math.min(...tr.map((p) => Math.hypot(p.x - w[0], p.y - w[1], p.z - w[2])));
            const lift = via.length ? via[0][1] : 0, slideZ = via.length ? via[via.length - 1][2] : 0;
            out.via[`${id}:${from}->${to}`] = {
              waypoints: via.length >= 2 && via.every((w) => near(w) < 0.002),
              clearOfRim: tr.every((p) => !(p.z > 0.01 && p.z < slideZ - 0.005) || p.y > lift - 0.001),
              lands: tr[tr.length - 1].distanceTo(new v.camera.position.constructor(...(to === 'stow' ? [0, 0, 0] : pose.t))) < 1e-6,
            };
          }
        }
        v.hidden = false;
        NA.setState({ mode: 'work' });
        fin();
      }
      // isolate every group: only it stays, and the camera frames it
      out.iso = {};
      for (const g of v.sj.groups) {
        NA.setState({ isolate: g.id });
        fin();
        const vis = [...v.model.groups.values()].filter((x) => x.node.visible).map((x) => x.id);
        const box = v.model.bounds([g.id], { includeInternal: true });
        out.iso[g.id] = vis.length === 1 && vis[0] === g.id && !box.isEmpty() && inView(box, 0.3);
      }
      NA.setState({ isolate: null });
      fin();
      out.isoBack = [...v.model.groups.values()].filter((x) => x.node.visible).length >= v.sj.groups.length - 1;
      // frame every group (no isolate): the group's box lands inside the view
      out.frame = {};
      for (const g of v.sj.groups) {
        NA.frame(g.id);
        fin();
        const box = v.model.bounds([g.id], { includeInternal: true, includeHidden: true });
        out.frame[g.id] = inView(box, 0.2);
      }
      NA.camera('hero');
      fin();
      // finish recolours material `titanium`
      const ti = v.materials.get('titanium');
      const col = {};
      for (const f of ['graphite', 'oxblood', 'titanium']) {
        NA.setState({ finish: f });
        fin();
        col[f] = ti.color.getHexString();
      }
      out.finish = col;
      out.finishDistinct = new Set(Object.values(col)).size === 3;
      // amber 0 = LEDs, practicals and pools off; 1 = on
      const led = v.materials.get('amber_led');
      NA.setState({ amber: 0 });
      fin();
      out.amberOff = led.emissiveIntensity === 0 && v.stage.amberLights.every((l) => !l.visible) && v.stage.pools.every((p) => !p.visible);
      const e0 = led.emissiveIntensity;
      NA.setState({ amber: 1 });
      fin();
      out.amberOn = led.emissiveIntensity > e0 && v.stage.amberLights.some((l) => l.visible && l.intensity > 0) && v.stage.pools.some((p) => p.visible);
      NA.setState({ amber: 0.8 });
      fin();
      // quality tiers: shadow map size and the bloom composer
      out.quality = {};
      for (const q of ['battery', 'balanced', 'high']) {
        NA.setState({ quality: q });
        fin();
        v.render();
        out.quality[q] = { shadow: v.stage.key.shadow.mapSize.x, composer: !!v.output.composer, msaa: v.output.composer ? v.output.composer.renderTarget1.samples : 0, pr: v.renderer.getPixelRatio() };
      }
      NA.camera('hero');
      fin();
      v.requestRender();
      return out;
    });
    const badCombos = r.combos.filter((c) => !c.ok);
    ok(badCombos.length === 0, `every mode x style renders (${r.combos.map((c) => `${c.mode}/${c.style}:${c.calls}`).join(' ')})`);
    ok(r.explode1 && r.explodeHalf && r.explode0, `explode follows scene.json vectors (1 ${r.explode1}, 0.5 ${r.explodeHalf}, 0 ${r.explode0})`);
    const badVia = Object.entries(r.via).filter(([, x]) => !(x.waypoints && x.clearOfRim && x.lands)).map(([k, x]) => `${k} ${JSON.stringify(x)}`);
    ok(Object.keys(r.via).length === 4 && badVia.length === 0, `devices follow scene.json via waypoints, clear of the rim, both ways ${badVia.length ? 'FAILED: ' + badVia.join('; ') : Object.keys(r.via).join(', ')}`);
    const badIso = Object.entries(r.iso).filter(([, x]) => !x).map(([k]) => k);
    ok(badIso.length === 0 && r.isoBack, `isolate shows and frames each group alone ${badIso.length ? 'FAILED: ' + badIso.join(',') : Object.keys(r.iso).join(',')}`);
    const badFrame = Object.entries(r.frame).filter(([, x]) => !x).map(([k]) => k);
    ok(badFrame.length === 0, `frame(group) puts each group in view ${badFrame.length ? 'FAILED: ' + badFrame.join(',') : Object.keys(r.frame).join(',')}`);
    ok(r.finishDistinct, `finish switch recolours titanium ${JSON.stringify(r.finish)}`);
    ok(r.amberOff && r.amberOn, `amber 0 turns LEDs/practicals/pools off, 1 turns them on (${r.amberOff}/${r.amberOn})`);
    const Q = r.quality;
    ok(Q.battery.shadow < Q.balanced.shadow && Q.balanced.shadow < Q.high.shadow && !Q.battery.composer && Q.balanced.composer && Q.high.composer && Q.high.msaa > Q.balanced.msaa,
      `quality tiers scale shadows / bloom / MSAA ${JSON.stringify(Q)}`);

    // a tap on the keyboard picks it, a tap on empty space picks null, a drag picks nothing
    await page.evaluate(() => window.NA.idle(30000));
    const kb = await groupPoint(page, 'keyboard');
    const n0 = (await picks(page)).length;
    await page.mouse.click(kb.x, kb.y);
    await page.mouse.click(8, 8);
    await page.waitForTimeout(250);
    await page.mouse.move(kb.x, kb.y);
    await page.mouse.down();
    await page.mouse.move(kb.x + 40, kb.y + 10, { steps: 6 });
    await page.mouse.up();
    await page.waitForTimeout(250);
    const p1 = (await picks(page)).slice(n0);
    ok(p1.length === 2 && p1[0] === 'keyboard' && p1[1] === null, `tap keyboard -> "keyboard", tap empty -> null, drag -> nothing (${JSON.stringify(p1)})`);
    ok(errors.length === 0, `no page errors (${errors.slice(0, 3).join(' | ')})`);
    await page.close();
  }

  // 3c. a phone: touch, isMobile, 390x844 at DPR 3
  {
    const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 3, isMobile: true, hasTouch: true });
    const page = await ctx.newPage();
    const errors = [];
    page.on('pageerror', (e) => errors.push(e.message));
    page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
    await page.addInitScript(HOST);
    await page.goto(`${srv.viewerUrl}?state=${encodeURIComponent(JSON.stringify({ mode: 'work' }))}`, { waitUntil: 'commit' });
    await waitEvent(page, 'ready', 180000);
    const info = await page.evaluate(() => {
      const v = window.NA._viewer;
      return { dpr: devicePixelRatio, touch: navigator.maxTouchPoints, pr: v.renderer.getPixelRatio(), cw: v.canvas.width, ch: v.canvas.height, cssW: v.canvas.clientWidth, cssH: v.canvas.clientHeight };
    });
    ok(info.dpr === 3 && info.touch > 0, `phone context (DPR ${info.dpr}, ${info.touch} touch points)`);
    ok(info.pr <= 2 && info.cw * info.ch <= 2.4e6 * 1.01 && info.cssW === 390 && info.cssH === 844, `canvas fills the phone within the pixel budget (${info.cw}x${info.ch} @ ${info.pr})`);
    await page.evaluate(() => { window.NA._capture(true); return window.NA.idle(60000); });
    // tap the keyboard and empty space with a finger
    const kb = await groupPoint(page, 'keyboard');
    const n0 = (await picks(page)).length;
    await page.touchscreen.tap(kb.x, kb.y);
    await page.waitForTimeout(300);
    await page.touchscreen.tap(12, 12);
    await page.waitForTimeout(300);
    const p1 = (await picks(page)).slice(n0);
    ok(p1.length === 2 && p1[0] === 'keyboard' && p1[1] === null, `finger tap keyboard -> "keyboard", empty -> null (${JSON.stringify(p1)})`);
    // one-finger drag orbits, two-finger pinch zooms; neither picks
    const cdp = await ctx.newCDPSession(page);
    const touch = (type, pts) => cdp.send('Input.dispatchTouchEvent', { type, touchPoints: pts.map(([x, y], id) => ({ x, y, id })) });
    const cam = () => page.evaluate(() => { const v = window.NA._viewer; return { p: v.camera.position.toArray(), d: v.camera.position.distanceTo(v.controls.target) }; });
    const c0 = await cam();
    await touch('touchStart', [[150, 520]]);
    for (let i = 1; i <= 8; i++) await touch('touchMove', [[150 + i * 15, 520]]);
    await touch('touchEnd', []);
    await page.waitForTimeout(600);
    const c1 = await cam();
    const moved = Math.hypot(c1.p[0] - c0.p[0], c1.p[2] - c0.p[2]);
    await touch('touchStart', [[170, 520], [220, 520]]);
    for (let i = 1; i <= 8; i++) await touch('touchMove', [[170 - i * 12, 520], [220 + i * 12, 520]]);
    await touch('touchEnd', []);
    await page.waitForTimeout(600);
    const c2 = await cam();
    const p2 = (await picks(page)).slice(n0);
    ok(moved > 0.05, `one-finger drag orbits the camera (${moved.toFixed(3)} m)`);
    ok(c2.d < c1.d * 0.95, `pinch zooms in (${c1.d.toFixed(2)} -> ${c2.d.toFixed(2)} m)`);
    ok(p2.length === 2, `drag and pinch don't pick (${p2.length - 2} extra)`);
    // quality tiers on a DPR-3 screen: pixel ratio steps down
    const prs = await page.evaluate(() => {
      const out = {};
      for (const q of ['high', 'balanced', 'battery']) { window.NA.setState({ quality: q }); out[q] = window.NA._viewer.renderer.getPixelRatio(); }
      window.NA.setState({ quality: 'high' });
      return out;
    });
    ok(prs.high > prs.balanced && prs.balanced > prs.battery && prs.battery === 1, `pixel ratio per tier ${JSON.stringify(prs)}`);
    ok(errors.length === 0, `no page errors on the phone (${errors.slice(0, 3).join(' | ')})`);
    await ctx.close();
  }

  // 4. no WebGL2 -> error event + friendly message, page stays transparent
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

  // 5. model fails to load -> error event
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

  // 6. desktop browser (no host) logs events to the console
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
