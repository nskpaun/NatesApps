// Kotlin <-> JS contract test, JS half. The Kotlin half (android/app/src/test/.../ContractDump.kt, run by
// `gradle testDebugUnitTest`) drives the real ViewerHost through realistic sessions and records exactly what the app
// hands the WebView: each page's loadUrl() URL, the onPageFinished window.NA probe, and every string flush() passes to
// evaluateJavascript(), plus the state Kotlin believes the page is in after each step. This replays that dump against
// the real bundle in headless Chromium, served the way WebViewAssetLoader + AssetsPathHandler serve it, and fails
// (exit code 1) on any disagreement between the two sides.
//
//   node test/bridge.mjs [dump.json] [--only=<session>] [--verbose]
//   dump: argv, else $NIGHTARRAY_CONTRACT_DUMP, else android/app/build/contract/kotlin-dump.json
import { chromium } from 'playwright';
import { MOUNTS } from './serve.mjs';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const args = process.argv.slice(2);
const flag = (name) => args.find((a) => a === `--${name}` || a.startsWith(`--${name}=`));
const only = flag('only')?.split('=')[1] || '';
const verbose = !!flag('verbose');
const dumpPath = path.resolve(args.find((a) => !a.startsWith('--')) || process.env.NIGHTARRAY_CONTRACT_DUMP
  || path.join(here, '../../android/app/build/contract/kotlin-dump.json'));

if (!fs.existsSync(dumpPath)) {
  console.error(`bridge: no Kotlin dump at ${dumpPath}
  It is written by the Android side of this test. Run it first:
    cd night-array/android && gradle testDebugUnitTest            (or: --tests '*ContractDump*')
  then: npm run test:bridge   (or pass a dump path / set NIGHTARRAY_CONTRACT_DUMP)`);
  process.exit(1);
}
const dump = JSON.parse(fs.readFileSync(dumpPath, 'utf8'));
if (dump.format !== 1 || !Array.isArray(dump.sessions)) {
  console.error(`bridge: ${dumpPath} is not a format-1 contract dump; re-run the Android side`);
  process.exit(1);
}

const GL_ARGS = ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'];
const HOST = dump.assetHost; // WebViewAssetLoader.DEFAULT_DOMAIN
const DOCK_ORDER = ['align', 'lower', 'release', 'lift', 'done'];
const sceneGroups = JSON.parse(fs.readFileSync(path.join(MOUNTS.model, 'scene.json'), 'utf8')).groups.map((g) => g.id);

// Known contract gaps: reported, not failed. Strict: an entry that no longer reproduces fails the run, so it gets removed.
const KNOWN = [
  {
    session: 'restored-isolated', label: /^(onPageFinished|page: ready)/, check: 'camera',
    note: "by design: a page created while a group is isolated frames that group itself, so its camera name stays 'hero' while "
      + 'Kotlin keeps the saved preset in lastCamera; Viewer.kt sends it on Show all (checked by the next step)',
  },
];
const knownHits = new Set();

// ---------------------------------------------------------------- reporting
const failures = [];
let current = '';
const fail = (msg) => { failures.push(`${current}: ${msg}`); console.log(`FAIL ${current}: ${msg}`); };
let tStart = Date.now();
const info = (msg) => { if (verbose) console.log(`     ${String(Date.now() - tStart).padStart(6)} ${msg}`); };
const isKnown = (session, label, check) => {
  const k = KNOWN.findIndex((e) => e.session === session && e.label.test(label) && e.check === check);
  if (k >= 0) knownHits.add(k);
  return k >= 0;
};

// ---------------------------------------------------------------- what ViewerHost.handle() makes of an event
/** org.json optString(): missing -> fallback, JSON null -> "null", anything else -> its string form. */
const optString = (o, k, fallback = '') => (!(k in o) ? fallback : o[k] === null ? 'null' : String(o[k]));
function kotlinParse(raw) {
  if (typeof raw !== 'string') return { bad: `NightArrayHost.post got a ${typeof raw}, not a string` };
  let o;
  try { o = JSON.parse(raw); } catch (e) { return { bad: 'not JSON (JSONObject() throws, the event is dropped)' }; }
  if (!o || typeof o !== 'object' || Array.isArray(o)) return { bad: 'not a JSON object (dropped)' };
  const type = optString(o, 'type');
  switch (type) {
    case 'ready': return { type };
    case 'pick': {
      const group = o.group === null || !('group' in o) ? null : optString(o, 'group') || null;
      return { type, group, bad: group === null || dump.groups.includes(group) ? null : `pick of a group the app doesn't know: ${group}` };
    }
    case 'dockStep': {
      const step = optString(o, 'step');
      return { type, step, bad: DOCK_ORDER.includes(step) ? null : `dockStep "${step}" is not one handle() understands` };
    }
    case 'error': return { type, message: optString(o, 'message'), bad: `error event: ${optString(o, 'message') || 'the live renderer stopped'}` };
    default: return { type, bad: `event type "${type}" is ignored by ViewerHost.handle()` };
  }
}
const sameParse = (a, b) => a.type === b.type && (a.type !== 'pick' || a.group === b.group) && (a.type !== 'dockStep' || a.step === b.step);

// ---------------------------------------------------------------- state comparison
const near = (a, b) => (typeof a === 'number' && typeof b === 'number' ? Math.abs(a - b) <= 1e-6 : a === b);
function diffState(kotlin, js) {
  const out = [];
  if (!js || typeof js !== 'object') return ['viewer state unavailable'];
  for (const k of Object.keys(kotlin)) {
    const a = kotlin[k], b = js[k];
    if (!(k in js)) out.push(`${k}: missing in the viewer`);
    else if (k === 'section') {
      const same = a === null || b === null ? a === b : a.axis === b.axis && near(a.t, b.t) && Object.keys(b).length === 2;
      if (!same) out.push(`section: kotlin ${JSON.stringify(a)} js ${JSON.stringify(b)}`);
    } else if (!near(a, b)) out.push(`${k}: kotlin ${JSON.stringify(a)} js ${JSON.stringify(b)}`);
  }
  for (const k of Object.keys(js)) if (!(k in kotlin)) out.push(`${k}: only in the viewer`);
  return out;
}

// ---------------------------------------------------------------- the WebView, emulated
// androidx.webkit 1.14 AssetHelper.guessMimeType -> MimeUtil.getMimeFromFileName: URLConnection.guessContentTypeFromName,
// then this hardcoded list (Chromium's), else "text/plain". No charset and no other headers. Extensions neither knows
// (.glb on most Android versions) get the text/plain fallback, so the viewer must not depend on their MIME type.
const MIME = {
  webm: 'video/webm', mpeg: 'video/mpeg', mpg: 'video/mpeg', mp3: 'audio/mpeg', wasm: 'application/wasm',
  xhtml: 'application/xhtml+xml', xht: 'application/xhtml+xml', xhtm: 'application/xhtml+xml', flac: 'audio/flac',
  ogg: 'audio/ogg', oga: 'audio/ogg', opus: 'audio/ogg', wav: 'audio/wav', m4a: 'audio/x-m4a', gif: 'image/gif',
  jpeg: 'image/jpeg', jpg: 'image/jpeg', jfif: 'image/jpeg', pjpeg: 'image/jpeg', pjp: 'image/jpeg', png: 'image/png',
  apng: 'image/apng', svg: 'image/svg+xml', svgz: 'image/svg+xml', webp: 'image/webp', mht: 'multipart/related',
  mhtml: 'multipart/related', css: 'text/css', html: 'text/html', htm: 'text/html', shtml: 'text/html', shtm: 'text/html',
  ehtml: 'text/html', js: 'text/javascript', mjs: 'text/javascript', xml: 'text/xml', mp4: 'video/mp4', m4v: 'video/mp4',
  ogv: 'video/ogg', ogm: 'video/ogg', ico: 'image/x-icon', woff: 'application/font-woff', gz: 'application/gzip',
  tgz: 'application/gzip', json: 'application/json', pdf: 'application/pdf', zip: 'application/zip', bmp: 'image/bmp',
  tiff: 'image/tiff', tif: 'image/tiff', txt: 'text/plain',
};
const mimeOf = (name) => MIME[name.slice(name.lastIndexOf('.') + 1).toLowerCase()] || 'text/plain';

const net = { offHost: [], unhandled: [], missing: [], served: new Map() };

/** WebViewAssetLoader with one AssetsPathHandler at /assets/ on https://appassets.androidplatform.net. */
async function route(r) {
  const u = new URL(r.request().url());
  if (u.protocol !== 'https:' || u.host !== HOST) { net.offHost.push(u.href); return r.abort('blockedbyclient'); }
  if (!u.pathname.startsWith('/assets/')) { net.unhandled.push(u.pathname); return r.abort('internetdisconnected'); }
  const rel = decodeURIComponent(u.pathname.slice('/assets/'.length));
  const [mount, ...rest] = rel.split('/');
  const base = MOUNTS[mount];
  const file = base && path.resolve(base, rest.join('/'));
  if (!file || !file.startsWith(base + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) {
    net.missing.push(u.pathname); // AssetsPathHandler: WebResourceResponse(null, null, null)
    return r.fulfill({ status: 404, body: '' });
  }
  net.served.set(u.pathname, mimeOf(file));
  return r.fulfill({ status: 200, headers: { 'content-type': mimeOf(file) }, body: fs.readFileSync(file) });
}

/** addJavascriptInterface(bridge, "NightArrayHost"): there before any page script runs; post() records the timeline. */
const HOST_INIT = () => {
  const c = { timeline: [], atLoad: null };
  window.__contract = c;
  window.NightArrayHost = {
    post(s) {
      let snap = null;
      try {
        const v = window.NA && window.NA._viewer;
        if (v) snap = { dockStep: v.dockStep, cameraName: v.cameraName };
      } catch (e) { /* diagnostics only */ }
      c.timeline.push({ raw: s, t: Math.round(performance.now()), snap });
    },
  };
  window.addEventListener('load', () => {
    let state = null;
    try { state = window.NA && window.NA.getState(); } catch (e) { /* reported below */ }
    c.atLoad = { NA: typeof window.NA, state, t: Math.round(performance.now()) };
  });
};

// ---------------------------------------------------------------- one page (= one WebView)
const SNAPSHOT = (n) => {
  const v = window.NA && window.NA._viewer;
  return {
    fresh: window.__contract.timeline.slice(n),
    live: window.NA ? {
      state: window.NA.getState(), ready: window.NA.ready, error: window.NA.error,
      camera: v ? v.cameraName : null, dockStep: v ? v.dockStep : null,
      groups: v && v.model && v.model.groups ? [...v.model.groups.keys()] : null,
    } : null,
  };
};

class Page {
  constructor(context, url) { this.context = context; this.url = url; this.seen = 0; this.queue = []; this.readies = 0; this.dock = { armed: false, last: -1 }; this.errors = []; this.warnings = 0; }

  async open() {
    this.page = await this.context.newPage();
    this.page.on('pageerror', (e) => this.errors.push(`page error: ${e.message}`));
    this.page.on('console', (m) => {
      if (m.type() === 'error') this.errors.push(`console.error: ${m.text()}`);
      else if (m.type() === 'warning') this.warnings++;
    });
    await this.page.goto(this.url, { waitUntil: 'load', timeout: 120000 });
    return this.page.evaluate(() => window.__contract.atLoad);
  }

  mark(m) { return this.page.evaluate((m) => window.__contract.timeline.push({ marker: m }), m); }

  /** Takes in what the page posted (and the dock markers) since last time, checking each event as handle() would. Returns the live viewer state. */
  async pull() {
    const { fresh, live } = await this.page.evaluate(SNAPSHOT, this.seen);
    this.seen += fresh.length;
    for (const e of fresh) {
      if (e.marker) {
        this.dock = { armed: e.marker === 'play', last: -1 };
        continue;
      }
      const p = kotlinParse(e.raw);
      info(`event @${e.t}ms ${e.raw} -> ${JSON.stringify({ type: p.type, group: p.group, step: p.step })}`);
      if (p.bad) fail(p.bad);
      if (p.type === 'ready' && ++this.readies > 1) fail(`ready #${this.readies} from one page (handle() expects exactly one)`);
      if (p.type === 'dockStep' && !p.bad) {
        const i = DOCK_ORDER.indexOf(p.step);
        if (!this.dock.armed) fail(`dockStep ${p.step} with no NA.dock("play") running`);
        else if (i <= this.dock.last) fail(`dockStep ${p.step} after ${DOCK_ORDER[this.dock.last]} (order is ${DOCK_ORDER.join(' -> ')})`);
        this.dock.last = i;
        if (p.step === 'done') this.dock.armed = false;
      }
      this.queue.push({ ...e, parsed: p });
    }
    for (const e of this.errors.splice(0)) fail(e);
    return live;
  }

  async nextEvent(timeoutMs) {
    const t0 = Date.now();
    for (;;) {
      await this.pull();
      if (this.queue.length) return this.queue.shift();
      if (Date.now() - t0 > timeoutMs) return null;
      await new Promise((r) => setTimeout(r, 40));
    }
  }

  async close() {
    await new Promise((r) => setTimeout(r, 250));
    await this.pull();
    for (const e of this.queue) fail(`the viewer posted ${e.raw}, which the Kotlin session never received`);
    if (this.readies !== 1) fail(`this page posted ready ${this.readies} times (expected exactly once)`);
    await this.page.close();
  }
}

/** Screen point (CSS px) on top of a group's visible bounds, as a finger would tap it. */
const groupPoint = (page, id) => page.evaluate((id) => {
  const v = window.NA._viewer;
  const b = v.model.bounds([id]);
  const c = b.getCenter(b.min.clone());
  c.y = b.max.y - 0.002;
  c.project(v.camera);
  const r = v.canvas.getBoundingClientRect();
  return { x: r.left + (c.x + 1) / 2 * r.width, y: r.top + (1 - c.y) / 2 * r.height };
}, id);

// ---------------------------------------------------------------- a session
async function runSession(context, sess) {
  const t0 = Date.now();
  tStart = t0;
  const before = failures.length;
  let pg = null;
  let phase = 'none'; // none: no WebView; loading: loadUrl() done, not yet onPageFinished; live: the queue flows
  const frames = new Set();
  let warnings = 0;
  const closePage = async () => { if (pg) { await pg.close(); warnings += pg.warnings; pg = null; } phase = 'none'; };

  for (const [i, st] of sess.steps.entries()) {
    current = `${sess.name} #${i} "${st.label}"`;
    const ex = st.expect;
    info(`[${st.kind}] ${st.label}`);

    if (st.load) {
      await closePage();
      const u = new URL(st.load);
      if (u.protocol !== 'https:' || u.host !== HOST || u.pathname !== '/assets/viewer/index.html') fail(`page URL ${st.load} is not the bundled viewer`);
      const urlState = JSON.parse(u.searchParams.get('state'));
      pg = new Page(context, st.load);
      const atLoad = await pg.open();
      phase = 'loading';
      if (!atLoad || atLoad.NA !== 'object') fail(`window.NA is ${atLoad ? atLoad.NA : 'unknown'} at load: every Kotlin call would be dropped`);
      else {
        for (const d of diffState(urlState, atLoad.state)) fail(`?state= vs NA.getState() at load: ${d}`);
        for (const d of diffState(ex.state, atLoad.state)) fail(`Kotlin state vs NA.getState() at load: ${d}`);
      }
      info(`loaded in ${atLoad ? atLoad.t : '?'} ms`);
    }
    if (!ex.webView && pg) await closePage(); // the renderer is gone (or was never there)

    if (st.kind === 'pageFinished') {
      if (!pg) { fail('onPageFinished with no page'); continue; }
      const answer = JSON.stringify(await pg.page.evaluate(st.probe.js));
      if (answer !== st.probe.answer) fail(`probe ${st.probe.js} answers ${answer}, Kotlin was told ${st.probe.answer}`);
      phase = 'live';
    }

    let posted = null; // the event this step hands Kotlin, with the viewer's dock step at the moment it was posted
    if (st.kind === 'event') {
      if (!pg) { fail('an event with no page'); continue; }
      const want = kotlinParse(st.event);
      if (st.tap) {
        await pg.page.waitForFunction(() => window.NA.ready && window.NA._viewer.tweens.size === 0, null, { timeout: 30000, polling: 50 });
        const pt = st.tap === 'empty' ? { x: 12, y: 12 } : await groupPoint(pg.page, st.tap);
        await pg.page.touchscreen.tap(pt.x, pt.y);
      }
      posted = await pg.nextEvent(want.type === 'ready' ? 120000 : 15000);
      if (!posted) { fail(`waited in vain for the viewer to post ${st.event}`); continue; }
      if (!sameParse(posted.parsed, want)) fail(`the viewer posted ${posted.raw} where Kotlin's session receives ${st.event}`);
    }

    for (const js of st.js) {
      if (!pg) { fail(`Kotlin evaluated JS with no page: ${js}`); continue; }
      if (phase !== 'live') fail(`Kotlin evaluated JS before onPageFinished: ${js}`);
      // dock markers bracket the commands in the page's own timeline: a play arms the step order check before it can post
      // its first step; any other dock command stops a running play once it has run
      const dock = /NA\.dock\("([^"]*)"\)/.exec(js);
      if (dock && dock[1] === 'play') await pg.mark('play');
      await pg.page.evaluate(js);
      if (dock && dock[1] !== 'play') await pg.mark(dock[1]);
      const fr = /NA\.frame\("([^"]*)"\)/.exec(js);
      if (fr) frames.add(fr[1]);
    }

    if (!pg) continue;
    const js = await pg.pull();
    if (phase !== 'live' || !js) continue;

    for (const d of diffState(ex.state, js.state)) fail(`state ${d}`);
    if (js.error) fail(`NA.error: ${js.error}`);
    if (!js.ready) continue;
    // camera: Kotlin tracks the preset (Camera chips, stills) except in Night shift, which orbits on its own
    if (!ex.state.cinematic && js.camera !== ex.camera) {
      const msg = `camera: Kotlin lastCamera ${ex.camera}, viewer cameraName ${js.camera}`;
      if (isKnown(sess.name, st.label, 'camera')) console.log(`KNOWN ${current}: ${msg}`);
      else fail(msg);
    }
    // dock step: Kotlin's follows the commands it sends and the dockStep events; mid-play only the events line up
    const dockStep = posted ? (posted.snap ? posted.snap.dockStep : null) : js.dockStep;
    if ((posted || !ex.dockPlaying) && (dockStep ?? null) !== ex.dockStep) fail(`dock step: Kotlin ${ex.dockStep}, viewer ${dockStep}`);
    if (js.groups) {
      for (const k of ['isolate', 'selected']) if (js.state[k] !== null && !js.groups.includes(js.state[k])) fail(`${k} ${js.state[k]} is no group the viewer knows`);
      for (const g of frames) if (!js.groups.includes(g)) fail(`NA.frame("${g}"): no group the viewer knows`);
      frames.clear();
      for (const g of dump.groups) if (!js.groups.includes(g)) fail(`scene group ${g} (Kotlin) is not in the viewer's model`);
    }
  }
  current = `${sess.name} (end)`;
  await closePage();
  const n = failures.length - before;
  console.log(`${n ? 'FAIL' : 'ok  '} session ${sess.name}: ${sess.steps.length} steps, ${((Date.now() - t0) / 1000).toFixed(1)} s`
    + `${warnings ? `, ${warnings} console warnings` : ''}${n ? `, ${n} failures` : ''}`);
}

// ---------------------------------------------------------------- main
const t0 = Date.now();
current = 'dump';
if (JSON.stringify(dump.groups) !== JSON.stringify(sceneGroups)) fail(`groups: Kotlin parsed ${dump.groups} from scene.json, the viewer's scene.json has ${sceneGroups}`);
const sessions = dump.sessions.filter((s) => s.name.includes(only));
if (!sessions.length) fail(`no session matches "${only}"`);
const browser = await chromium.launch({ args: GL_ARGS });
try {
  // a phone's Studio viewport, touch; pages share nothing (no storage), so one context serves every session
  const context = await browser.newContext({ viewport: { width: 390, height: 520 }, deviceScaleFactor: 1, hasTouch: true, isMobile: true });
  await context.route('**/*', route);
  await context.addInitScript(HOST_INIT);
  for (const s of sessions) await runSession(context, s);
} finally {
  await browser.close();
}
current = 'network';
for (const u of new Set(net.offHost)) fail(`off-host request (aborted; the app has no network): ${u}`);
for (const u of new Set(net.unhandled)) fail(`request on ${HOST} outside /assets/ (WebViewAssetLoader would pass it to the network): ${u}`);
for (const u of new Set(net.missing)) fail(`asset not in the APK (AssetsPathHandler answers with no data): ${u}`);
current = 'known issues';
KNOWN.forEach((k, i) => {
  if (!knownHits.has(i) && sessions.some((s) => s.name === k.session)) fail(`no longer reproduces, remove it from KNOWN: ${k.session} ${k.label} ${k.check}`);
  else if (knownHits.has(i)) console.log(`note: known gap (${k.session}, ${k.check}): ${k.note}`);
});
const steps = sessions.reduce((n, s) => n + s.steps.length, 0);
console.log(`served: ${[...net.served].map(([p, m]) => `${p} (${m})`).join(', ')}`);
console.log(`${failures.length ? 'FAIL' : 'ok'}: ${sessions.length} sessions, ${steps} steps from ${path.relative(process.cwd(), dumpPath) || dumpPath}, `
  + `${failures.length} failures, ${((Date.now() - t0) / 1000).toFixed(1)} s`);
process.exit(failures.length ? 1 : 0);
