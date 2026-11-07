// Dimension overlay (SPEC.md section 4: dims): 3D dimension lines from scene.json dims (extension lines, the
// dimension line and arrowheads, offset along each dim's `dir`) plus crisp HTML labels projected every frame.
// A dim with a "pose" only shows in that mode; dims fade out while the station is exploded, and with an isolated
// group only the dims that belong to that group stay.
import * as THREE from 'three';
import { LineSegments2 } from 'three/examples/jsm/lines/LineSegments2.js';
import { LineSegmentsGeometry } from 'three/examples/jsm/lines/LineSegmentsGeometry.js';
import { lineMaterial, LOOK } from './styles.js';
import { OVERLAY_LAYER, clamp } from './util.js';

const STUDIO_INK = '#F2D2A6';
const ARROW = 0.011; // arrowhead length (m)
const GAP = 0.004; // extension lines start this far off the part
const OVERSHOOT = 0.008; // ...and run this far past the dimension line

const v3 = (a) => new THREE.Vector3(a[0], a[1], a[2]);

export class Dims {
  constructor(v, labelsEl) {
    this.v = v;
    this.el = labelsEl;
    this.items = [];
    this.on = false;
    this.group = new THREE.Group();
    this.group.name = 'dims';
    v.scene.add(this.group);
    this._p = new THREE.Vector3();
  }

  /** Builds lines + labels for scene.json dims. `groupBoxes`: id -> Box3 at rest (which groups a dim measures). */
  build(dims, groupBoxes) {
    const placed = [];
    // shorter dims sit closer to the part; longer ones stack outside them
    const order = dims.map((d, i) => ({ d, i, len: v3(d.a).distanceTo(v3(d.b)) })).sort((x, y) => x.len - y.len);
    for (const { d, len } of order) {
      if (!Array.isArray(d.a) || !Array.isArray(d.b)) continue;
      const a = v3(d.a), b = v3(d.b);
      const dir = v3(d.dir || [0, 1, 0]).normalize();
      const u = b.clone().sub(a).normalize();
      let off = 0.03 + 0.02 * clamp(len, 0, 1);
      // parallel dims on the same side must not overlap
      for (let guard = 0; guard < 6; guard++) {
        const lvl = a.dot(dir) + off;
        const clash = placed.some((p) => p.dir.dot(dir) > 0.95 && Math.abs(p.u.dot(u)) > 0.9 && Math.abs(p.lvl - lvl) < 0.02 && overlaps(p, a, b, u));
        if (!clash) break;
        off += 0.03;
      }
      const A = a.clone().addScaledVector(dir, off), B = b.clone().addScaledVector(dir, off);
      const segs = [];
      const seg = (p, q) => segs.push(p.x, p.y, p.z, q.x, q.y, q.z);
      seg(a.clone().addScaledVector(dir, GAP), A.clone().addScaledVector(dir, OVERSHOOT));
      seg(b.clone().addScaledVector(dir, GAP), B.clone().addScaledVector(dir, OVERSHOOT));
      const short = len < ARROW * 3.2;
      const s = short ? -1 : 1; // short dims: arrows outside, pointing in
      const wing = (tip, toward) => {
        const base = tip.clone().addScaledVector(toward, ARROW);
        seg(tip, base.clone().addScaledVector(dir, ARROW * 0.38));
        seg(tip, base.clone().addScaledVector(dir, -ARROW * 0.38));
      };
      if (short) {
        seg(A.clone().addScaledVector(u, -ARROW * 2.2), B.clone().addScaledVector(u, ARROW * 2.2));
      } else seg(A, B);
      wing(A, u.clone().multiplyScalar(s));
      wing(B, u.clone().multiplyScalar(-s));

      const geo = new LineSegmentsGeometry().setPositions(segs);
      const mat = lineMaterial({ color: STUDIO_INK, width: 1.15, opacity: 0, depthTest: false });
      const line = new LineSegments2(geo, mat);
      line.renderOrder = 20;
      line.layers.set(OVERLAY_LAYER);
      line.visible = false;
      line.name = `dim:${d.id}`;
      this.group.add(line);

      const label = document.createElement('div');
      label.className = 'dim hide';
      label.textContent = d.label || `${Math.round(len * 1000)} mm`;
      label.dataset.dim = d.id;
      this.el.appendChild(label);
      // which groups does it measure? (both ends must sit on/near the group, at rest)
      const near = (p) => [...groupBoxes].filter(([, box]) => box.clone().expandByScalar(0.008).containsPoint(p)).map(([id]) => id);
      const anchor = A.clone().lerp(B, 0.5).addScaledVector(dir, short ? 0.022 : 0);
      this.items.push({ def: d, line, mat, label, anchor, ends: [near(a), near(b)], opacity: 0, target: 0 });
      placed.push({ dir, u, lvl: a.dot(dir) + off, a, b });
    }
  }

  /** Which dims should show for this state. Returns true if anything changes. */
  setTargets(state, on) {
    this.on = on;
    let changed = false;
    for (const it of this.items) {
      let t = on ? 1 : 0;
      if (it.def.pose && it.def.pose !== state.mode) t = 0;
      if (state.explode > 0.02) t = 0;
      if (state.isolate && !it.ends.every((g) => g.includes(state.isolate))) t = 0;
      if (t !== it.target) { it.target = t; changed = true; }
    }
    this.el.classList.toggle('on', on);
    return changed;
  }

  /** Fade step toward the targets; returns a tween fn for the app's Tweens. */
  fadeFn() {
    const from = this.items.map((it) => it.opacity);
    return (k) => {
      this.items.forEach((it, i) => {
        it.opacity = from[i] + (it.target - from[i]) * k;
        it.mat.opacity = it.opacity * this.inkOpacity;
        it.line.visible = it.opacity > 0.002;
      });
    };
  }

  setStyle(style) {
    const ink = style === 'studio' ? STUDIO_INK : LOOK[style].dim;
    this.inkOpacity = style === 'cad' ? 0.9 : 0.85;
    for (const it of this.items) {
      it.mat.color.set(ink);
      it.mat.opacity = it.opacity * this.inkOpacity;
    }
    this.el.dataset.style = style;
  }

  setResolution(w, h) {
    for (const it of this.items) it.mat.resolution.set(w, h);
  }

  /** Projects the label anchors (call after the camera moved, before/after rendering). */
  project(camera, w, h) {
    const placed = [];
    for (const it of this.items) {
      const show = it.opacity > 0.02;
      if (!show) {
        if (!it.label.classList.contains('hide')) it.label.classList.add('hide');
        continue;
      }
      const p = this._p.copy(it.anchor).project(camera);
      const visible = p.z < 1 && p.z > -1 && Math.abs(p.x) < 1.2 && Math.abs(p.y) < 1.2;
      it.label.classList.toggle('hide', !visible);
      if (!visible) continue;
      if (!it.lw) {
        it.lw = it.label.offsetWidth || 60;
        it.lh = it.label.offsetHeight || 18;
      }
      placed.push({ it, x: (p.x * 0.5 + 0.5) * w, y: (-p.y * 0.5 + 0.5) * h });
    }
    // labels near the edge slide inside the view; overlapping labels step apart vertically
    placed.sort((a, b) => a.y - b.y);
    for (let i = 0; i < placed.length; i++) {
      const L = placed[i], mx = L.it.lw / 2 + 6, my = L.it.lh / 2 + 6;
      L.x = clamp(L.x, mx, Math.max(mx, w - mx));
      L.y = clamp(L.y, my, Math.max(my, h - my));
      for (let j = 0; j < i; j++) {
        const o = placed[j];
        const dx = Math.abs(L.x - o.x) - (L.it.lw + o.it.lw) / 2, dy = Math.abs(L.y - o.y) - (L.it.lh + o.it.lh) / 2;
        if (dx < 2 && dy < 2) L.y = o.y + (L.it.lh + o.it.lh) / 2 + 3;
      }
      L.it.label.style.transform = `translate(${L.x.toFixed(1)}px, ${L.y.toFixed(1)}px) translate(-50%, -50%)`;
      L.it.label.style.opacity = L.it.opacity.toFixed(3);
    }
  }
}

function overlaps(p, a, b, u) {
  const r0 = [p.a.dot(u), p.b.dot(u)].sort((x, y) => x - y);
  const r1 = [a.dot(u), b.dot(u)].sort((x, y) => x - y);
  return r0[0] < r1[1] + 0.01 && r1[0] < r0[1] + 0.01;
}
