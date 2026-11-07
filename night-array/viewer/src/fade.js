// Fades whole nodes in and out (isolate, the desk mat, the laptop in standalone). For the duration of a fade
// every material under the node is swapped for a transparent twin; at the end the originals come back and the
// node is hidden or shown for good.
//
// Twins are pooled per source material and never thrown away while their source lives: a transparent variant
// is its own shader program (three keys programs on `transparent`), and disposing the last material that uses
// a program destroys it, so throwaway clones would re-link every program on the first frame of every fade.
// Each fade borrows a twin per material (two fades of the same material at once get two twins, sharing the
// program), re-synced from its source first because finish, amber, style and selection change between fades.
import { cloneMaterial, ease } from './util.js';

export class Fader {
  constructor(v) {
    this.v = v;
    this.active = new Map(); // node -> { node, k, swaps, clones, key }
    this.pool = new Map(); // source material -> free twins
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

  /** Can this material be faded (stencil writers and depth-only materials stay as they are)? */
  static fadeable(o) {
    const m = o.material;
    return !!m && !Array.isArray(m) && !o.userData.noFade && m.colorWrite !== false && !m.stencilWrite;
  }

  swapIn(e) {
    const borrowed = new Map();
    e.node.traverse((o) => {
      if (!Fader.fadeable(o)) return;
      const m = o.material;
      let c = borrowed.get(m);
      if (!c) {
        c = this.take(m);
        borrowed.set(m, c);
      }
      e.swaps.push([o, m]);
      o.material = c;
    });
    e.clones = [...borrowed.values()];
  }

  /** A transparent twin of `src`, in sync with it (from the pool when one is free). */
  take(src) {
    const free = this.pool.get(src);
    let c = free && free.pop();
    if (c) this.sync(c, src);
    else {
      c = cloneMaterial(src, this.v.section);
      c.userData.fadeSource = src;
      if (!this.pool.has(src)) {
        this.pool.set(src, []);
        // a source that goes away takes its twins with it
        src.addEventListener('dispose', () => this.drop(src));
      }
    }
    c.transparent = true;
    c.userData.baseOpacity = src.uniforms && src.uniforms.opacity ? src.uniforms.opacity.value : src.opacity;
    return c;
  }

  /** Hands a twin back to the pool (it stays registered with the section and keeps its programs). */
  give(c) {
    const src = c.userData.fadeSource;
    const free = src && this.pool.get(src);
    if (free) free.push(c);
    else {
      this.v.section.unregister(c);
      c.dispose();
    }
  }

  drop(src) {
    for (const c of this.pool.get(src) || []) {
      this.v.section.unregister(c);
      c.dispose();
    }
    this.pool.delete(src);
  }

  /**
   * Re-syncs a pooled twin with its source. Material.copy() drops the shader hooks and clones the clipping planes;
   * ShaderMaterial.copy() also replaces the uniform objects, which the renderer keeps using for an existing program,
   * so their values are copied into the twin's own objects instead. needsUpdate re-resolves the program, which finds
   * the one it already has unless the source's program-relevant settings changed (then it compiles, as it must).
   */
  sync(c, src) {
    const uniforms = c.uniforms;
    const userData = c.userData;
    c.copy(src);
    if (uniforms && c.uniforms !== uniforms) {
      for (const [k, u] of Object.entries(c.uniforms)) {
        if (uniforms[k]) uniforms[k].value = u.value;
        else uniforms[k] = u;
      }
      c.uniforms = uniforms;
    }
    c.onBeforeCompile = src.onBeforeCompile;
    c.customProgramCacheKey = src.customProgramCacheKey;
    c.userData = { ...src.userData, fadeSource: userData.fadeSource };
    this.v.section.register(c); // clipping planes: the live, shared section plane (copy() cloned them)
    c.needsUpdate = true;
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
    for (const c of e.clones) this.give(c);
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
