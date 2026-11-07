// Selection highlight (SPEC.md section 4: selected). Studio: an additive amber rim glow over the group's parts,
// with a short pulse when it appears. CAD: a softer orange fresnel tint (plus orange edges, see styles.js).
// X-ray and blueprint highlight through their own materials (amber shells / amber edges).
import * as THREE from 'three';
import { rimMaterial, AMBER, LOOK } from './styles.js';
import { OVERLAY_LAYER } from './util.js';

export class Highlighter {
  constructor(v) {
    this.v = v;
    this.group = null;
    this.rims = [];
    this.mats = {
      studio: v.section.register(rimMaterial(new THREE.Color(AMBER).multiplyScalar(1.2), { additive: true, fill: 0.035, rim: 0.8, power: 2.4 })),
      cad: v.section.register(rimMaterial(LOOK.cad.edgeSel.color, { additive: false, fill: 0.1, rim: 0.45, power: 1.6 })),
    };
    this.strength = 0;
  }

  /** Highlights `group` (or nothing). */
  set(group, style, immediate = false) {
    const v = this.v;
    if (group === this.group && this.rims.length) return this.setStyle(style);
    this.clear();
    this.group = group && v.model.groups.has(group) ? group : null;
    if (!this.group) return;
    for (const p of v.model.groups.get(this.group).parts) {
      const r = new THREE.Mesh(p.mesh.geometry, this.mats.studio);
      r.name = `${p.id}:rim`;
      r.renderOrder = 4;
      r.layers.set(OVERLAY_LAYER);
      r.userData.noFade = true;
      p.mesh.add(r);
      this.rims.push(r);
    }
    this.setStyle(style);
    const set = (k) => { this.strength = k; for (const m of Object.values(this.mats)) m.uniforms.uStrength.value = k; };
    if (immediate) set(1);
    else {
      set(0);
      // a quick pulse, then settle
      v.tweens.run('highlight', 0.75, (t) => set(t < 0.4 ? 1.7 * (t / 0.4) : 1.7 - 0.7 * ((t - 0.4) / 0.6)), { ease: (x) => x });
    }
  }

  setStyle(style) {
    const mat = this.mats[style];
    for (const r of this.rims) {
      r.visible = !!mat;
      if (mat) r.material = mat;
    }
  }

  clear() {
    for (const r of this.rims) r.removeFromParent();
    this.rims = [];
    this.group = null;
    this.v.tweens.cancel('highlight');
  }
}
