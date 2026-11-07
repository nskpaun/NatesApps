// Entry point (bundled into one classic IIFE script). Installs window.NA immediately so the app can queue
// calls before the model has loaded, reads ?state=, checks for WebGL2 and boots the viewer.
import { DEFAULT_STATE, mergeState, stateFromUrl } from './state.js';
import { post, onEvent, hasHost } from './bridge.js';
import { Viewer } from './app.js';

/* global __VIEWER_VERSION__, __THREE_VERSION__ */
const VERSION = typeof __VIEWER_VERSION__ !== 'undefined' ? __VIEWER_VERSION__ : 'dev';
const THREE_VERSION = typeof __THREE_VERSION__ !== 'undefined' ? __THREE_VERSION__ : '';

const stageEl = document.getElementById('stage');
const msgEl = document.getElementById('msg');
if (!hasHost()) document.documentElement.classList.add('standalone-page');

const initial = mergeState(DEFAULT_STATE, stateFromUrl(location.search)).state;
let viewer = null;
let pendingState = initial;
const preQueue = [];
let failed = null;

function showMessage(title, body, { fade = false } = {}) {
  if (!msgEl) return;
  msgEl.innerHTML = '';
  const b = document.createElement('b');
  b.textContent = title;
  const s = document.createElement('span');
  s.textContent = body;
  msgEl.append(b, s);
  msgEl.hidden = false;
  msgEl.classList.remove('fade');
  if (fade) setTimeout(() => msgEl.classList.add('fade'), 4500);
}

const FAILURES = {
  webgl2: {
    message: "WebGL2 isn't available on this device",
    body: 'This device’s browser engine has no WebGL2, so the live 3D view can’t run here. The still renders still show every view.',
  },
  hdr: {
    message: "this device's GPU can't run the live 3D view",
    body: 'This device’s GPU can’t draw into the floating-point targets the live 3D view needs. The still renders still show every view.',
  },
  model: {
    message: "the 3D model couldn't be loaded",
    body: 'The 3D model didn’t load. The still renders still show every view.',
  },
};

function fail(err) {
  if (failed) return;
  failed = err;
  const f = FAILURES[err && err.friendly] || FAILURES.model;
  console.error('[NightArray]', err);
  post({ type: 'error', message: f.message });
  // In the app a still image sits underneath and the app shows its own notice: keep ours brief.
  showMessage('Live view unavailable', f.body, { fade: hasHost() });
}

function call(type, payload) {
  if (failed) return false;
  const cmd = { type, ...payload };
  if (viewer) viewer.enqueue(cmd);
  else preQueue.push(cmd);
  return true;
}

const NA = {
  version: VERSION,
  three: THREE_VERSION,
  /** Merge a partial ViewerState (object or JSON string). Returns the full state. */
  setState(partial) {
    if (typeof partial === 'string') {
      try { partial = JSON.parse(partial); } catch (e) { return NA.getState(); }
    }
    if (viewer) return viewer.setState(partial);
    pendingState = mergeState(pendingState, partial).state;
    return NA.getState();
  },
  getState() {
    return JSON.parse(JSON.stringify(viewer ? viewer.state : pendingState));
  },
  camera(name) { return call('camera', { name: String(name) }); },
  dock(step) { return call('dock', { step: String(step) }); },
  frame(group) { return call('frame', { group: String(group) }); },
  /** In-page event listener (tests / stills tool). Returns an unsubscribe function. */
  on(fn) { return onEvent(fn); },
  /** Resolves once nothing is animating and a frame has been drawn (stills tool). */
  idle(timeoutMs = 15000) {
    return new Promise((resolve) => {
      const t0 = performance.now();
      const check = () => {
        const v = viewer;
        const busy = !v || !v.readySent || v.tweens.size > 0 || v.dirty || v.raf || (v.dockPlay && v.dockPlay.length) || v.pendingPlay;
        if (!busy || performance.now() - t0 > timeoutMs) resolve(!busy);
        else setTimeout(check, 50);
      };
      check();
    });
  },
  /** Capture mode for the stills tool / tests: no continuous animation (LED breathing). */
  _capture(on = true) { if (viewer) { viewer.capture = !!on; viewer.requestRender(); } },
  get ready() { return !!(viewer && viewer.readySent); },
  get error() { return failed ? String(failed.message || failed) : null; },
  get _viewer() { return viewer; },
};
window.NA = NA;

async function boot() {
  const v = new Viewer(stageEl, pendingState);
  // anything that arrived while we were constructing goes in front of the viewer's own queue
  v.queue.push(...preQueue.splice(0));
  viewer = v;
  // state set before init keeps flowing into the same object
  try {
    await v.init();
  } catch (e) {
    fail(e);
  }
}

window.addEventListener('error', (e) => {
  if (!viewer || !viewer.readySent) fail(e.error || new Error(e.message));
});

boot();
