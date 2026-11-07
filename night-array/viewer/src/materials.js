// Material library: one MeshPhysicalMaterial per scene.json material key, built from scene.json's
// colour / metallic / roughness / emissive hints plus the physical extras the studio look needs
// (brushed anisotropy, clearcoat, sheen, procedural maps). Also owns the finish selector and amber level.
import * as THREE from 'three';
import { brushedTextures, pcbTexture, feltTexture } from './textures.js';
import { lerp } from './util.js';

// Physical extras per material key. Colour, metalness, roughness and "emissive" always come from scene.json.
const EXTRAS = {
  titanium: { brushed: true, anisotropy: 0.55, envBoost: 1.0, clearcoat: 0.0 },
  graphite: { sheen: 0.35, sheenRoughness: 0.75, sheenTint: 1.6, envBoost: 0.85 },
  oxblood: { brushed: true, anisotropy: 0.5, clearcoat: 0.8, clearcoatRoughness: 0.14, envBoost: 1.0 },
  glass_black: { clearcoat: 1.0, clearcoatRoughness: 0.02, ior: 1.52, envBoost: 1.2 },
  screen: { clearcoat: 0.35, clearcoatRoughness: 0.18, ior: 1.5, envBoost: 0.6 },
  keycap: { sheen: 0.12, sheenRoughness: 0.6, sheenTint: 1.4, envBoost: 0.55 },
  rubber: { envBoost: 0.6 },
  amber_led: { emissiveIntensity: 5.5, envBoost: 0.4 },
  copper: { brushed: true, anisotropy: 0.35, envBoost: 1.0 },
  pcb: { map: 'pcb', clearcoat: 0.4, clearcoatRoughness: 0.35, envBoost: 0.8 },
  ferrite: { envBoost: 0.6 },
  laptop_alu: { brushed: true, anisotropy: 0.4, envBoost: 1.0 },
  felt: { sheen: 0.5, sheenRoughness: 0.9, sheenTint: 1.3, roughMap: 'felt', envBoost: 0.22 },
  steel: { brushed: true, anisotropy: 0.45, envBoost: 1.0 },
};

// Brushed textures span 0.3 m along the brushing direction and 60 mm across it (UVs are in metres), so the
// streaks are fine enough to average out at viewing distance and only show as anisotropic highlights.
const BRUSH_REPEAT = [1 / 0.3, 1 / 0.05];
const ROUGH_MAP_MEAN = 214 / 255; // mean of the brushed roughness canvas (see textures.js)

const tmpColor = new THREE.Color();

function colorFrom(hex, fallback = '#808080') {
  return new THREE.Color().setStyle(typeof hex === 'string' ? hex : fallback); // sRGB -> linear working space
}

export class MaterialLib {
  /** @param {object} sceneJson  parsed scene.json */
  constructor(sceneJson) {
    this.defs = sceneJson.materials || {};
    this.materials = new Map();
    this.amber = 1;
    this.finish = 'titanium';
    this.textures = {};
    this.envIntensity = 1;
    const br = brushedTextures();
    for (const t of [br.map, br.rough]) t.repeat.set(BRUSH_REPEAT[0], BRUSH_REPEAT[1]);
    this.textures.brushMap = br.map;
    this.textures.brushRough = br.rough;
    this.textures.pcb = pcbTexture();
    this.textures.pcb.repeat.set(1 / 0.12, 1 / 0.12);
    this.textures.felt = feltTexture();
    this.textures.felt.repeat.set(1 / 0.08, 1 / 0.08);
    for (const key of Object.keys(this.defs)) this.materials.set(key, this.build(key));
  }

  hint(key) {
    const d = this.defs[key] || {};
    return {
      color: colorFrom(d.color),
      metalness: typeof d.metallic === 'number' ? d.metallic : 0,
      roughness: typeof d.roughness === 'number' ? d.roughness : 0.5,
      emissive: !!d.emissive,
    };
  }

  /** Does geometry with this material need box-projected UVs / brushing tangents? */
  needsUV(key) {
    const x = EXTRAS[key] || {};
    return !!(x.brushed || x.map || x.roughMap) || key === 'titanium';
  }
  prepare(geom, key) {
    prepareGeometry(geom, { uv: this.needsUV(key), tangent: this.needsTangent(key) });
  }
  needsTangent(key) {
    const x = EXTRAS[key] || {};
    return !!x.brushed || key === 'titanium';
  }

  build(key) {
    const h = this.hint(key);
    const x = EXTRAS[key] || {};
    const m = new THREE.MeshPhysicalMaterial({
      name: key,
      color: h.color,
      metalness: h.metalness,
      roughness: h.roughness,
    });
    m.userData.key = key;
    m.userData.envBoost = x.envBoost ?? 1;
    if (x.brushed) this.applyBrushed(m, x.anisotropy ?? 0.5, h.roughness);
    if (x.clearcoat) {
      m.clearcoat = x.clearcoat;
      m.clearcoatRoughness = x.clearcoatRoughness ?? 0.1;
    }
    if (x.ior) m.ior = x.ior;
    if (x.sheen) {
      m.sheen = x.sheen;
      m.sheenRoughness = x.sheenRoughness ?? 0.7;
      m.sheenColor = h.color.clone().multiplyScalar(x.sheenTint ?? 1.5);
    }
    if (x.map === 'pcb') {
      m.map = this.textures.pcb;
      m.color.set(0xffffff); // the painted board already carries the solder-mask colour
    }
    if (x.roughMap === 'felt') {
      m.roughnessMap = this.textures.felt;
    }
    if (h.emissive) {
      m.userData.emissiveBase = x.emissiveIntensity ?? 6;
      m.userData.onColor = h.color.clone();
      m.userData.offColor = h.color.clone().multiplyScalar(0.18);
      m.emissive = h.color.clone();
      m.toneMapped = true;
    }
    m.envMapIntensity = m.userData.envBoost * this.envIntensity;
    if (this.envMap) m.envMap = this.envMap;
    return m;
  }

  applyBrushed(m, anisotropy, roughness) {
    m.map = this.textures.brushMap;
    m.roughnessMap = this.textures.brushRough;
    m.roughness = Math.min(1, roughness / ROUGH_MAP_MEAN);
    m.anisotropy = anisotropy;
    m.anisotropyRotation = 0;
  }

  get(key) {
    return this.materials.get(key) || this.materials.get('graphite');
  }

  setEnvIntensity(k) {
    this.envIntensity = k;
    for (const m of this.all()) m.envMapIntensity = (m.userData.envBoost ?? 1) * k;
  }

  /**
   * Materials get the environment explicitly: with scene.environment alone three overrides every material's
   * envMapIntensity with scene.environmentIntensity, and the per-material boosts would be lost.
   */
  setEnvMap(tex) {
    this.envMap = tex;
    for (const m of this.all()) { m.envMap = tex; m.needsUpdate = true; }
  }

  /** Base materials plus registered variants (screen, charge LEDs, highlights...). */
  all() {
    return [...this.materials.values(), ...(this.variants || [])];
  }

  /** A tracked clone of a base material (follows env / quality changes). */
  variant(key, name) {
    const base = this.get(key);
    const m = base.clone();
    m.name = name;
    m.userData = { ...base.userData };
    (this.variants || (this.variants = [])).push(m);
    return m;
  }

  /**
   * Finish selector: recolours material `titanium` using the scene.json hints of the chosen material key
   * (titanium -> Neutral Titanium, graphite -> Charcoal Graphite, oxblood -> Brushed Oxblood); the brushed
   * texture and anisotropy stay, so every finish still reads as machined metal.
   * Returns a tween function (t in 0..1) so the caller can animate it, or applies it at once.
   */
  finishTween(finish) {
    const m = this.materials.get('titanium');
    if (!m) return null;
    const from = { color: m.color.clone(), metalness: m.metalness, roughness: m.roughness, clearcoat: m.clearcoat, aniso: m.anisotropy };
    const h = this.hint(finish in this.defs ? finish : 'titanium');
    const x = EXTRAS[finish] || {};
    // A finish is always a metal: keep a little more metalness than a painted part would have.
    const to = {
      color: h.color,
      metalness: Math.max(h.metalness, 0.82),
      roughness: Math.min(1, h.roughness / ROUGH_MAP_MEAN),
      clearcoat: finish === 'titanium' ? 0 : (x.clearcoat ?? 0.35),
      aniso: finish === 'titanium' ? EXTRAS.titanium.anisotropy : (x.anisotropy ?? 0.45),
    };
    this.finish = finish;
    return (t) => {
      m.color.copy(from.color).lerp(to.color, t);
      m.metalness = lerp(from.metalness, to.metalness, t);
      m.roughness = lerp(from.roughness, to.roughness, t);
      m.clearcoat = lerp(from.clearcoat, to.clearcoat, t);
      m.clearcoatRoughness = 0.16;
      m.anisotropy = lerp(from.aniso, to.aniso, t);
    };
  }

  /** amber 0..1 (0 = LEDs off). `breath` multiplies the charge indicators only. */
  setAmber(a) {
    this.amber = a;
    const m = this.materials.get('amber_led');
    if (!m) return;
    const k = a <= 0.001 ? 0 : 0.18 + 0.82 * a;
    m.emissiveIntensity = m.userData.emissiveBase * k;
    tmpColor.copy(m.userData.offColor).lerp(m.userData.onColor, Math.min(1, k * 1.3));
    m.color.copy(tmpColor);
  }
}

/**
 * Box-projected UVs (metres) and a "brushing" tangent for CAD meshes that come without them.
 * The tangent follows world X projected onto the surface (Z on faces that look along X), so the
 * brushing direction is continuous across fillets instead of jumping at UV seams.
 */
export function prepareGeometry(geom, { uv = false, tangent = false } = {}) {
  const pos = geom.attributes.position, nor = geom.attributes.normal;
  if (!pos || !nor) return;
  const n = pos.count;
  if (uv && !geom.attributes.uv) {
    const a = new Float32Array(n * 2);
    for (let i = 0; i < n; i++) {
      const x = pos.getX(i), y = pos.getY(i), z = pos.getZ(i);
      const ax = Math.abs(nor.getX(i)), ay = Math.abs(nor.getY(i)), az = Math.abs(nor.getZ(i));
      let u, v;
      if (ax >= ay && ax >= az) { u = z; v = y; }
      else if (ay >= az) { u = x; v = z; }
      else { u = x; v = y; }
      a[i * 2] = u;
      a[i * 2 + 1] = v;
    }
    geom.setAttribute('uv', new THREE.BufferAttribute(a, 2));
  }
  if (tangent && !geom.attributes.tangent) {
    const t = new Float32Array(n * 4);
    for (let i = 0; i < n; i++) {
      const nx = nor.getX(i), ny = nor.getY(i), nz = nor.getZ(i);
      let tx, ty, tz;
      if (Math.abs(nx) < 0.9) { // X projected on the tangent plane
        tx = 1 - nx * nx; ty = -nx * ny; tz = -nx * nz;
      } else { // faces looking along X: brush along Z
        tx = -nz * nx; ty = -nz * ny; tz = 1 - nz * nz;
      }
      const l = Math.hypot(tx, ty, tz) || 1;
      t[i * 4] = tx / l; t[i * 4 + 1] = ty / l; t[i * 4 + 2] = tz / l; t[i * 4 + 3] = 1;
    }
    geom.setAttribute('tangent', new THREE.BufferAttribute(t, 4));
  }
}
