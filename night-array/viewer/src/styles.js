// Render styles (SPEC.md section 4):
//   studio    - the PBR night scene (stage.js / materials.js)
//   cad       - light neutral background, matte grey solids, crisp black B-rep edges (station-edges.glb), like Onshape
//   xray      - translucent fresnel shells; internals in their real materials (copper coils, PCB, heatsink, VESA spine)
//   blueprint - dark navy, ivory / amber edge lines only (hidden lines faint and dashed), subtle grid, no solids
// Switching style cross-fades a snapshot of the old frame over the new one (StyleFade).
import * as THREE from 'three';
import { LineSegments2 } from 'three/examples/jsm/lines/LineSegments2.js';
import { LineSegmentsGeometry } from 'three/examples/jsm/lines/LineSegmentsGeometry.js';
import { LineMaterial } from 'three/examples/jsm/lines/LineMaterial.js';
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js';
import { backgroundTexture } from './textures.js';
import { OVERLAY_LAYER } from './util.js';

export const AMBER = '#F2A04A';

/** Per-style scene settings. Colours that are not part data (backgrounds, inks) live here. */
export const LOOK = {
  studio: { toneMapping: THREE.ACESFilmicToneMapping, bloom: true, stage: true, grid: null, contact: 1 },
  cad: {
    toneMapping: THREE.NeutralToneMapping, bloom: false, stage: false, contact: 0.55,
    grid: { minor: '#C3C8CE', major: '#AEB4BB', opacity: 0.55 },
    edge: { color: '#16181B', width: 1.05 }, edgeSel: { color: '#E8782A', width: 1.6 },
    dim: '#2A2E33', capBg: '#D5D9DD', capLine: '#7A828A',
  },
  xray: {
    toneMapping: THREE.ACESFilmicToneMapping, bloom: true, bloomStrength: 0.3, stage: false, contact: 0,
    grid: { minor: '#2A2421', major: '#3A302A', opacity: 0.6 },
    edge: { color: '#EADFCF', width: 0.9, opacity: 0.16 }, shellSel: AMBER,
    dim: '#EADFCF',
  },
  blueprint: {
    toneMapping: THREE.NoToneMapping, bloom: false, stage: false, contact: 0,
    grid: { minor: '#17345C', major: '#24497A', opacity: 0.85 },
    edge: { color: '#F1E6D2', width: 1.1, opacity: 0.95 }, edgeLed: { color: AMBER, width: 1.4 },
    edgeSel: { color: AMBER, width: 1.7 }, hidden: { color: '#C9D6EA', width: 0.9, opacity: 0.2 },
    dim: '#F2C58A', capBg: '#10294B', capLine: '#8FA6C6',
  },
};

// ---------------------------------------------------------------- shaders

// Edges are pulled toward the camera so they win the depth test against their own faces: 0.5 mm plus 0.025 % of the
// distance (about 1 mm at 2 m). More than that and edges just behind a thin part (the VESA plate 3 mm behind the
// panel glass) bleed through; polygonOffset on the solids proved unreliable.
const LINE_PULL = '1.0 - ( 0.0005 / max( length( start.xyz ), 0.01 ) + 0.00025 )';

/** Fat line material (width in CSS px) with the depth pull. */
export function lineMaterial({ color, width = 1, opacity = 1, hidden = false, dashed = false, depthTest = true, blending = THREE.NormalBlending }) {
  const m = new LineMaterial({
    color: new THREE.Color(color), linewidth: width, worldUnits: false, opacity,
    transparent: opacity < 1 || hidden, depthTest, depthWrite: false, dashed,
  });
  m.blending = blending;
  if (dashed) {
    m.dashSize = 0.006;
    m.gapSize = 0.004;
    m.dashScale = 1;
  }
  if (hidden) m.depthFunc = THREE.GreaterDepth;
  m.onBeforeCompile = (shader) => {
    shader.vertexShader = shader.vertexShader.replace(
      'vec4 end = modelViewMatrix * vec4( instanceEnd, 1.0 );',
      `vec4 end = modelViewMatrix * vec4( instanceEnd, 1.0 );\n\t\t\tfloat naPull = ${LINE_PULL};\n\t\t\tstart.xyz *= naPull; end.xyz *= naPull;`,
    );
  };
  m.customProgramCacheKey = () => 'na-line';
  return m;
}

const CLIP_V = '#include <clipping_planes_pars_vertex>';
const CLIP_F = '#include <clipping_planes_pars_fragment>';

/** View-space normal + view vector, with clipping (shared by the fresnel shaders). */
const FRESNEL_VERT = /* glsl */`
  #include <common>
  ${CLIP_V}
  varying vec3 vN;
  varying vec3 vV;
  void main() {
    vec4 mvPosition = modelViewMatrix * vec4( position, 1.0 );
    vN = normalize( normalMatrix * normal );
    vV = -mvPosition.xyz;
    gl_Position = projectionMatrix * mvPosition;
    #include <clipping_planes_vertex>
  }`;

/** Fresnel shell for the x-ray style (additive, so overlapping shells read like an x-ray plate). */
export function xrayMaterial(color, { base = 0.012, rim = 0.34, power = 3.0 } = {}) {
  return new THREE.ShaderMaterial({
    name: 'xray-shell',
    uniforms: {
      uColor: { value: new THREE.Color(color) }, opacity: { value: 1 },
      uBase: { value: base }, uRim: { value: rim }, uPower: { value: power },
    },
    vertexShader: FRESNEL_VERT,
    fragmentShader: /* glsl */`
      #include <common>
      ${CLIP_F}
      uniform vec3 uColor;
      uniform float opacity, uBase, uRim, uPower;
      varying vec3 vN;
      varying vec3 vV;
      void main() {
        #include <clipping_planes_fragment>
        float ndv = abs( dot( normalize( vN ), normalize( vV ) ) );
        float f = pow( 1.0 - ndv, uPower );
        gl_FragColor = vec4( uColor, ( uBase + uRim * f ) * opacity );
      }`,
    transparent: true, depthWrite: false, side: THREE.DoubleSide, blending: THREE.AdditiveBlending, clipping: true,
  });
}

/** Rim glow drawn over a selected part (same geometry, depth-equal). */
export function rimMaterial(color, { additive = true, fill = 0.06, rim = 1.0, power = 2.0 } = {}) {
  return new THREE.ShaderMaterial({
    name: 'rim',
    uniforms: {
      uColor: { value: new THREE.Color(color) }, opacity: { value: 1 }, uStrength: { value: 0 },
      uFill: { value: fill }, uRim: { value: rim }, uPower: { value: power },
    },
    vertexShader: FRESNEL_VERT,
    fragmentShader: /* glsl */`
      #include <common>
      ${CLIP_F}
      uniform vec3 uColor;
      uniform float opacity, uStrength, uFill, uRim, uPower;
      varying vec3 vN;
      varying vec3 vV;
      void main() {
        #include <clipping_planes_fragment>
        float ndv = abs( dot( normalize( vN ), normalize( vV ) ) );
        float f = pow( 1.0 - ndv, uPower );
        gl_FragColor = vec4( uColor, ( uFill + uRim * f ) * uStrength * opacity );
      }`,
    transparent: true, depthWrite: false, depthFunc: THREE.LessEqualDepth,
    blending: additive ? THREE.AdditiveBlending : THREE.NormalBlending,
    polygonOffset: true, polygonOffsetFactor: -1, polygonOffsetUnits: -1, clipping: true,
  });
}

/** Ground grid (5 cm minor / 25 cm major lines), anti-aliased with derivatives and fading out radially. */
function gridMaterial() {
  return new THREE.ShaderMaterial({
    name: 'grid',
    uniforms: {
      uMinor: { value: new THREE.Color() }, uMajor: { value: new THREE.Color() }, opacity: { value: 1 },
      uCenter: { value: new THREE.Vector2(0.07, 0.1) }, uRadius: { value: 1.6 },
    },
    vertexShader: /* glsl */`
      varying vec3 vW;
      void main() {
        vec4 w = modelMatrix * vec4( position, 1.0 );
        vW = w.xyz;
        gl_Position = projectionMatrix * viewMatrix * w;
      }`,
    fragmentShader: /* glsl */`
      uniform vec3 uMinor, uMajor;
      uniform float opacity, uRadius;
      uniform vec2 uCenter;
      varying vec3 vW;
      float grid( vec2 p, float s, float w ) {
        vec2 q = p / s;
        vec2 g = abs( fract( q - 0.5 ) - 0.5 ) / ( fwidth( q ) * w );
        return 1.0 - min( min( g.x, g.y ), 1.0 );
      }
      void main() {
        float minor = grid( vW.xz, 0.05, 1.0 );
        float major = grid( vW.xz, 0.25, 1.4 );
        float fade = 1.0 - smoothstep( uRadius * 0.35, uRadius, length( ( vW.xz - uCenter ) * vec2( 0.8, 1.0 ) ) );
        vec3 col = mix( uMinor, uMajor, major );
        float a = max( minor * 0.55, major ) * fade * opacity;
        if ( a < 0.003 ) discard;
        gl_FragColor = vec4( col, a );
      }`,
    transparent: true, depthWrite: false,
  });
}

// ---------------------------------------------------------------- colour derivation from scene.json

const _hsl = { h: 0, s: 0, l: 0 };

/** CAD grey for a material: scene.json colour, desaturated and lifted into the light-grey range (Onshape-like). */
function cadColor(hint) {
  const c = hint.color.clone();
  c.getHSL(_hsl, THREE.SRGBColorSpace);
  if (hint.emissive) return c; // indicator lights keep their colour
  const l = 0.5 + 0.34 * _hsl.l + (hint.metalness > 0.5 ? 0.1 : 0);
  return new THREE.Color().setHSL(_hsl.h, Math.min(0.16, _hsl.s * 0.3), Math.min(0.86, l), THREE.SRGBColorSpace);
}

/** X-ray tint: metals warm ivory, the rest a cool steel blue, nudged toward the material's own hue. */
function xrayColor(hint) {
  if (hint.emissive) return hint.color.clone().multiplyScalar(1.4);
  const base = new THREE.Color(hint.metalness > 0.5 ? '#E9D9C2' : '#9FB3C9');
  return base.lerp(hint.color, 0.15).multiplyScalar(hint.metalness > 0.5 ? 0.9 : 0.7);
}

// ---------------------------------------------------------------- style manager

export class StyleManager {
  /** @param v the Viewer (scene, stage, model, materials, section) */
  constructor(v) {
    this.v = v;
    this.style = 'studio';
    this.built = false;
    this.lineMats = new Set();
    this.selected = null;
    this.bg = {};
    // grid
    this.grid = new THREE.Mesh(new THREE.PlaneGeometry(6, 6).rotateX(-Math.PI / 2), gridMaterial());
    this.grid.position.y = 0.0002;
    this.grid.renderOrder = -1;
    this.grid.visible = false;
    this.grid.layers.set(OVERLAY_LAYER);
    this.grid.name = 'grid';
    v.scene.add(this.grid);
    // CAD light rig: neutral room environment + a soft key and sky/ground fill, no cast shadows
    this.cadRig = new THREE.Group();
    this.cadRig.name = 'cad-lights';
    const key = new THREE.DirectionalLight('#FFFFFF', 1.25);
    key.position.set(-1.2, 2.2, 2.4);
    const back = new THREE.DirectionalLight('#FFFFFF', 0.45);
    back.position.set(1.6, 1.2, -2.0);
    this.cadRig.add(key, back, new THREE.HemisphereLight('#FFFFFF', '#9AA0A6', 0.75));
    this.cadRig.visible = false;
    v.scene.add(this.cadRig);
  }

  /** Builds the per-style materials and the edge lines (lazily: studio-only sessions never pay for them). */
  build() {
    if (this.built) return;
    this.built = true;
    const v = this.v, M = v.model, lib = v.materials;
    const env = new THREE.PMREMGenerator(v.renderer);
    this.neutralEnv = env.fromScene(new RoomEnvironment(), 0.04).texture;
    env.dispose();
    this.mats = { cad: new Map(), xray: new Map(), xraySel: new Map() };
    for (const key of Object.keys(lib.defs)) {
      const h = lib.hint(key);
      const cad = new THREE.MeshStandardMaterial({
        name: `cad-${key}`, color: cadColor(h), roughness: h.emissive ? 0.5 : 0.62, metalness: 0,
        envMap: this.neutralEnv, envMapIntensity: 0.55,
      });
      if (h.emissive) { cad.emissive = h.color.clone(); cad.emissiveIntensity = 0.5; }
      this.mats.cad.set(key, v.section.register(cad));
      this.mats.xray.set(key, v.section.register(xrayMaterial(xrayColor(h))));
      this.mats.xraySel.set(key, v.section.register(xrayMaterial(new THREE.Color(AMBER).multiplyScalar(1.2), { base: 0.06, rim: 0.8, power: 2.2 })));
    }
    this.depthOnly = v.section.register(new THREE.MeshBasicMaterial({ name: 'depth-only', colorWrite: false }));
    // edge line materials per style (normal / led / selected / hidden)
    const L = (o) => { const m = v.section.register(lineMaterial(o)); this.lineMats.add(m); return m; };
    this.lines = {
      cad: { edge: L(LOOK.cad.edge), sel: L(LOOK.cad.edgeSel) },
      xray: { edge: L({ ...LOOK.xray.edge, blending: THREE.AdditiveBlending }) },
      blueprint: {
        edge: L(LOOK.blueprint.edge), led: L(LOOK.blueprint.edgeLed), sel: L(LOOK.blueprint.edgeSel),
        hidden: L({ ...LOOK.blueprint.hidden, hidden: true, dashed: true }),
        hiddenSel: L({ ...LOOK.blueprint.hidden, color: AMBER, opacity: 0.35, hidden: true, dashed: true }),
      },
    };
    // edges: one visible + one hidden-line object per part, sharing a LineSegmentsGeometry
    for (const p of M.parts.values()) {
      if (!p.edgeGeom) continue;
      const g = new LineSegmentsGeometry().setPositions(segmentPositions(p.edgeGeom));
      const vis = new LineSegments2(g, this.lines.cad.edge);
      vis.computeLineDistances();
      vis.name = `${p.id}:edges`;
      const hid = new LineSegments2(g, this.lines.blueprint.hidden);
      hid.name = `${p.id}:hidden-edges`;
      for (const o of [vis, hid]) {
        o.layers.set(OVERLAY_LAYER);
        o.visible = false;
        o.renderOrder = 3;
        p.mesh.add(o); // follows the mesh's visibility (internals) and transforms
      }
      p.lineV = vis;
      p.lineH = hid;
    }
    this.setResolution();
  }

  /** After a lost context: the neutral environment was a render target, build it again. */
  restore() {
    if (!this.built) return;
    const env = new THREE.PMREMGenerator(this.v.renderer);
    const old = this.neutralEnv;
    this.neutralEnv = env.fromScene(new RoomEnvironment(), 0.04).texture;
    env.dispose();
    for (const m of this.mats.cad.values()) m.envMap = this.neutralEnv;
    if (old) old.dispose();
  }

  setResolution() {
    const { w, h } = this.v.viewSize();
    for (const m of this.lineMats) m.resolution.set(w, h);
  }

  background(kind) {
    if (!this.bg[kind]) this.bg[kind] = backgroundTexture(kind);
    return this.bg[kind];
  }

  /** Applies a style at once (the caller handles the cross-fade). */
  apply(style) {
    const v = this.v, S = v.stage, look = LOOK[style] || LOOK.studio;
    if (style !== 'studio') this.build();
    this.style = style;
    // scene / stage
    const studio = style === 'studio';
    S.room.visible = studio;
    S.desk.visible = studio;
    S.group.getObjectByName('floor').visible = studio;
    S.contact.plane.visible = look.contact > 0;
    S.contact.plane.material.opacity = 0.92 * (look.contact || 0);
    S.key.visible = studio || style === 'xray';
    S.key.castShadow = studio;
    S.rim.visible = studio || style === 'xray';
    S.fill.visible = studio || style === 'xray';
    S.fill.intensity = style === 'xray' ? 1.1 : S.fillBase; // x-ray: internals need more light than the night set
    v.materials.setEnvIntensity(style === 'xray' ? 1.9 : 1);
    S.practicalsVisible(studio);
    this.cadRig.visible = style === 'cad';
    v.scene.fog = studio ? v.fog : null;
    v.scene.background = studio ? v.bgColor : this.background(style);
    v.renderer.toneMapping = look.toneMapping;
    v.output.setBloomEnabled(look.bloom);
    v.output.setBloom(look.bloomStrength ?? v.output.bloom.strength);
    // grid
    this.grid.visible = !!look.grid;
    if (look.grid) {
      const u = this.grid.material.uniforms;
      u.uMinor.value.set(look.grid.minor);
      u.uMajor.value.set(look.grid.major);
      u.opacity.value = look.grid.opacity;
    }
    this.assign();
  }

  /** Material + edge-line assignment for the current style and selection. */
  assign() {
    const v = this.v, style = this.style;
    const sel = this.selected;
    for (const p of v.model.parts.values()) {
      const studioMat = p.mesh.userData.studioMat;
      const isSel = !!sel && p.group === sel;
      const led = !!v.materials.hint(p.material).emissive;
      let mat = studioMat;
      if (style === 'cad') mat = this.mats.cad.get(p.material) || studioMat;
      else if (style === 'xray') mat = p.internal || led ? studioMat : (isSel ? this.mats.xraySel : this.mats.xray).get(p.material) || studioMat;
      else if (style === 'blueprint') mat = this.depthOnly;
      p.mesh.material = mat;
      p.mesh.castShadow = style === 'studio' || (style === 'xray' && p.internal);
      p.mesh.receiveShadow = style === 'studio' || style === 'xray';
      if (p.lineV) {
        const L = this.lines[style];
        p.lineV.visible = !!L && (style !== 'xray' || !(p.internal || led));
        p.lineH.visible = style === 'blueprint';
        if (L) {
          p.lineV.material = isSel && L.sel ? L.sel : led && L.led ? L.led : L.edge;
          if (style === 'blueprint') p.lineH.material = isSel ? L.hiddenSel : L.hidden;
        }
      }
    }
  }

  setSelected(group) {
    this.selected = group;
    if (this.style !== 'studio') this.assign();
  }

  /** Every material the styles own (for clipping / disposal). */
  allMaterials() {
    if (!this.built) return [];
    return [...this.mats.cad.values(), ...this.mats.xray.values(), ...this.mats.xraySel.values(), this.depthOnly, ...this.lineMats];
  }
}

/** Indexed or plain line-pair geometry -> flat array of segment endpoints for LineSegmentsGeometry. */
function segmentPositions(geom) {
  const pos = geom.attributes.position;
  const idx = geom.index;
  const n = idx ? idx.count : pos.count;
  const out = new Float32Array(n * 3);
  for (let i = 0; i < n; i++) {
    const k = idx ? idx.getX(i) : i;
    out[i * 3] = pos.getX(k);
    out[i * 3 + 1] = pos.getY(k);
    out[i * 3 + 2] = pos.getZ(k);
  }
  return out;
}

/**
 * Cross-fade for style changes: the last frame of the old style is copied into a texture and drawn over the
 * new style with falling opacity. Cheap (one textured quad) and immune to programs compiling mid-fade.
 */
export class StyleFade {
  constructor(renderer) {
    this.renderer = renderer;
    this.alpha = 0;
    this.tex = null;
    this.scene = new THREE.Scene();
    this.cam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
    this.mat = new THREE.ShaderMaterial({
      uniforms: { tSnap: { value: null }, uAlpha: { value: 0 } },
      vertexShader: 'varying vec2 vUv; void main() { vUv = uv; gl_Position = vec4( position.xy, 0.0, 1.0 ); }',
      fragmentShader: 'uniform sampler2D tSnap; uniform float uAlpha; varying vec2 vUv; void main() { gl_FragColor = vec4( texture2D( tSnap, vUv ).rgb, uAlpha ); }',
      transparent: true, depthTest: false, depthWrite: false, toneMapped: false,
    });
    const quad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), this.mat);
    quad.frustumCulled = false;
    this.scene.add(quad);
    this._size = new THREE.Vector2();
  }

  /**
   * Copies the frame that was just drawn to the canvas. Call right after a render, in the same task.
   * The canvas is RGB (alpha: false) and three can't allocate a sized RGB8 texture, so the copy target is a raw
   * GL texture handed to three through its texture properties.
   */
  capture() {
    const r = this.renderer, gl = r.getContext();
    r.getDrawingBufferSize(this._size);
    const w = Math.floor(this._size.x), h = Math.floor(this._size.y);
    r.setRenderTarget(null);
    if (!this.tex || this.w !== w || this.h !== h) {
      this.release();
      this.glTex = gl.createTexture();
      gl.bindTexture(gl.TEXTURE_2D, this.glTex);
      gl.texStorage2D(gl.TEXTURE_2D, 1, gl.RGB8, w, h);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
      this.tex = new THREE.Texture();
      const props = r.properties.get(this.tex);
      props.__webglTexture = this.glTex;
      props.__webglInit = true;
      this.w = w;
      this.h = h;
    }
    gl.bindTexture(gl.TEXTURE_2D, this.glTex);
    gl.copyTexSubImage2D(gl.TEXTURE_2D, 0, 0, 0, 0, 0, w, h);
    r.resetState(); // raw GL calls above: resync three's state cache
    this.mat.uniforms.tSnap.value = this.tex;
    this.alpha = 1;
  }

  /** Drops the snapshot texture (resize, lost context). */
  release(contextLost = false) {
    if (this.glTex && !contextLost) this.renderer.getContext().deleteTexture(this.glTex);
    if (this.tex) this.renderer.properties.remove(this.tex);
    this.glTex = null;
    this.tex = null;
    this.alpha = 0;
  }

  draw() {
    if (this.alpha <= 0.001 || !this.tex) return;
    const r = this.renderer;
    this.mat.uniforms.uAlpha.value = this.alpha;
    const auto = r.autoClear;
    r.autoClear = false;
    r.setRenderTarget(null);
    r.render(this.scene, this.cam);
    r.autoClear = auto;
  }

  cancel() {
    this.alpha = 0;
  }
}
