// The studio "night" set around the station: a warm room with an out-of-focus city behind tall windows,
// a dark smoked-oak desk with soft contact shadows and a blurred reflection, a PMREM environment built
// from the same room, a soft key light with shadows, and the amber practicals (bounce lights + light pools).
import * as THREE from 'three';
import { HorizontalBlurShader } from 'three/examples/jsm/shaders/HorizontalBlurShader.js';
import { VerticalBlurShader } from 'three/examples/jsm/shaders/VerticalBlurShader.js';
import { backdropTexture, deskTextures, poolTexture } from './textures.js';

export const BG = new THREE.Color('#0C0A09');
const AMBER = new THREE.Color('#F2A04A');

const DESK = { w: 7.0, d: 4.0, t: 0.045, z: -1.05 }; // desk top at y = 0; front edge at z = DESK.z + DESK.d / 2
const ROOM_R = 6;
const ROOM_Y = [-1.2, 3.8];

/** Backdrop cylinder (room walls) with the painted night room; u = 0.5 is behind the station. */
function makeRoom(tex, boost = 1) {
  const h = ROOM_Y[1] - ROOM_Y[0];
  const g = new THREE.CylinderGeometry(ROOM_R, ROOM_R, h, 96, 1, true);
  const m = new THREE.MeshBasicMaterial({ map: tex, side: THREE.BackSide, depthWrite: false, fog: false });
  m.color.setScalar(boost);
  const mesh = new THREE.Mesh(g, m);
  mesh.position.y = (ROOM_Y[0] + ROOM_Y[1]) / 2;
  mesh.renderOrder = -10;
  mesh.name = 'room';
  return mesh;
}

/**
 * Environment for PMREM: the same room plus a few soft boxes (warm overhead, dim front card, amber sconce
 * strips) so metals pick up long soft highlights like the concept board's, all seen from ~station height.
 */
function makeEnvScene(roomTex) {
  const s = new THREE.Scene();
  s.background = BG.clone().multiplyScalar(0.6);
  const off = -0.28; // probe sits 0.28 m above the desk
  const room = makeRoom(roomTex, 2.2);
  room.position.y += off;
  s.add(room);
  const card = (w, h, color, k, pos, look) => {
    const m = new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshBasicMaterial({ color: new THREE.Color(color).multiplyScalar(k), side: THREE.DoubleSide }));
    m.position.set(pos[0], pos[1] + off, pos[2]);
    m.lookAt(look[0], look[1] + off, look[2]);
    s.add(m);
    return m;
  };
  // desk underneath (dark wood) and a dark ceiling
  const desk = new THREE.Mesh(new THREE.PlaneGeometry(14, 14), new THREE.MeshBasicMaterial({ color: new THREE.Color('#1a120d').multiplyScalar(0.9) }));
  desk.rotation.x = -Math.PI / 2;
  desk.position.y = off - 0.002;
  s.add(desk);
  card(3.6, 1.8, '#FFF0E2', 3.2, [0.2, 2.4, 0.5], [0.2, 0, 0.3]); // big soft overhead
  card(5.0, 1.6, '#FFE9D4', 1.25, [0, 1.3, 3.4], [0, 0.4, 0]); // large front softbox (behind the camera)
  card(5.0, 0.35, '#FFE2C4', 2.2, [0, 0.35, 3.0], [0, 0.2, 0]); // low strip -> long highlight on front edges
  card(0.35, 2.2, '#FF9A48', 2.2, [-3.2, 1.2, 0.8], [0, 0.6, 0]); // amber sconce left
  card(0.35, 2.2, '#FF9A48', 2.2, [3.2, 1.2, 0.8], [0, 0.6, 0]); // amber sconce right
  card(1.2, 1.6, '#FFE4CC', 0.9, [-2.6, 0.7, 1.2], [0, 0.4, 0]); // soft side cards: side faces of metal parts
  card(1.2, 1.6, '#FFE4CC', 0.9, [2.6, 0.7, 1.2], [0, 0.4, 0]);
  card(1.6, 0.6, '#FFC890', 1.4, [-1.6, 1.4, -2.6], [0, 0.4, 0]); // warm back-left kicker (rim on the top edges)
  card(1.6, 0.6, '#FFC890', 1.1, [1.8, 1.3, -2.6], [0, 0.4, 0]);
  return s;
}

/** Soft contact shadow on the desk (render-from-below + blur), re-rendered only when the layout changes. */
class ContactShadow {
  constructor({ width, depth, cx, cz, y = 0.0035, height = 0.32, res = 512, blur = 2.2, darkness = 1.35, opacity = 0.92 }) {
    this.w = width;
    this.d = depth;
    this.res = res;
    this.blur = blur;
    const rh = Math.round((res * depth) / width);
    const opts = { type: THREE.UnsignedByteType };
    this.rt = new THREE.WebGLRenderTarget(res, rh, opts);
    this.rt.texture.generateMipmaps = false;
    this.rtBlur = new THREE.WebGLRenderTarget(res, rh, opts);
    this.rtBlur.texture.generateMipmaps = false;
    this.group = new THREE.Group();
    this.group.position.set(cx, y, cz);
    const planeGeo = new THREE.PlaneGeometry(width, depth).rotateX(Math.PI / 2);
    this.plane = new THREE.Mesh(planeGeo, new THREE.MeshBasicMaterial({
      map: this.rt.texture, transparent: true, opacity, depthWrite: false, fog: false, toneMapped: false,
    }));
    this.plane.renderOrder = 1;
    this.plane.scale.y = -1;
    this.plane.name = 'contact-shadow';
    this.group.add(this.plane);
    this.blurPlane = new THREE.Mesh(planeGeo);
    this.blurPlane.visible = false;
    this.group.add(this.blurPlane);
    this.cam = new THREE.OrthographicCamera(-width / 2, width / 2, depth / 2, -depth / 2, 0, height);
    this.cam.rotation.x = Math.PI / 2;
    this.group.add(this.cam);
    this.depthMat = new THREE.MeshDepthMaterial();
    this.depthMat.userData.darkness = { value: darkness };
    this.depthMat.onBeforeCompile = (shader) => {
      shader.uniforms.darkness = this.depthMat.userData.darkness;
      shader.fragmentShader = 'uniform float darkness;\n' + shader.fragmentShader.replace(
        'gl_FragColor = vec4( vec3( 1.0 - fragCoordZ ), opacity );',
        'gl_FragColor = vec4( vec3( 0.0 ), pow( 1.0 - fragCoordZ, 1.6 ) * darkness );',
      );
    };
    this.depthMat.depthTest = false;
    this.depthMat.depthWrite = false;
    this.hBlur = new THREE.ShaderMaterial(HorizontalBlurShader);
    this.hBlur.depthTest = false;
    this.vBlur = new THREE.ShaderMaterial(VerticalBlurShader);
    this.vBlur.depthTest = false;
    this.scene = new THREE.Scene();
    this.scene.overrideMaterial = this.depthMat;
    this.dirty = true;
  }

  blurPass(renderer, amount) {
    this.blurPlane.visible = true;
    this.blurPlane.material = this.hBlur;
    this.hBlur.uniforms.tDiffuse.value = this.rt.texture;
    this.hBlur.uniforms.h.value = amount / 256;
    renderer.setRenderTarget(this.rtBlur);
    renderer.render(this.blurPlane, this.cam);
    this.blurPlane.material = this.vBlur;
    this.vBlur.uniforms.tDiffuse.value = this.rtBlur.texture;
    this.vBlur.uniforms.v.value = amount / 256;
    renderer.setRenderTarget(this.rt);
    renderer.render(this.blurPlane, this.cam);
    this.blurPlane.visible = false;
  }

  /** Renders the station (minus `exclude`d objects) from below into the shadow texture. */
  update(renderer, stationRoot, exclude = []) {
    const parent = stationRoot.parent;
    const hidden = [];
    for (const o of exclude) if (o.visible) { o.visible = false; hidden.push(o); }
    const prevTarget = renderer.getRenderTarget();
    const prevClear = renderer.getClearAlpha();
    const prevColor = renderer.getClearColor(new THREE.Color());
    const prevShadow = renderer.shadowMap.enabled;
    this.scene.add(stationRoot);
    this.scene.updateMatrixWorld(true);
    this.group.updateMatrixWorld(true);
    renderer.shadowMap.enabled = false;
    renderer.setClearColor(0x000000, 0);
    renderer.setRenderTarget(this.rt);
    renderer.clear();
    renderer.render(this.scene, this.cam);
    if (parent) parent.add(stationRoot);
    this.blurPass(renderer, this.blur);
    this.blurPass(renderer, this.blur * 0.45);
    renderer.setRenderTarget(prevTarget);
    renderer.setClearColor(prevColor, prevClear);
    renderer.shadowMap.enabled = prevShadow;
    for (const o of hidden) o.visible = true;
    this.dirty = false;
  }

  dispose() {
    this.rt.dispose();
    this.rtBlur.dispose();
  }
}

/** Planar mirror of the station into a small mip-mapped target; the desk shader adds it, blurred. */
class DeskReflection {
  constructor() {
    this.rt = null;
    this.scale = 0.5;
    this.matrix = new THREE.Matrix4();
    this.cam = new THREE.PerspectiveCamera();
    this.uniforms = {
      uReflectMap: { value: null },
      uReflectMatrix: { value: this.matrix },
      uReflectStrength: { value: 0 },
      uReflectTexel: { value: new THREE.Vector2(1 / 512, 1 / 512) },
    };
    this._v = new THREE.Vector3();
    this._t = new THREE.Vector3();
    this._r = new THREE.Matrix4();
    this._plane = new THREE.Plane();
    this._clip = new THREE.Vector4();
    this._q = new THREE.Vector4();
  }

  setSize(w, h, scale) {
    this.scale = scale;
    if (scale <= 0) {
      if (this.rt) { this.rt.dispose(); this.rt = null; }
      this.uniforms.uReflectMap.value = null;
      return;
    }
    const rw = Math.max(64, Math.round(w * scale)), rh = Math.max(64, Math.round(h * scale));
    if (!this.rt) {
      this.rt = new THREE.WebGLRenderTarget(rw, rh, {
        type: THREE.HalfFloatType, generateMipmaps: true, minFilter: THREE.LinearMipmapLinearFilter, magFilter: THREE.LinearFilter,
      });
    } else this.rt.setSize(rw, rh);
    this.uniforms.uReflectMap.value = this.rt.texture;
    this.uniforms.uReflectTexel.value.set(1 / rw, 1 / rh);
  }

  /** Port of three's Reflector camera maths for the desk plane y = 0 (normal +Y). */
  render(renderer, scene, camera, hide) {
    if (!this.rt) return;
    const normal = this._v.set(0, 1, 0);
    const camPos = new THREE.Vector3().setFromMatrixPosition(camera.matrixWorld);
    if (camPos.y <= 0.001) return;
    const view = camPos.clone().reflect(normal).negate(); // mirror of the camera position: (x, -y, z)
    view.set(camPos.x, -camPos.y, camPos.z);
    this._r.extractRotation(camera.matrixWorld);
    const look = new THREE.Vector3(0, 0, -1).applyMatrix4(this._r).add(camPos);
    const target = new THREE.Vector3(look.x, -look.y, look.z);
    const vc = this.cam;
    vc.position.copy(view);
    vc.up.set(0, 1, 0).applyMatrix4(this._r);
    vc.up.y = -vc.up.y;
    vc.lookAt(target);
    vc.far = camera.far;
    vc.updateMatrixWorld();
    vc.projectionMatrix.copy(camera.projectionMatrix);
    this.matrix.set(0.5, 0, 0, 0.5, 0, 0.5, 0, 0.5, 0, 0, 0.5, 0.5, 0, 0, 0, 1);
    this.matrix.multiply(vc.projectionMatrix).multiply(vc.matrixWorldInverse);
    // oblique near plane = the desk, so nothing under the desk leaks into the mirror
    this._plane.setFromNormalAndCoplanarPoint(normal, new THREE.Vector3(0, 0, 0)).applyMatrix4(vc.matrixWorldInverse);
    const clip = this._clip.set(this._plane.normal.x, this._plane.normal.y, this._plane.normal.z, this._plane.constant);
    const p = vc.projectionMatrix.elements;
    const q = this._q;
    q.x = (Math.sign(clip.x) + p[8]) / p[0];
    q.y = (Math.sign(clip.y) + p[9]) / p[5];
    q.z = -1.0;
    q.w = (1.0 + p[10]) / p[14];
    clip.multiplyScalar(2.0 / clip.dot(q));
    p[2] = clip.x; p[6] = clip.y; p[10] = clip.z + 1.0 - 0.003; p[14] = clip.w;

    const hidden = [];
    for (const o of hide) if (o.visible) { o.visible = false; hidden.push(o); }
    const prev = renderer.getRenderTarget();
    const prevAuto = renderer.shadowMap.autoUpdate;
    renderer.shadowMap.autoUpdate = false;
    renderer.setRenderTarget(this.rt);
    renderer.clear();
    renderer.render(scene, vc);
    renderer.setRenderTarget(prev);
    renderer.shadowMap.autoUpdate = prevAuto;
    for (const o of hidden) o.visible = true;
  }

  dispose() {
    if (this.rt) this.rt.dispose();
  }
}

function deskMaterial(maps, reflection) {
  const m = new THREE.MeshPhysicalMaterial({
    name: 'desk', map: maps.map, roughnessMap: maps.rough, roughness: 0.7, metalness: 0,
    clearcoat: 0.12, clearcoatRoughness: 0.36, color: new THREE.Color(1, 1, 1), envMapIntensity: 0.3, specularIntensity: 0.4,
  });
  m.onBeforeCompile = (shader) => {
    Object.assign(shader.uniforms, reflection.uniforms);
    shader.vertexShader = 'uniform mat4 uReflectMatrix;\nvarying vec4 vReflectUv;\nvarying vec2 vDeskXZ;\n' + shader.vertexShader.replace(
      '#include <fog_vertex>',
      '#include <fog_vertex>\n\tvec4 deskWorld = modelMatrix * vec4( transformed, 1.0 );\n\tvReflectUv = uReflectMatrix * deskWorld;\n\tvDeskXZ = deskWorld.xz;',
    );
    shader.fragmentShader = 'uniform sampler2D uReflectMap;\nuniform float uReflectStrength;\nuniform vec2 uReflectTexel;\nvarying vec4 vReflectUv;\nvarying vec2 vDeskXZ;\n' +
      shader.fragmentShader.replace('#include <opaque_fragment>', `
	if ( uReflectStrength > 0.0 ) {
		vec2 ruv = vReflectUv.xy / vReflectUv.w;
		// grain-driven wobble so the mirror reads as lacquered wood, not glass
		ruv.x += ( roughnessFactor - 0.6 ) * 0.004;
		vec3 rc = vec3( 0.0 );
		vec2 o = uReflectTexel * 2.5;
		rc += texture( uReflectMap, ruv, 1.5 ).rgb * 0.28;
		rc += texture( uReflectMap, ruv + vec2( o.x, 0.0 ), 1.5 ).rgb * 0.18;
		rc += texture( uReflectMap, ruv - vec2( o.x, 0.0 ), 1.5 ).rgb * 0.18;
		rc += texture( uReflectMap, ruv + vec2( 0.0, o.y * 1.6 ), 1.5 ).rgb * 0.18;
		rc += texture( uReflectMap, ruv - vec2( 0.0, o.y * 1.6 ), 1.5 ).rgb * 0.18;
		float ndv = clamp( dot( normal, normalize( vViewPosition ) ), 0.0, 1.0 );
		float fres = 0.05 + 0.95 * pow( 1.0 - ndv, 4.0 );
		outgoingLight += rc * uReflectStrength * fres;
	}
	// the desk falls off into the night away from the station (a pool of light, not a lit table top)
	float deskFall = smoothstep( 2.3, 0.75, length( ( vDeskXZ - vec2( 0.07, 0.05 ) ) * vec2( 0.72, 1.0 ) ) );
	outgoingLight *= mix( 0.12, 1.0, deskFall );
	#include <opaque_fragment>`);
  };
  m.customProgramCacheKey = () => 'desk-reflect';
  return m;
}

export class Stage {
  constructor(renderer, opts = {}) {
    this.renderer = renderer;
    this.group = new THREE.Group();
    this.group.name = 'stage';
    const roomTex = backdropTexture(opts.lowMem ? 1536 : 2048, opts.lowMem ? 384 : 512, ROOM_R);
    roomTex.repeat.x = -1; // seen from inside the cylinder
    roomTex.wrapS = THREE.RepeatWrapping;
    this.roomTex = roomTex;
    this.room = makeRoom(roomTex, 1.0);
    this.group.add(this.room);

    // desk
    const maps = deskTextures(opts.lowMem ? 0.5 : 1);
    this.reflection = new DeskReflection();
    this.desk = new THREE.Mesh(new THREE.BoxGeometry(DESK.w, DESK.t, DESK.d), deskMaterial(maps, this.reflection));
    this.desk.position.set(0.05, -DESK.t / 2, DESK.z);
    this.desk.receiveShadow = true;
    this.desk.name = 'desk';
    this.group.add(this.desk);
    // floor far below the desk, so looking past the desk edge finds a dark floor rather than the wall
    const floor = new THREE.Mesh(new THREE.CircleGeometry(ROOM_R, 48).rotateX(-Math.PI / 2),
      new THREE.MeshBasicMaterial({ color: '#060404' }));
    floor.position.y = -0.74;
    floor.name = 'floor';
    this.group.add(floor);

    // contact shadow under the station (covers the work-mode desk mat too)
    this.contact = new ContactShadow({ width: 2.0, depth: 1.25, cx: 0.07, cz: 0.13, res: opts.lowMem ? 256 : 512 });
    this.group.add(this.contact.group);

    // lights: the key is a big soft spot, so the desk falls off into the night around the station
    this.key = new THREE.SpotLight('#FFEEDD', 1.0, 0, 34 * Math.PI / 180, 0.75, 0);
    this.key.position.set(1.25, 2.6, 1.75);
    this.key.target.position.set(0.06, 0.05, 0.05);
    this.key.castShadow = true;
    this.key.shadow.camera.near = 1.5;
    this.key.shadow.camera.far = 5.5;
    this.key.shadow.bias = -0.0003;
    this.key.shadow.normalBias = 0.01;
    this.key.shadow.radius = 4;
    this.key.shadow.mapSize.set(2048, 2048);
    this.keyBase = 2.0;
    this.key.intensity = this.keyBase;
    this.group.add(this.key, this.key.target);

    this.rim = new THREE.DirectionalLight('#FFB57E', 1.4);
    this.rim.position.set(-1.6, 1.4, -2.2);
    this.group.add(this.rim);
    this.fill = new THREE.HemisphereLight('#6b5444', '#0c0908', 0.35);
    this.group.add(this.fill);

    // amber practicals: bounce lights (no shadows) and soft light pools on the surfaces they hit
    this.amberLights = [];
    this.pools = [];
    this.poolTex = poolTexture();

    this.envScene = makeEnvScene(roomTex);
    this.pmrem = new THREE.PMREMGenerator(renderer);
    this.envMap = null;
    this.reflectStrength = 0.5;
  }

  /** Pools / bounce lights that sit in world space (base glow, neck light, dock latch). Called once the model is known. */
  addPractical({ pos, size, light = 0, distance = 0.5, parent = null, poolK = 1, rot = 0, world = false }) {
    const host = parent || this.group;
    if (world && parent) {
      parent.updateMatrixWorld(true);
      const v = parent.worldToLocal(new THREE.Vector3(pos[0], pos[1], pos[2]));
      pos = [v.x, v.y, v.z];
    }
    if (size) {
      const m = new THREE.Mesh(new THREE.PlaneGeometry(1, 1).rotateX(-Math.PI / 2), new THREE.MeshBasicMaterial({
        map: this.poolTex, color: AMBER.clone(), transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, fog: false,
        polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2,
      }));
      m.scale.set(size[0], 1, size[1]);
      m.rotation.y = rot;
      m.position.set(pos[0], pos[1], pos[2]);
      m.renderOrder = 2;
      m.userData.k = poolK;
      host.add(m);
      this.pools.push(m);
    }
    if (light > 0) {
      const l = new THREE.PointLight(AMBER.clone(), light, distance, 2);
      l.position.set(pos[0], pos[1] + (size ? 0.02 : 0), pos[2]);
      l.userData.k = light;
      host.add(l);
      this.amberLights.push(l);
    }
  }

  /** Pools belong to an assembled station: they fade out as it explodes. */
  setExplodeFade(explode) {
    this.poolFade = Math.max(0, 1 - explode * 2.5);
    this.setAmber(this.amber ?? 1);
  }

  setAmber(a) {
    this.amber = a;
    const fade = this.poolFade ?? 1;
    const k = a <= 0.001 ? 0 : 0.15 + 0.85 * a;
    for (const l of this.amberLights) { l.intensity = l.userData.k * k; l.visible = k > 0; }
    for (const p of this.pools) {
      const f = fade;
      p.material.color.copy(AMBER).multiplyScalar(p.userData.k * k * f);
      p.visible = k * f > 0;
    }
  }

  buildEnvironment() {
    if (this.envMap) this.envMap.dispose();
    const rt = this.pmrem.fromScene(this.envScene, 0.035, 0.05, 30);
    this.envMap = rt;
    return rt.texture;
  }

  setQuality(q, w, h) {
    this.key.shadow.mapSize.set(q.shadow, q.shadow);
    if (this.key.shadow.map) { this.key.shadow.map.dispose(); this.key.shadow.map = null; }
    this.reflection.setSize(w, h, q.reflect);
    this.reflection.uniforms.uReflectStrength.value = q.reflect > 0 ? this.reflectStrength : 0;
  }

  resize(w, h) {
    if (this.reflection.scale > 0) this.reflection.setSize(w, h, this.reflection.scale);
  }

  /** Per-frame passes that must run before the main render. */
  prerender(scene, camera, stationRoot, contactExclude) {
    if (this.contact.dirty) this.contact.update(this.renderer, stationRoot, contactExclude);
    if (this.reflection.rt && this.reflection.uniforms.uReflectStrength.value > 0) {
      this.reflection.render(this.renderer, scene, camera, [this.desk, this.contact.plane, ...this.pools, this.room]);
    }
  }

  dispose() {
    this.contact.dispose();
    this.reflection.dispose();
    this.pmrem.dispose();
    if (this.envMap) this.envMap.dispose();
  }
}
