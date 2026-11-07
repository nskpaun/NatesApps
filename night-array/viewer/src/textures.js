// Procedural canvas textures: everything the viewer paints itself instead of shipping images.
import * as THREE from 'three';
import { makeCanvas, rng, clamp } from './util.js';

function canvasTexture(canvas, { srgb = true, repeat = false, flipY = true, aniso = 4 } = {}) {
  const t = new THREE.CanvasTexture(canvas);
  t.colorSpace = srgb ? THREE.SRGBColorSpace : THREE.NoColorSpace;
  t.flipY = flipY;
  t.anisotropy = aniso;
  if (repeat) t.wrapS = t.wrapT = THREE.RepeatWrapping;
  return t;
}

/** Brushed-metal streaks along u: a subtle colour modulation map and a stronger roughness map. */
export function brushedTextures() {
  const W = 1024, H = 256;
  const mk = () => makeCanvas(W, H);
  const cMap = mk(), cRough = mk();
  const a = cMap.getContext('2d'), b = cRough.getContext('2d');
  a.fillStyle = 'rgb(236,236,236)'; a.fillRect(0, 0, W, H);
  b.fillStyle = 'rgb(214,214,214)'; b.fillRect(0, 0, W, H);
  const r = rng(7);
  for (let i = 0; i < 5200; i++) {
    const y = Math.floor(r() * H) + 0.5;
    const x = r() * W;
    const len = 30 + r() * r() * 900;
    const light = r() < 0.5;
    const alpha = 0.03 + r() * 0.1;
    for (const [ctx, k] of [[a, 1], [b, 2.2]]) {
      ctx.strokeStyle = light ? `rgba(255,255,255,${alpha * k})` : `rgba(0,0,0,${alpha * k})`;
      ctx.lineWidth = r() < 0.85 ? 1 : 2;
      ctx.beginPath();
      ctx.moveTo(x, y); ctx.lineTo(x + len, y);
      if (x + len > W) { ctx.moveTo(x - W, y); ctx.lineTo(x + len - W, y); }
      ctx.stroke();
    }
  }
  const map = canvasTexture(cMap, { srgb: false, repeat: true, aniso: 8 });
  const rough = canvasTexture(cRough, { srgb: false, repeat: true, aniso: 8 });
  return { map, rough };
}

/** Dark smoked-oak desk top: long, quiet grain with a little large-scale mottling. 3.6 m x 1.25 m. */
export function deskTextures(scale = 1) {
  const W = Math.round(2048 * scale), H = Math.round(1024 * scale);
  const c = makeCanvas(W, H), cr = makeCanvas(W, H);
  const g = c.getContext('2d'), gr = cr.getContext('2d');
  g.fillStyle = '#1b1410'; g.fillRect(0, 0, W, H);
  gr.fillStyle = 'rgb(120,120,120)'; gr.fillRect(0, 0, W, H);
  const r = rng(11);
  // large mottling
  for (let i = 0; i < 60; i++) {
    const x = r() * W, y = r() * H, rad = (80 + r() * 380) * scale;
    const grd = g.createRadialGradient(x, y, 0, x, y, rad);
    const warm = r() < 0.5;
    grd.addColorStop(0, warm ? 'rgba(60,40,26,0.18)' : 'rgba(8,6,5,0.25)');
    grd.addColorStop(1, 'rgba(0,0,0,0)');
    g.fillStyle = grd; g.fillRect(x - rad, y - rad, rad * 2, rad * 2);
  }
  // grain lines along x with gentle waves
  for (let i = 0; i < 900; i++) {
    const y0 = r() * H, amp = (2 + r() * 10) * scale, freq = 0.0015 + r() * 0.004, ph = r() * 6.28;
    const light = r() < 0.42;
    const alpha = 0.035 + r() * 0.09;
    const x0 = r() * W * 0.6 - W * 0.2, x1 = x0 + W * (0.4 + r() * 0.9);
    g.strokeStyle = light ? `rgba(92,66,46,${alpha})` : `rgba(5,3,2,${alpha * 1.3})`;
    gr.strokeStyle = light ? `rgba(90,90,90,${alpha * 1.6})` : `rgba(200,200,200,${alpha * 1.6})`;
    const lw = (0.6 + r() * 2.2) * scale;
    g.lineWidth = lw; gr.lineWidth = lw;
    for (const ctx of [g, gr]) {
      ctx.beginPath();
      for (let x = x0; x <= x1; x += 24 * scale) {
        const y = y0 + Math.sin(x * freq + ph) * amp + Math.sin(x * freq * 3.1 + ph * 2) * amp * 0.25;
        if (x === x0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      }
      ctx.stroke();
    }
  }
  // fine pores
  const img = g.getImageData(0, 0, W, H), d = img.data;
  for (let i = 0; i < d.length; i += 4) {
    const n = (r() - 0.5) * 7;
    d[i] = clamp(d[i] + n, 0, 255); d[i + 1] = clamp(d[i + 1] + n * 0.85, 0, 255); d[i + 2] = clamp(d[i + 2] + n * 0.7, 0, 255);
  }
  g.putImageData(img, 0, 0);
  return { map: canvasTexture(c, { aniso: 8 }), rough: canvasTexture(cr, { srgb: false, aniso: 8 }) };
}

/**
 * The night room around the desk, painted onto a cylinder (u = angle, u 0.5 = behind the station):
 * tall windows onto an out-of-focus city, warm sconces between them, a dark wall behind the camera.
 */
export function backdropTexture(W = 3072, H = 768) {
  const c = makeCanvas(W, H);
  const g = c.getContext('2d');
  const r = rng(23);
  // cylinder spans y in [-1.2, 3.8] m; row 0 = top
  const yToRow = (y) => ((3.8 - y) / 5.0) * H;
  const uToX = (u) => u * W;

  // base wall gradient
  const wall = g.createLinearGradient(0, 0, 0, H);
  wall.addColorStop(0, '#050404');
  wall.addColorStop(yToRow(2.2) / H, '#0d0a08');
  wall.addColorStop(yToRow(0.9) / H, '#191210');
  wall.addColorStop(yToRow(0.0) / H, '#130e0b');
  wall.addColorStop(1, '#070504');
  g.fillStyle = wall; g.fillRect(0, 0, W, H);

  // window band on the back half
  const winTop = yToRow(3.05), winBot = yToRow(0.18);
  const bays = [];
  const bayW = 1.25 / (2 * Math.PI * 6); // 1.25 m bays as a fraction of the circumference
  for (let u = 0.31; u < 0.69; u += bayW) bays.push(u);
  const sky = g.createLinearGradient(0, winTop, 0, winBot);
  sky.addColorStop(0, '#0b0d12');
  sky.addColorStop(0.45, '#141419');
  sky.addColorStop(0.72, '#231b19');
  sky.addColorStop(1, '#1b1411');
  g.save();
  g.beginPath();
  g.rect(uToX(bays[0]), winTop, uToX(bays[bays.length - 1] + bayW) - uToX(bays[0]), winBot - winTop);
  g.clip();
  g.fillStyle = sky; g.fillRect(0, winTop, W, winBot - winTop);
  // skyline: three depth layers of buildings with lit windows, then blur
  g.filter = 'blur(1.5px)';
  for (let layer = 0; layer < 3; layer++) {
    const baseY = yToRow(0.35 + layer * 0.12);
    let x = uToX(bays[0]) - 20;
    const xEnd = uToX(bays[bays.length - 1] + bayW) + 20;
    while (x < xEnd) {
      const bw = (10 + r() * 34) * (W / 3072) * (1 + layer * 0.3);
      const bh = (yToRow(0) - yToRow(0.35 + r() * (1.0 - layer * 0.2))) * (0.6 + r() * 0.8);
      const top = baseY - bh;
      const shade = [14, 11, 9][layer];
      g.fillStyle = `rgb(${shade + 2},${shade + 1},${shade + 3})`;
      g.fillRect(x, top, bw, baseY - top + 40);
      // lit windows
      const cols = Math.max(1, Math.floor(bw / 5)), rows = Math.max(1, Math.floor((baseY - top) / 6));
      for (let i = 0; i < cols; i++) for (let j = 0; j < rows; j++) {
        if (r() < 0.16 - layer * 0.03) {
          const warm = r() < 0.8;
          const a = 0.25 + r() * 0.5;
          g.fillStyle = warm ? `rgba(255,${150 + r() * 60},${70 + r() * 50},${a})` : `rgba(170,190,215,${a * 0.6})`;
          g.fillRect(x + 1.5 + i * 5, top + 2 + j * 6, 2, 2.4);
        }
      }
      x += bw + r() * 6;
    }
  }
  g.filter = 'none';
  // bokeh: soft discs, warm with a few cool ones, densest around the skyline
  g.globalCompositeOperation = 'lighter';
  for (let i = 0; i < 260; i++) {
    const u = bays[0] + r() * (bays[bays.length - 1] + bayW - bays[0]);
    const y = 0.35 + Math.pow(r(), 1.6) * 1.9;
    const x = uToX(u), row = yToRow(y);
    const rad = (3 + Math.pow(r(), 2.2) * 22) * (W / 3072);
    const warm = r() < 0.86;
    const a = 0.08 + r() * 0.3;
    const col = warm ? [255, 150 + r() * 70, 60 + r() * 60] : [150, 175, 210];
    const grd = g.createRadialGradient(x, row, 0, x, row, rad);
    grd.addColorStop(0, `rgba(${col[0]},${col[1] | 0},${col[2] | 0},${a})`);
    grd.addColorStop(0.7, `rgba(${col[0]},${col[1] | 0},${col[2] | 0},${a * 0.85})`);
    grd.addColorStop(1, 'rgba(0,0,0,0)');
    g.fillStyle = grd;
    g.beginPath(); g.arc(x, row, rad, 0, Math.PI * 2); g.fill();
  }
  g.globalCompositeOperation = 'source-over';
  g.restore();

  // mullions and transom (faint window grid), with a warm rim on one edge
  const mullW = Math.max(3, (0.07 / (2 * Math.PI * 6)) * W);
  for (const u of [...bays, bays[bays.length - 1] + bayW]) {
    const x = uToX(u);
    g.fillStyle = '#0a0807'; g.fillRect(x - mullW / 2, winTop - 6, mullW, winBot - winTop + 12);
    g.fillStyle = 'rgba(255,170,90,0.07)'; g.fillRect(x + mullW / 2 - 1.5, winTop, 1.5, winBot - winTop);
  }
  const tY = yToRow(2.35);
  g.fillStyle = '#0a0807'; g.fillRect(uToX(bays[0]), tY - mullW * 0.35, uToX(bays[bays.length - 1] + bayW) - uToX(bays[0]), mullW * 0.7);
  g.fillStyle = '#080605'; g.fillRect(uToX(bays[0]) - 4, winBot, uToX(bays[bays.length - 1] + bayW) - uToX(bays[0]) + 8, mullW * 1.2);

  // warm sconces: vertical light columns with a wall wash (two flank the windows, more around the room)
  const sconce = (u, y0, y1, k = 1) => {
    const x = uToX(u), top = yToRow(y1), bot = yToRow(y0);
    const wash = g.createRadialGradient(x, (top + bot) / 2, 0, x, (top + bot) / 2, (bot - top) * 1.1);
    wash.addColorStop(0, `rgba(255,140,60,${0.22 * k})`);
    wash.addColorStop(0.5, `rgba(200,100,40,${0.08 * k})`);
    wash.addColorStop(1, 'rgba(0,0,0,0)');
    g.globalCompositeOperation = 'lighter';
    g.fillStyle = wash; g.fillRect(x - (bot - top) * 1.1, top - (bot - top) * 0.6, (bot - top) * 2.2, (bot - top) * 2.2);
    const colW = Math.max(4, W * 0.004);
    const col = g.createLinearGradient(x - colW * 2, 0, x + colW * 2, 0);
    col.addColorStop(0, 'rgba(255,150,70,0)');
    col.addColorStop(0.5, `rgba(255,190,120,${0.85 * k})`);
    col.addColorStop(1, 'rgba(255,150,70,0)');
    g.fillStyle = col; g.fillRect(x - colW * 2, top, colW * 4, bot - top);
    g.globalCompositeOperation = 'source-over';
  };
  sconce(bays[0] - 0.012, 0.45, 2.6, 1.0);
  sconce(bays[bays.length - 1] + bayW + 0.012, 0.45, 2.6, 1.0);
  sconce(0.2, 0.7, 2.2, 0.7);
  sconce(0.8, 0.7, 2.2, 0.7);
  sconce(0.06, 0.9, 1.9, 0.45);
  sconce(0.94, 0.9, 1.9, 0.45);
  // a few far practical lights (lamps) on the side walls
  g.globalCompositeOperation = 'lighter';
  for (const [u, y, s] of [[0.17, 0.9, 1], [0.86, 1.1, 0.8], [0.02, 1.0, 0.6]]) {
    const x = uToX(u), row = yToRow(y), rad = 60 * (W / 3072) * s;
    const grd = g.createRadialGradient(x, row, 0, x, row, rad);
    grd.addColorStop(0, 'rgba(255,190,120,0.35)');
    grd.addColorStop(0.3, 'rgba(255,140,60,0.12)');
    grd.addColorStop(1, 'rgba(0,0,0,0)');
    g.fillStyle = grd; g.fillRect(x - rad, row - rad, rad * 2, rad * 2);
  }
  g.globalCompositeOperation = 'source-over';
  // ceiling falloff and floor
  const ceil = g.createLinearGradient(0, 0, 0, yToRow(2.6));
  ceil.addColorStop(0, 'rgba(3,2,2,0.95)');
  ceil.addColorStop(1, 'rgba(3,2,2,0)');
  g.fillStyle = ceil; g.fillRect(0, 0, W, yToRow(2.6));
  const floor = g.createLinearGradient(0, yToRow(0.1), 0, H);
  floor.addColorStop(0, 'rgba(6,4,3,0)');
  floor.addColorStop(0.4, 'rgba(6,4,3,0.85)');
  floor.addColorStop(1, 'rgba(4,3,2,1)');
  g.fillStyle = floor; g.fillRect(0, yToRow(0.1), W, H - yToRow(0.1));
  // overall softness: everything back here is out of focus
  const soft = makeCanvas(W, H);
  const sg = soft.getContext('2d');
  sg.filter = `blur(${Math.max(1, W / 1500).toFixed(1)}px)`;
  sg.drawImage(c, 0, 0);
  // dithering against banding
  const img = sg.getImageData(0, 0, W, H), d = img.data;
  for (let i = 0; i < d.length; i += 4) {
    const n = (r() - 0.5) * 3;
    d[i] = clamp(d[i] + n, 0, 255); d[i + 1] = clamp(d[i + 1] + n, 0, 255); d[i + 2] = clamp(d[i + 2] + n, 0, 255);
  }
  sg.putImageData(img, 0, 0);
  const t = canvasTexture(soft, { aniso: 4 });
  t.wrapS = THREE.RepeatWrapping;
  return t;
}

/** Soft elliptical light pool (white; tinted by the material colour). */
export function poolTexture() {
  const W = 256, H = 256;
  const c = makeCanvas(W, H), g = c.getContext('2d');
  const grd = g.createRadialGradient(W / 2, H / 2, 0, W / 2, H / 2, W / 2);
  const stops = [[0, 1], [0.12, 0.82], [0.3, 0.45], [0.5, 0.2], [0.7, 0.07], [0.88, 0.015], [1, 0]];
  for (const [p, a] of stops) grd.addColorStop(p, `rgba(255,255,255,${a})`);
  g.fillStyle = grd; g.fillRect(0, 0, W, H);
  return canvasTexture(c, { srgb: false });
}

/** 45-degree hatch for section caps. */
export function hatchTexture(bg, line) {
  const S = 128;
  const c = makeCanvas(S, S), g = c.getContext('2d');
  g.fillStyle = bg; g.fillRect(0, 0, S, S);
  g.strokeStyle = line; g.lineWidth = 6;
  for (let k = -S; k <= S * 2; k += 32) {
    g.beginPath(); g.moveTo(k, 0); g.lineTo(k - S, S); g.stroke();
  }
  return canvasTexture(c, { repeat: true, aniso: 4 });
}

/** FR-4 board: dark green solder mask, copper traces and pads (box-projected, 0.12 m per tile). */
export function pcbTexture() {
  const S = 512;
  const c = makeCanvas(S, S), g = c.getContext('2d');
  g.fillStyle = '#16241c'; g.fillRect(0, 0, S, S);
  const r = rng(5);
  g.lineCap = 'round';
  for (let i = 0; i < 140; i++) {
    let x = r() * S, y = r() * S;
    g.strokeStyle = `rgba(170,140,70,${0.18 + r() * 0.25})`;
    g.lineWidth = 1 + r() * 2.5;
    g.beginPath(); g.moveTo(x, y);
    for (let k = 0; k < 4; k++) {
      const len = 20 + r() * 90;
      const dir = Math.floor(r() * 4);
      if (dir === 0) x += len; else if (dir === 1) x -= len; else if (dir === 2) y += len; else { x += len * 0.7; y += len * 0.7; }
      g.lineTo(x, y);
    }
    g.stroke();
  }
  for (let i = 0; i < 70; i++) {
    const x = r() * S, y = r() * S, w = 6 + r() * 34, h = 4 + r() * 22;
    g.fillStyle = r() < 0.7 ? '#0b0c0d' : '#2a2620';
    g.fillRect(x, y, w, h);
    g.fillStyle = 'rgba(200,170,90,0.6)';
    for (let k = 0; k < w / 4; k++) { g.fillRect(x + k * 4, y - 2, 2, 2); g.fillRect(x + k * 4, y + h, 2, 2); }
  }
  return canvasTexture(c, { repeat: true, aniso: 4 });
}

/** Screen-space background gradients for the cad / xray / blueprint styles. */
export function backgroundTexture(kind) {
  const W = 512, H = 512;
  const c = makeCanvas(W, H), g = c.getContext('2d');
  if (kind === 'cad') {
    const v = g.createLinearGradient(0, 0, 0, H);
    v.addColorStop(0, '#F4F5F6'); v.addColorStop(0.6, '#E6E8EA'); v.addColorStop(1, '#D3D6DA');
    g.fillStyle = v; g.fillRect(0, 0, W, H);
  } else if (kind === 'xray') {
    g.fillStyle = '#0B0A09'; g.fillRect(0, 0, W, H);
    const rad = g.createRadialGradient(W * 0.5, H * 0.45, 0, W * 0.5, H * 0.45, W * 0.75);
    rad.addColorStop(0, '#221D19'); rad.addColorStop(0.55, '#14110F'); rad.addColorStop(1, '#090807');
    g.fillStyle = rad; g.fillRect(0, 0, W, H);
  } else {
    g.fillStyle = '#071223'; g.fillRect(0, 0, W, H);
    const rad = g.createRadialGradient(W * 0.5, H * 0.42, 0, W * 0.5, H * 0.42, W * 0.8);
    rad.addColorStop(0, '#12294A'); rad.addColorStop(0.6, '#0B1B33'); rad.addColorStop(1, '#060F1D');
    g.fillStyle = rad; g.fillRect(0, 0, W, H);
  }
  // dither
  const img = g.getImageData(0, 0, W, H), d = img.data, r = rng(3);
  for (let i = 0; i < d.length; i += 4) {
    const n = (r() - 0.5) * 3;
    d[i] = clamp(d[i] + n, 0, 255); d[i + 1] = clamp(d[i + 1] + n, 0, 255); d[i + 2] = clamp(d[i + 2] + n, 0, 255);
  }
  g.putImageData(img, 0, 0);
  return canvasTexture(c, { aniso: 1 });
}

/** Fine fibre noise for felt. */
export function feltTexture() {
  const S = 256;
  const c = makeCanvas(S, S), g = c.getContext('2d');
  const img = g.createImageData(S, S), d = img.data, r = rng(9);
  for (let i = 0; i < d.length; i += 4) {
    const n = 222 + (r() - 0.5) * 50;
    d[i] = d[i + 1] = d[i + 2] = n; d[i + 3] = 255;
  }
  g.putImageData(img, 0, 0);
  g.globalAlpha = 0.08;
  for (let i = 0; i < 900; i++) {
    g.strokeStyle = r() < 0.5 ? '#fff' : '#000';
    const x = r() * S, y = r() * S, a = r() * Math.PI;
    g.beginPath(); g.moveTo(x, y); g.lineTo(x + Math.cos(a) * 6, y + Math.sin(a) * 6); g.stroke();
  }
  return canvasTexture(c, { srgb: false, repeat: true, aniso: 4 });
}
