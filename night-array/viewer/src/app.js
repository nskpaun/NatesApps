// The Night Array viewer: scene, state application, camera, render-on-demand loop and the NA command API.
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { DEFAULT_STATE, mergeState, CAMERAS, DOCK_COMMANDS } from './state.js';
import { post } from './bridge.js';
import { Tweens, ease, clamp, lerp, smoothstep, smootherstep, DEG, OVERLAY_LAYER } from './util.js';
import { loadModelFiles, Model } from './model.js';
import { MaterialLib } from './materials.js';
import { Stage, BG } from './stage.js';
import { Output, QUALITY } from './post.js';
import { PRESETS, fovFor, dirFrom, fitPoints, boxCorners, sphericalOf, cameraTween } from './cameras.js';
import { ScreenSurface } from './screen.js';
import { StyleManager, StyleFade, AMBER } from './styles.js';
import { SectionTool } from './section.js';
import { Dims } from './dims.js';
import { Highlighter } from './highlight.js';
import { Fader } from './fade.js';

const MODEL_BASE = '../model/';
const PIXEL_BUDGET = { high: 2.4e6, balanced: 1.5e6, battery: 0.9e6 };
// emissive gain of the desktop texture (ACES has a deep toe: the dark wallpaper needs a push to read)
const SCREEN_GLOW = { on: 1.8, stow: 1.25 };
const MODES_ALL = ['work', 'stow', 'standalone'];
// dock step motion: seconds for the laptop and the latch sub-group (scene.json gives the poses, these the pace)
const DOCK_PACE = {
  align: { laptop: 1.0, latch: 0.25 },
  lower: { laptop: 1.15, latch: 0.25 },
  release: { laptop: 0.4, latch: 0.2 },
  lift: { laptop: 1.1, latch: 0.32 },
  reset: { laptop: 1.1, latch: 0.25 },
};
// NA.dock('play'): when each step starts (ms); null = the reset motion, which posts 'done' as it starts
const DOCK_PLAY = [['align', 0], ['lower', 1500], ['release', 3050], ['lift', 3900], [null, 5500]];
const DOCK_PLAY_DONE = 5500 + DOCK_PACE.reset.laptop * 1000 + 80;
// Night shift orbit: elevation range (min, mid, max degrees) and the breathing of its distance (+-)
const CINE_EL = [8, 13, 18];
const CINE_BREATH = 0.06;
const CINE_STEP = 5; // degrees between the orbit-distance table's entries
const TAP_SLOP = 8; // CSS px: a pointer that moves less than this (and lifts within 350 ms) is a tap
// touch picking: groups smaller than this on screen (CSS px = dp in the WebView) get a padded target
const TOUCH_TARGET = 44;

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
    this.layoutKeys = new Set();
    this.layoutEnd = null;
    this.chargeAt = 0;
    this.glow = { k: 1, flash: 0, seated: true };
    this.compiled = new Set(); // program sets compiled for the output target (programKey())
    this.hold = null; // behindFrame(): the frame on screen stays up while new programs compile
  }

  // ------------------------------------------------------------------ boot
  async init() {
    this.t0 = performance.now();
    const canvas = document.createElement('canvas');
    canvas.setAttribute('aria-label', 'Night Array live 3D view');
    this.el.insertBefore(canvas, this.el.firstChild);
    this.canvas = canvas;
    const gl = canvas.getContext('webgl2', { antialias: true, alpha: false, powerPreference: 'high-performance', preserveDrawingBuffer: false, stencil: true });
    if (!gl) throw Object.assign(new Error("WebGL2 isn't available on this device"), { friendly: 'webgl2' });
    const renderer = new THREE.WebGLRenderer({ canvas, context: gl, antialias: true });
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.0;
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.autoUpdate = false;
    renderer.shadowMap.needsUpdate = true;
    renderer.setClearColor(BG, 1);
    renderer.localClippingEnabled = true; // section view clips the model's materials only
    renderer.info.autoReset = false; // reset once per frame in render()
    this.renderer = renderer;
    this.hdrOk = renderer.extensions.has('EXT_color_buffer_float') || renderer.extensions.has('EXT_color_buffer_half_float');
    // Every tier needs half-float render targets: the PMREM environment (all tiers), the desk reflection and the
    // bloom composer. Without them the framebuffers are incomplete and the frame comes out dark and wrong, so the app
    // keeps its stills instead of getting a 'ready' for a broken image.
    if (!this.hdrOk) {
      renderer.dispose();
      renderer.forceContextLoss();
      throw Object.assign(new Error('this GPU cannot render to half-float targets'), { friendly: 'hdr' });
    }

    // start the downloads first; paint the procedural set while they are in flight
    const T0 = performance.now();
    const mark = (k) => { this.timings[k] = Math.round(performance.now() - T0); };
    this.timings = {};
    const files = loadModelFiles(MODEL_BASE);
    files.catch(() => {});

    this.scene = new THREE.Scene();
    this.scene.background = BG.clone();
    this.scene.fog = new THREE.Fog(BG.clone().multiplyScalar(0.8), 4.5, 11);
    this.fog = this.scene.fog;
    this.bgColor = this.scene.background;
    this.camera = new THREE.PerspectiveCamera(30, 1, 0.02, 40);
    this.camera.layers.enable(OVERLAY_LAYER); // edges, rims, caps, dims: main view only
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
    this.setupDockGlow();
    this.setupPracticals();
    for (const p of this.model.parts.values()) p.mesh.userData.studioMat = p.mesh.material;
    this.section = new SectionTool(this);
    for (const m of this.materials.all()) this.section.register(m);
    for (const pool of this.stage.pools) this.section.register(pool.material); // light pools belong to the station
    this.section.attach(this.model);
    this.styles = new StyleManager(this);
    this.fader = new Fader(this);
    this.highlight = new Highlighter(this);
    this.styleFade = new StyleFade(renderer);
    this.dims = new Dims(this, document.getElementById('labels') || this.el);
    this.dims.build(sceneJson.dims || [], this.restGroupBoxes());
    this.resize(true);
    mark('model');

    this.loaded = true;
    this.cameraSet = false;
    this.applyState(new Set(Object.keys(this.state)), { immediate: true, initial: true });
    // queued commands run before the first frame, so they jump instead of animating
    this.drainQueue(true);
    if (!this.cameraSet) this.setCamera('hero', { immediate: true, group: this.state.isolate && this.model.groups.has(this.state.isolate) ? this.state.isolate : null });
    this.tweens.finishAll();
    mark('state');
    await this.compileForOutput(); // (a failure just compiles lazily on the first frame)
    mark('compiled');
    this.compiled.add(this.programKey());
    this.requestRender();
    // paint the other modes' desktops (so a mode change cross-fades without a hitch) and compile the fades' programs
    // once the page is idle: not in the middle of an animation or a dock play, since on GPUs without parallel shader
    // compilation both stall the main thread (and with it the dock sequence's timers)
    const idleWork = (tries) => {
      if (tries < 8 && (this.tweens.size || this.dockPlay || this.pendingPlay || this.hold)) {
        setTimeout(() => idleWork(tries + 1), 1000);
        return;
      }
      if (this.screen) this.screen.prepaint(MODES_ALL);
      if (!this.capture) this.prewarm();
    };
    setTimeout(() => idleWork(0), 2500);
  }

  /** World boxes of each group at rest (stow pose, nothing exploded), hidden groups included. */
  restGroupBoxes() {
    const out = new Map();
    for (const id of this.model.groups.keys()) out.set(id, this.model.bounds([id], { includeInternal: true, includeHidden: true }));
    return out;
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
    // OrbitControls fires 'start' on pointerdown, before anything moves, so a plain tap (every pick) must not count
    // as the user taking over the view: only a 'change' during a real gesture does (a drag or pinch past the tap
    // slop, or the wheel). Until then presets, isolate and resizes keep re-framing, and camera moves keep flying.
    c.addEventListener('start', () => {
      this.interacting = true;
      this.requestRender();
    });
    c.addEventListener('change', () => {
      if (this.interacting && (!this.pointer || this.pointer.dragged)) {
        this.userMoved = true;
        this.tweens.cancel('camera');
      }
      this.requestRender();
    });
    c.addEventListener('end', () => { this.interacting = false; });
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
      if (this.styles) this.styles.restore();
      if (this.styleFade) this.styleFade.release(true);
      if (this.section) this.section.setStyle(this.state.style);
      this.stage.desk.material.envMap = this.scene.environment;
      this.stage.contact.dirty = true;
      this.renderer.shadowMap.needsUpdate = true;
      if (this.screen) this.screen.touch();
      this.firstFrameAfterRestore = true;
      this.compiled.clear(); // every program is gone with the old context
      if (this.hold) this.releaseHold(this.hold, false);
      this.requestRender();
    });
    // tap (not drag) picking. this.pointer is the gesture in progress; `dragged` once it is no longer a tap
    // (moved TAP_SLOP or more, or a second finger came down). These listeners run before OrbitControls' pointermove
    // (it adds its own on each pointerdown), so `dragged` is current when the controls report the change.
    this.pointer = null;
    this.canvas.addEventListener('pointerdown', (e) => {
      const down = this.pointer;
      // event times, not handler times: a long frame between down and up must not turn a tap into a long press
      if (e.isPrimary) this.pointer = { x: e.clientX, y: e.clientY, t: e.timeStamp || performance.now(), id: e.pointerId, multi: false, dragged: false };
      else if (down) { down.multi = true; down.dragged = true; }
    });
    this.canvas.addEventListener('pointermove', (e) => {
      const down = this.pointer;
      if (down && e.pointerId === down.id && !down.dragged && Math.hypot(e.clientX - down.x, e.clientY - down.y) >= TAP_SLOP) down.dragged = true;
    });
    this.canvas.addEventListener('pointerup', (e) => {
      const down = this.pointer;
      if (!down || e.pointerId !== down.id) return;
      const d = Math.hypot(e.clientX - down.x, e.clientY - down.y);
      const dt = (e.timeStamp || performance.now()) - down.t;
      const multi = down.multi;
      this.pointer = null;
      if (multi || d >= TAP_SLOP || dt >= 350 || this.state.cinematic || !this.loaded) return; // a tap, not a drag
      this.pick(e.clientX, e.clientY, e.pointerType);
    });
    this.canvas.addEventListener('pointercancel', () => { this.pointer = null; });
  }

  // ------------------------------------------------------------------ model extras
  setupLeds() {
    // charge indicators get their own instance of the LED material so they can breathe while charging
    this.chargeMat = this.materials.variant('amber_led', 'amber_led-charge');
    this.materials.extraAmber = [this.chargeMat];
    for (const id of ['kb_charge_led', 'mouse_charge_led']) {
      const p = this.model.parts.get(id);
      if (p) p.mesh.material = this.chargeMat;
    }
  }

  /** The sprung USB-C connector glows when the laptop is seated; the latch light follows (flash on seat). */
  setupDockGlow() {
    const conn = this.model.parts.get('dock_connector');
    if (conn) {
      const m = this.materials.variant(conn.material, `${conn.material}-connector`);
      m.emissive = new THREE.Color(AMBER);
      m.emissiveIntensity = 0;
      conn.mesh.material = m;
      this.connectorMat = m;
    }
    const led = this.model.parts.get('dock_latch_led');
    if (led) {
      this.latchMat = this.materials.variant(led.material, `${led.material}-latch`);
      led.mesh.material = this.latchMat;
    }
  }

  /** Seated = the laptop rests in the cradle (at its pose, not lifted). Returns true while the glow animates. */
  updateDockGlow(dt) {
    const g = this.glow;
    const lap = this.model.movables.get('laptop');
    const base = this.materials.get('amber_led');
    if (!lap || !base) return false;
    const seated = !!this.laptopSeat && lap.node.visible && !this.fader.isFading(lap.node) && lap.node.position.distanceTo(this.laptopSeat) < 0.0025;
    if (seated && !g.seated && this.readySent) g.flash = 1;
    g.seated = seated;
    const target = seated ? 1 : 0;
    const a = 1 - Math.exp(-dt * 7);
    g.k += (target - g.k) * a;
    g.flash *= Math.exp(-dt * 3.2);
    if (Math.abs(g.k - target) < 0.004) g.k = target;
    if (g.flash < 0.004) g.flash = 0;
    const amber = base.emissiveIntensity; // already follows the amber level (0 = off)
    if (this.connectorMat) this.connectorMat.emissiveIntensity = amber * (0.12 * g.k + 0.5 * g.flash);
    if (this.latchMat) {
      this.latchMat.color.copy(base.color);
      this.latchMat.emissiveIntensity = amber * (0.3 + 0.7 * g.k + 0.6 * g.flash);
    }
    return g.k !== target || g.flash > 0;
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
    const has = (...k) => initial || k.some((x) => changed.has(x));
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
    if (has('style')) this.applyStyle(immediate || initial);
    if (has('mode')) this.screenTo(s.mode, immediate || initial);
    if (has('selected', 'style')) {
      if (changed.has('selected') || initial) {
        this.fader.finishAll(); // material swaps below must not race a running fade
        this.styles.setSelected(s.selected);
      }
      this.highlight.set(s.selected, s.style, immediate || initial);
    }
    if (has('mode', 'explode', 'isolate', 'style', 'section')) {
      this.layout(immediate, changed.has('isolate') ? (s.isolate ? 'group' : 'preset') : changed.has('mode') || changed.has('explode') ? 'preset' : null);
    }
    if (has('section', 'style', 'mode', 'explode', 'isolate')) this.applySection(immediate || initial, changed.has('section') || initial);
    if (has('dims', 'mode', 'explode', 'isolate', 'style')) {
      this.dims.setTargets(s, s.dims);
      const fn = this.dims.fadeFn();
      if (immediate || initial) fn(1);
      else this.tweens.run('dims', 0.4, fn, { delay: changed.has('mode') && s.dims ? 0.9 : 0, ease: ease.inOutSine });
    }
    if (has('autorotate', 'cinematic')) {
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
    // shadow filter, tone mapping (composer or canvas) and pixel ratio change: every material gets new programs,
    // compiled behind a snapshot of the current frame, which then cross-fades to the new tier
    this.behindFrame(() => {
      this.q = q;
      this.renderer.shadowMap.type = q.shadowType;
      this.renderer.shadowMap.needsUpdate = true;
      this.resize(true);
      if (this.screen && this.screen.setScale(q.screen) && this.screenMat) {
        this.screenTo(this.state.mode, true);
        this.screenMat.needsUpdate = true;
      }
      for (const m of this.materials ? this.materials.all() : []) m.needsUpdate = true;
    }, { key: this.programKey(), snapshot: true, fade: 0.35 });
  }

  /** Names the set of shader programs a frame needs: per style, tier (shadow filter, output target) and clipping. */
  programKey(section = !!(this.section && this.section.active)) {
    return `${this.state.style}|${this.state.quality}|${section ? 'cut' : 'whole'}`;
  }

  canAnimate() {
    return this.readySent && !this.hidden && !this.contextLost && !this.capture;
  }

  /**
   * Compiles `root`'s programs (lit by this.scene) for the target the frame really draws into: the composer's HDR
   * target on the bloom tiers (no tone mapping, linear output), the canvas on battery. Programs compiled with no
   * target bound would be the canvas variants, which the bloom tiers never draw. compile() runs synchronously inside
   * compileAsync and reads the bound target, so it is bound just for the call. Never rejects.
   * While the section is active its materials compile in a pass of their own: three's compile() doesn't set up
   * local clipping per material (it keeps the plane count of the last material drawn), so a no-op draw of a clipped
   * material sets that count first (primeClipping) and only the section's materials are compiled under it.
   */
  compileForOutput(root = this.scene) {
    const r = this.renderer, S = this.section;
    const prev = r.getRenderTarget();
    const jobs = [];
    const compile = (obj) => {
      r.setRenderTarget(this.output.sceneTarget());
      jobs.push(r.compileAsync(obj, this.camera, this.scene).catch(() => {}));
    };
    try {
      if (S && S.active) {
        const cut = new THREE.Group(), whole = new THREE.Group();
        root.traverseVisible((o) => {
          const m = o.material;
          if (!m || Array.isArray(m)) return;
          const Kind = o.isMesh ? THREE.Mesh : o.isLineSegments ? THREE.LineSegments : o.isLine ? THREE.Line : o.isPoints ? THREE.Points : null;
          if (Kind) (S.mats.has(m) ? cut : whole).add(new Kind(o.geometry, m)); // proxies: same geometry, same material
        });
        this.primeClipping(false);
        compile(whole);
        this.primeClipping(true);
        compile(cut);
        this.primeClipping(false);
      } else compile(root);
    } catch (e) {
      /* compiles lazily on the next frame instead */
    } finally {
      r.setRenderTarget(prev);
    }
    return Promise.all(jobs);
  }

  /** Sets three's current clipping plane count (none, or the section plane) with a draw of nothing into 1 x 1. */
  primeClipping(on) {
    let P = this.clipPrime;
    if (!P) {
      const geo = new THREE.BufferGeometry();
      geo.setAttribute('position', new THREE.Float32BufferAttribute(new Float32Array(9), 3));
      geo.setDrawRange(0, 0); // three sets the program (and the clipping state) up, then finds nothing to draw
      const mesh = new THREE.Mesh(geo);
      mesh.frustumCulled = false;
      const scene = new THREE.Scene();
      scene.add(mesh);
      P = this.clipPrime = {
        mesh, scene, rt: new THREE.WebGLRenderTarget(1, 1),
        on: new THREE.MeshBasicMaterial({ colorWrite: false, depthWrite: false }), off: new THREE.MeshBasicMaterial({ colorWrite: false, depthWrite: false }),
      };
    }
    P.on.clippingPlanes = this.section.planes;
    P.mesh.material = on ? P.on : P.off;
    const r = this.renderer;
    r.setRenderTarget(P.rt);
    r.render(P.scene, this.camera);
  }

  /**
   * A change that needs shader programs the GPU may not have yet (style, quality tier, the first section cut).
   * `apply()` makes the change; the programs compile (in parallel where KHR_parallel_shader_compile exists) while the
   * canvas keeps the current frame, for at most 4 s; then `start()` runs (a sweep, ...). With `snapshot` the current
   * frame is captured first and cross-fades out over `fade` s. `key` names the program set (programKey()): a set that
   * compiled before skips the hold. Changes that arrive during a hold join it.
   */
  behindFrame(apply, { key, snapshot = false, fade = 0.6, start = null } = {}) {
    const animate = this.canAnimate();
    if (animate && snapshot && !(this.hold && this.hold.snapshot)) {
      this.render();
      this.styleFade.capture();
    }
    apply();
    if (!animate) {
      if (snapshot) {
        this.tweens.cancel('stylefade');
        this.styleFade.cancel();
      }
      this.compiled.add(key); // compiled by the next frame anyway
      if (start) start();
      return;
    }
    const h = this.hold || { snapshot: false, redraw: false, starts: [], token: 0 };
    h.starts.push({ start, snapshot, fade });
    if (snapshot) {
      this.tweens.cancel('stylefade');
      h.snapshot = true;
      h.redraw = true; // apply() may have resized (cleared) the canvas: the snapshot stands in for the old frame
    }
    if (this.compiled.has(key) && !this.hold) {
      this.releaseHold(h);
      return;
    }
    this.compiled.add(key);
    this.hold = h;
    const token = ++h.token;
    const done = () => { if (this.hold === h && h.token === token) this.releaseHold(h); };
    this.compileForOutput().then(done);
    setTimeout(done, 4000); // never hold longer than this
  }

  /** Ends a hold: cross-fades from the snapshot (fade = false: drops it) and runs the waiting starts. */
  releaseHold(h = this.hold, fade = true) {
    if (!h) return;
    if (this.hold === h) this.hold = null;
    let dur = 0;
    for (const x of h.starts) if (x.snapshot) dur = Math.max(dur, x.fade);
    if (dur && fade) this.tweens.run('stylefade', dur, (t) => { this.styleFade.alpha = 1 - t; }, { ease: ease.inOutSine });
    else if (!fade && h.snapshot) {
      this.tweens.cancel('stylefade');
      this.styleFade.release();
    }
    for (const x of h.starts) if (x.start) x.start();
    this.requestRender();
  }

  /**
   * Style switch: cross-fades from a snapshot of the old style's last frame. The new style's shader programs are
   * compiled first (behindFrame) while the old frame stays on screen.
   */
  applyStyle(immediate) {
    const style = this.state.style;
    this.fader.finishAll();
    const apply = () => {
      this.styles.apply(style);
      this.section.setStyle(style);
      this.highlight.setStyle(style);
      this.dims.setStyle(style);
      this.stage.contact.dirty = true;
      this.renderer.shadowMap.needsUpdate = true;
    };
    if (immediate) {
      apply();
      this.tweens.cancel('stylefade');
      this.styleFade.cancel();
      this.compiled.add(this.programKey());
      return;
    }
    this.behindFrame(apply, { key: this.programKey(), snapshot: true, fade: 0.6 });
  }

  /**
   * Transparent twins of the studio materials (what fades draw with) compile while the page is idle after load,
   * straight into the Fader's pool, so the first isolate / desk-mat / standalone fade finds its programs ready.
   * Each twin is compiled on the real part geometry (brushed metals need its tangents: a different program) and
   * for the target the frame draws into.
   */
  prewarm() {
    if (this.prewarmed || !this.loaded) return Promise.resolve();
    this.prewarmed = true;
    const root = new THREE.Group();
    const twins = new Map();
    const add = (o) => {
      if (!Fader.fadeable(o)) return;
      let c = twins.get(o.material);
      if (!c) twins.set(o.material, (c = this.fader.take(o.material)));
      root.add(new THREE.Mesh(o.geometry, c));
    };
    for (const p of this.model.parts.values()) add(p.mesh);
    for (const pool of this.stage.pools) add(pool);
    return this.compileForOutput(root).then(() => {
      for (const c of twins.values()) this.fader.give(c);
      root.clear(); // the proxies share the parts' geometry: nothing to dispose
    });
  }

  // ------------------------------------------------------------------ screen: one desktop per mode, wake / sleep
  setupScreen() {
    const def = this.sj.screen || {};
    const part = this.model.parts.get(def.part || 'display_screen');
    if (!part) return;
    this.screen = new ScreenSurface(THREE, def, QUALITY[this.state.quality].screen);
    const m = this.materials.variant('screen', 'screen-live');
    m.emissive = new THREE.Color(1, 1, 1);
    m.emissiveMap = this.screen.texture(this.state.mode);
    m.emissiveIntensity = SCREEN_GLOW.on;
    // cross-fade between two desktop textures (uScreenMix: 0 = previous, 1 = current)
    const u = { uScreenPrev: { value: m.emissiveMap }, uScreenMix: { value: 1 } };
    this.screenUniforms = u;
    m.onBeforeCompile = (shader) => {
      Object.assign(shader.uniforms, u);
      shader.fragmentShader = 'uniform sampler2D uScreenPrev;\nuniform float uScreenMix;\n' + shader.fragmentShader.replace(
        '#include <emissivemap_fragment>',
        `#ifdef USE_EMISSIVEMAP
	vec4 emissiveColor = mix( texture2D( uScreenPrev, vEmissiveMapUv ), texture2D( emissiveMap, vEmissiveMapUv ), uScreenMix );
	totalEmissiveRadiance *= emissiveColor.rgb;
#endif`);
    };
    m.customProgramCacheKey = () => 'screen-xfade';
    part.mesh.material = m;
    this.screenMat = m;
    this.screenMode = this.state.mode;
  }

  /** Wake (stow -> work / standalone), sleep (-> stow) or switch desktops, as a cross-fade with a dip in brightness. */
  screenTo(mode, immediate) {
    if (!this.screen || !this.screenMat) return;
    const m = this.screenMat, u = this.screenUniforms;
    const from = this.screenMode;
    const tex = this.screen.texture(mode);
    const i1 = mode === 'stow' ? SCREEN_GLOW.stow : SCREEN_GLOW.on;
    this.screenMode = mode;
    if (immediate || from === mode) {
      this.tweens.cancel('screen');
      m.emissiveMap = tex;
      u.uScreenPrev.value = tex;
      u.uScreenMix.value = 1;
      m.emissiveIntensity = i1;
      return;
    }
    const prevTex = m.emissiveMap;
    const mix0 = u.uScreenMix.value;
    u.uScreenPrev.value = mix0 < 0.5 ? u.uScreenPrev.value : prevTex;
    m.emissiveMap = tex;
    u.uScreenMix.value = 0;
    const i0 = m.emissiveIntensity;
    const sleeping = mode === 'stow', waking = from === 'stow';
    const dip = sleeping ? 0.85 : waking ? 0.7 : 0.35;
    this.tweens.run('screen', sleeping ? 1.3 : 1.0, (t) => {
      // the old desktop dims away, the new one comes up through the dip (a wake has a slight overshoot)
      u.uScreenMix.value = smoothstep(0.3, 0.7, t);
      const bump = waking ? 0.08 * smoothstep(0.6, 0.85, t) * (1 - smoothstep(0.85, 1, t)) : 0;
      m.emissiveIntensity = lerp(i0, i1, t) * (1 - dip * Math.sin(Math.PI * t)) * (1 + bump);
    }, { ease: ease.linear, delay: sleeping ? 0.35 : 0, onDone: () => { u.uScreenPrev.value = tex; u.uScreenMix.value = 1; } });
  }

  // ------------------------------------------------------------------ layout & choreography
  /** Pose delta that carries a group out through the top when its pose hides it (the laptop leaving for standalone). */
  liftOut(id) {
    const step = (this.sj.dock_sequence || []).find((x) => x.step === 'lift');
    const d = step && step[id];
    return d && Array.isArray(d.t) ? new THREE.Vector3(d.t[0], d.t[1], d.t[2]) : null;
  }

  /**
   * Visibility + transforms for mode pose, dock step, explode and isolate, choreographed:
   *  - devices (keyboard, mouse) travel between their pockets and the desk mat through scene.json's "via" waypoints
   *    (lift clear of the rim, slide, set down), both on the same timing; poses without waypoints get a computed arc
   *  - the desk mat fades in before they land and out after they leave
   *  - the laptop lifts out and fades for standalone (and comes back down the same way)
   *  - dock steps move the laptop / latch at their own pace; isolate fades the other groups
   */
  layout(immediate, reframe = null, dock = null) {
    const s = this.state;
    const M = this.model;
    const fromMode = this.layoutMode || s.mode;
    this.layoutMode = s.mode;
    const modeChanged = fromMode !== s.mode;
    const targets = M.targets(s.mode, this.dockStep);
    const restTargets = M.targets(s.mode, null);
    if (this.dockStep) {
      const step = (this.sj.dock_sequence || []).find((x) => x.step === this.dockStep);
      for (const id of Object.keys(step || {})) if (targets.has(id)) targets.get(id).hidden = false;
    }
    const iso = s.isolate && M.groups.has(s.isolate) ? s.isolate : null;
    const showInternal = s.style === 'xray' || s.explode > 0.001 || !!s.section || iso === 'internals';

    // plans: where every movable goes and whether it is shown
    const plans = [];
    for (const [id, mv] of M.movables) {
      const tg = targets.get(id);
      const rest = mv.parent ? mv.pivot.clone().sub(mv.parent.pivot) : mv.pivot.clone();
      const p1 = rest.clone().add(tg.t);
      const q1 = new THREE.Quaternion().setFromEuler(tg.r);
      const isolated = mv.isGroup && iso && iso !== id;
      // isolating a group the pose hides (the laptop in standalone, the desk mat in stow) shows it at its rest place:
      // isolate means "show only this group", never an empty stage
      const forced = mv.isGroup && iso === id && tg.hidden;
      const poseHidden = tg.hidden && !forced;
      const visible = !poseHidden && !isolated;
      const lift = poseHidden ? this.liftOut(id) : null;
      if (lift) p1.add(lift);
      if (id === 'laptop') this.laptopSeat = rest.clone().add(restTargets.get(id).t);
      const shown = mv.shown ?? mv.node.visible;
      plans.push({ id, mv, rest, p0: mv.node.position.clone(), q0: mv.node.quaternion.clone(), p1, q1, visible, shown, isolated, poseHidden, lift });
      mv.shown = visible;
    }
    this.layoutEnd = plans;

    const keys = new Set();
    const run = (key, dur, fn, opts) => { keys.add(key); this.tweens.run(key, dur, fn, opts); };
    const dirty = () => { this.stage.contact.dirty = true; this.renderer.shadowMap.needsUpdate = true; };
    const ex = s.explode;
    for (const p of M.parts.values()) p.mesh.visible = !p.internal || showInternal;

    // keep the framing honest: a camera that sits on a preset (or an isolated group) re-frames the new layout.
    // Framed first (on where everything will land), so an isolate's fade can follow the camera move.
    let camDur = 0;
    if (this.readySent && this.cameraSet && !s.cinematic) {
      if (reframe === 'group' && iso) camDur = this.setCamera(null, { group: iso, immediate, endLayout: true });
      else if (!this.userMoved && (reframe || iso)) camDur = this.setCamera(this.cameraName || 'hero', { immediate, group: iso, endLayout: true });
    }

    if (immediate) {
      for (const k of this.layoutKeys) this.tweens.cancel(k);
      for (const pl of plans) {
        if (this.fader.isFading(pl.mv.node)) this.tweens.finish(`fade:${pl.mv.node.uuid}`);
        pl.mv.node.position.copy(pl.p1);
        pl.mv.node.quaternion.copy(pl.q1);
        pl.mv.node.visible = pl.visible;
      }
      for (const p of M.parts.values()) p.node.position.copy(p.rest).addScaledVector(p.explode, ex);
      this.chargeAt = s.mode === 'stow' ? 0 : Infinity;
      dirty();
    } else {
      // devices that change place between modes (pocket <-> desk mat): through scene.json's "via" waypoints when the
      // pose has them (lift clear of the rim, slide out, set down; reversed going back), else on a computed arc
      const arcs = plans.filter((pl) => pl.visible && pl.shown && pl.mv.isGroup && Math.hypot(pl.p1.x - pl.p0.x, pl.p1.z - pl.p0.z) > 0.05 && modeChanged);
      const obstacle = M.bounds(['base'], { includeHidden: true }).max.y;
      let arcEnd = 0;
      for (const pl of arcs) pl.route = this.viaRoute(pl, fromMode, s.mode);
      // segment timing is shared by every device on a route with the same number of legs (SPEC: same timing for both)
      const legDurs = new Map();
      for (const pl of arcs) {
        if (!pl.route) continue;
        const n = pl.route.length - 1;
        const d = legDurs.get(n) || new Array(n).fill(0);
        for (let k = 0; k < n; k++) d[k] = Math.max(d[k], 0.24 + 1.5 * pl.route[k].distanceTo(pl.route[k + 1]));
        legDurs.set(n, d);
      }
      arcs.forEach((pl, i) => {
        const returning = pl.p1.distanceTo(pl.rest) < pl.p0.distanceTo(pl.rest);
        let path, dur, delay;
        if (pl.route) {
          const durs = legDurs.get(pl.route.length - 1);
          dur = durs.reduce((a, b) => a + b, 0);
          delay = returning ? 0 : 0.22; // leaving the pockets waits for the mat to start fading in
          path = waypointPath(pl.route, durs, pl.q0, pl.q1);
        } else {
          delay = (returning ? 0 : 0.22) + i * 0.16;
          dur = 1.35 - i * 0.08;
          const bottom = M.bounds([pl.id], { includeHidden: true }).min.y - pl.mv.node.getWorldPosition(new THREE.Vector3()).y;
          const apex = Math.max(obstacle + 0.018 - bottom, Math.max(pl.p0.y, pl.p1.y) + 0.03);
          path = arcPath(pl.p0, pl.p1, apex, pl.q0, pl.q1);
        }
        arcEnd = Math.max(arcEnd, delay + dur);
        run(`mv:${pl.id}`, dur, (t) => { path(t, pl.mv.node.position, pl.mv.node.quaternion); dirty(); }, { delay, ease: ease.linear });
        pl.done = true;
      });
      if (modeChanged) this.chargeAt = s.mode === 'stow' ? performance.now() + arcEnd * 1000 : Infinity;

      const dockPace = dock ? DOCK_PACE[dock.to || 'reset'] : null;
      for (const pl of plans) {
        if (pl.done) continue;
        const node = pl.mv.node;
        let dur = 0.9, delay = 0, easing = ease.inOutCubic, path = null;
        const appear = pl.visible && !pl.shown, vanish = !pl.visible && pl.shown;
        if (dockPace && (pl.id === 'laptop' || pl.id === 'dock_latch')) {
          dur = pl.id === 'laptop' ? dockPace.laptop : dockPace.latch;
          if (pl.id === 'laptop' && dock.to === 'lower') path = seatPath(pl.p0, pl.p1);
          if (pl.id === 'dock_latch') easing = dock.to === 'lift' ? ease.outQuart : ease.inOutSine;
        }
        if (pl.lift && vanish) {
          // standalone: the laptop lifts out of the cradle and fades away up there
          dur = 1.15;
          this.fader.fade(node, 0, { duration: 0.6, delay: 0.5 });
        } else if (appear && this.liftOut(pl.id) && !pl.isolated && !node.visible) {
          // back from standalone: appear above the cradle and come down into it
          node.position.copy(pl.p1).add(this.liftOut(pl.id));
          pl.p0.copy(node.position);
          dur = 1.25;
          easing = ease.inOutCubic;
          this.fader.fade(node, 1, { duration: 0.55 });
        } else if (vanish && pl.isolated && reframe === 'group' && camDur > 0) {
          // isolate: the others fade along with the camera move, so the stage doesn't empty before the framed
          // group has arrived in the middle of the view
          this.fader.fade(node, 0, { duration: 0.6 * camDur, delay: 0.15 });
        } else if (vanish) {
          // the desk mat waits for the devices to leave it
          this.fader.fade(node, 0, { duration: 0.45, delay: pl.poseHidden && arcs.length ? Math.max(0, arcEnd - 0.3) : 0 });
        } else if (appear) {
          this.fader.fade(node, 1, { duration: 0.45 });
        }
        if (pl.p0.distanceToSquared(pl.p1) < 1e-12 && Math.abs(pl.q0.dot(pl.q1)) > 1 - 1e-9) {
          // already where it belongs: a move still running from the previous layout must not carry it off
          this.tweens.cancel(`mv:${pl.id}`);
          continue;
        }
        const p0 = pl.p0, q0 = pl.q0;
        run(`mv:${pl.id}`, dur, (t) => {
          if (path) path(t, node.position);
          else node.position.lerpVectors(p0, pl.p1, t);
          node.quaternion.slerpQuaternions(q0, pl.q1, t);
          dirty();
        }, { ease: path ? ease.linear : easing, delay });
      }
      const parts = [];
      for (const p of M.parts.values()) {
        const b = p.rest.clone().addScaledVector(p.explode, ex);
        if (p.node.position.distanceToSquared(b) > 1e-12) parts.push({ p, a: p.node.position.clone(), b });
      }
      // slider drags send many small steps: small changes follow quickly, big jumps take their time
      const exDur = clamp(0.3 + Math.abs(ex - (this.layoutExplode ?? ex)) * 0.9, 0.3, 0.9);
      if (parts.length) run('explode', exDur, (t) => { for (const x of parts) x.p.node.position.lerpVectors(x.a, x.b, t); dirty(); }, { ease: ease.inOutCubic });
      else this.tweens.cancel('explode');
      dirty();
    }
    this.layoutKeys = keys;
    this.layoutExplode = ex;
    this.stage.setExplodeFade(ex);
    this.targetBox = null; // clampTarget() bounds follow the layout
  }

  /**
   * Positions (parent space) a device passes through from where it is now (p0) to its new pose: the old pose's
   * "via" waypoints reversed (back toward stow), then the new pose's in order. A move that interrupts another joins
   * the route at its nearest leg, so it never doubles back through a waypoint it has already passed.
   * Null when neither pose has waypoints.
   */
  viaRoute(pl, fromMode, toMode) {
    const M = this.model;
    const back = fromMode === toMode ? [] : M.via(fromMode, pl.id).reverse();
    const out = M.via(toMode, pl.id);
    if (!back.length && !out.length) return null;
    const from = pl.rest.clone().add(M.targets(fromMode, null).get(pl.id).t);
    const full = [from, ...[...back, ...out].map((d) => pl.rest.clone().add(d)), pl.p1.clone()];
    let best = 0, bestD = Infinity;
    const seg = new THREE.Line3(), q = new THREE.Vector3();
    for (let k = 0; k < full.length - 1; k++) {
      seg.set(full[k], full[k + 1]);
      const d = seg.closestPointToPoint(pl.p0, true, q).distanceToSquared(pl.p0);
      if (d < bestD - 1e-12) { bestD = d; best = k; }
    }
    const route = [pl.p0.clone(), ...full.slice(best + 1)];
    return route.filter((p, k) => k === 0 || p.distanceToSquared(route[k - 1]) > 1e-10);
  }

  layoutRunning() {
    for (const k of this.layoutKeys) if (this.tweens.has(k)) return true;
    return false;
  }

  /**
   * Runs fn with every node where the running layout will leave it (framing must target where things land).
   * force: even when nothing is animating yet (layout() frames before it starts its tweens).
   */
  withEndLayout(fn, force = false) {
    if (!this.layoutEnd || (!force && !this.layoutRunning() && !(this.fader && this.fader.active.size))) return fn();
    const saved = [];
    for (const pl of this.layoutEnd) {
      const n = pl.mv.node;
      saved.push([n, n.position.clone(), n.quaternion.clone(), n.visible]);
      n.position.copy(pl.p1);
      n.quaternion.copy(pl.q1);
      n.visible = pl.visible;
    }
    const ex = this.state.explode;
    for (const p of this.model.parts.values()) {
      saved.push([p.node, p.node.position.clone(), null, p.node.visible]);
      p.node.position.copy(p.rest).addScaledVector(p.explode, ex);
    }
    try {
      return fn();
    } finally {
      for (const [n, pos, q, vis] of saved) {
        n.position.copy(pos);
        if (q) n.quaternion.copy(q);
        n.visible = vis;
      }
      this.model.root.updateMatrixWorld(true);
    }
  }

  // ------------------------------------------------------------------ section
  /** Bounds the section's t runs across: scene.json bounds plus wherever the visible parts end up (work mode, explode). */
  sectionBounds() {
    // an isolated group is cut across its own extent; otherwise the whole station's
    const iso = this.state.isolate && this.model.groups.has(this.state.isolate);
    const b = iso ? new THREE.Box3() : this.model.sceneBounds().clone();
    this.withEndLayout(() => b.union(this.model.bounds(null, { includeInternal: true })));
    return b.isEmpty() ? this.model.sceneBounds().clone() : b;
  }

  applySection(immediate, sectionChanged) {
    const sec = this.state.section, S = this.section, style = this.state.style;
    if (!sec) {
      if (!S.active) return;
      const fin = () => { S.setActive(false, style); this.requestRender(); };
      if (immediate || !sectionChanged) { this.tweens.cancel('section'); fin(); return; }
      // sweep the plane back out, then drop the clipping
      const c0 = S.c, c1 = S.coordFor(S.axis, 0);
      this.tweens.run('section', 0.5, (t) => S.place(S.axis, lerp(c0, c1, t), 1 - t), { ease: ease.inOutCubic, onDone: fin });
      return;
    }
    const wasActive = S.active;
    S.bounds = this.sectionBounds();
    const c1 = S.coordFor(sec.axis, sec.t);
    if (immediate) {
      S.setActive(true, style);
      this.tweens.cancel('section');
      S.place(sec.axis, c1);
      return;
    }
    // first cut (or a new axis) sweeps in from the edge; slider moves follow quickly
    const sweep = !wasActive || S.axis !== sec.axis;
    const c0 = sweep ? S.coordFor(sec.axis, 0) : S.c;
    const run = () => this.tweens.run('section', sweep ? 0.8 : 0.22, (t) => S.place(sec.axis, lerp(c0, c1, t), sweep ? t : 1), { ease: sweep ? ease.inOutCubic : ease.outCubic });
    const cut = () => {
      S.setActive(true, style);
      if (sweep) S.place(sec.axis, c0, 0);
    };
    if (!wasActive) {
      // the first cut gives every model material a clipping variant: compiled behind the current frame (which the
      // plane at t = 0 doesn't change), then the sweep starts
      this.behindFrame(cut, { key: this.programKey(true), start: run });
      return;
    }
    cut();
    run();
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
      if (spec.groups) {
        const own = M.partBoxes(spec.groups, { includeInternal: !!spec.internal });
        boxes.push(...own);
        if (spec.reach) boxes.push(...this.dockReach(spec.groups));
      }
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
    if (spec && spec.section && this.section && this.section.active) {
      // only what the section keeps, within `section` metres of the cut (stills of the cut face)
      const S = this.section, d = typeof spec.section === 'number' ? spec.section : Infinity;
      const lim = new THREE.Box3(new THREE.Vector3(-Infinity, -Infinity, -Infinity), new THREE.Vector3(Infinity, Infinity, Infinity));
      if (S.axis === 'x') { lim.min.x = S.c; lim.max.x = S.c + d; } else { lim.max.z = S.c; lim.min.z = S.c - d; }
      const kept = boxes.map((b) => b.clone().intersect(lim)).filter((b) => !b.isEmpty());
      if (kept.length) boxes = kept;
    }
    const pts = [];
    for (const b of boxes) boxCorners(b, pts);
    return pts;
  }

  /** Boxes of `groups` moved to every place scene.json's dock_sequence takes them (relative to where they are now). */
  dockReach(groups) {
    const out = [];
    const seq = this.sj.dock_sequence || [];
    const cur = (id) => {
      const s = this.dockStep && seq.find((x) => x.step === this.dockStep);
      return s && s[id] && Array.isArray(s[id].t) ? new THREE.Vector3(...s[id].t) : new THREE.Vector3();
    };
    for (const id of groups) {
      const boxes = this.model.partBoxes([id]);
      const now = cur(id);
      for (const step of seq) {
        const d = step[id];
        if (!d || !Array.isArray(d.t)) continue;
        const off = new THREE.Vector3(...d.t).sub(now);
        if (off.lengthSq() < 1e-8) continue;
        for (const b of boxes) out.push(b.clone().translate(off));
      }
    }
    return out;
  }

  /** Camera pose for a preset; `over` replaces any of its fields (the stills tool also passes fov / minDistance). */
  presetPose(name, over = null) {
    const P = over ? { ...(PRESETS[name] || PRESETS.hero), ...over } : PRESETS[name] || PRESETS.hero;
    const { w, h } = this.viewSize();
    const aspect = w / h;
    const pts = this.fitPointsFor(P.fit, name);
    const dir = dirFrom(P.az, P.el);
    const portrait = aspect < 1;
    const pad = portrait ? (P.ppad ?? P.pad * 0.7) : P.pad;
    const fit = fitPoints(pts, dir, P.fov || fovFor(aspect), aspect, pad, P.lift * (portrait ? 1.15 : 1), P.shift || 0);
    const distance = Math.max(fit.distance, P.minDistance ?? 0.34); // a lone small group (isolate) must not fill the view
    return { pos: fit.target.clone().addScaledVector(dir, distance), target: fit.target, distance, fov: P.fov || null };
  }

  /**
   * Stills tool: jump to a preset-like framing ({ preset, az, el, fit, pad, lift, shift, fov, minDistance }) with its own
   * lens. The framing holds until the next camera command or resize.
   */
  stillCamera(spec) {
    if (!this.loaded) return null;
    const pose = this.withEndLayout(() => this.presetPose(spec.preset || 'hero', spec));
    this.tweens.cancel('camera');
    const { w, h } = this.viewSize();
    this.camera.fov = pose.fov || fovFor(w / h);
    this.camera.updateProjectionMatrix();
    this.updateLimits(pose.distance);
    this.camera.position.copy(pose.pos);
    this.controls.target.copy(pose.target);
    this.camera.lookAt(pose.target);
    this.controls.update();
    this.cameraSet = true;
    this.userMoved = true; // a resize must not re-frame it
    this.requestRender();
    return { pos: pose.pos.toArray(), target: pose.target.toArray(), fov: this.camera.fov };
  }

  /**
   * Animated (or immediate) move to a named preset, or to frame a group when `group` is given.
   * Returns the move's duration in seconds (0 when it jumps or doesn't happen).
   */
  setCamera(name, { immediate = false, group = null, endLayout = false } = {}) {
    if (!this.loaded) return 0;
    if (!group && !PRESETS[name]) return 0;
    if (!group) this.cameraName = name;
    const pose = this.withEndLayout(() => (group ? this.groupPose(group) : this.presetPose(name)), endLayout);
    if (!pose) return 0;
    this.cameraSet = true;
    this.userMoved = false;
    this.updateLimits(pose.distance);
    let duration = 0;
    if (immediate || !this.readySent) {
      this.tweens.cancel('camera');
      this.camera.position.copy(pose.pos);
      this.controls.target.copy(pose.target);
      this.camera.lookAt(pose.target);
      this.controls.update();
    } else {
      // framing a group: the view centre reaches it early, so it never drifts toward the edge while the camera closes in
      const tw = cameraTween(this.camera, this.controls, pose.pos, pose.target, () => this.requestRender(), { targetEase: group ? ease.outCubic : null });
      this.tweens.run('camera', tw.duration, tw.fn, { ease: tw.ease, onDone: () => this.controls.update() });
      duration = tw.duration;
    }
    this.requestRender();
    return duration;
  }

  groupPose(groupId) {
    if (!this.model.groups.has(groupId)) return null;
    const inside = groupId === 'internals' || this.state.style === 'xray';
    let box = this.model.bounds([groupId], { includeInternal: inside });
    // a group that is hidden right now (internals in studio, the mat in stow) still frames where it is
    if (box.isEmpty()) box = this.model.bounds([groupId], { includeInternal: true, includeHidden: true });
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

  /**
   * Keeps the orbit target on the station (its scene.json bounds plus wherever the layout puts the visible parts:
   * the desk mat and devices in work mode, explode) and above the desk; a pan can't wander off into the room.
   */
  clampTarget() {
    const t = this.controls.target;
    if (!this.targetBox) {
      this.targetBox = this.withEndLayout(() => this.model.bounds(null, { includeInternal: true })).union(this.model.sceneBounds());
      this.targetBox.expandByScalar(0.05);
    }
    const b = this.targetBox;
    const cx = clamp(t.x, b.min.x, b.max.x);
    const cy = clamp(t.y, 0.01, b.max.y);
    const cz = clamp(t.z, b.min.z, b.max.z);
    if (cx !== t.x || cy !== t.y || cz !== t.z) {
      const d = new THREE.Vector3(cx - t.x, cy - t.y, cz - t.z);
      t.add(d);
      this.camera.position.add(d);
    }
    if (this.camera.position.y < 0.03) this.camera.position.y = 0.03;
  }

  /**
   * Keeps the orbiting / zooming / panning camera out of the station: if its move this frame (from `prev`) would
   * enter a visible part the section keeps, it stops 3 cm (the near plane's margin) short of that surface. Only
   * camera.position changes; OrbitControls re-derives its orbit from it on the next update, so a drag pushing
   * against a panel just stays there, and a zoom-out or an orbit the other way moves on. Moves through free space
   * (orbiting behind the display at any normal distance) are untouched: unlike a target-to-camera test, this never
   * pulls the camera in front of a part that merely sits between it and the orbit target.
   */
  avoidStation(prev) {
    const cam = this.camera.position;
    const len = cam.distanceTo(prev);
    if (!(len > 1e-6)) return false;
    const dir = new THREE.Vector3().subVectors(cam, prev).divideScalar(len);
    const ray = this.avoidRay || (this.avoidRay = new THREE.Raycaster());
    ray.set(prev, dir);
    ray.near = 0;
    ray.far = len + 0.03;
    // only parts whose (slightly grown) box the move crosses get triangle tests
    const box = new THREE.Box3(), at = new THREE.Vector3(), near = [];
    for (const p of this.model.parts.values()) {
      if (!isShown(p.mesh)) continue;
      const g = p.mesh.geometry;
      if (!g.boundingBox) g.computeBoundingBox();
      box.copy(g.boundingBox).applyMatrix4(p.mesh.matrixWorld).expandByScalar(0.01);
      if (box.containsPoint(prev) || (ray.ray.intersectBox(box, at) && at.distanceTo(prev) <= ray.far)) near.push(p.mesh);
    }
    if (!near.length) return false;
    const n = new THREE.Vector3();
    for (const h of ray.intersectObjects(near, false)) {
      if (!h.face || !this.section.keeps(h.point)) continue;
      n.copy(h.face.normal).transformDirection(h.object.matrixWorld);
      if (n.dot(dir) >= 0) continue; // a back face: leaving a part, not entering one
      cam.copy(prev).addScaledVector(dir, Math.max(0, Math.min(len, h.distance - 0.03)));
      return true;
    }
    return false;
  }

  startCinematic() {
    const sph = sphericalOf(this.camera.position, this.controls.target);
    this.cine = { t0: performance.now(), az0: sph.az, from: { pos: this.camera.position.clone(), target: this.controls.target.clone() } };
    this.fitCinematic(true);
  }

  /**
   * Night shift's orbit: around the middle of the station (not the hero target, which sits the station low under
   * the app's top chrome: Night shift has a tagline at the bottom, and a centred orbit needs the least distance).
   * The distance follows the azimuth, from a table where every entry keeps the whole station in view (the orbit's
   * elevation range, its breathing at the closest) at every azimuth within 20 degrees, smoothed only inside that
   * window: the camera dollies in gently at the front and back and out at the sides, and never clips the station.
   * Refitted on resize (the WebView moves to the full-screen slot, a rotation), easing over 0.6 s.
   */
  fitCinematic(initial = false) {
    const c = this.cine;
    const { w, h } = this.viewSize();
    const aspect = w / h;
    const pts = this.withEndLayout(() => this.fitPointsFor(PRESETS.hero.fit, 'hero'));
    const target = new THREE.Box3().setFromPoints(pts).getCenter(new THREE.Vector3());
    const tv = Math.tan((fovFor(aspect) * DEG) / 2), th = tv * aspect;
    const pad = 0.03;
    const kv = tv * (1 - 2 * pad), kh = th * (1 - 2 * pad);
    const r = new THREE.Vector3(), u = new THREE.Vector3(), up = new THREE.Vector3(0, 1, 0), q = new THREE.Vector3();
    const N = 360 / CINE_STEP, need = [];
    for (let i = 0; i < N; i++) {
      let n = 0;
      for (const el of CINE_EL) {
        const dir = dirFrom(i * CINE_STEP, el);
        r.crossVectors(up, dir).normalize();
        u.crossVectors(dir, r).normalize();
        for (const p of pts) {
          q.copy(p).sub(target);
          const along = q.dot(dir);
          n = Math.max(n, along + Math.abs(q.dot(r)) / kh, along + Math.abs(q.dot(u)) / kv);
        }
      }
      need.push(n);
    }
    // max over +-4 entries (20 deg), then two [1 2 1] passes (reach +-10 deg, inside the window, so still safe)
    const at = (arr, i) => arr[((i % N) + N) % N];
    let d = need.map((_, i) => { let m = 0; for (let k = -4; k <= 4; k++) m = Math.max(m, at(need, i + k)); return m; });
    for (let pass = 0; pass < 2; pass++) d = d.map((x, i) => (at(d, i - 1) + 2 * x + at(d, i + 1)) / 4);
    d = d.map((x) => (x * 1.02) / (1 - CINE_BREATH));
    if (!initial && c.dists) c.blend = { t: performance.now(), target: c.target.clone(), dists: c.dists };
    c.target = target;
    c.dists = d;
  }

  /** Orbit distance at azimuth `az` (degrees) from a fitCinematic table. */
  cineDist(dists, az) {
    const N = dists.length, x = ((((az % 360) + 360) % 360) / CINE_STEP), i = Math.floor(x);
    return lerp(dists[i % N], dists[(i + 1) % N], x - i);
  }

  updateCinematic(now) {
    const c = this.cine;
    const t = (now - c.t0) / 1000;
    const az = c.az0 + t * 5.5; // ~65 s per orbit
    let target = c.target, base = this.cineDist(c.dists, az);
    if (c.blend) {
      const k = ease.inOutSine(clamp((now - c.blend.t) / 600, 0, 1));
      target = c.blend.target.clone().lerp(c.target, k);
      base = lerp(this.cineDist(c.blend.dists, az), base, k);
      if (k >= 1) c.blend = null;
    }
    const el = CINE_EL[1] + (CINE_EL[2] - CINE_EL[1]) * Math.sin(t * 0.21);
    const dist = base * (1 + CINE_BREATH * Math.sin(t * 0.13 + 1));
    const pos = target.clone().addScaledVector(dirFrom(az, el), dist);
    const k = ease.inOutSine(clamp(t / 2.5, 0, 1)); // ease in from wherever the camera was
    this.camera.position.lerpVectors(c.from.pos, pos, k);
    this.controls.target.lerpVectors(c.from.target, target, k);
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
    this.setDockStep(step === 'reset' ? null : step, immediate);
  }

  setDockStep(step, immediate) {
    const from = this.dockStep;
    this.dockStep = step;
    this.layout(immediate, null, { from, to: step });
    this.requestRender();
  }

  stopDockPlay() {
    this.pendingPlay = false;
    if (this.dockPlay) {
      for (const t of this.dockPlay) clearTimeout(t);
      this.dockPlay = null;
    }
  }

  /**
   * align -> lower -> release -> lift -> reset, with dockStep events (the app highlights its cards from them).
   * 'done' is posted when the reset motion starts (the laptop going back into the cradle is not "lift" any more);
   * dockPlay stays set until that motion ends, so NA.idle() still waits for it. Called before the first frame (a
   * queued play), the sequence waits for it: its wall-clock steps and events start from the first visible frame.
   */
  playDock() {
    this.stopDockPlay();
    if (!this.readySent) {
      this.pendingPlay = true;
      return;
    }
    const timers = [];
    if (this.loaded && !this.state.cinematic && this.cameraName !== 'dock') this.setCamera('dock');
    for (const [step, at] of DOCK_PLAY) {
      timers.push(setTimeout(() => {
        this.setDockStep(step, false);
        post({ type: 'dockStep', step: step || 'done' });
      }, at));
    }
    timers.push(setTimeout(() => {
      this.dockPlay = null;
      this.requestRender();
    }, DOCK_PLAY_DONE));
    this.dockPlay = timers;
  }

  pick(x, y, pointerType = 'mouse') {
    post({ type: 'pick', group: this.pickGroup(x, y, pointerType === 'touch') });
  }

  /** Group under a client point (null = empty space): the first hit on a shown part that the section keeps. */
  rayGroup(x, y) {
    const r = this.canvas.getBoundingClientRect();
    const ndc = new THREE.Vector2(((x - r.left) / r.width) * 2 - 1, -((y - r.top) / r.height) * 2 + 1);
    const ray = this.pickRay || (this.pickRay = new THREE.Raycaster());
    ray.setFromCamera(ndc, this.camera);
    const targets = this.model.meshes.filter((m) => isShown(m));
    // hits on the cut-away side of a section don't count
    const hit = ray.intersectObjects(targets, false).find((h) => this.section.keeps(h.point));
    return hit ? hit.object.userData.group : null;
  }

  /**
   * Touch picking with target expansion. A fingertip lands several dp off, and in the phone's hero view the mouse is
   * about 25 x 18 dp: a single exact ray often opens the desk mat instead. When the exact ray finds nothing, or a
   * group that is big on screen (the mat, the base), a small group (under TOUCH_TARGET dp on either axis) whose
   * screen box, padded to TOUCH_TARGET x TOUCH_TARGET, contains the tap wins, nearest box first, provided a ray
   * toward it really reaches it (not hidden behind something). Taps on a big group well clear of a small one keep
   * the big one. Mouse and pen keep the exact ray.
   */
  pickGroup(x, y, touch) {
    const exact = this.rayGroup(x, y);
    if (!touch) return exact;
    const boxes = this.groupScreenBoxes();
    const small = (b) => b.x1 - b.x0 < TOUCH_TARGET || b.y1 - b.y0 < TOUCH_TARGET;
    if (exact && boxes.has(exact) && small(boxes.get(exact))) return exact;
    const cands = [];
    for (const [id, b] of boxes) {
      if (id === exact || !small(b)) continue;
      const px = Math.max(0, (TOUCH_TARGET - (b.x1 - b.x0)) / 2), py = Math.max(0, (TOUCH_TARGET - (b.y1 - b.y0)) / 2);
      if (x < b.x0 - px || x > b.x1 + px || y < b.y0 - py || y > b.y1 + py) continue;
      const qx = clamp(x, b.x0, b.x1), qy = clamp(y, b.y0, b.y1);
      cands.push({ id, d: Math.hypot(x - qx, y - qy), b, qx, qy });
    }
    cands.sort((a, b) => a.d - b.d);
    for (const { id, b, qx, qy } of cands) {
      const cx = (b.x0 + b.x1) / 2, cy = (b.y0 + b.y1) / 2;
      // the box centre (the body of a compact device), else the tap pulled halfway into the box
      if (this.rayGroup(cx, cy) === id || this.rayGroup((qx + cx) / 2, (qy + cy) / 2) === id) return id;
    }
    return exact;
  }

  /** Client-space rectangles of every shown group's box (what the section keeps of it), in front of the camera. */
  groupScreenBoxes() {
    const out = new Map();
    const rect = this.canvas.getBoundingClientRect();
    const S = this.section;
    const keep = new THREE.Box3(new THREE.Vector3(-Infinity, -Infinity, -Infinity), new THREE.Vector3(Infinity, Infinity, Infinity));
    if (S.active) {
      if (S.axis === 'x') keep.min.x = S.c;
      else keep.max.z = S.c;
    }
    const p = new THREE.Vector3();
    for (const id of this.model.groups.keys()) {
      const box = this.model.bounds([id], { includeInternal: id === 'internals' || this.state.style === 'xray' });
      if (box.isEmpty() || box.intersect(keep).isEmpty()) continue;
      let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity, behind = false;
      for (let i = 0; i < 8 && !behind; i++) {
        p.set(i & 1 ? box.max.x : box.min.x, i & 2 ? box.max.y : box.min.y, i & 4 ? box.max.z : box.min.z).project(this.camera);
        if (p.z > 1) behind = true;
        const sx = rect.left + ((p.x + 1) / 2) * rect.width, sy = rect.top + ((1 - p.y) / 2) * rect.height;
        x0 = Math.min(x0, sx); x1 = Math.max(x1, sx); y0 = Math.min(y0, sy); y1 = Math.max(y1, sy);
      }
      if (!behind) out.set(id, { x0, y0, x1, y1 });
    }
    return out;
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
    if (this.forcePixelRatio) pr = this.forcePixelRatio; // stills tool: supersampling
    if (!force && this.size && this.size.w === w && this.size.h === h && this.size.pr === pr) return;
    const reshaped = !!this.size && (this.size.w !== w || this.size.h !== h); // CSS size changed (not just the pixel ratio)
    const resampled = !this.size || reshaped || this.size.pr !== pr; // the canvas is re-allocated (and cleared)
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
    if (this.styles) this.styles.setResolution();
    if (this.section) this.section.setResolution(w, h);
    if (this.dims) this.dims.setResolution(w, h);
    if (this.styleFade && reshaped && (this.styleFade.alpha > 0 || this.tweens.has('stylefade') || this.hold)) {
      // the old-style snapshot has the old shape: drop it (a running cross-fade would draw it squeezed) and stop
      // holding the frame, so the resized canvas, which setSize cleared, renders at once
      this.releaseHold(this.hold, false);
      this.tweens.cancel('stylefade');
      this.styleFade.release();
    } else if (this.hold && resampled) {
      // same shape, new pixel ratio (a quality switch): the snapshot stands in for the cleared canvas; a hold
      // without one can't keep anything up
      if (this.hold.snapshot && this.styleFade.tex) this.hold.redraw = true;
      else this.releaseHold(this.hold, false);
    }
    if (this.loaded && this.state.cinematic && this.cine) this.fitCinematic();
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

  /** The pockets charge (and their indicators breathe) only in stow, once the devices have landed. */
  charging(now = performance.now()) {
    return this.state.mode === 'stow' && now >= this.chargeAt;
  }

  breathing() {
    return !this.capture && this.q && this.q.breathe && this.charging() && this.state.amber > 0.001 && !this.hidden;
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
      const prev = (this.camPrev || (this.camPrev = new THREE.Vector3())).copy(this.camera.position);
      moving = this.controls.update(dt);
      this.clampTarget();
      if (moving) this.avoidStation(prev);
    }
    const breathing = this.breathing();
    this.updateLeds(now, breathing);
    const glowing = this.updateDockGlow(this.capture ? 10 : dt);
    const continuous = tweening || moving || glowing || this.controls.autoRotate || !!this.state.cinematic;
    if (this.hold) {
      // the old frame stays up while the new programs compile (no scene renders: they would compile them in place)
      if (this.hold.redraw) {
        this.hold.redraw = false;
        this.styleFade.draw();
      }
      this.dirty = true;
      this.schedule(50);
      return;
    }
    // frames drawn only because the charge LEDs breathe keep the last desk reflection: the camera and the layout
    // are still, and the pocket LEDs can't be seen in the mirror
    if (this.dirty || continuous) this.render();
    else if (breathing) this.render({ reflect: false });
    if (continuous) this.schedule(0);
    else if (breathing) this.schedule(66); // ~15 fps is plenty for a 3.2 s breath, and halves the idle GPU load in stow
    else if (this.state.mode === 'stow' && this.chargeAt > now && this.chargeAt < Infinity) this.schedule(Math.min(1000, this.chargeAt - now + 20));
  }

  updateLeds(now, breathing) {
    if (!this.chargeMat) return;
    const base = this.materials.get('amber_led');
    let k;
    if (this.charging(now)) k = breathing ? 0.35 + 0.65 * (0.5 - 0.5 * Math.cos((now / 1000) * ((2 * Math.PI) / 3.2))) : 0.8;
    else k = 0.22; // devices out of their pockets (or still travelling): indicators idle
    this.chargeMat.emissiveIntensity = base.emissiveIntensity * k;
  }

  render({ reflect = true } = {}) {
    this.dirty = false;
    this.renderer.info.reset(); // info.render = totals for this frame (shadow, reflection, passes), not just the last pass
    this.stage.prerender(this.scene, this.camera, this.model.root, this.contactExclude(), { reflect });
    this.output.render();
    this.styleFade.draw();
    this.dims.project(this.camera, this.size.w, this.size.h);
    if (!this.readySent) {
      this.timings.firstFrame = Math.round(performance.now() - (this.t0 || 0));
      this.readySent = true;
      this.el.classList.add('ready');
      post({ type: 'ready' });
      if (this.pendingPlay) this.playDock(); // a dock('play') queued before load starts with the first visible frame
    } else if (this.firstFrameAfterRestore) {
      this.firstFrameAfterRestore = false;
      if (this.lostReported) {
        this.lostReported = false;
        post({ type: 'ready' });
      }
    }
  }

  contactExclude() {
    const mat = this.model.groups.get('deskmat');
    return mat ? [mat.node] : [];
  }
}

/**
 * Lift -> arc -> lower: the device rises straight out of its pocket to `apexY`, travels on a shallow arc with a
 * slight tilt, and settles down onto its target. t is linear 0..1 (the shaping is done here).
 */
function arcPath(p0, p1, apexY, q0, q1) {
  const tilt = new THREE.Quaternion();
  const axis = new THREE.Vector3(p1.z - p0.z, 0, -(p1.x - p0.x)).normalize(); // pitch toward the travel direction
  const lift0 = apexY - p0.y, lift1 = apexY - p1.y;
  return (t, pos, quat) => {
    const h = smootherstep(0.2, 0.84, t); // horizontal progress
    const up = smootherstep(0, 0.3, t), down = smootherstep(0.72, 1, t);
    pos.lerpVectors(p0, p1, h);
    pos.y = p0.y + lift0 * up - lift1 * down + 0.018 * Math.sin(Math.PI * h);
    if (quat) {
      quat.slerpQuaternions(q0, q1, h);
      tilt.setFromAxisAngle(axis, 3.5 * DEG * Math.sin(Math.PI * h) * (1 - down));
      quat.premultiply(tilt);
    }
  };
}

/**
 * Through scene.json waypoints leg by leg (lift, slide, set down): each leg eases in and out over its share of the
 * time, so the device passes exactly through every waypoint. t is linear 0..1.
 */
function waypointPath(points, durs, q0, q1) {
  const total = durs.reduce((a, b) => a + b, 0) || 1;
  const ends = [];
  let acc = 0;
  for (const d of durs) ends.push((acc += d) / total);
  return (t, pos, quat) => {
    let i = 0;
    while (i < ends.length - 1 && t > ends[i]) i++;
    const t0 = i ? ends[i - 1] : 0;
    const k = ease.inOutSine(clamp((t - t0) / Math.max(1e-6, ends[i] - t0), 0, 1));
    pos.lerpVectors(points[i], points[Math.min(i + 1, points.length - 1)], k);
    if (quat) quat.slerpQuaternions(q0, q1, t);
  };
}

/** Lowering onto the sprung connector: ease down, press 1.5 mm past the seat, spring back. */
function seatPath(p0, p1) {
  return (t, pos) => {
    const e = ease.inOutCubic(Math.min(1, t / 0.86));
    pos.lerpVectors(p0, p1, e);
    pos.y -= 0.0015 * smoothstep(0.78, 0.9, t) * (1 - smoothstep(0.9, 1, t));
  };
}

function syncAmber(dst, src) {
  dst.emissiveIntensity = src.emissiveIntensity;
  dst.color.copy(src.color);
}

function isShown(o) {
  for (let x = o; x; x = x.parent) if (!x.visible) return false;
  return true;
}

