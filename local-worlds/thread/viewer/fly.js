// First-person camera: W A S D to move, drag the mouse to look. Sits on top of OrbitControls:
// while on, orbit's own mouse handling is off and its target is kept just ahead of the camera,
// so everything that reads orbit.target (bounds, switching back to orbit) keeps working.
import * as THREE from "three";

const KEYS = { KeyW: [0, 0, 1], ArrowUp: [0, 0, 1], KeyS: [0, 0, -1], ArrowDown: [0, 0, -1], KeyA: [-1, 0, 0], ArrowLeft: [-1, 0, 0], KeyD: [1, 0, 0], ArrowRight: [1, 0, 0], KeyE: [0, 1, 0], Space: [0, 1, 0], KeyQ: [0, -1, 0] };
const typing = (el) => el && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName) && !/^(checkbox|radio|range|button)$/.test(el.type));

export function createFly(camera, dom, orbit, { speed = 2.2, fast = 3, turn = 0.0028, ahead = 1.2 } = {}) {
  const held = new Set(), e = new THREE.Euler(0, 0, 0, "YXZ"), fwd = new THREE.Vector3(), right = new THREE.Vector3(), vel = new THREE.Vector3(), want = new THREE.Vector3();
  let on = false, look = null, shift = false;
  const aim = () => orbit.target.copy(camera.position).addScaledVector(camera.getWorldDirection(fwd), ahead);
  const fly = {
    get enabled() { return on; },
    setEnabled(b) {
      on = !!b; held.clear(); vel.set(0, 0, 0); look = null;
      orbit.enableRotate = orbit.enablePan = orbit.enableZoom = !on;
      if (on) aim();
    },
    update(dt) {                                        // call before orbit.update()
      if (!on) return;
      want.set(0, 0, 0);
      for (const k of held) want.add(new THREE.Vector3(...KEYS[k]));
      camera.getWorldDirection(fwd); right.crossVectors(fwd, camera.up).normalize();
      const v = new THREE.Vector3().addScaledVector(right, want.x).addScaledVector(fwd, want.z); v.y += want.y;
      if (v.lengthSq() > 1) v.normalize();
      v.multiplyScalar(speed * (shift ? fast : 1));
      vel.lerp(v, 1 - Math.exp(-dt * 12));              // ease in and out so steps are not jerky
      if (vel.lengthSq() > 1e-8) camera.position.addScaledVector(vel, dt);
      aim();
    },
  };
  addEventListener("keydown", (ev) => {
    shift = ev.shiftKey;
    if (!on || !KEYS[ev.code] || ev.metaKey || ev.ctrlKey || ev.altKey || typing(document.activeElement)) return;
    held.add(ev.code); ev.preventDefault();
  });
  addEventListener("keyup", (ev) => { shift = ev.shiftKey; held.delete(ev.code); });
  addEventListener("blur", () => { held.clear(); look = null; });
  dom.addEventListener("pointerdown", (ev) => { if (on && ev.button === 0) { look = [ev.clientX, ev.clientY]; document.activeElement?.blur?.(); } });
  addEventListener("pointerup", () => (look = null));
  addEventListener("pointermove", (ev) => {
    if (!on || !look || !orbit.enabled) { if (look) look = [ev.clientX, ev.clientY]; return; }   // orbit.enabled is off while a gizmo is dragged
    const dx = ev.clientX - look[0], dy = ev.clientY - look[1]; look = [ev.clientX, ev.clientY];
    e.setFromQuaternion(camera.quaternion);
    e.y -= dx * turn; e.x = Math.max(-1.5, Math.min(1.5, e.x - dy * turn)); e.z = 0;
    camera.quaternion.setFromEuler(e); aim();
  });
  dom.addEventListener("wheel", (ev) => { if (on) { camera.position.addScaledVector(camera.getWorldDirection(fwd), -ev.deltaY * 0.002); aim(); ev.preventDefault(); } }, { passive: false });
  return fly;
}
