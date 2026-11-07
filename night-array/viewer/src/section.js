// Section view (SPEC.md section 4: section {axis x|z, t}): one clipping plane swept across the station's bounds,
// with solid section caps. Caps use the classic stencil trick: every clipped solid draws its back faces
// (stencil +1) and front faces (stencil -1) with colour and depth writes off; wherever the count is not zero
// the ray crossed the plane inside a solid, and a hatched cap plane is drawn there.
//   axis 'x': keeps x >= c, the cut faces -X (toward the hero camera on the left); t = 0 shows everything.
//   axis 'z': keeps z <= c, the cut faces +Z (toward the front cameras);           t = 0 shows everything.
import * as THREE from 'three';
import { LineSegments2 } from 'three/examples/jsm/lines/LineSegments2.js';
import { LineSegmentsGeometry } from 'three/examples/jsm/lines/LineSegmentsGeometry.js';
import { hatchTexture } from './textures.js';
import { OVERLAY_LAYER, lerp } from './util.js';
import { LOOK, AMBER, lineMaterial } from './styles.js';

const HATCH_MM = 24; // one hatch tile (4 lines) in millimetres

export class SectionTool {
  constructor(v) {
    this.v = v;
    this.plane = new THREE.Plane(new THREE.Vector3(1, 0, 0), 1e3);
    this.planes = [this.plane];
    this.active = false;
    this.mats = new Set();
    this.axis = 'x';
    this.c = 0; // current plane coordinate along the axis
    this.bounds = new THREE.Box3(new THREE.Vector3(-1, 0, -1), new THREE.Vector3(1, 1, 1));

    const stencilBase = { colorWrite: false, depthWrite: false, depthTest: false, stencilWrite: true, stencilFunc: THREE.AlwaysStencilFunc };
    this.backMat = this.register(new THREE.MeshBasicMaterial({
      ...stencilBase, side: THREE.BackSide,
      stencilFail: THREE.IncrementWrapStencilOp, stencilZFail: THREE.IncrementWrapStencilOp, stencilZPass: THREE.IncrementWrapStencilOp,
    }));
    this.frontMat = this.register(new THREE.MeshBasicMaterial({
      ...stencilBase, side: THREE.FrontSide,
      stencilFail: THREE.DecrementWrapStencilOp, stencilZFail: THREE.DecrementWrapStencilOp, stencilZPass: THREE.DecrementWrapStencilOp,
    }));
    this.stencilMeshes = [];

    // caps: one material per style (studio is lit, the drafting styles are flat hatch)
    const capStencil = {
      stencilWrite: true, stencilRef: 0, stencilFunc: THREE.NotEqualStencilFunc,
      stencilFail: THREE.ReplaceStencilOp, stencilZFail: THREE.ReplaceStencilOp, stencilZPass: THREE.ReplaceStencilOp,
      side: THREE.DoubleSide,
    };
    this.capMats = {
      // studio: warm machined-metal hatch with an amber glow, so even 2 mm walls read as cut
      studio: new THREE.MeshStandardMaterial({
        ...capStencil, map: hatchTexture('#CDBBA6', '#8E7A66'), roughness: 0.55, metalness: 0.1, envMapIntensity: 0.6,
        emissive: new THREE.Color(AMBER), emissiveIntensity: 0.22,
      }),
      cad: new THREE.MeshBasicMaterial({ ...capStencil, map: hatchTexture(LOOK.cad.capBg, LOOK.cad.capLine) }),
      blueprint: new THREE.MeshBasicMaterial({ ...capStencil, map: hatchTexture(LOOK.blueprint.capBg, LOOK.blueprint.capLine) }),
    };
    this.cap = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), this.capMats.studio);
    this.cap.name = 'section-cap';
    this.cap.renderOrder = 6;
    this.cap.visible = false;
    this.cap.layers.set(OVERLAY_LAYER);
    this.cap.onAfterRender = (renderer) => renderer.clearStencil();
    v.scene.add(this.cap);

    // a thin frame where the plane meets the bounds, so the cut reads as a tool
    this.frameMat = lineMaterial({ color: AMBER, width: 1.1, opacity: 0.55 });
    this.frameGeo = new LineSegmentsGeometry().setPositions(new Float32Array(24));
    this.frame = new LineSegments2(this.frameGeo, this.frameMat);
    this.frame.name = 'section-frame';
    this.frame.renderOrder = 7;
    this.frame.visible = false;
    this.frame.layers.set(OVERLAY_LAYER);
    v.scene.add(this.frame);
    this.frameOpacity = 0.55;
  }

  /** Model-side materials follow the plane (studio, styles, highlights, fade clones). */
  register(m) {
    this.mats.add(m);
    m.clippingPlanes = this.active ? this.planes : null;
    m.clipShadows = this.active;
    return m;
  }

  unregister(m) {
    this.mats.delete(m);
  }

  /** Stencil writers for every part mesh (children of the mesh, so they follow its visibility and transforms). */
  attach(model) {
    for (const p of model.parts.values()) {
      for (const mat of [this.backMat, this.frontMat]) {
        const s = new THREE.Mesh(p.mesh.geometry, mat);
        s.renderOrder = 5;
        s.visible = false;
        s.layers.set(OVERLAY_LAYER);
        s.name = `${p.id}:stencil`;
        p.mesh.add(s);
        this.stencilMeshes.push(s);
      }
    }
  }

  setActive(on, style) {
    if (on !== this.active) {
      this.active = on;
      for (const m of this.mats) {
        m.clippingPlanes = on ? this.planes : null;
        m.clipShadows = on;
        m.needsUpdate = true;
      }
      const cd = this.v.stage.contact.depthMat;
      cd.clippingPlanes = on ? this.planes : null;
      cd.needsUpdate = true;
    }
    this.setStyle(style);
  }

  setStyle(style) {
    const caps = this.active && style !== 'xray';
    this.cap.visible = caps;
    for (const s of this.stencilMeshes) s.visible = caps;
    this.cap.material = this.capMats[style] || this.capMats.studio;
    if (style === 'studio' && this.v.scene.environment) this.capMats.studio.envMap = this.v.scene.environment;
    this.frame.visible = this.active;
    this.frameMat.color.set(style === 'cad' ? LOOK.cad.edgeSel.color : AMBER);
    this.frameOpacity = style === 'cad' ? 0.7 : style === 'blueprint' ? 0.7 : 0.5;
  }

  /** Coordinate of the plane for a t in 0..1 across `bounds` (t = 0: nothing cut away). */
  coordFor(axis, t, bounds = this.bounds) {
    return axis === 'x' ? lerp(bounds.min.x, bounds.max.x, t) : lerp(bounds.max.z, bounds.min.z, t);
  }

  /** Moves the plane to coordinate c along `axis`, resizes the cap and frame to the bounds' cross-section. */
  place(axis, c, fade = 1) {
    this.axis = axis;
    this.c = c;
    const b = this.bounds;
    const m = 0.03; // frame margin
    if (axis === 'x') this.plane.set(new THREE.Vector3(1, 0, 0), -c);
    else this.plane.set(new THREE.Vector3(0, 0, -1), c);
    const y0 = -0.002, y1 = b.max.y + m;
    let pts;
    if (axis === 'x') {
      const z0 = b.min.z - m, z1 = b.max.z + m;
      this.cap.position.set(c, (y0 + y1) / 2, (z0 + z1) / 2);
      this.cap.rotation.set(0, Math.PI / 2, 0);
      this.cap.scale.set(z1 - z0, y1 - y0, 1);
      pts = [[c, y0, z0], [c, y0, z1], [c, y0, z1], [c, y1, z1], [c, y1, z1], [c, y1, z0], [c, y1, z0], [c, y0, z0]];
    } else {
      const x0 = b.min.x - m, x1 = b.max.x + m;
      this.cap.position.set((x0 + x1) / 2, (y0 + y1) / 2, c);
      this.cap.rotation.set(0, 0, 0);
      this.cap.scale.set(x1 - x0, y1 - y0, 1);
      pts = [[x0, y0, c], [x1, y0, c], [x1, y0, c], [x1, y1, c], [x1, y1, c], [x0, y1, c], [x0, y1, c], [x0, y0, c]];
    }
    for (const mat of Object.values(this.capMats)) mat.map.repeat.set(this.cap.scale.x * 1000 / HATCH_MM, this.cap.scale.y * 1000 / HATCH_MM);
    const buf = this.frameGeo.attributes.instanceStart.data; // update in place (setPositions would allocate)
    buf.array.set(pts.flat());
    buf.needsUpdate = true;
    this.frameGeo.computeBoundingBox();
    this.frameGeo.computeBoundingSphere();
    this.frameMat.opacity = this.frameOpacity * fade;
    this.v.stage.contact.dirty = true;
    this.v.renderer.shadowMap.needsUpdate = true;
  }

  /** Raycast hits on the cut-away side don't count. */
  keeps(point) {
    return !this.active || this.plane.distanceToPoint(point) >= -1e-4;
  }

  setResolution(w, h) {
    this.frameMat.resolution.set(w, h);
  }
}
