// Loads scene.json + station.glb + station-edges.glb and turns them into a group hierarchy:
//   station (root)
//     <group node>   at scene.json group pivot (stow pose); poses / dock deltas move this node
//       [<subgroup>] e.g. dock_latch, at groups[].subgroups[id].pivot
//         <part node> at the part's GLB translation (relative to its parent pivot); explode offsets move it
//           mesh (+ B-rep edge lines)
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { DEG } from './util.js';

async function fetchJson(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`);
  return r.json();
}

/** Loads the three model files from `base` (e.g. '../model/'). Edges are optional (cad / blueprint styles). */
export async function loadModelFiles(base, onProgress) {
  const loader = new GLTFLoader();
  const progress = { scene: 0, glb: 0, edges: 0 };
  const report = () => onProgress && onProgress((progress.scene + progress.glb * 4 + progress.edges) / 6);
  const track = (k) => (e) => {
    if (e && e.lengthComputable) {
      progress[k] = e.loaded / e.total;
      report();
    }
  };
  const scene = fetchJson(base + 'scene.json').then((j) => { progress.scene = 1; report(); return j; });
  const glb = loader.loadAsync(base + 'station.glb', track('glb'));
  const edges = loader.loadAsync(base + 'station-edges.glb', track('edges')).catch((e) => {
    console.warn('[NightArray] station-edges.glb failed to load; cad/blueprint fall back to shaded edges', e);
    return null;
  });
  const [sceneJson, gltf, edgesGltf] = await Promise.all([scene, glb, edges]);
  return { sceneJson, gltf, edgesGltf };
}

const v3 = (a) => new THREE.Vector3(a?.[0] || 0, a?.[1] || 0, a?.[2] || 0);

export class Model {
  constructor(sceneJson, gltf, edgesGltf, materials) {
    this.sj = sceneJson;
    this.root = new THREE.Group();
    this.root.name = 'station';
    /** id -> { def, node, pivot, parts: [] } for groups AND subgroups (movable keys used by poses / dock_sequence) */
    this.movables = new Map();
    this.groups = new Map();
    this.parts = new Map();
    this.meshes = [];
    this.edgeLines = [];
    this.groupOrder = (sceneJson.groups || []).map((g) => g.id);

    const partDefs = new Map((sceneJson.parts || []).map((p) => [p.id, p]));
    const subOf = new Map(); // partId -> subgroup id

    for (const g of sceneJson.groups || []) {
      const pivot = v3(g.pivot);
      const node = new THREE.Group();
      node.name = `group:${g.id}`;
      node.position.copy(pivot);
      this.root.add(node);
      const entry = { id: g.id, def: g, node, pivot, parent: null, parts: [], isGroup: true };
      this.groups.set(g.id, entry);
      this.movables.set(g.id, entry);
      for (const [sid, s] of Object.entries(g.subgroups || {})) {
        const sp = v3(s.pivot);
        const sn = new THREE.Group();
        sn.name = `sub:${sid}`;
        sn.position.copy(sp).sub(pivot);
        node.add(sn);
        const se = { id: sid, def: s, node: sn, pivot: sp, parent: entry, parts: [], isGroup: false };
        this.movables.set(sid, se);
        for (const pid of s.parts || []) subOf.set(pid, sid);
      }
    }

    const edgeByName = new Map();
    if (edgesGltf) {
      edgesGltf.scene.updateMatrixWorld(true);
      for (const o of edgesGltf.scene.children) edgeByName.set(o.name, o);
    }

    gltf.scene.updateMatrixWorld(true);
    for (const obj of [...gltf.scene.children]) {
      const mesh = obj.isMesh ? obj : obj.getObjectByProperty('isMesh', true);
      if (!mesh) continue;
      const pid = obj.name;
      const extras = obj.userData || {};
      const def = partDefs.get(pid) || { id: pid, group: extras.group, material: extras.material, internal: !!extras.internal, explode: [0, 0, 0] };
      const group = this.groups.get(def.group);
      if (!group) continue;
      const sid = subOf.get(pid);
      const container = sid ? this.movables.get(sid) : group;
      const worldPos = new THREE.Vector3().setFromMatrixPosition(obj.matrixWorld);

      const partNode = new THREE.Group();
      partNode.name = `part:${pid}`;
      partNode.position.copy(worldPos).sub(container.pivot);
      container.node.add(partNode);

      const matKey = def.material || mesh.material?.name || 'graphite';
      const geom = mesh.geometry;
      materials && materials.prepare(geom, matKey);
      const m = new THREE.Mesh(geom, materials ? materials.get(matKey) : mesh.material);
      m.name = pid;
      m.castShadow = true;
      m.receiveShadow = true;
      m.userData = { part: pid, group: def.group, material: matKey, internal: !!def.internal };
      partNode.add(m);

      let edges = null;
      const eo = edgeByName.get(pid);
      if (eo) {
        const lines = eo.isLineSegments || eo.isLine ? eo : eo.getObjectByProperty('isLineSegments', true);
        if (lines) {
          edges = new THREE.LineSegments(lines.geometry, null);
          edges.name = `${pid}:edges`;
          edges.visible = false;
          edges.userData = { part: pid, group: def.group, internal: !!def.internal };
          partNode.add(edges);
          this.edgeLines.push(edges);
        }
      }

      const part = {
        id: pid, def, group: def.group, sub: sid || null, node: partNode, mesh: m, edges,
        rest: partNode.position.clone(), explode: v3(def.explode), internal: !!def.internal, material: matKey,
      };
      this.parts.set(pid, part);
      group.parts.push(part);
      if (sid) this.movables.get(sid).parts.push(part);
      this.meshes.push(m);
    }
    this.root.updateMatrixWorld(true);
  }

  /**
   * Per-movable delta transforms for a mode pose plus an optional dock step (both from scene.json).
   * Returns Map(id -> { t: Vector3, r: Euler, hidden: bool }).
   */
  targets(mode, dockStep) {
    const out = new Map();
    for (const id of this.movables.keys()) out.set(id, { t: new THREE.Vector3(), r: new THREE.Euler(), hidden: false });
    const add = (deltas) => {
      for (const [id, d] of Object.entries(deltas || {})) {
        const e = out.get(id);
        if (!e || !d || typeof d !== 'object') continue;
        if (Array.isArray(d.t)) e.t.add(v3(d.t));
        if (Array.isArray(d.r)) e.r.set(e.r.x + d.r[0] * DEG, e.r.y + d.r[1] * DEG, e.r.z + d.r[2] * DEG);
        if (d.hidden) e.hidden = true;
      }
    };
    add((this.sj.poses || {})[mode]);
    if (dockStep) {
      const s = (this.sj.dock_sequence || []).find((x) => x.step === dockStep);
      if (s) {
        const { step, title, caption, ...deltas } = s; // eslint-disable-line no-unused-vars
        add(deltas);
      }
    }
    return out;
  }

  /** Bounding box (world) of the visible, non-internal meshes of the given groups (all when null). */
  bounds(groupIds = null, { includeInternal = false, includeHidden = false } = {}) {
    const box = new THREE.Box3();
    const tmp = new THREE.Box3();
    this.root.updateMatrixWorld(true);
    for (const p of this.parts.values()) {
      if (groupIds && !groupIds.includes(p.group)) continue;
      if (p.internal && !includeInternal) continue;
      if (!includeHidden && !isShown(p.mesh)) continue;
      const g = p.mesh.geometry;
      if (!g.boundingBox) g.computeBoundingBox();
      tmp.copy(g.boundingBox).applyMatrix4(p.mesh.matrixWorld);
      box.union(tmp);
    }
    return box;
  }

  /** World boxes of the visible, non-internal parts of the given groups (tighter framing than one big box). */
  partBoxes(groupIds = null, { includeInternal = false, partIds = null } = {}) {
    const out = [];
    this.root.updateMatrixWorld(true);
    for (const p of this.parts.values()) {
      if (partIds ? !partIds.includes(p.id) : groupIds && !groupIds.includes(p.group)) continue;
      if (p.internal && !includeInternal) continue;
      if (!isShown(p.mesh)) continue;
      const g = p.mesh.geometry;
      if (!g.boundingBox) g.computeBoundingBox();
      out.push(g.boundingBox.clone().applyMatrix4(p.mesh.matrixWorld));
    }
    return out;
  }

  /** Static bounds from scene.json (stow pose). */
  sceneBounds() {
    const b = this.sj.bounds;
    return b ? new THREE.Box3(v3(b.min), v3(b.max)) : this.bounds(null, { includeHidden: true });
  }
}

function isShown(o) {
  for (let x = o; x; x = x.parent) if (!x.visible) return false;
  return true;
}
