// Orbit viewer for the Night Array with the light-ribbon optics. Real-time PBR, not ray traced.
// The model is the one the Cycles render used (render/scene.py --export). The ribbon is drawn as a live
// single-bounce reflection: each point of the cove shows the slot under the sill if its mirror direction
// from the camera passes through the slot, which is why it brightens and fades as you orbit.
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';

const A = window.__ASSETS__;                       // { glb: base64, screen: data URI, band: data URI, info: {...} }
const $ = id => document.getElementById(id);
const mm = v => v / 1000;
const TOE = 10 * Math.PI / 180;
const SEAM_Z = mm(-62), ROW0_Y = mm(172), SLOT_Y = mm(172 - 16);

function fail(msg) { $('status').textContent = msg; $('status').hidden = false; }

let renderer;
try {
  renderer = new THREE.WebGLRenderer({ canvas: $('gl'), antialias: true, powerPreference: 'high-performance' });
} catch (e) { fail('This browser could not start WebGL, so the 3D view is unavailable here.'); throw e; }
renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.0;
renderer.localClippingEnabled = true;

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x0c0a09);
const pmrem = new THREE.PMREMGenerator(renderer);
scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
const key = new THREE.DirectionalLight(0xffe2c4, 1);
key.position.set(-2.2, 1.6, 1.8);
const hemi = new THREE.HemisphereLight(0xfff1e0, 0x1a1512, 1);
scene.add(key, hemi);
// two rooms: a dim one in which the ribbon reads about as it would at the desk, and studio light for the shapes
function setLight(studio) {
  scene.environmentIntensity = studio ? 0.85 : 0.22;
  key.intensity = studio ? 1.1 : 0.35;
  hemi.intensity = studio ? 0.35 : 0.06;
}

const camera = new THREE.PerspectiveCamera(40, 2, 0.02, 30);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.08;
controls.minDistance = 0.12;
controls.maxDistance = 4.5;
controls.maxPolarAngle = Math.PI * 0.53;

// ---------------------------------------------------------------- materials, by the names the model carries
const cut = new THREE.Plane(new THREE.Vector3(1, 0, 0), 10);       // keeps x > -constant; 10 = nothing cut
const lin = (r, g, b) => new THREE.Color().setRGB(r, g, b);
const std = (color, roughness, metalness = 0, extra = {}) => new THREE.MeshStandardMaterial(
  { color, roughness, metalness, side: THREE.DoubleSide, clippingPlanes: [cut], ...extra });
const tex = (uri, mip) => { const t = new THREE.TextureLoader().load(uri); t.colorSpace = THREE.SRGBColorSpace; t.flipY = false;
  t.anisotropy = 8; t.generateMipmaps = mip; t.minFilter = mip ? THREE.LinearMipmapLinearFilter : THREE.LinearFilter; return t; };
const screenTex = tex(A.screen, true), bandTex = tex(A.band, false);
bandTex.wrapS = THREE.ClampToEdgeWrapping;
const MATS = {
  titanium: std(lin(0.60, 0.565, 0.52), 0.34, 1),
  graphite: std(lin(0.032, 0.030, 0.029), 0.55),
  glass_black: std(lin(0.004, 0.004, 0.004), 0.10),
  oxblood: std(lin(0.20, 0.028, 0.034), 0.38),
  keycap: std(lin(0.028, 0.027, 0.027), 0.5),
  rubber: std(lin(0.012, 0.012, 0.012), 0.85),
  laptop_alu: std(lin(0.74, 0.74, 0.75), 0.36, 1),
  felt: std(lin(0.045, 0.045, 0.05), 1),
  steel: std(lin(0.55, 0.55, 0.56), 0.4, 1),
  amber_led_off: std(lin(0.03, 0.02, 0.012), 0.3),
  matte_black: std(lin(0.03, 0.03, 0.03), 0.95),
  sill_graphite: std(lin(0.030, 0.028, 0.027), 0.42),
  mirror: std(lin(0.9, 0.9, 0.9), 0.03, 1),
  // finer brush: roughness 0.05 along the ribbon, 0.08 across it (the UV's U runs across)
  cove_brushed: new THREE.MeshPhysicalMaterial({ color: lin(0.62, 0.58, 0.52), roughness: 0.224, metalness: 1,
    anisotropy: 0.18, side: THREE.DoubleSide, clippingPlanes: [cut] }),
  screen: new THREE.MeshBasicMaterial({ map: screenTex, toneMapped: false, side: THREE.DoubleSide, clippingPlanes: [cut] }),
  band: new THREE.MeshBasicMaterial({ map: bandTex, toneMapped: false, side: THREE.DoubleSide, clippingPlanes: [cut] }),
};

// ---------------------------------------------------------------- the ribbon: live reflection of the slot in the cove
const glow = new THREE.ShaderMaterial({
  transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, clipping: true, clippingPlanes: [cut],
  polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2, side: THREE.DoubleSide, toneMapped: false,
  uniforms: {
    band: { value: bandTex }, gain: { value: 0.5 },      // 0.5 x tint puts a white band near a quarter of screen white
    seam: { value: new THREE.Vector3(0, 0, SEAM_Z) }, slotY: { value: SLOT_Y },
    z0: { value: A.info.screen_z0_mm }, slot: { value: 12.0 }, tint: { value: lin(0.62 * 0.81, 0.58 * 0.81, 0.52 * 0.81) },
    cs: { value: new THREE.Vector2(Math.cos(TOE), Math.sin(TOE)) },
  },
  vertexShader: `
    #include <clipping_planes_pars_vertex>
    varying vec3 vWorld; varying vec3 vNormalW;
    void main() {
      vec4 w = modelMatrix * vec4(position, 1.0);
      vWorld = w.xyz;
      vNormalW = normalize(mat3(modelMatrix) * normal);
      vec4 mvPosition = viewMatrix * w;
      gl_Position = projectionMatrix * mvPosition;
      #include <clipping_planes_vertex>
    }`,
  fragmentShader: `
    #include <clipping_planes_pars_fragment>
    uniform sampler2D band; uniform float gain, slotY, z0, slot; uniform vec3 seam, tint; uniform vec2 cs;
    varying vec3 vWorld; varying vec3 vNormalW;
    void main() {
      #include <clipping_planes_fragment>
      float side = vWorld.x >= 0.0 ? 1.0 : -1.0;
      vec3 t = vec3(side * cs.x, 0.0, cs.y);              // along this panel, from the seam outward
      vec3 n = vec3(-side * cs.y, 0.0, cs.x);             // out of the screen
      vec3 N = normalize(vNormalW);
      vec3 V = normalize(cameraPosition - vWorld);
      if (dot(N, V) < 0.0) N = -N;
      vec3 R = reflect(-V, N);
      if (R.y <= 0.02) discard;
      float d = (slotY - vWorld.y) / R.y;                 // metres to the slot's plane
      if (d <= 0.0 || d > 0.2) discard;
      vec3 H = vWorld + d * R - seam;
      float zl = dot(H, n) * 1000.0 - z0;                 // mm in front of the screen face
      float xl = dot(H, t) * 1000.0 + 22.0 * dot(R, t) / R.y;   // on along the path inside the sill
      float blur = max(0.6, 95.0 * d);                    // the brushed lobe across the ribbon, in mm at the slot
      float a = smoothstep(-blur, blur, zl) * (1.0 - smoothstep(slot - blur, slot + blur, zl));
      float u = (xl - 7.0) / 596.7;
      a *= smoothstep(-0.01, 0.01, u) * (1.0 - smoothstep(0.99, 1.01, u));
      vec3 c = texture2D(band, vec2(0.5 + side * 0.5 * clamp(u, 0.0, 1.0), 0.5)).rgb;
      gl_FragColor = vec4(c * tint * a * gain, 1.0);
      #include <colorspace_fragment>
    }`,
});

// ---------------------------------------------------------------- model
const b64 = A.glb, bin = atob(b64), buf = new Uint8Array(bin.length);
for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
let glowMesh = null;
new GLTFLoader().parse(buf.buffer, '', gltf => {
  const meshes = [];
  gltf.scene.traverse(o => { if (o.isMesh) meshes.push(o); });
  for (const o of meshes) {
    const first = Array.isArray(o.material) ? o.material[0] : o.material;
    const pick = m => MATS[m.name] || MATS.graphite;
    const isCove = first.name === 'cove_brushed';
    o.material = Array.isArray(o.material) ? o.material.map(pick) : pick(o.material);
    if (isCove) {                                        // the glow rides on the cove's own geometry
      glowMesh = new THREE.Mesh(o.geometry, glow);
      glowMesh.renderOrder = 5;
      o.add(glowMesh);
    }
  }
  scene.add(gltf.scene);
  $('status').hidden = true;
}, e => fail('The model could not be read.'));

const desk = new THREE.Mesh(new THREE.BoxGeometry(2.3, 0.035, 0.96),
  new THREE.MeshStandardMaterial({ color: lin(0.04, 0.026, 0.019), roughness: 0.45 }));
desk.position.set(0.1, -0.0176, 0.14);
scene.add(desk);

// ---------------------------------------------------------------- views
const VIEWS = {
  quarter: { pos: [-0.95, 0.72, 1.25], at: [0.05, 0.17, 0.02], fov: 38, cut: null, label: 'Three-quarter' },
  seat: { pos: [0, 0.452, 0.588], at: [0.03, 0.2, -0.03], fov: 78, cut: null, label: 'From the seat' },
  front: { pos: [0, 0.33, 1.75], at: [0.055, 0.215, 0], fov: 36, cut: null, label: 'Front' },
  sill: { pos: [-0.25, 0.5, 0.62], at: [-0.17, 0.135, -0.01], fov: 30, cut: null, label: 'Sill close-up' },
  section: { pos: [-0.6, 0.19, 0.2], at: [-0.3, 0.115, 0.0], fov: 26, cut: -0.3, label: 'Section' },
  back: { pos: [0.95, 0.6, -1.15], at: [0.05, 0.2, -0.05], fov: 38, cut: null, label: 'Back' },
};
let tween = null;
function go(name, instant) {
  const v = VIEWS[name];
  if (v.cut !== null) setCut(true, v.cut); else if (state.cutFromView) setCut(false);
  state.cutFromView = v.cut !== null;
  const to = { pos: new THREE.Vector3(...v.pos), at: new THREE.Vector3(...v.at), fov: v.fov };
  if (instant) { camera.position.copy(to.pos); controls.target.copy(to.at); camera.fov = to.fov; camera.updateProjectionMatrix(); controls.update(); return; }
  tween = { t: 0, from: { pos: camera.position.clone(), at: controls.target.clone(), fov: camera.fov }, to };
  document.querySelectorAll('#views button').forEach(b => b.setAttribute('aria-pressed', b.dataset.v === name));
}
const state = { glow: true, cut: false, cutX: -0.3, spin: false, cutFromView: false, studio: false };
function setCut(on, x) {
  state.cut = on;
  if (x !== undefined) state.cutX = x;
  cut.constant = on ? -state.cutX : 10;
  $('t-cut').setAttribute('aria-pressed', on);
  $('cutx').disabled = !on;
  $('cutx').value = Math.round(state.cutX * 1000);
  $('cutv').textContent = on ? `${Math.round(state.cutX * 1000)} mm` : 'off';
}

// ---------------------------------------------------------------- UI
$('views').innerHTML = Object.entries(VIEWS).map(([k, v]) => `<button type="button" data-v="${k}" aria-pressed="${k === 'quarter'}">${v.label}</button>`).join('');
$('views').addEventListener('click', e => { const b = e.target.closest('button'); if (b) go(b.dataset.v); });
$('t-glow').addEventListener('click', () => { state.glow = !state.glow; $('t-glow').setAttribute('aria-pressed', state.glow); if (glowMesh) glowMesh.visible = state.glow; MATS.band.visible = state.glow; });
$('t-cut').addEventListener('click', () => { state.cutFromView = false; setCut(!state.cut); });
$('cutx').addEventListener('input', e => setCut(true, e.target.value / 1000));
$('t-studio').addEventListener('click', () => { state.studio = !state.studio; $('t-studio').setAttribute('aria-pressed', state.studio); setLight(state.studio); });
$('t-spin').addEventListener('click', () => { state.spin = !state.spin; $('t-spin').setAttribute('aria-pressed', state.spin); controls.autoRotate = state.spin; });
controls.autoRotateSpeed = 0.8;
controls.addEventListener('start', () => { tween = null; document.querySelectorAll('#views button').forEach(b => b.setAttribute('aria-pressed', 'false')); });

function resize() {
  const el = $('stage'), w = el.clientWidth, h = el.clientHeight;
  if (!w || !h) return;
  renderer.setSize(w, h, false);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
}
new ResizeObserver(resize).observe($('stage'));
resize();
setCut(false);
setLight(false);
go('quarter', true);

const clock = new THREE.Clock();
renderer.setAnimationLoop(() => {
  const dt = Math.min(clock.getDelta(), 0.05);
  if (tween) {
    tween.t = Math.min(1, tween.t + dt / 0.9);
    const k = tween.t * tween.t * (3 - 2 * tween.t);
    camera.position.lerpVectors(tween.from.pos, tween.to.pos, k);
    controls.target.lerpVectors(tween.from.at, tween.to.at, k);
    camera.fov = tween.from.fov + (tween.to.fov - tween.from.fov) * k;
    camera.updateProjectionMatrix();
    if (tween.t >= 1) tween = null;
  }
  controls.update();
  renderer.render(scene, camera);
});
window.__viewer = { go, setCut, setLight, camera, controls, scene, glow, MATS, state };
