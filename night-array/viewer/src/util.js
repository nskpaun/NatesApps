export const clamp = (v, a, b) => (v < a ? a : v > b ? b : v);
export const lerp = (a, b, t) => a + (b - a) * t;
export const smoothstep = (a, b, x) => {
  const t = clamp((x - a) / (b - a), 0, 1);
  return t * t * (3 - 2 * t);
};
export const DEG = Math.PI / 180;

export const ease = {
  linear: (t) => t,
  inOutCubic: (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2),
  outCubic: (t) => 1 - Math.pow(1 - t, 3),
  inCubic: (t) => t * t * t,
  inOutSine: (t) => -(Math.cos(Math.PI * t) - 1) / 2,
  outQuart: (t) => 1 - Math.pow(1 - t, 4),
  inOutQuint: (t) => (t < 0.5 ? 16 * t * t * t * t * t : 1 - Math.pow(-2 * t + 2, 5) / 2),
};

/** Small deterministic PRNG (mulberry32) so procedural textures and stills are reproducible. */
export function rng(seed = 1) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function makeCanvas(w, h) {
  const c = document.createElement('canvas');
  c.width = w;
  c.height = h;
  return c;
}

/**
 * Keyed tweens driven by the render loop. Starting a tween with a key that is running replaces it.
 * fn(easedProgress, rawProgress) is called every frame; onDone after the final call.
 */
export class Tweens {
  constructor() {
    this.map = new Map();
  }
  run(key, duration, fn, opts = {}) {
    this.map.delete(key);
    this.map.set(key, {
      start: null, duration: Math.max(0, duration) * 1000, delay: (opts.delay || 0) * 1000,
      fn, ease: opts.ease || ease.inOutCubic, onDone: opts.onDone || null,
    });
  }
  has(key) {
    return this.map.has(key);
  }
  cancel(key) {
    this.map.delete(key);
  }
  /** Jumps one tween to its end (runs its last frame and onDone). */
  finish(key) {
    const tw = this.map.get(key);
    if (!tw) return;
    this.map.delete(key);
    tw.fn(1, 1);
    if (tw.onDone) tw.onDone();
  }
  get size() {
    return this.map.size;
  }
  /** Advances all tweens; returns true while any is still running. */
  update(now) {
    let active = false;
    for (const [key, tw] of this.map) {
      if (tw.start === null) tw.start = now;
      const e = now - tw.start - tw.delay;
      if (e < 0) {
        active = true;
        continue;
      }
      const s = tw.duration > 0 ? Math.min(1, e / tw.duration) : 1;
      tw.fn(tw.ease(s), s);
      if (s >= 1) {
        if (this.map.get(key) === tw) this.map.delete(key);
        if (tw.onDone) tw.onDone();
      } else active = true;
    }
    return active || this.map.size > 0;
  }
  /** Jumps every tween (and any tween they chain) to its end. */
  finishAll() {
    for (let guard = 0; guard < 64 && this.map.size; guard++) {
      const items = [...this.map.entries()];
      this.map.clear();
      for (const [, tw] of items) {
        tw.fn(1, 1);
        if (tw.onDone) tw.onDone();
      }
    }
  }
}

export const smootherstep = (a, b, x) => {
  const t = clamp((x - a) / (b - a), 0, 1);
  return t * t * t * (t * (t * 6 - 15) + 10);
};

/** Object layer for overlays (edges, rims, section stencil/caps, dims, grid): seen by the main camera only,
 *  so the contact shadow, the desk mirror, the shadow map and the raycaster all ignore them. */
export const OVERLAY_LAYER = 1;

/**
 * Clone of a material that keeps what Material.copy drops (onBeforeCompile hooks, program cache key) and
 * points its clipping planes at the live section plane (copy() clones planes, which would freeze them).
 */
export function cloneMaterial(m, clip) {
  const c = m.clone();
  c.onBeforeCompile = m.onBeforeCompile;
  c.customProgramCacheKey = m.customProgramCacheKey;
  c.userData = { ...m.userData };
  if (m.clippingPlanes) c.clippingPlanes = m.clippingPlanes;
  if (clip) clip.register(c);
  return c;
}
