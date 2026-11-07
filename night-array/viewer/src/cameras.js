// Camera presets, aspect-aware framing and animated moves (orbiting around, never cutting through the model).
import * as THREE from 'three';
import { DEG, clamp, lerp, ease } from './util.js';

/**
 * az: degrees around Y from +Z (front) toward +X (right); el: degrees above the desk.
 * fit: which groups (or parts) to frame; pad: breathing room as a fraction of the view (ppad: in portrait);
 * lift: shifts the framed box down in the view (fraction of view height) to clear the app's top chrome.
 */
export const PRESETS = {
  hero: { az: -24, el: 12.5, fit: { all: true }, pad: 0.05, lift: 0.05 },
  front: { az: 0, el: 6, fit: { all: true }, pad: 0.05, lift: 0.04 },
  top: { az: 0, el: 89, fit: { all: true }, pad: 0.05, lift: 0.02 },
  side: { az: 82, el: 11, fit: { all: true }, pad: 0.09, lift: 0.04 },
  back: { az: 207, el: 19, fit: { all: true }, pad: 0.05, lift: 0.04 },
  dock: { az: 40, el: 17, fit: { groups: ['dock', 'laptop'] }, pad: 0.12, ppad: 0.2, lift: 0.03 },
  trays: { az: -7, el: 52, fit: { parts: ['tray_pad_kb', 'tray_pad_mouse'], groups: ['keyboard', 'mouse'], within: 'base' }, pad: 0.07, lift: 0.02 },
  display: { az: -13, el: 5, fit: { groups: ['display'] }, pad: 0.035, lift: 0.03 },
};

/** Vertical FOV from the aspect: wider when the viewport is tall so portrait phones don't push the camera miles away. */
export function fovFor(aspect) {
  const hfov = 34 * DEG; // horizontal field we like in portrait
  const v = 2 * Math.atan(Math.tan(hfov / 2) / Math.max(0.3, aspect)) / DEG;
  return clamp(v, 27, 50);
}

export function dirFrom(az, el) {
  const a = az * DEG, e = el * DEG;
  return new THREE.Vector3(Math.sin(a) * Math.cos(e), Math.sin(e), Math.cos(a) * Math.cos(e));
}

const _r = new THREE.Vector3(), _u = new THREE.Vector3(), _p = new THREE.Vector3();

/**
 * Frames a point cloud (e.g. the corners of every visible part's box) seen from direction `dir`
 * (unit, target -> camera): finds the target and distance at which the points' projection is centred
 * and fills the view up to `pad` (fraction of the half-extent kept free on each side).
 * `lift` moves the framed content down by that fraction of the view height (clears the app's top chrome).
 * Returns { target, distance }.
 */
export function fitPoints(points, dir, fovDeg, aspect, pad = 0.05, lift = 0) {
  const box = new THREE.Box3().setFromPoints(points);
  const c = box.getCenter(new THREE.Vector3());
  const up = Math.abs(dir.y) > 0.995 ? new THREE.Vector3(0, 0, -1) : new THREE.Vector3(0, 1, 0);
  _r.crossVectors(up, dir).normalize();
  _u.crossVectors(dir, _r).normalize();
  const tv = Math.tan((fovDeg * DEG) / 2), th = tv * aspect;
  // the content is centred `lift` below the middle, so it gets that much less vertical room
  const kv = tv * Math.max(0.2, 1 - pad * 2 - lift * 2), kh = th * (1 - pad * 2);
  const need = () => {
    let dd = 0;
    for (const p of points) {
      _p.copy(p).sub(c);
      const along = _p.dot(dir);
      dd = Math.max(dd, along + Math.abs(_p.dot(_u)) / kv, along + Math.abs(_p.dot(_r)) / kh);
    }
    return dd;
  };
  let d = need();
  for (let iter = 0; iter < 8; iter++) {
    // where do the points land on screen from there? re-centre on their projected extent
    let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
    for (const p of points) {
      _p.copy(p).sub(c);
      const z = d - _p.dot(dir);
      const x = _p.dot(_r) / z, y = _p.dot(_u) / z;
      if (x < x0) x0 = x;
      if (x > x1) x1 = x;
      if (y < y0) y0 = y;
      if (y > y1) y1 = y;
    }
    const mx = (x0 + x1) / 2, my = (y0 + y1) / 2;
    if (Math.abs(mx) < 1e-3 * tv && Math.abs(my) < 1e-3 * tv) break;
    c.addScaledVector(_r, mx * d).addScaledVector(_u, my * d);
    d = need();
  }
  // the content sits `lift` (fraction of the view height) below the middle
  const target = c.clone().addScaledVector(_u, lift * 2 * d * tv);
  return { target, distance: d };
}

/** Corners of a Box3 as points. */
export function boxCorners(box, out = []) {
  const { min, max } = box;
  for (let i = 0; i < 8; i++) out.push(new THREE.Vector3(i & 1 ? max.x : min.x, i & 2 ? max.y : min.y, i & 4 ? max.z : min.z));
  return out;
}

/** Spherical description of a camera relative to its target. */
export function sphericalOf(pos, target) {
  const v = pos.clone().sub(target);
  const dist = v.length();
  const el = Math.asin(clamp(v.y / dist, -1, 1)) / DEG;
  const az = Math.atan2(v.x, v.z) / DEG;
  return { az, el, dist };
}

/**
 * Animated camera move: interpolates target linearly and (azimuth, elevation, distance) spherically,
 * taking the short way round, so the camera orbits instead of flying through the station.
 */
export function cameraTween(camera, controls, toPos, toTarget, onUpdate) {
  const fromTarget = controls.target.clone();
  const a = sphericalOf(camera.position, fromTarget);
  const b = sphericalOf(toPos, toTarget);
  let daz = b.az - a.az;
  while (daz > 180) daz -= 360;
  while (daz < -180) daz += 360;
  const span = Math.abs(daz) + Math.abs(b.el - a.el) + Math.abs(Math.log(b.dist / Math.max(1e-3, a.dist))) * 40 + fromTarget.distanceTo(toTarget) * 60;
  const duration = clamp(0.7 + span / 160, 0.75, 1.6);
  const fn = (t) => {
    const tg = fromTarget.clone().lerp(toTarget, t);
    const az = a.az + daz * t;
    const el = lerp(a.el, b.el, t);
    const dist = Math.exp(lerp(Math.log(a.dist), Math.log(b.dist), t));
    camera.position.copy(tg).addScaledVector(dirFrom(az, el), dist);
    controls.target.copy(tg);
    camera.lookAt(tg);
    if (onUpdate) onUpdate();
  };
  return { fn, duration, ease: ease.inOutCubic };
}
