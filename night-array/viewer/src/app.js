// The Night Array viewer: scene, state application, camera, render-on-demand loop and the NA command API.
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { DEFAULT_STATE, mergeState, CAMERAS, DOCK_COMMANDS } from './state.js';
import { post } from './bridge.js';
import { Tweens, ease, clamp, DEG } from './util.js';
import { loadModelFiles, Model } from './model.js';
import { MaterialLib } from './materials.js';
import { Stage, BG } from './stage.js';
import { Output, QUALITY } from './post.js';
import { PRESETS, fovFor, dirFrom, fitPoints, boxCorners, sphericalOf, cameraTween } from './cameras.js';
import { ScreenSurface } from './screen.js';

const MODEL_BASE = '../model/';
const PIXEL_BUDGET = { high: 2.4e6, balanced: 1.5e6, battery: 0.9e6 };
// emissive gain of the desktop texture (ACES has a deep toe: the dark wallpaper needs a push to read)
const SCREEN_GLOW = { on: 1.8, stow: 1.25 };

export class Viewer {
  constructor(stageEl, initialState) {
    this.el = stageEl;
    this.state = { ...DEFAULT_STATE, ...initialState };
    this.loaded = false;
    this.readySent = false;
    this.queue = [];
    this.tweens = new Tweens();
    this.dirty = true;
    this.raf = 0;
    this.timer = 0;
    this.lastFrame = 0;
    this.hidden = typeof document !== 'undefined' && document.hidden;
    this.contextLost = false;
    this.dockStep = null;
    this.dockPlay = null;
    this.userMoved = false;
    this.cameraName = 'hero';
    this.cameraSet = false;
    this.capture = false;
  }

  // ------------------------------------------------------------------ boot
  async init() {
    this.t0 = performance.now();
    const canvas = document.createElement('canvas');
    canvas.setAttribute('aria-label', 'Night Array live 3D view');
    this.el.insertBefore(canvas, this.el.firstChild);
    this.canvas = canvas;
    const gl = canvas.getContext('webgl2', { antialias: true, alpha: false, powerPreference: 'high-performance', preserveDrawingBuffer: false, stencil: false });
    if (!gl) throw Object.assign(new Error("WebGL2 isn't available on this device"), { friendly: 'webgl2' });
    const renderer = new THREE.WebGLRenderer({ canvas, context: gl, antialias: true });
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.0;
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.autoUpdate = false;
    renderer.shadowMap.needsUpdate = true;
    renderer.setClearColor(BG, 1);
    this.renderer = renderer;
    this.hdrOk = renderer.extensions.has('EXT_color_buffer_float') || renderer.extensions.has('EXT_color_buffer_half_float');

    // start the downloads first; paint the procedural set while they are in flight
    const T0 = performance.now();
    const mark = (k) => { this.timings[k] = Math.round(performance.now() - T0); };
    this.timings = {};
    const files = loadModelFiles(MODEL_BASE);
    files.catch(() => {});

    this.scene = new THREE.Scene();
    this.scene.background = BG.clone();
    this.scene.fog = new THREE.Fog(BG.clone().multiplyScalar(0.8), 4.5, 11);
    this.camera = new THREE.PerspectiveCamera(30, 1, 0.02, 40);
    this.camera.position.set(-0.8, 0.7, 2.2);

    const small = Math.min(window.screen.width, window.screen.height) * (window.devicePixelRatio || 1) < 900;
    this.stage = new Stage(renderer, { lowMem: this.state.quality === 'battery' || small });
    this.scene.add(this.stage.group);
    mark('stage');
    this.scene.environment = this.stage.buildEnvironment();
    this.stage.desk.material.envMap = this.scene.environment;
    mark('env');

    this.output = new Output(renderer, this.scene, this.camera);
    this.controls = this.makeControls();
    this.installEvents();
    this.resize(true);

    const { sceneJson, gltf, edgesGltf } = await files;
    mark('files');
    this.sj = sceneJson;
    this.materials = new MaterialLib(sceneJson);
    this.materials.setEnvMap(this.scene.environment);
    this.model = new Model(sceneJson, gltf, edgesGltf, this.materials);
    this.scene.add(this.model.root);
    this.setupScreen();
    this.setupLeds();
    this.setupPracticals();
    mark('model');

    this.loaded = true;
    this.cameraSet = false;
    this.applyState(new Set(Object.keys(this.state)), { immediate: true, initial: true });
    // queued commands run before the first frame, so they jump instead of animating
    this.drainQueue(true);
    if (!this.cameraSet) this.setCamera('hero', { immediate: true, group: this.state.isolate && this.model.groups.has(this.state.isolate) ? this.state.isolate : null });
    this.tweens.finishAll();
    try {
      mark('state');
      await renderer.compileAsync(this.scene, this.camera);
      mark('compiled');
    } catch (e) { /* compile lazily on first frame instead */ }
    this.requestRender();
  }

  makeControls() {
    const c = new OrbitControls(this.camera, this.canvas);
    c.enableDamping = true;
    c.dampingFactor = 0.085;
    c.rotateSpeed = 0.75;
    c.zoomSpeed = 0.9;
    c.panSpeed = 0.7;
    c.screenSpacePanning = true;
    c.minDistance = 0.22;
    c.maxDistance = 6;
    c.minPolarAngle = 4 * DEG;
    c.maxPolarAngle = 86 * DEG; // never below the desk
    c.autoRotateSpeed = 0.9;
    c.touches = { ONE: THREE.TOUCH.ROTATE, TWO: THREE.TOUCH.DOLLY_PAN };
    c.addEventListener('start', () => {
      this.userMoved = true;
      this.tweens.cancel('camera');
      this.requestRender();
    });
    c.addEventListener('change', () => this.requestRender());
    return c;
  }

  installEvents() {
    const onResize = () => this.resize();
    window.addEventListener('resize', onResize);
    if (typeof ResizeObserver !== 'undefined') new ResizeObserver(onResize).observe(this.el);
    document.addEventListener('visibilitychange', () => {
      this.hidden = document.hidden;
      if (this.hidden) this.stopLoop();
      else this.requestRender();
    });
    this.canvas.addEventListener('webglcontextlost', (e) => {
      e.preventDefault();
      this.contextLost = true;
      this.stopLoop();
      clearTimeout(this.lostTimer);
      this.lostTimer = setTimeout(() => {
        if (this.contextLost) {
          this.lostReported = true;
          post({ type: 'error', message: 'the live renderer lost its graphics context' });
        }
      }, 4000);
    });
    this.canvas.addEventListener('webglcontextrestored', () => {
      this.contextLost = false;
      clearTimeout(this.lostTimer);
      this.scene.environment = this.stage.buildEnvironment();
      if (this.materials) this.materials.setEnvMap(this.scene.environment);
      this.stage.desk.material.envMap = this.scene.environment;
      this.stage.contact.dirty = true;
      this.renderer.shadowMap.needsUpdate = true;
      if (this.screen) this.screen.texture.needsUpdate = true;
      this.firstFrameAfterRestore = true;
      this.requestRender();
    });
    // tap (not drag) picking
    let down = null;
    this.canvas.addEventListener('pointerdown', (e) => {
      down = e.isPrimary ? { x: e.clientX, y: e.clientY, t: performance.now(), id: e.pointerId, multi: false } : down && { ...down, multi: true };
    });
    this.canvas.addEventListener('pointerup', (e) => {
      if (!down || e.pointerId !== down.id) return;
      const d = Math.hypot(e.clientX - down.x, e.clientY - down.y);
      const dt = performance.now() - down.t;
      const multi = down.multi;
      down = null;
      if (multi || d > 8 || dt > 650 || this.state.cinematic || !this.loaded) return;
      this.pick(e.clientX, e.clientY);
    });
    this.canvas.addEventListener('pointercancel', () => { down = null; });
  }

  // ------------------------------------------------------------------ model extras
  setupScreen() {
    const def = this.sj.screen || {};
    const part = this.model.parts.get(def.part || 'display_screen');
    if (!part) return;
    this.screen = new ScreenSurface(THREE, def, QUALITY[this.state.quality].screen);
    const m = this.materials.variant('screen', 'screen-live');
    m.emissive = new THREE.Color(1, 1, 1);
    m.emissiveMap = this.screen.texture;
    m.emissiveIntensity = SCREEN_GLOW.on;
    part.mesh.material = m;
    this.screenMat = m;
  }

  setupLeds() {
    // charge indicators get their own instance of the LED material so they can breathe while charging
    this.chargeMat = this.materials.variant('amber_led', 'amber_led-charge');
    this.materials.extraAmber = [this.chargeMat];
    for (const id of ['kb_charge_led', 'mouse_charge_led']) {
      const p = this.model.parts.get(id);
      if (p) p.mesh.material = this.chargeMat;
    }
  }

  setupPracticals() {
    const S = this.stage;
    const part = (id) => this.model.parts.get(id);
    const center = (id) => {
      const p = part(id);
      if (!p) return null;
      const g = p.mesh.geometry;
      if (!g.boundingBox) g.computeBoundingBox();
      return g.boundingBox.getCenter(new THREE.Vector3()).applyMatrix4(p.mesh.matrixWorld);
    };
    const size = (id) => {
      const p = part(id);
      if (!p) return null;
      return p.mesh.geometry.boundingBox.getSize(new THREE.Vector3());
    };
    // Point lights sit low and short-ranged so they warm nearby surfaces without leaving hot specular dots
    // on the glossy screens; the soft pools carry most of the glow.
    // Each practical hangs off the group that owns its LED, so it hides with it (isolate, poses).
    const host = (partId) => {
      const p = part(partId);
      return p ? (this.model.movables.get(p.group) || {}).node || null : null;
    };
    const glow = center('base_glow');
    if (glow) {
      const w = size('base_glow').x, parent = host('base_glow');
      S.addPractical({ pos: [glow.x, 0.0006, glow.z + 0.075], size: [w * 1.25, 0.2], poolK: 0.5, parent, world: true });
      for (const f of [-0.33, 0, 0.33]) S.addPractical({ pos: [glow.x + w * f, 0.006, glow.z + 0.02], light: 0.006, distance: 0.28, parent, world: true });
    }
    const neck = center('neck_light');
    const deck = this.model.parts.get('deck_liner');
    if (neck) {
      const deckY = deck ? new THREE.Box3().setFromObject(deck.mesh).max.y : 0.03;
      S.addPractical({ pos: [neck.x, deckY + 0.0004, neck.z + 0.07], size: [0.42, 0.2], poolK: 0.32, parent: host('neck_light'), world: true });
    }
    const latch = center('dock_latch_led');
    if (latch) {
      const parent = host('dock_latch_led');
      S.addPractical({ pos: [latch.x, 0.0006, latch.z + 0.06], size: [0.13, 0.1], poolK: 0.5, parent, world: true });
      S.addPractical({ pos: [latch.x, latch.y + 0.004, latch.z + 0.03], light: 0.006, distance: 0.18, parent, world: true });
    }
    // the mouse's tail light rides with the mouse (pool on whatever it rests on)
    const mg = this.model.groups.get('mouse');
    const mouseGlow = part('mouse_glow');
    if (mg && mouseGlow) {
      const c = center('mouse_glow').sub(mg.pivot);
      S.addPractical({ pos: [c.x, 0.0007, c.z + 0.03], size: [0.09, 0.07], poolK: 0.45, parent: mg.node });
    }
  }

  // ------------------------------------------------------------------ state
  setState(partial) {
    if (typeof partial === 'string') {
      try { partial = JSON.parse(partial); } catch (e) { return this.getState(); }
    }
    const { state, changed } = mergeState(this.state, partial);
    this.state = state;
    if (this.loaded && changed.size) this.applyState(changed, { immediate: !this.readySent });
    return this.getState();
  }

  getState() {
    return JSON.parse(JSON.stringify(this.state));
  }

  applyState(changed, { immediate = false, initial = false } = {}) {
    const s = this.state;
    if (changed.has('quality')) this.applyQuality();
    if (changed.has('finish')) {
      const fn = this.materials.finishTween(s.finish);
      if (fn) {
        if (immediate) fn(1);
        else this.tweens.run('finish', 0.6, fn, { ease: ease.inOutSine });
      }
    }
    if (changed.has('amber')) {
      this.materials.setAmber(s.amber);
      for (const m of this.materials.extraAmber || []) syncAmber(m, this.materials.get('amber_led'));
      this.stage.setAmber(s.amber);
    }
    if (changed.has('mode')) {
      if (this.screen) this.screen.paint(s.mode);
      if (this.screenMat) this.screenMat.emissiveIntensity = s.mode === 'stow' ? SCREEN_GLOW.stow : SCREEN_GLOW.on;
    }
    if (changed.has('mode') || changed.has('explode') || changed.has('isolate') || changed.has('style') || changed.has('section') || initial) {
      this.layout(immediate, changed.has('isolate') ? (s.isolate ? 'group' : 'preset') : changed.has('mode') || changed.has('explode') ? 'preset' : null);
    }
    if (changed.has('autorotate') || changed.has('cinematic')) {
      this.controls.autoRotate = s.autorotate && !s.cinematic;
      this.controls.enabled = !s.cinematic;
      if (s.cinematic) this.startCinematic();
      else this.cine = null;
    }
    this.requestRender();
  }

  applyQuality() {
    const q = { ...QUALITY[this.state.quality] };
    if (!this.hdrOk) q.bloom = false;
    this.q = q;
    this.renderer.shadowMap.type = q.shadowType;
    this.renderer.shadowMap.needsUpdate = true;
    this.resize(true);
    if (this.screen && this.screen.setScale(q.screen) && this.screenMat) {
      this.screenMat.emissiveMap = this.screen.texture;
      this.screenMat.needsUpdate = true;
    }
    for (const m of this.materials ? this.materials.all() : []) m.needsUpdate = true;
  }

  /** Visibility + transforms for mode pose, dock step, explode and isolate. */
  layout(immediate, reframe = null) {
    const s = this.state;
    const M = this.model;
    const targets = M.targets(s.mode, this.dockStep);
    if (this.dockStep) {
      const step = (this.sj.dock_sequence || []).find((x) => x.step === this.dockStep);
      for (const id of Object.keys(step || {})) if (targets.has(id)) targets.get(id).hidden = false;
    }
    const showInternal = s.style === 'xray' || s.explode > 0.001 || !!s.section || s.isolate === 'internals';
    const from = new Map();
    for (const [id, mv] of M.movables) {
      const tg = targets.get(id);
      const base = mv.parent ? mv.pivot.clone().sub(mv.parent.pivot) : mv.pivot.clone();
      const pos = base.add(tg.t);
      const quat = new THREE.Quaternion().setFromEuler(tg.r);
      from.set(id, { p0: mv.node.position.clone(), q0: mv.node.quaternion.clone(), p1: pos, q1: quat });
      const isolated = mv.isGroup && s.isolate && s.isolate !== id && M.groups.has(s.isolate);
      mv.node.visible = !tg.hidden && !isolated;
    }
    const ex = s.explode;
    const parts = [];
    for (const p of M.parts.values()) {
      p.mesh.visible = !p.internal || showInternal;
      parts.push({ p, a: p.node.position.clone(), b: p.rest.clone().addScaledVector(p.explode, ex) });
    }
    const apply = (t) => {
      for (const [id, f] of from) {
        const n = M.movables.get(id).node;
        n.position.lerpVectors(f.p0, f.p1, t);
        n.quaternion.slerpQuaternions(f.q0, f.q1, t);
      }
      for (const x of parts) x.p.node.position.lerpVectors(x.a, x.b, t);
      this.stage.contact.dirty = true;
      this.renderer.shadowMap.needsUpdate = true;
    };
    this.layoutApply = apply;
    if (immediate) {
      this.tweens.cancel('layout');
      apply(1);
    } else {
      this.tweens.run('layout', 0.9, apply, { ease: ease.inOutCubic });
    }
    this.stage.setExplodeFade(ex);
    // keep the framing honest: a camera that sits on a preset (or an isolated group) re-frames the new layout
    if (this.readySent && this.cameraSet && !s.cinematic) {
      if (reframe === 'group' && s.isolate && M.groups.has(s.isolate)) this.setCamera(null, { group: s.isolate, immediate });
      else if (!this.userMoved && (reframe || s.isolate)) this.setCamera(this.cameraName || 'hero', { immediate, group: s.isolate && M.groups.has(s.isolate) ? s.isolate : null });
    }
  }

  /** Runs fn with every node at the end of the running layout tween (framing must target where things land). */
  withEndLayout(fn) {
    if (!this.tweens.has('layout') || !this.layoutApply) return fn();
    const saved = [];
    for (const mv of this.model.movables.values()) saved.push([mv.node, mv.node.position.clone(), mv.node.quaternion.clone()]);
    for (const p of this.model.parts.values()) saved.push([p.node, p.node.position.clone(), null]);
    this.layoutApply(1);
    try {
      return fn();
    } finally {
      for (const [n, pos, q] of saved) {
        n.position.copy(pos);
        if (q) n.quaternion.copy(q);
      }
      this.model.root.updateMatrixWorld(true);
    }
  }

  // ------------------------------------------------------------------ camera
  viewSize() {
    return { w: Math.max(1, this.el.clientWidth || window.innerWidth), h: Math.max(1, this.el.clientHeight || window.innerHeight) };
  }

  /** Points to frame for a preset's fit spec: corners of the visible parts' boxes. */
  fitPointsFor(spec, name) {
    const M = this.model;
    let boxes;
    if (!spec || spec.all) boxes = M.partBoxes(null, { includeInternal: true });
    else {
      boxes = [];
      if (spec.groups) boxes.push(...M.partBoxes(spec.groups));
      if (spec.parts) {
        let pb = M.partBoxes(null, { partIds: spec.parts });
        if (spec.within) {
          // devices count only while they sit in their pockets (trays view)
          const lim = M.bounds([spec.within]).expandByScalar(0.004);
          boxes = boxes.map((b) => b.clone().intersect(lim)).filter((b) => !b.isEmpty());
        }
        if (name === 'trays') pb = pb.map((b) => { const x = b.clone(); x.max.y = Math.max(x.max.y, x.min.y + 0.045); return x; });
        boxes.push(...pb);
      }
    }
    if (!boxes.length) boxes = M.partBoxes(null);
    const pts = [];
    for (const b of boxes) boxCorners(b, pts);
    return pts;
  }

  presetPose(name) {
    const P = PRESETS[name] || PRESETS.hero;
    const { w, h } = this.viewSize();
    const aspect = w / h;
    const pts = this.fitPointsFor(P.fit, name);
    const dir = dirFrom(P.az, P.el);
    const portrait = aspect < 1;
    const pad = portrait ? (P.ppad ?? P.pad * 0.7) : P.pad;
    const fit = fitPoints(pts, dir, fovFor(aspect), aspect, pad, P.lift * (portrait ? 1.15 : 1));
    return { pos: fit.target.clone().addScaledVector(dir, fit.distance), target: fit.target, distance: fit.distance };
  }

  /** Animated (or immediate) move to a named preset, or to frame a group when `group` is given. */
  setCamera(name, { immediate = false, group = null } = {}) {
    if (!this.loaded) return;
    if (!group && !PRESETS[name]) return;
    if (!group) this.cameraName = name;
    const pose = this.withEndLayout(() => (group ? this.groupPose(group) : this.presetPose(name)));
    if (!pose) return;
    this.cameraSet = true;
    this.userMoved = false;
    this.updateLimits(pose.distance);
    if (immediate || !this.readySent) {
      this.tweens.cancel('camera');
      this.camera.position.copy(pose.pos);
      this.controls.target.copy(pose.target);
      this.camera.lookAt(pose.target);
      this.controls.update();
    } else {
      const tw = cameraTween(this.camera, this.controls, pose.pos, pose.target, () => this.requestRender());
      this.tweens.run('camera', tw.duration, tw.fn, { ease: tw.ease, onDone: () => this.controls.update() });
    }
    this.requestRender();
  }

  groupPose(groupId) {
    if (!this.model.groups.has(groupId)) return null;
    const box = this.model.bounds([groupId], { includeInternal: groupId === 'internals' || this.state.style === 'xray' });
    if (box.isEmpty()) return null;
    const { w, h } = this.viewSize();
    const aspect = w / h;
    const cur = sphericalOf(this.camera.position, this.controls.target);
    const el = clamp(cur.el, 12, 40);
    const dir = dirFrom(cur.az, el);
    const size = box.getSize(new THREE.Vector3());
    const pad = Math.max(size.x, size.y, size.z) < 0.2 ? 0.16 : 0.08;
    const fit = fitPoints(boxCorners(box), dir, fovFor(aspect), aspect, pad, aspect < 1 ? 0.06 : 0.03);
    const distance = Math.max(fit.distance, 0.28);
    return { pos: fit.target.clone().addScaledVector(dir, distance), target: fit.target, distance };
  }

  frame(groupId) {
    if (!this.loaded) return;
    this.setCamera(null, { group: groupId });
  }

  updateLimits(d) {
    const hero = this.presetPose('hero').distance;
    this.controls.maxDistance = Math.max(hero * 1.7, d * 1.3);
    this.controls.minDistance = Math.min(0.22, d * 0.6);
  }

  /** Keeps the orbit target near the station and above the desk. */
  clampTarget() {
    const t = this.controls.target;
    const b = this.model.sceneBounds();
    const cx = clamp(t.x, b.min.x - 0.25, b.max.x + 0.25);
    const cy = clamp(t.y, 0.01, b.max.y + 0.2);
    const cz = clamp(t.z, b.min.z - 0.3, b.max.z + 0.5);
    if (cx !== t.x || cy !== t.y || cz !== t.z) {
      const d = new THREE.Vector3(cx - t.x, cy - t.y, cz - t.z);
      t.add(d);
      this.camera.position.add(d);
    }
    if (this.camera.position.y < 0.03) this.camera.position.y = 0.03;
  }

  startCinematic() {
    const hero = this.presetPose('hero');
    const sph = sphericalOf(this.camera.position, this.controls.target);
    this.cine = { t0: performance.now(), az0: sph.az, target: hero.target.clone(), dist: hero.distance * 0.92, from: { pos: this.camera.position.clone(), target: this.controls.target.clone() } };
  }

  updateCinematic(now) {
    const c = this.cine;
    const t = (now - c.t0) / 1000;
    const az = c.az0 + t * 5.5; // ~65 s per orbit
    const el = 13 + 5 * Math.sin(t * 0.21);
    const dist = c.dist * (1 + 0.06 * Math.sin(t * 0.13 + 1));
    const pos = c.target.clone().addScaledVector(dirFrom(az, el), dist);
    const k = ease.inOutSine(clamp(t / 2.5, 0, 1)); // ease in from wherever the camera was
    this.camera.position.lerpVectors(c.from.pos, pos, k);
    this.controls.target.lerpVectors(c.from.target, c.target, k);
    this.camera.lookAt(this.controls.target);
  }

  // ------------------------------------------------------------------ commands
  enqueue(cmd) {
    if (!this.loaded) {
      this.queue.push(cmd);
      return;
    }
    this.exec(cmd, false);
  }

  drainQueue(immediate) {
    const q = this.queue;
    this.queue = [];
    for (const c of q) this.exec(c, immediate);
  }

  exec(cmd, immediate) {
    try {
      if (cmd.type === 'camera') {
        if (CAMERAS.includes(cmd.name)) this.setCamera(cmd.name, { immediate });
      } else if (cmd.type === 'frame') {
        if (this.model.groups.has(cmd.group)) {
          this.setCamera(null, { group: cmd.group, immediate });
        }
      } else if (cmd.type === 'dock') {
        if (DOCK_COMMANDS.includes(cmd.step)) this.dock(cmd.step, immediate);
      }
    } catch (e) {
      console.error('[NightArray] command failed', cmd, e);
    }
  }

  dock(step, immediate = false) {
    if (step === 'play') return this.playDock();
    this.stopDockPlay();
    if (step === 'reset') this.dockStep = null;
    else this.dockStep = step;
    this.layout(immediate);
    this.requestRender();
  }

  stopDockPlay() {
    if (this.dockPlay) {
      for (const t of this.dockPlay) clearTimeout(t);
      this.dockPlay = null;
    }
  }

  playDock() {
    this.stopDockPlay();
    const timers = [];
    const at = (ms, fn) => timers.push(setTimeout(fn, ms));
    const step = (s) => () => {
      this.dockStep = s;
      this.layout(false);
      post({ type: 'dockStep', step: s });
      this.requestRender();
    };
    // start lifted above the cradle so "align" reads as a guided entry
    at(0, step('align'));
    at(1500, step('lower'));
    at(3000, step('release'));
    at(4300, step('lift'));
    at(6000, () => {
      this.dockStep = null;
      this.layout(false);
      this.dockPlay = null;
      post({ type: 'dockStep', step: 'done' });
      this.requestRender();
    });
    this.dockPlay = timers;
  }

  pick(x, y) {
    const r = this.canvas.getBoundingClientRect();
    const ndc = new THREE.Vector2(((x - r.left) / r.width) * 2 - 1, -((y - r.top) / r.height) * 2 + 1);
    const ray = new THREE.Raycaster();
    ray.setFromCamera(ndc, this.camera);
    const targets = this.model.meshes.filter((m) => isShown(m));
    const hit = ray.intersectObjects(targets, false)[0];
    post({ type: 'pick', group: hit ? hit.object.userData.group : null });
  }

  // ------------------------------------------------------------------ render loop
  resize(force = false) {
    if (!this.renderer) return;
    const { w, h } = this.viewSize();
    const q = this.q || QUALITY[this.state.quality] || QUALITY.high;
    const dpr = window.devicePixelRatio || 1;
    let pr = Math.min(dpr, q.pixelRatio);
    const budget = PIXEL_BUDGET[this.state.quality] || PIXEL_BUDGET.high;
    if (w * h * pr * pr > budget) pr = Math.max(0.75, Math.sqrt(budget / (w * h)));
    if (!force && this.size && this.size.w === w && this.size.h === h && this.size.pr === pr) return;
    this.size = { w, h, pr };
    this.renderer.setPixelRatio(pr);
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    this.camera.fov = fovFor(w / h);
    this.camera.updateProjectionMatrix();
    if (this.q) {
      this.output.configure(this.q, w, h, pr);
      this.stage.setQuality(this.q, w * pr, h * pr);
    }
    if (this.loaded && this.cameraSet && !this.userMoved && !this.state.cinematic && !this.tweens.has('camera')) {
      if (this.state.isolate && this.model.groups.has(this.state.isolate)) this.setCamera(null, { group: this.state.isolate, immediate: true });
      else this.setCamera(this.cameraName || 'hero', { immediate: true });
    }
    this.requestRender();
  }

  requestRender() {
    this.dirty = true;
    this.schedule(0);
  }

  schedule(delay) {
    if (this.hidden || this.contextLost || !this.loaded) return;
    if (this.raf) return;
    if (delay > 0) {
      if (this.timer) return;
      this.timer = setTimeout(() => {
        this.timer = 0;
        if (!this.raf && !this.hidden) this.raf = requestAnimationFrame((t) => this.tick(t));
      }, delay);
      return;
    }
    if (this.timer) { clearTimeout(this.timer); this.timer = 0; }
    this.raf = requestAnimationFrame((t) => this.tick(t));
  }

  stopLoop() {
    if (this.raf) cancelAnimationFrame(this.raf);
    if (this.timer) clearTimeout(this.timer);
    this.raf = 0;
    this.timer = 0;
  }

  breathing() {
    return !this.capture && this.q && this.q.breathe && this.state.mode === 'stow' && this.state.amber > 0.001 && !this.hidden;
  }

  tick(now) {
    this.raf = 0;
    if (this.hidden || this.contextLost) return;
    const dt = this.lastFrame ? Math.min(0.1, (now - this.lastFrame) / 1000) : 1 / 60;
    this.lastFrame = now;
    const tweening = this.tweens.update(now);
    let moving = false;
    if (this.state.cinematic && this.cine) {
      this.updateCinematic(now);
      moving = true;
    } else if (!this.tweens.has('camera')) {
      moving = this.controls.update(dt);
      this.clampTarget();
    }
    const breathing = this.breathing();
    this.updateLeds(now, breathing);
    const continuous = tweening || moving || this.controls.autoRotate || !!this.state.cinematic;
    if (this.dirty || continuous || breathing) this.render();
    if (continuous) this.schedule(0);
    else if (breathing) this.schedule(40); // ~24 fps is plenty for a slow breath
  }

  updateLeds(now, breathing) {
    if (!this.chargeMat) return;
    const base = this.materials.get('amber_led');
    let k;
    if (this.state.mode === 'stow') k = breathing ? 0.35 + 0.65 * (0.5 - 0.5 * Math.cos((now / 1000) * ((2 * Math.PI) / 3.2))) : 0.8;
    else k = 0.22; // devices out of their pockets: indicators idle
    this.chargeMat.emissiveIntensity = base.emissiveIntensity * k;
  }

  render() {
    this.dirty = false;
    this.stage.prerender(this.scene, this.camera, this.model.root, this.contactExclude());
    this.output.render();
    if (!this.readySent) {
      this.timings.firstFrame = Math.round(performance.now() - (this.t0 || 0));
      this.readySent = true;
      this.el.classList.add('ready');
      post({ type: 'ready' });
    } else if (this.firstFrameAfterRestore) {
      this.firstFrameAfterRestore = false;
      if (this.lostReported) {
        this.lostReported = false;
        post({ type: 'ready' });
      }
    }
  }

  contactExclude() {
    const out = [];
    const mat = this.model.groups.get('deskmat');
    if (mat) out.push(mat.node);
    for (const l of this.model.edgeLines) out.push(l);
    return out;
  }
}

function syncAmber(dst, src) {
  dst.emissiveIntensity = src.emissiveIntensity;
  dst.color.copy(src.color);
}

function isShown(o) {
  for (let x = o; x; x = x.parent) if (!x.visible) return false;
  return true;
}

