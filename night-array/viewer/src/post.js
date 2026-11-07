// Output pipeline: HDR render -> (bloom) -> tone mapping + sRGB. Quality tiers trade pixel ratio,
// shadow resolution, MSAA, bloom and the desk reflection for battery life.
import * as THREE from 'three';
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/examples/jsm/postprocessing/OutputPass.js';

export const QUALITY = {
  high: { pixelRatio: 2, shadow: 2048, shadowType: THREE.PCFSoftShadowMap, msaa: 4, bloom: true, reflect: 0.5, screen: 1, breathe: true },
  balanced: { pixelRatio: 1.5, shadow: 1024, shadowType: THREE.PCFSoftShadowMap, msaa: 2, bloom: true, reflect: 0.33, screen: 0.8, breathe: true },
  battery: { pixelRatio: 1, shadow: 512, shadowType: THREE.PCFShadowMap, msaa: 0, bloom: false, reflect: 0, screen: 0.6, breathe: false },
};

export class Output {
  constructor(renderer, scene, camera) {
    this.renderer = renderer;
    this.scene = scene;
    this.camera = camera;
    this.composer = null;
    this.bloomPass = null;
    this.q = null;
    this.size = new THREE.Vector2(1, 1);
    this.bloom = { strength: 0.55, radius: 0.55, threshold: 1.0 };
    this.bloomEnabled = true;
  }

  /**
   * Builds (once) and sizes the HDR composer for a tier. One composer serves the whole session: a tier without bloom
   * parks it (its render targets are freed, its passes and so their compiled shader programs stay), an MSAA change
   * re-allocates the same targets with the new sample count. Switching tiers therefore never rebuilds the bloom and
   * output programs.
   */
  configure(q, w, h, pr) {
    this.q = q;
    this.size.set(w, h);
    if (!q.bloom) {
      this.park();
      return;
    }
    let c = this.composer || this.parked;
    this.parked = null;
    if (!c) c = this.build(w, h, pr, q.msaa);
    else if (c.renderTarget1.samples !== q.msaa) {
      for (const rt of [c.renderTarget1, c.renderTarget2]) {
        rt.samples = q.msaa;
        rt.dispose(); // re-allocated (lazily, with the new sample count) the next time it is bound
      }
    }
    c.setPixelRatio(pr);
    c.setSize(w, h);
    this.composer = c;
  }

  build(w, h, pr, msaa) {
    // stencil: section caps (section.js) count faces in the stencil buffer
    const rt = new THREE.WebGLRenderTarget(Math.max(1, w * pr), Math.max(1, h * pr), {
      type: THREE.HalfFloatType, samples: msaa, depthBuffer: true, stencilBuffer: true,
    });
    rt.texture.name = 'NightArray.hdr';
    const c = new EffectComposer(this.renderer, rt);
    c.setPixelRatio(pr);
    c.setSize(w, h);
    c.addPass(new RenderPass(this.scene, this.camera));
    this.bloomPass = new UnrealBloomPass(new THREE.Vector2(w, h), this.bloom.strength, this.bloom.radius, this.bloom.threshold);
    this.bloomPass.enabled = this.bloomEnabled;
    if (this.bloomStrength !== undefined) this.bloomPass.strength = this.bloomStrength;
    c.addPass(this.bloomPass);
    // The output pass draws to the canvas and must stay the LAST pass. It doesn't swap, so the render and bloom
    // passes always work in one HDR target (the composer's read buffer, renderTarget2) and renderTarget1 is never
    // bound, so three never allocates it: one full MSAA RGBA16F + depth/stencil set saved, pixel-identical output.
    const outPass = new OutputPass();
    outPass.needsSwap = false;
    c.addPass(outPass);
    return c;
  }

  /** The target the scene is drawn into (null = the canvas): shader programs depend on it (tone mapping, colour space). */
  sceneTarget() {
    return this.composer ? this.composer.readBuffer : null;
  }

  /** No bloom on this tier: free the composer's GPU memory but keep its passes for the way back. */
  park() {
    const c = this.composer;
    if (!c) return;
    this.composer = null;
    const b = this.bloomPass;
    const targets = [c.renderTarget1, c.renderTarget2];
    if (b) targets.push(...b.renderTargetsHorizontal, ...b.renderTargetsVertical, b.renderTargetBright);
    for (const rt of targets) rt.dispose();
    this.parked = c;
  }

  /** Bloom belongs to the lit styles (studio, x-ray); the drafting styles stay crisp. */
  setBloomEnabled(on) {
    this.bloomEnabled = on;
    if (this.bloomPass) this.bloomPass.enabled = on;
  }

  setBloom(strength) {
    this.bloomStrength = strength;
    if (this.bloomPass) this.bloomPass.strength = strength;
  }

  setSize(w, h, pr) {
    this.size.set(w, h);
    if (this.composer) {
      this.composer.setPixelRatio(pr);
      this.composer.setSize(w, h);
    }
  }

  render() {
    if (this.composer) this.composer.render();
    else this.renderer.render(this.scene, this.camera);
  }

  dispose() {
    for (const c of [this.composer, this.parked]) {
      if (!c) continue;
      for (const p of c.passes) if (p.dispose) p.dispose();
      c.renderTarget1.dispose();
      c.renderTarget2.dispose();
    }
    this.composer = null;
    this.parked = null;
    this.bloomPass = null;
  }
}
