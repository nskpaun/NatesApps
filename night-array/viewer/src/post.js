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

  configure(q, w, h, pr) {
    const prev = this.q;
    this.q = q;
    this.size.set(w, h);
    const needComposer = q.bloom;
    if (!needComposer) {
      if (this.composer) this.disposeComposer();
      return;
    }
    if (this.composer && prev && prev.msaa === q.msaa) {
      this.composer.setPixelRatio(pr);
      this.composer.setSize(w, h);
      return;
    }
    this.disposeComposer();
    // stencil: section caps (section.js) count faces in the stencil buffer
    const rt = new THREE.WebGLRenderTarget(Math.max(1, w * pr), Math.max(1, h * pr), {
      type: THREE.HalfFloatType, samples: q.msaa, depthBuffer: true, stencilBuffer: true,
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
    c.addPass(new OutputPass());
    this.composer = c;
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

  disposeComposer() {
    if (!this.composer) return;
    for (const p of this.composer.passes) if (p.dispose) p.dispose();
    this.composer.renderTarget1.dispose();
    this.composer.renderTarget2.dispose();
    this.composer = null;
    this.bloomPass = null;
  }
}
