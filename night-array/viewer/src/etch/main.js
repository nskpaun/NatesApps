// Deck etch concept: the studio's station with a design etched into the deck liner and lit by the screen.
// Bundled on its own (build-etch.mjs -> web/dist/deck-etch.js) for web/deck-etch.html; installs window.Etch.
//
// The etch is drawn with the real mirror geometry, in world space (metres, Y up, desk top at y = 0):
//   mirror facets  every point of the design is a tiny mirror tilted so that it bounces one spot of the screen to
//                  the seat. The fragment shader reflects the actual view ray off that facet and looks up what it hits.
//   matte          a white etch that just scatters the light the screen spills on it.
// Brightness is physical relative to the screen: the same radiance units as the screen's own emissive.
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { RectAreaLightUniformsLib } from 'three/examples/jsm/lights/RectAreaLightUniformsLib.js';
import { Model } from '../model.js';
import { MaterialLib } from '../materials.js';
import { Stage, BG } from '../stage.js';
import { Output, QUALITY } from '../post.js';
import { paintScreen } from '../screen.js';
import { clamp, lerp, DEG } from '../util.js';

const MODEL_BASE = 'model/';
const SCREEN_GAIN = 1.8; // emissive gain of the desktop texture, as in the Studio
// Where the etch is aimed: a seated person's eyes, 0.68 m from the glass and 0.46 m above the desk.
const SEAT_EYE = new THREE.Vector3(0, 0.46, 0.62);
const LOOK_AT = new THREE.Vector3(0, 0.15, -0.04);
// Screen geometry (SPEC.md): two facets toed in 10 degrees about the seam axis.
const SEAM = new THREE.Vector3(0, 0, -0.062);
const TOE = 10 * DEG;
const PANEL = { s0: 0.007, w: 0.5967, y0: 0.172, h: 0.3357 };

const VIEWS = {
  seat: { pos: SEAT_EYE.toArray(), target: LOOK_AT.toArray(), fov: 54, wide: true },
  // the same eye point, looking down at the left field of the deck
  deck: { pos: SEAT_EYE.toArray(), target: [-0.3, 0.03, 0.05], fov: 31 },
  lean: { pos: [0.26, 0.5, 0.6], target: LOOK_AT.toArray(), fov: 54, wide: true },
  standing: { pos: [0.06, 1.02, 0.98], target: [0, 0.1, 0.0], fov: 40 },
  visitor: { pos: [1.32, 0.6, 1.0], target: [0.06, 0.13, 0.0], fov: 38 },
  overview: { pos: [-0.98, 0.66, 2.15], target: [0.06, 0.17, 0.0], fov: 30 },
};
const DESIGNS = ['array', 'rings', 'field'];
const CONTENTS = ['desktop', 'colour', 'page'];

const listeners = new Set();
const state = { etch: 'facets', film: false, view: 'seat', content: 'colour', design: 'array', room: 0.25 };

// ---------------------------------------------------------------------------------------------- screen content
function paintColour(g, W, H, t) {
  g.globalCompositeOperation = 'source-over';
  g.fillStyle = '#06070c';
  g.fillRect(0, 0, W, H);
  g.globalCompositeOperation = 'lighter';
  const blobs = [
    ['255,60,140', 0.13, 0.0, 0.11, 1.3], ['40,210,255', 0.09, 2.1, 0.14, 0.4], ['255,170,40', 0.11, 4.2, 0.08, 2.6],
    ['90,255,150', 0.07, 1.2, 0.12, 3.9], ['110,90,255', 0.1, 5.3, 0.09, 5.1], ['255,90,50', 0.06, 3.3, 0.13, 0.9],
  ];
  for (const [rgb, fx, px, fy, py] of blobs) {
    const x = W * (0.5 + 0.46 * Math.sin(t * fx + px)), y = H * (0.5 + 0.42 * Math.cos(t * fy + py));
    const r = H * 0.85;
    const grad = g.createRadialGradient(x, y, 0, x, y, r);
    grad.addColorStop(0, `rgba(${rgb},0.95)`);
    grad.addColorStop(0.45, `rgba(${rgb},0.4)`);
    grad.addColorStop(1, `rgba(${rgb},0)`);
    g.fillStyle = grad;
    g.fillRect(x - r, y - r, r * 2, r * 2);
  }
  g.globalCompositeOperation = 'source-over';
}

function paintPage(g, W, H) {
  const half = W / 2;
  g.fillStyle = '#b6b3ae'; // a white page, held under the bloom threshold
  g.fillRect(0, 0, W, H);
  const line = (x, y, w, h, c) => { g.fillStyle = c; g.fillRect(x, y, w, h); };
  for (const x0 of [0, half]) {
    const m = half * 0.08, w = half - m * 2;
    line(x0 + m, H * 0.1, w * 0.46, H * 0.05, '#26282c');
    for (let i = 0; i < 7; i++) line(x0 + m, H * (0.22 + i * 0.045), w * (0.92 - (i % 3) * 0.11), H * 0.014, '#8d8f94');
    // a chart: the colours are what the etch picks up
    const cols = x0 === 0 ? ['#2f6fed', '#18a36b', '#e5484d', '#f2a04a', '#7c5cff'] : ['#e5484d', '#f2a04a', '#18a36b', '#2f6fed', '#00a3b4'];
    const bw = w / (cols.length * 1.6);
    cols.forEach((c, i) => {
      const bh = H * (0.14 + 0.2 * Math.abs(Math.sin(i * 1.7 + (x0 ? 1 : 0))));
      line(x0 + m + i * bw * 1.6, H * 0.94 - bh, bw, bh, c);
    });
  }
}

class Screens {
  constructor() {
    this.cache = new Map();
    this.avg = document.createElement('canvas');
    this.avg.width = 2;
    this.avg.height = 1;
    this.avgCtx = this.avg.getContext('2d', { willReadFrequently: true });
  }

  entry(name) {
    let e = this.cache.get(name);
    if (!e) {
      const canvas = document.createElement('canvas');
      const live = name === 'colour';
      canvas.width = live ? 1024 : 2048;
      canvas.height = live ? 288 : 576;
      const g = canvas.getContext('2d');
      if (name === 'desktop') paintScreen(canvas, 'work');
      else if (name === 'page') paintPage(g, canvas.width, canvas.height);
      else paintColour(g, canvas.width, canvas.height, 0);
      const texture = new THREE.CanvasTexture(canvas);
      texture.colorSpace = THREE.SRGBColorSpace;
      texture.flipY = false; // glTF UVs: v = 0 at the top
      texture.anisotropy = 8;
      texture.generateMipmaps = true;
      texture.minFilter = THREE.LinearMipmapLinearFilter;
      e = { canvas, texture, g, live, colors: null };
      this.measure(e);
      this.cache.set(name, e);
    }
    return e;
  }

  /** Mean linear colour of each panel, for the light the screen throws on the station. */
  measure(e) {
    this.avgCtx.clearRect(0, 0, 2, 1);
    this.avgCtx.drawImage(e.canvas, 0, 0, 2, 1);
    const d = this.avgCtx.getImageData(0, 0, 2, 1).data;
    e.colors = [0, 1].map((i) => new THREE.Color().setRGB(d[i * 4] / 255, d[i * 4 + 1] / 255, d[i * 4 + 2] / 255, THREE.SRGBColorSpace));
  }

  animate(e, t) {
    paintColour(e.g, e.canvas.width, e.canvas.height, t);
    e.texture.needsUpdate = true;
    this.measure(e);
  }
}

// ---------------------------------------------------------------------------------------------- etch material
const ETCH_PARS = /* glsl */ `
uniform sampler2D uScreen;
uniform float uGain, uFacets, uFilm, uSpread, uDesign, uRise;
uniform vec3 uEye;
varying vec3 vEtchWorld;

const vec3 E_SEAM = vec3(${SEAM.x.toFixed(4)}, 0.0, ${SEAM.z.toFixed(4)});
const float E_C = ${Math.cos(TOE).toFixed(7)}, E_S = ${Math.sin(TOE).toFixed(7)};
const float E_S0 = ${PANEL.s0.toFixed(4)}, E_W = ${PANEL.w.toFixed(4)}, E_Y0 = ${PANEL.y0.toFixed(4)}, E_H = ${PANEL.h.toFixed(4)};
const vec2 E_TAPS[8] = vec2[8](vec2(0.0, 0.0), vec2(0.62, 0.11), vec2(-0.31, 0.56), vec2(-0.48, -0.42),
  vec2(0.25, -0.67), vec2(0.93, -0.3), vec2(-0.9, 0.28), vec2(0.12, 0.97));

// panel on the +x (side = 1) or -x (side = -1) half: unit vector along the facet from the seam, and its normal
void etchPanel(float side, out vec3 a, out vec3 n) {
  a = vec3(side * E_C, 0.0, E_S);
  n = vec3(-side * E_S, 0.0, E_C);
}

// radiance leaving a panel at (s along the facet, height y) toward a receiver at cosine cs off the panel normal.
// A bare IPS panel dims off axis (about cos^2); the angle-sorting film fills the steep directions at full brightness.
vec3 etchScreen(float side, float s, float y, float cs, float lod) {
  float t = (s - E_S0) / E_W;
  vec2 uv = vec2(0.5 + side * 0.5 * t, (E_Y0 + E_H - y) / E_H);
  return textureLod(uScreen, uv, lod).rgb * uGain * mix(cs * cs, 1.0, uFilm);
}

// light arriving at P from direction r: the screen where the ray hits an active area, nothing otherwise
vec3 etchTrace(vec3 P, vec3 r, float lod) {
  vec3 acc = vec3(0.0);
  for (int i = 0; i < 2; i++) {
    float side = i == 0 ? 1.0 : -1.0;
    vec3 a, n;
    etchPanel(side, a, n);
    float dn = dot(r, n);
    if (dn < -1e-4) {
      float tt = dot(E_SEAM - P, n) / dn;
      if (tt > 0.0) {
        vec3 hit = P + r * tt;
        float s = dot(hit - E_SEAM, a);
        float e = 0.003;
        float w = smoothstep(E_S0, E_S0 + e, s) * smoothstep(E_S0 + E_W, E_S0 + E_W - e, s)
          * smoothstep(E_Y0, E_Y0 + e, hit.y) * smoothstep(E_Y0 + E_H, E_Y0 + E_H - e, hit.y);
        if (w > 0.0) acc += w * etchScreen(side, s, hit.y, -dn, lod);
      }
    }
  }
  return acc;
}

// distance of a deck point in front of the panel above it (negative behind the glass line)
float etchFront(vec3 P) {
  float side = P.x >= 0.0 ? 1.0 : -1.0;
  vec3 a, n;
  etchPanel(side, a, n);
  return dot(P - E_SEAM, n);
}

// the screen spot a facet at P is aimed at: straight above it on the panel, as high as P is far in front of the
// glass, so the design shows the lower part of the screen folded down flat onto the deck
vec3 etchAim(vec3 P) {
  float side = P.x >= 0.0 ? 1.0 : -1.0;
  vec3 a, n;
  etchPanel(side, a, n);
  float s = clamp(dot(P - E_SEAM, a), E_S0 + 0.004, E_S0 + E_W - 0.004);
  float d = max(dot(P - E_SEAM, n), 0.0);
  float y = min(E_Y0 + 0.006 + d * uRise, E_Y0 + E_H - 0.006);
  return E_SEAM + a * s + vec3(0.0, y, 0.0);
}

// a mirror facet's normal: halfway between the direction to its screen spot and the direction to the seat
vec3 etchFacetNormal(vec3 P) {
  return normalize(normalize(etchAim(P) - P) + normalize(uEye - P));
}

// what the facet shows the camera: the view ray mirrored off it, averaged over the facets' small angular spread
vec3 etchFacets(vec3 P, vec3 nf, vec3 v) {
  vec3 t1 = normalize(cross(nf, vec3(1.0, 0.0, 0.0)));
  vec3 t2 = cross(nf, t1);
  vec3 acc = vec3(0.0);
  for (int i = 0; i < 8; i++) {
    vec2 o = E_TAPS[i] * uSpread;
    vec3 nk = normalize(nf + t1 * o.x + t2 * o.y);
    acc += etchTrace(P, reflect(-v, nk), 2.5);
  }
  return acc * (0.78 / 8.0); // facet reflectance times the share of the sawtooth that faces the right way
}

// what a matte white etch scatters: the irradiance from both panels, summed over a coarse grid of screen patches
vec3 etchMatte(vec3 P) {
  vec3 E = vec3(0.0);
  for (int i = 0; i < 2; i++) {
    float side = i == 0 ? 1.0 : -1.0;
    vec3 a, n;
    etchPanel(side, a, n);
    for (int j = 0; j < 6; j++) {
      for (int k = 0; k < 3; k++) {
        float s = E_S0 + E_W * (float(j) + 0.5) / 6.0;
        float y = E_Y0 + E_H * (float(k) + 0.5) / 3.0;
        vec3 w = E_SEAM + a * s + vec3(0.0, y, 0.0) - P;
        float r2 = dot(w, w);
        vec3 dir = w * inversesqrt(r2);
        float cs = dot(-dir, n), cd = dir.y;
        if (cs > 0.0 && cd > 0.0) E += etchScreen(side, s, y, cs, 7.0) * cs * cd / r2;
      }
    }
  }
  return E * (E_W / 6.0) * (E_H / 3.0) * (0.8 / 3.14159265);
}

// nearest dot centre of a hex-packed array (rows shifted by half a pitch)
vec2 etchHex(vec2 p, float pitch) {
  float rowH = pitch * 0.8660254;
  float row = floor(p.y / rowH + 0.5);
  float off = mod(row, 2.0) * 0.5 * pitch;
  float col = floor((p.x - off) / pitch + 0.5);
  return vec2(col * pitch + off, row * rowH);
}

// 0..1 coverage of the etched design at deck position p (x, z in metres)
float etchDesign(vec2 p) {
  vec2 hub = vec2(0.0, -0.075); // the foot of the neck: the rings spread out from it
  if (uDesign < 0.5) {
    float pitch = 0.0056;
    vec2 c = etchHex(p, pitch);
    float ring = 0.5 + 0.5 * cos(6.2831853 * (length(c - hub) - 0.018) / 0.078);
    float rad = pitch * (0.15 + 0.27 * ring);
    float d = length(p - c);
    float aa = max(fwidth(d), 1e-5);
    return 1.0 - smoothstep(rad - aa, rad + aa, d);
  }
  if (uDesign < 1.5) {
    float d = length(p - hub);
    float band = abs(fract(d / 0.013) - 0.5);
    float aa = max(fwidth(d / 0.013), 1e-5);
    return 1.0 - smoothstep(0.27 - aa, 0.27 + aa, band);
  }
  return 1.0;
}
`;

function makeEtchMaterial(envMap) {
  const uniforms = {
    uScreen: { value: null },
    uGain: { value: SCREEN_GAIN },
    uFacets: { value: 1 },
    uFilm: { value: 0 },
    uSpread: { value: 0.03 },
    uDesign: { value: 0 },
    uRise: { value: 1.0 },
    uEye: { value: SEAT_EYE.clone() },
  };
  const m = new THREE.MeshStandardMaterial({
    color: '#d6d1c8', metalness: 1, roughness: 0.2, envMap, envMapIntensity: 0.35,
    transparent: true, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2,
  });
  m.name = 'deck-etch';
  m.onBeforeCompile = (shader) => {
    Object.assign(shader.uniforms, uniforms);
    shader.vertexShader = 'varying vec3 vEtchWorld;\n' + shader.vertexShader
      .replace('#include <begin_vertex>', '#include <begin_vertex>\n\tvEtchWorld = (modelMatrix * vec4(transformed, 1.0)).xyz;');
    shader.fragmentShader = ETCH_PARS + shader.fragmentShader
      .replace('#include <color_fragment>', `#include <color_fragment>
	// only the liner's top face is etched, and only in front of the glass, where it can see the screen
	vec3 etchFace = normalize(cross(dFdx(vEtchWorld), dFdy(vEtchWorld)));
	float etchCover = etchDesign(vEtchWorld.xz) * step(0.9, abs(etchFace.y)) * step(0.0296, vEtchWorld.y)
		* smoothstep(0.004, 0.026, etchFront(vEtchWorld));
	diffuseColor.a *= etchCover;
	if (diffuseColor.a < 0.003) discard;`)
      .replace('#include <normal_fragment_maps>', `#include <normal_fragment_maps>
	vec3 etchNf = etchFacetNormal(vEtchWorld);
	if (uFacets > 0.5) normal = normalize((viewMatrix * vec4(etchNf, 0.0)).xyz);`)
      .replace('#include <lights_fragment_begin>', THREE.ShaderChunk.lights_fragment_begin.replace(/NUM_RECT_AREA_LIGHTS/g, '0'))
      .replace('#include <emissivemap_fragment>', `#include <emissivemap_fragment>
	totalEmissiveRadiance += uFacets > 0.5
		? etchFacets(vEtchWorld, etchNf, normalize(cameraPosition - vEtchWorld))
		: etchMatte(vEtchWorld);`);
  };
  m.customProgramCacheKey = () => 'deck-etch';
  m.userData.uniforms = uniforms;
  return m;
}

/** The angle-sorting film keeps the cone toward the seat and sends the rest away: from anywhere else the screen is dim. */
function addPrivacy(screenMat, uFilm) {
  const u = { uFilm, uEyeView: { value: new THREE.Vector3() } };
  screenMat.onBeforeCompile = (shader) => {
    Object.assign(shader.uniforms, u);
    shader.fragmentShader = 'uniform float uFilm;\nuniform vec3 uEyeView;\n' + shader.fragmentShader.replace(
      '#include <emissivemap_fragment>',
      `#include <emissivemap_fragment>
	float sortCos = dot(normalize(vViewPosition), normalize(uEyeView + vViewPosition));
	totalEmissiveRadiance *= mix(1.0, mix(0.045, 1.0, smoothstep(0.78, 0.93, sortCos)), uFilm);`);
  };
  screenMat.customProgramCacheKey = () => 'screen-sorting-film';
  return u;
}

// ---------------------------------------------------------------------------------------------- the scene
class EtchScene {
  constructor(el) {
    this.el = el;
    this.dirty = true;
    this.tween = null;
    this.listeners = listeners;
  }

  async init() {
    const canvas = document.createElement('canvas');
    canvas.setAttribute('aria-label', 'Night Array deck etch, live 3D view');
    this.el.insertBefore(canvas, this.el.firstChild);
    this.canvas = canvas;
    const gl = canvas.getContext('webgl2', { antialias: true, alpha: false, powerPreference: 'high-performance', stencil: true });
    if (!gl) throw Object.assign(new Error("WebGL2 isn't available"), { friendly: 'webgl2' });
    const renderer = new THREE.WebGLRenderer({ canvas, context: gl, antialias: true });
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.autoUpdate = false;
    renderer.setClearColor(BG, 1);
    this.renderer = renderer;
    if (!(renderer.extensions.has('EXT_color_buffer_float') || renderer.extensions.has('EXT_color_buffer_half_float'))) {
      throw Object.assign(new Error('this GPU cannot render to half-float targets'), { friendly: 'hdr' });
    }
    const files = Promise.all([
      fetch(MODEL_BASE + 'scene.json').then((r) => { if (!r.ok) throw new Error(`scene.json: HTTP ${r.status}`); return r.json(); }),
      new GLTFLoader().loadAsync(MODEL_BASE + 'station.glb'),
    ]);
    files.catch(() => {});

    this.scene = new THREE.Scene();
    this.scene.background = BG.clone();
    this.scene.fog = new THREE.Fog(BG.clone().multiplyScalar(0.8), 4.5, 11);
    this.camera = new THREE.PerspectiveCamera(58, 1, 0.02, 40);
    const small = Math.min(window.screen.width, window.screen.height) * (window.devicePixelRatio || 1) < 900;
    this.q = { ...(small ? QUALITY.balanced : QUALITY.high) };
    renderer.shadowMap.type = this.q.shadowType;
    this.stage = new Stage(renderer, { lowMem: small });
    this.scene.add(this.stage.group);
    this.scene.environment = this.stage.buildEnvironment();
    this.stage.desk.material.envMap = this.scene.environment;
    this.output = new Output(renderer, this.scene, this.camera);

    const c = new OrbitControls(this.camera, canvas);
    c.enableDamping = true;
    c.dampingFactor = 0.085;
    c.rotateSpeed = 0.7;
    c.minDistance = 0.25;
    c.maxDistance = 5;
    c.minPolarAngle = 4 * DEG;
    c.maxPolarAngle = 86 * DEG; // never below the desk
    c.touches = { ONE: THREE.TOUCH.ROTATE, TWO: THREE.TOUCH.DOLLY_PAN };
    c.addEventListener('start', () => { this.tween = null; });
    c.addEventListener('change', () => { this.dirty = true; });
    this.controls = c;

    const [sceneJson, gltf] = await files;
    this.materials = new MaterialLib(sceneJson);
    this.materials.setEnvMap(this.scene.environment);
    this.model = new Model(sceneJson, gltf, null, this.materials);
    this.scene.add(this.model.root);
    this.pose('work');

    // the screen: content texture as emissive, plus the film's privacy falloff
    this.screens = new Screens();
    this.screenMat = this.materials.variant('screen', 'screen-live');
    this.screenMat.emissive = new THREE.Color(1, 1, 1);
    this.screenMat.emissiveIntensity = SCREEN_GAIN;
    const screenPart = this.model.parts.get('display_screen');
    if (screenPart) screenPart.mesh.material = this.screenMat;

    // the etch: the liner's own geometry again, drawn just above it
    this.etchMat = makeEtchMaterial(this.scene.environment);
    this.etch = this.etchMat.userData.uniforms;
    this.privacy = addPrivacy(this.screenMat, this.etch.uFilm);
    const liner = this.model.parts.get('deck_liner');
    if (liner) {
      const mesh = new THREE.Mesh(liner.mesh.geometry, this.etchMat);
      mesh.name = 'deck_etch';
      mesh.receiveShadow = true;
      mesh.renderOrder = 1;
      liner.node.add(mesh);
    }

    // the light the screens throw on the station (one soft panel light each, in the content's mean colour)
    RectAreaLightUniformsLib.init();
    this.panelLights = [1, -1].map((side) => {
      const a = new THREE.Vector3(side * Math.cos(TOE), 0, Math.sin(TOE));
      const n = new THREE.Vector3(-side * Math.sin(TOE), 0, Math.cos(TOE));
      const l = new THREE.RectAreaLight('#ffffff', 1, PANEL.w, PANEL.h);
      l.position.copy(SEAM).addScaledVector(a, PANEL.s0 + PANEL.w / 2).add(new THREE.Vector3(0, PANEL.y0 + PANEL.h / 2, 0)).addScaledVector(n, 0.002);
      l.lookAt(l.position.clone().add(n));
      this.scene.add(l);
      return l;
    });

    this.setupPracticals();
    this.materials.setAmber(0.8);
    this.stage.setAmber(0.8);

    // where the etch is aimed, shown when you look from somewhere else
    this.eyeMark = new THREE.Mesh(new THREE.SphereGeometry(0.008, 20, 12), new THREE.MeshBasicMaterial({ color: '#F2A04A', fog: false }));
    this.eyeMark.position.copy(SEAT_EYE);
    this.scene.add(this.eyeMark);

    new ResizeObserver(() => this.resize()).observe(this.el);
    this.resize();
    this.apply(state, true);
    this.renderer.shadowMap.needsUpdate = true;
    this.stage.contact.dirty = true;
    if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) Etch._freeze(12, 0, this);
    this.loop = this.loop.bind(this);
    requestAnimationFrame(this.loop);
  }

  pose(mode) {
    for (const [id, d] of this.model.targets(mode)) {
      const g = this.model.movables.get(id);
      g.node.position.copy(g.pivot).add(d.t);
      g.node.visible = !d.hidden;
    }
    this.model.root.updateMatrixWorld(true);
  }

  /** The amber pools of the Studio (base under-glow, neck light, the mouse's tail light). */
  setupPracticals() {
    const S = this.stage, parts = this.model.parts;
    const center = (id) => {
      const p = parts.get(id);
      if (!p) return null;
      const g = p.mesh.geometry;
      if (!g.boundingBox) g.computeBoundingBox();
      return g.boundingBox.getCenter(new THREE.Vector3()).applyMatrix4(p.mesh.matrixWorld);
    };
    const host = (id) => (this.model.movables.get(parts.get(id).group) || {}).node || null;
    const glow = center('base_glow');
    if (glow) {
      const w = parts.get('base_glow').mesh.geometry.boundingBox.getSize(new THREE.Vector3()).x, parent = host('base_glow');
      S.addPractical({ pos: [glow.x, 0.0006, glow.z + 0.075], size: [w * 1.25, 0.2], poolK: 0.5, parent, world: true });
      for (const f of [-0.33, 0, 0.33]) S.addPractical({ pos: [glow.x + w * f, 0.006, glow.z + 0.02], light: 0.006, distance: 0.28, parent, world: true });
    }
    const mg = this.model.groups.get('mouse');
    if (mg && parts.get('mouse_glow')) {
      const cm = center('mouse_glow').sub(mg.node.position);
      S.addPractical({ pos: [cm.x, 0.0007, cm.z + 0.03], size: [0.09, 0.07], poolK: 0.45, parent: mg.node });
    }
  }

  resize() {
    const w = Math.max(1, this.el.clientWidth), h = Math.max(1, this.el.clientHeight);
    let pr = Math.min(window.devicePixelRatio || 1, this.q.pixelRatio);
    if (w * h * pr * pr > 2.2e6) pr = Math.max(0.75, Math.sqrt(2.2e6 / (w * h)));
    if (this.forcePixelRatio) pr = this.forcePixelRatio;
    this.size = { w, h, pr };
    this.renderer.setPixelRatio(pr);
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    this.setFov(this.fov || VIEWS.seat);
    this.output.configure(this.q, w, h, pr);
    this.stage.setQuality(this.q, w * pr, h * pr);
    this.dirty = true;
  }

  /** The seat views keep most of the station's width in frame, so narrow viewports get a taller field. */
  setFov(view) {
    this.fov = view;
    let f = view.fov;
    if (view.wide) f = clamp(2 * Math.atan(Math.tan(41 * DEG) / Math.max(0.3, this.camera.aspect)) / DEG, view.fov, 84);
    this.camera.fov = f;
    this.camera.updateProjectionMatrix();
  }

  apply(s, immediate = false, view = false) {
    const u = this.etch, facets = s.etch === 'facets';
    u.uFacets.value = facets ? 1 : 0;
    u.uFilm.value = s.film ? 1 : 0;
    u.uDesign.value = Math.max(0, DESIGNS.indexOf(s.design));
    // matte: a white, diffuse etch; facets: bright bare metal
    this.etchMat.color.set(facets ? '#d6d1c8' : '#cfcac2');
    this.etchMat.metalness = facets ? 1 : 0;
    this.etchMat.roughness = facets ? 0.2 : 0.9;
    this.etchMat.envMapIntensity = facets ? 0.35 : 0.5;

    const e = this.screens.entry(s.content);
    this.content = e;
    this.screenMat.emissiveMap = e.texture;
    u.uScreen.value = e.texture;
    this.panelColours();

    // room light: 0 = only the station's own light, 1 = the Studio's evening set
    const k = clamp(s.room, 0, 1), S = this.stage;
    S.key.intensity = S.keyBase * k;
    S.rim.intensity = 1.4 * k;
    S.fill.intensity = S.fillBase * (0.12 + 0.88 * k);
    S.room.material.color.setScalar(0.1 + 0.9 * k);
    this.materials.setEnvIntensity(0.1 + 0.9 * k);
    this.etchMat.envMapIntensity *= 0.1 + 0.9 * k;

    if (view || this.viewName !== s.view) this.setView(s.view, immediate);
    this.dirty = true;
  }

  panelColours() {
    const e = this.content;
    if (!e || !this.panelLights) return;
    // u 0..0.5 is the left panel (-x): the lights are ordered [+x, -x]. A flat panel light has no off-axis falloff,
    // so it is turned down to what a real panel sends sideways and down.
    this.panelLights[0].color.copy(e.colors[1]);
    this.panelLights[1].color.copy(e.colors[0]);
    for (const l of this.panelLights) l.intensity = SCREEN_GAIN * 0.38;
  }

  setView(name, immediate) {
    const v = VIEWS[name] || VIEWS.seat;
    this.viewName = name;
    const to = { pos: new THREE.Vector3(...v.pos), target: new THREE.Vector3(...v.target) };
    if (immediate) {
      this.camera.position.copy(to.pos);
      this.controls.target.copy(to.target);
      this.setFov(v);
      this.controls.update();
      return;
    }
    this.tween = { t: 0, from: { pos: this.camera.position.clone(), target: this.controls.target.clone(), fov: this.camera.fov }, to, view: v };
  }

  loop(now) {
    requestAnimationFrame(this.loop);
    if (document.hidden) return;
    const gap = now - (this.last || now);
    const dt = Math.min(0.1, gap / 1000);
    this.last = now;
    // on a slow GPU the moving content repaints less often, so the page stays responsive between frames
    this.pace = lerp(this.pace || 16, Math.min(gap, 1500), 0.2);
    if (this.tween) {
      const tw = this.tween;
      tw.t = Math.min(1, tw.t + dt / 1.1);
      const e = tw.t < 0.5 ? 4 * tw.t ** 3 : 1 - ((-2 * tw.t + 2) ** 3) / 2;
      this.camera.position.lerpVectors(tw.from.pos, tw.to.pos, e);
      this.controls.target.lerpVectors(tw.from.target, tw.to.target, e);
      this.setFov(tw.view);
      const fovTo = this.camera.fov;
      this.camera.fov = lerp(tw.from.fov, fovTo, e);
      this.camera.updateProjectionMatrix();
      if (tw.t >= 1) this.tween = null;
      this.dirty = true;
    }
    this.controls.update();
    if (this.content && this.content.live && !this.frozen && now - (this.lastPaint || 0) > Math.max(60, this.pace * 4)) {
      this.lastPaint = now;
      this.screens.animate(this.content, now / 1000);
      this.panelColours();
      this.dirty = true;
    }
    if (this.dirty) this.render();
  }

  render() {
    this.dirty = false;
    // the eye marker shows where the etch is aimed; it is in the way when you are sitting there
    this.eyeMark.visible = this.camera.position.distanceTo(SEAT_EYE) > 0.12;
    this.camera.updateMatrixWorld();
    this.privacy.uEyeView.value.copy(SEAT_EYE).applyMatrix4(this.camera.matrixWorldInverse);
    const mat = this.model.groups.get('deskmat');
    this.stage.prerender(this.scene, this.camera, this.model.root, mat ? [mat.node] : [], { reflect: true });
    this.output.render();
    if (!this.ready) {
      this.ready = true;
      this.el.classList.add('ready');
      for (const fn of this.listeners) fn({ type: 'ready' });
    }
  }
}

// ---------------------------------------------------------------------------------------------- page API
let sceneRef = null;
const Etch = {
  views: Object.keys(VIEWS), designs: DESIGNS, contents: CONTENTS,
  /** Merge a partial state: { etch: 'matte' | 'facets', film, view, content, design, room }. Returns the full state. */
  set(partial) {
    Object.assign(state, partial || {});
    if (sceneRef) sceneRef.apply(state, false, !!(partial && 'view' in partial));
    return { ...state };
  },
  get() { return { ...state }; },
  on(fn) {
    listeners.add(fn);
    if (Etch.ready) fn({ type: 'ready' });
    else if (Etch._error) fn({ type: 'error', reason: Etch._error });
  },
  /** Stills: stop the moving content at time t (seconds) and draw one frame. */
  _freeze(t = 0, pixelRatio = 0, scene = sceneRef) {
    const s = scene;
    if (!s) return;
    s.frozen = true;
    if (pixelRatio) { s.forcePixelRatio = pixelRatio; s.resize(); }
    if (s.content && s.content.live) { s.screens.animate(s.content, t); s.panelColours(); }
    if (s.tween) { s.tween.t = 1; }
    s.dirty = true;
  },
  get ready() { return !!(sceneRef && sceneRef.ready); },
  get error() { return Etch._error || null; },
  get _scene() { return sceneRef; },
};
window.Etch = Etch;

(async () => {
  const el = document.getElementById('stage');
  const s = new EtchScene(el);
  try {
    await s.init();
    sceneRef = s;
  } catch (e) {
    console.error('[DeckEtch]', e);
    Etch._error = e && e.friendly ? e.friendly : 'model';
    for (const fn of listeners) fn({ type: 'error', reason: Etch._error });
  }
})();
