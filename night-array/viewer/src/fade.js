// Fades whole nodes in and out (isolate, the desk mat, the laptop in standalone). For the duration of a fade
// every material under the node is swapped for a transparent clone; at the end the originals come back and the
// node is hidden or shown for good.
import { cloneMaterial, ease } from './util.js';

export class Fader {
  constructor(v) {
    this.v = v;
    this.active = new Map(); // node -> { node, k, swaps, clones, key }
  }

  /** Fades `node` to shown (to = 1) or hidden (to = 0). */
  fade(node, to, { duration = 0.45, delay = 0, onDone = null } = {}) {
    let e = this.active.get(node);
    if (!e) {
      const from = node.visible ? 1 : 0;
      if (from === to) {
        if (onDone) onDone();
        return;
      }
      e = { node, k: from, swaps: [], clones: [], key: `fade:${node.uuid}` };
      this.swapIn(e);
      this.active.set(node, e);
    }
    node.visible = true;
    const k0 = e.k;
    this.apply(e);
    this.v.tweens.run(e.key, duration, (t) => { e.k = k0 + (to - k0) * t; this.apply(e); }, {
      delay, ease: ease.inOutSine, onDone: () => { this.finish(e, to); if (onDone) onDone(); },
    });
  }

  isFading(node) {
    return this.active.has(node);
  }

  swapIn(e) {
    const cache = new Map();
    e.node.traverse((o) => {
      const m = o.material;
      if (!m || Array.isArray(m) || o.userData.noFade || m.colorWrite === false || m.stencilWrite) return;
      let c = cache.get(m);
      if (!c) {
        c = cloneMaterial(m, this.v.section);
        c.transparent = true;
        c.userData.baseOpacity = m.uniforms && m.uniforms.opacity ? m.uniforms.opacity.value : m.opacity;
        cache.set(m, c);
      }
      e.swaps.push([o, m]);
      o.material = c;
    });
    e.clones = [...cache.values()];
  }

  apply(e) {
    for (const c of e.clones) {
      const op = c.userData.baseOpacity * e.k;
      if (c.uniforms && c.uniforms.opacity) c.uniforms.opacity.value = op;
      else c.opacity = op;
    }
  }

  finish(e, to) {
    for (const [o, m] of e.swaps) o.material = m;
    for (const c of e.clones) {
      this.v.section.unregister(c);
      c.dispose();
    }
    this.active.delete(e.node);
    e.node.visible = to > 0.5;
    this.v.stage.contact.dirty = true;
    this.v.renderer.shadowMap.needsUpdate = true;
  }

  /** Jumps every running fade to its end (before materials are reassigned, e.g. a style change). */
  finishAll() {
    for (const e of [...this.active.values()]) this.v.tweens.finish(e.key);
  }
}
