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

/**
 * Brushed-metal streaks along u: per-row noise that drifts slowly along the row, at low contrast so it
 * averages out when minified (no moire bands) and reads as fine brushing up close. Mean values are
 * 236 (colour) and 214 (roughness), see materials.js.
 */
export function brushedTextures() {
  const W = 512, H = 256;
  const cMap = makeCanvas(W, H), cRough = makeCanvas(W, H);
  const a = cMap.getContext('2d'), b = cRough.getContext('2d');
  const ia = a.createImageData(W, H), ib = b.createImageData(W, H);
  const r = rng(7);
  const KN = 8; // knots per row for the slow drift along u
  for (let y = 0; y < H; y++) {
    const row = (r() - 0.5) * 2;
    const knots = [];
    for (let k = 0; k <= KN; k++) knots.push((r() - 0.5) * 2);
    knots[KN] = knots[0]; // tile seamlessly along u
    const scratch = r() < 0.08 ? (r() - 0.5) * 2 : 0;
    for (let x = 0; x < W; x++) {
      const f = (x / W) * KN, k = Math.floor(f), t = f - k;
      const s = t * t * (3 - 2 * t);
      const drift = knots[k] * (1 - s) + knots[k + 1] * s;
      const n = row * 0.6 + drift * 0.4 + scratch;
      const i = (y * W + x) * 4;
      const cv = 236 + n * 6, rv = 214 + n * 16;
      ia.data[i] = ia.data[i + 1] = ia.data[i + 2] = cv; ia.data[i + 3] = 255;
      ib.data[i] = ib.data[i + 1] = ib.data[i + 2] = rv; ib.data[i + 3] = 255;
    }
  }
  a.putImageData(ia, 0, 0);
  b.putImageData(ib, 0, 0);
  const map = canvasTexture(cMap, { srgb: false, repeat: true, aniso: 8 });
  const rough = canvasTexture(cRough, { srgb: false, repeat: true, aniso: 8 });
  return { map, rough };
}

/**
 * A small tile of grey noise (mid-grey +- amp). Drawn with 'overlay' it dithers dark gradients against banding
 * without a full-size getImageData pass (which is slow on phones and in software canvas).
 */
export function noiseTile(size = 128, amp = 24, seed = 3) {
  const c = makeCanvas(size, size), g = c.getContext('2d');
  const img = g.createImageData(size, size), d = img.data, r = rng(seed);
  for (let i = 0; i < d.length; i += 4) {
    const n = 128 + (r() - 0.5) * 2 * amp;
    d[i] = d[i + 1] = d[i + 2] = n; d[i + 3] = 255;
  }
  g.putImageData(img, 0, 0);
  return c;
}

export function ditherOverlay(g, W, H, alpha = 1, tile = null) {
  g.save();
  g.globalCompositeOperation = 'overlay';
  g.globalAlpha = alpha;
  g.fillStyle = g.createPattern(tile || noiseTile(), 'repeat');
  g.fillRect(0, 0, W, H);
  g.restore();
}

/** Dark smoked-oak desk top: quiet long grain, three wide boards, a little mottling. Covers 4.2 m x 2.0 m. */
export function deskTextures(scale = 1) {
  const W = Math.round(2048 * scale), H = Math.round(1024 * scale);
  const c = makeCanvas(W, H), cr = makeCanvas(W, H);
  const g = c.getContext('2d'), gr = cr.getContext('2d');
  g.fillStyle = '#18110d'; g.fillRect(0, 0, W, H);
  gr.fillStyle = 'rgb(150,150,150)'; gr.fillRect(0, 0, W, H);
  const r = rng(11);
  // boards run along x (the desk's long side); each gets its own tone
  const boards = 5;
  for (let i = 0; i < boards; i++) {
    const y0 = (i / boards) * H, h = H / boards;
    const k = r();
    g.fillStyle = `rgba(${k < 0.5 ? '48,32,22' : '6,4,3'},${0.18 + r() * 0.2})`;
    g.fillRect(0, y0, W, h);
    g.fillStyle = 'rgba(0,0,0,0.55)';
    g.fillRect(0, y0, W, Math.max(1, 1.2 * scale));
    gr.fillStyle = 'rgba(255,255,255,0.4)';
    gr.fillRect(0, y0, W, Math.max(1, 1.2 * scale));
  }
  // large soft mottling
  for (let i = 0; i < 46; i++) {
    const x = r() * W, y = r() * H, rad = (90 + r() * 360) * scale;
    const grd = g.createRadialGradient(x, y, 0, x, y, rad);
    grd.addColorStop(0, r() < 0.5 ? 'rgba(62,42,28,0.16)' : 'rgba(5,3,2,0.22)');
    grd.addColorStop(1, 'rgba(0,0,0,0)');
    g.fillStyle = grd; g.fillRect(x - rad, y - rad, rad * 2, rad * 2);
  }
  // grain: long gently waving lines
  const seg = 48 * scale;
  for (let i = 0; i < 380; i++) {
    const y0 = r() * H, amp = (1.5 + r() * 7) * scale, freq = (0.0012 + r() * 0.003) / scale, ph = r() * 6.28;
    const light = r() < 0.4;
    const alpha = 0.03 + r() * 0.07;
    const x0 = r() * W * 0.7 - W * 0.2, x1 = x0 + W * (0.35 + r() * 0.9);
    g.strokeStyle = light ? `rgba(98,70,48,${alpha})` : `rgba(4,2,1,${alpha * 1.4})`;
    gr.strokeStyle = light ? `rgba(70,70,70,${alpha * 1.8})` : `rgba(215,215,215,${alpha * 1.8})`;
    const lw = (0.7 + r() * 2.4) * scale;
    g.lineWidth = lw; gr.lineWidth = lw;
    for (const ctx of [g, gr]) {
      ctx.beginPath();
      for (let x = x0; x <= x1; x += seg) {
        const y = y0 + Math.sin(x * freq + ph) * amp + Math.sin(x * freq * 3.1 + ph * 2) * amp * 0.25;
        if (x === x0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      }
      ctx.stroke();
    }
  }
  ditherOverlay(g, W, H, 0.5, noiseTile(128, 40, 12));
  ditherOverlay(gr, W, H, 0.6, noiseTile(128, 50, 13));
  return { map: canvasTexture(c, { aniso: 8 }), rough: canvasTexture(cr, { srgb: false, aniso: 8 }) };
}

/**
 * The night room around the desk, painted onto a cylinder (u = angle, u 0.5 = behind the station):
 * tall windows onto an out-of-focus city, warm sconces between them, a dark wall behind the camera.
 * Everything here is out of focus, so it is painted at half resolution and upscaled (a free blur);
 * no canvas filters and no per-pixel passes, which are very slow in software canvas.
 */
export function backdropTexture(W = 2048, H = 512, R = 6) {
  const w = W >> 1, h = H >> 1;
  const c = makeCanvas(w, h);
  const g = c.getContext('2d');
  const r = rng(23);
  // cylinder spans y in [-1.2, 3.8] m; row 0 = top
  const yToRow = (y) => ((3.8 - y) / 5.0) * h;
  const uToX = (u) => u * w;
  const metre = w / (2 * Math.PI * R); // px per metre along the wall

  const wall = g.createLinearGradient(0, 0, 0, h);
  wall.addColorStop(0, '#040303');
  wall.addColorStop(yToRow(2.4) / h, '#0a0706');
  wall.addColorStop(yToRow(1.1) / h, '#16100c');
  wall.addColorStop(yToRow(0.2) / h, '#120c0a');
  wall.addColorStop(1, '#050403');
  g.fillStyle = wall; g.fillRect(0, 0, w, h);

  // window band behind the station: 1.4 m bays
  const bayW = 1.4 / (2 * Math.PI * R);
  const u0 = 0.5 - bayW * 4.5, u1 = 0.5 + bayW * 4.5;
  const winTop = yToRow(3.05), winBot = yToRow(0.12);
  g.save();
  g.beginPath(); g.rect(uToX(u0), winTop, uToX(u1) - uToX(u0), winBot - winTop); g.clip();
  const sky = g.createLinearGradient(0, winTop, 0, winBot);
  sky.addColorStop(0, '#07080c');
  sky.addColorStop(0.5, '#0f1016');
  sky.addColorStop(0.78, '#1d1719');
  sky.addColorStop(1, '#251a15');
  g.fillStyle = sky; g.fillRect(uToX(u0), winTop, uToX(u1) - uToX(u0), winBot - winTop);
  // warm city haze on the horizon
  const haze = g.createLinearGradient(0, yToRow(1.3), 0, winBot);
  haze.addColorStop(0, 'rgba(120,70,40,0)');
  haze.addColorStop(1, 'rgba(150,85,45,0.28)');
  g.fillStyle = haze; g.fillRect(uToX(u0), yToRow(1.3), uToX(u1) - uToX(u0), winBot - yToRow(1.3));
  // skyline: three depth layers of towers with lit windows
  for (let layer = 0; layer < 3; layer++) {
    const baseY = winBot + 2;
    let x = uToX(u0) - 10;
    while (x < uToX(u1) + 10) {
      const bw = (0.25 + r() * 0.9) * metre * (1 + layer * 0.35);
      const top = yToRow(0.5 + r() * (2.1 - layer * 0.45));
      const shade = [12, 9, 7][layer];
      g.fillStyle = `rgb(${shade + 2},${shade + 1},${shade + 3})`;
      g.fillRect(x, top, bw, baseY - top);
      const cell = Math.max(1.6, metre * 0.07);
      for (let yy = top + cell; yy < baseY - cell; yy += cell * 1.6) {
        for (let xx = x + cell * 0.5; xx < x + bw - cell; xx += cell * 1.4) {
          if (r() < 0.13 - layer * 0.025) {
            const warm = r() < 0.82;
            const a = 0.35 + r() * 0.55;
            g.fillStyle = warm ? `rgba(255,${(150 + r() * 70) | 0},${(70 + r() * 50) | 0},${a})` : `rgba(165,185,215,${a * 0.7})`;
            g.fillRect(xx, yy, cell * 0.8, cell * 0.9);
          }
        }
      }
      x += bw + r() * metre * 0.15;
    }
  }
  // a few big soft bokeh discs (near street lights / car lights out of focus)
  g.globalCompositeOperation = 'lighter';
  for (let i = 0; i < 70; i++) {
    const x = uToX(u0 + r() * (u1 - u0));
    const row = yToRow(0.25 + Math.pow(r(), 1.8) * 1.6);
    const rad = (0.04 + Math.pow(r(), 2.4) * 0.16) * metre * 3;
    const warm = r() < 0.85;
    const a = 0.05 + r() * 0.16;
    const col = warm ? [255, (140 + r() * 70) | 0, (55 + r() * 50) | 0] : [150, 175, 215];
    const grd = g.createRadialGradient(x, row, 0, x, row, rad);
    grd.addColorStop(0, `rgba(${col},${a})`);
    grd.addColorStop(0.75, `rgba(${col},${a * 0.8})`);
    grd.addColorStop(1, 'rgba(0,0,0,0)');
    g.fillStyle = grd;
    g.beginPath(); g.arc(x, row, rad, 0, Math.PI * 2); g.fill();
  }
  g.globalCompositeOperation = 'source-over';
  g.restore();

  // mullions + transom
  const mullW = Math.max(2, 0.08 * metre);
  for (let u = u0; u <= u1 + 1e-6; u += bayW) {
    const x = uToX(u);
    g.fillStyle = '#080605'; g.fillRect(x - mullW / 2, winTop - 3, mullW, winBot - winTop + 6);
    g.fillStyle = 'rgba(255,170,90,0.08)'; g.fillRect(x + mullW / 2 - 1, winTop, 1, winBot - winTop);
  }
  g.fillStyle = '#080605';
  g.fillRect(uToX(u0), yToRow(2.4) - mullW * 0.35, uToX(u1) - uToX(u0), mullW * 0.7);
  g.fillRect(uToX(u0) - 3, winBot, uToX(u1) - uToX(u0) + 6, mullW * 1.4);

  // warm sconces: light columns with a wall wash
  const sconce = (u, y0, y1, k = 1) => {
    const x = uToX(u), top = yToRow(y1), bot = yToRow(y0), hh = bot - top;
    g.globalCompositeOperation = 'lighter';
    const wash = g.createRadialGradient(x, top + hh / 2, 0, x, top + hh / 2, hh * 1.1);
    wash.addColorStop(0, `rgba(255,140,60,${0.2 * k})`);
    wash.addColorStop(0.5, `rgba(200,100,40,${0.07 * k})`);
    wash.addColorStop(1, 'rgba(0,0,0,0)');
    g.fillStyle = wash; g.fillRect(x - hh * 1.1, top - hh * 0.6, hh * 2.2, hh * 2.2);
    const colW = Math.max(2.5, 0.06 * metre);
    const col = g.createLinearGradient(x - colW * 2, 0, x + colW * 2, 0);
    col.addColorStop(0, 'rgba(255,150,70,0)');
    col.addColorStop(0.5, `rgba(255,192,125,${0.9 * k})`);
    col.addColorStop(1, 'rgba(255,150,70,0)');
    g.fillStyle = col; g.fillRect(x - colW * 2, top, colW * 4, hh);
    g.globalCompositeOperation = 'source-over';
  };
  sconce(u0 - 0.012, 0.5, 2.7, 1.0);
  sconce(u1 + 0.012, 0.5, 2.7, 1.0);
  sconce(0.22, 0.7, 2.2, 0.6);
  sconce(0.78, 0.7, 2.2, 0.6);
  sconce(0.07, 0.9, 1.9, 0.4);
  sconce(0.93, 0.9, 1.9, 0.4);
  g.globalCompositeOperation = 'lighter';
  for (const [u, y, s] of [[0.17, 0.9, 1], [0.86, 1.1, 0.8], [0.02, 1.0, 0.6]]) {
    const x = uToX(u), row = yToRow(y), rad = 0.5 * metre * s;
    const grd = g.createRadialGradient(x, row, 0, x, row, rad);
    grd.addColorStop(0, 'rgba(255,190,120,0.35)');
    grd.addColorStop(0.3, 'rgba(255,140,60,0.12)');
    grd.addColorStop(1, 'rgba(0,0,0,0)');
    g.fillStyle = grd; g.fillRect(x - rad, row - rad, rad * 2, rad * 2);
  }
  g.globalCompositeOperation = 'source-over';
  const ceil = g.createLinearGradient(0, 0, 0, yToRow(2.7));
  ceil.addColorStop(0, 'rgba(3,2,2,0.95)');
  ceil.addColorStop(1, 'rgba(3,2,2,0)');
  g.fillStyle = ceil; g.fillRect(0, 0, w, yToRow(2.7));
  const floor = g.createLinearGradient(0, yToRow(0.12), 0, h);
  floor.addColorStop(0, 'rgba(6,4,3,0)');
  floor.addColorStop(0.35, 'rgba(6,4,3,0.85)');
  floor.addColorStop(1, 'rgba(4,3,2,1)');
  g.fillStyle = floor; g.fillRect(0, yToRow(0.12), w, h - yToRow(0.12));

  // upscale (bilinear) = the out-of-focus blur, then dither
  const out = makeCanvas(W, H), og = out.getContext('2d');
  og.imageSmoothingEnabled = true;
  og.imageSmoothingQuality = 'high';
  const q = makeCanvas(w >> 1, h >> 1), qg = q.getContext('2d');
  qg.imageSmoothingQuality = 'high';
  qg.drawImage(c, 0, 0, q.width, q.height);
  og.drawImage(c, 0, 0, W, H);
  og.globalAlpha = 0.55;
  og.drawImage(q, 0, 0, W, H); // extra softness from a quarter-res copy
  og.globalAlpha = 1;
  ditherOverlay(og, W, H, 0.35);
  const t = canvasTexture(out, { aniso: 4 });
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
