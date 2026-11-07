// One 5120x1440-style desktop painted across BOTH panels, split exactly like an OS spans two displays:
// canvas x in [0, W/2) is the left monitor (u 0 -> 0.5), [W/2, W) the right monitor (u 0.5 -> 1).
import { rng } from './util.js';
import { ditherOverlay } from './textures.js';

const FONT = 'Inter, Roboto, "Helvetica Neue", Arial, sans-serif';

function rr(g, x, y, w, h, r) {
  g.beginPath();
  g.moveTo(x + r, y);
  g.arcTo(x + w, y, x + w, y + h, r);
  g.arcTo(x + w, y + h, x, y + h, r);
  g.arcTo(x, y + h, x, y, r);
  g.arcTo(x, y, x + w, y, r);
  g.closePath();
}

/** Smooth path through points [[x,y],...] (normalised), using midpoint quadratic segments. */
function curve(g, pts, W, H, close) {
  g.beginPath();
  if (close) {
    g.moveTo(pts[0][0] * W, H + 2);
    g.lineTo(pts[0][0] * W, pts[0][1] * H);
  } else g.moveTo(pts[0][0] * W, pts[0][1] * H);
  for (let i = 1; i < pts.length - 1; i++) {
    const [x0, y0] = pts[i], [x1, y1] = pts[i + 1];
    g.quadraticCurveTo(x0 * W, y0 * H, ((x0 + x1) / 2) * W, ((y0 + y1) / 2) * H);
  }
  const last = pts[pts.length - 1];
  g.lineTo(last[0] * W, last[1] * H);
  if (close) {
    g.lineTo(last[0] * W, H + 2);
    g.closePath();
  }
}

function paintDunes(g, W, H) {
  // sky
  const sky = g.createLinearGradient(0, 0, 0, H);
  sky.addColorStop(0, '#0b0910');
  sky.addColorStop(0.32, '#16111b');
  sky.addColorStop(0.5, '#261b23');
  sky.addColorStop(0.6, '#3a2724');
  sky.addColorStop(0.75, '#1c1414');
  sky.addColorStop(1, '#0d0a0a');
  g.fillStyle = sky;
  g.fillRect(0, 0, W, H);
  // low sun glow behind the left dunes
  g.save();
  g.translate(W * 0.24, H * 0.6);
  g.scale(1, 0.32);
  const sun = g.createRadialGradient(0, 0, 0, 0, 0, W * 0.38);
  sun.addColorStop(0, 'rgba(255,160,80,0.55)');
  sun.addColorStop(0.25, 'rgba(220,110,60,0.22)');
  sun.addColorStop(0.6, 'rgba(120,60,50,0.08)');
  sun.addColorStop(1, 'rgba(0,0,0,0)');
  g.fillStyle = sun;
  g.fillRect(-W * 0.4, -W * 0.4, W * 0.8, W * 0.8);
  g.restore();

  const layers = [
    { pts: [[0, 0.6], [0.1, 0.56], [0.24, 0.585], [0.4, 0.545], [0.55, 0.575], [0.7, 0.535], [0.86, 0.565], [1, 0.54]], top: '#30232a', bot: '#1d161c' },
    { pts: [[0, 0.72], [0.12, 0.64], [0.27, 0.535], [0.36, 0.52], [0.47, 0.565], [0.6, 0.625], [0.76, 0.6], [0.9, 0.63], [1, 0.62]], top: '#3c2a27', bot: '#140e10', rim: [0.06, 0.52, 1.0] },
    { pts: [[0.3, 1.02], [0.42, 0.8], [0.52, 0.69], [0.63, 0.645], [0.74, 0.65], [0.86, 0.69], [1, 0.71]], top: '#2c1f1d', bot: '#0f0b0c', rim: [0.44, 0.9, 0.55] },
    { pts: [[0, 0.9], [0.14, 0.84], [0.3, 0.9], [0.46, 0.93], [0.62, 0.88], [0.8, 0.91], [1, 0.87]], top: '#160f10', bot: '#080606' },
  ];
  for (const L of layers) {
    let minY = 1;
    for (const p of L.pts) minY = Math.min(minY, p[1]);
    const fill = g.createLinearGradient(0, minY * H, 0, H);
    fill.addColorStop(0, L.top);
    fill.addColorStop(1, L.bot);
    curve(g, L.pts, W, H, true);
    g.fillStyle = fill;
    g.fill();
    if (L.rim) {
      const [x0, x1, k] = L.rim;
      // warm wash on the lit face just under the crest
      g.save();
      curve(g, L.pts, W, H, true);
      g.clip();
      g.translate(0, H * 0.018);
      const wash = g.createLinearGradient(x0 * W, 0, x1 * W, 0);
      wash.addColorStop(0, 'rgba(255,150,80,0)');
      wash.addColorStop(0.35, `rgba(255,150,80,${0.16 * k})`);
      wash.addColorStop(1, 'rgba(255,150,80,0)');
      g.strokeStyle = wash;
      // soft falloff from stacked strokes (canvas blur filters are very slow in software canvas)
      g.globalAlpha = 0.34;
      for (const lw of [0.075, 0.055, 0.038, 0.024, 0.012]) {
        g.lineWidth = H * lw;
        curve(g, L.pts, W, H, false);
        g.stroke();
      }
      g.globalAlpha = 1;
      g.restore();
      // the rim light on the crest
      g.save();
      g.globalCompositeOperation = 'lighter';
      const grad = g.createLinearGradient(x0 * W, 0, x1 * W, 0);
      grad.addColorStop(0, 'rgba(255,170,90,0)');
      grad.addColorStop(0.18, `rgba(255,175,95,${0.5 * k})`);
      grad.addColorStop(0.42, `rgba(255,200,130,${0.95 * k})`);
      grad.addColorStop(0.7, `rgba(255,160,80,${0.35 * k})`);
      grad.addColorStop(1, 'rgba(255,150,70,0)');
      g.strokeStyle = grad;
      g.shadowColor = 'rgba(255,140,60,0.9)';
      g.shadowBlur = H * 0.02;
      g.lineWidth = H * 0.0042;
      curve(g, L.pts, W, H, false);
      g.stroke();
      g.shadowBlur = 0;
      g.lineWidth = H * 0.0016;
      const core = g.createLinearGradient(x0 * W, 0, x1 * W, 0);
      core.addColorStop(0, 'rgba(255,230,190,0)');
      core.addColorStop(0.4, `rgba(255,236,205,${0.85 * k})`);
      core.addColorStop(0.75, 'rgba(255,220,170,0)');
      g.strokeStyle = core;
      curve(g, L.pts, W, H, false);
      g.stroke();
      g.restore();
    }
  }
}

function paintMenuBar(g, x0, W, H, right) {
  const h = H * 0.024;
  g.fillStyle = 'rgba(8,7,7,0.42)';
  g.fillRect(x0, 0, W, h);
  g.fillStyle = 'rgba(242,234,225,0.55)';
  const t = h * 0.36;
  let x = x0 + h * 0.9;
  for (const w of right ? [3.5, 2.2] : [1.4, 3.2, 2.6, 2.8, 2.2]) {
    g.fillRect(x, h / 2 - t / 2, w * t, t);
    x += w * t + h * 0.8;
  }
  if (right) {
    g.font = `${(h * 0.52).toFixed(1)}px ${FONT}`;
    g.textAlign = 'right';
    g.textBaseline = 'middle';
    g.fillText('Thu 22:47', x0 + W - h * 0.9, h / 2 + 0.5);
  }
}

function paintWindow(g, x, y, w, h, H, kind, r, frost) {
  const rad = H * 0.012;
  g.save();
  g.shadowColor = 'rgba(0,0,0,0.5)';
  g.shadowBlur = H * 0.035;
  g.shadowOffsetY = H * 0.008;
  rr(g, x, y, w, h, rad);
  g.fillStyle = 'rgba(14,11,10,0.9)';
  g.fill();
  g.restore();
  if (frost) {
    // frosted glass: the wallpaper behind, heavily blurred, glows through the window
    g.save();
    rr(g, x, y, w, h, rad);
    g.clip();
    g.globalAlpha = 0.85;
    g.drawImage(frost, 0, 0, g.canvas.width, g.canvas.height);
    g.globalAlpha = 1;
    g.fillStyle = 'rgba(16,12,11,0.5)';
    g.fillRect(x, y, w, h);
    g.restore();
  }
  rr(g, x, y, w, h, rad);
  g.strokeStyle = 'rgba(242,234,225,0.09)';
  g.lineWidth = Math.max(1, H * 0.0012);
  g.stroke();
  const tb = H * 0.036;
  g.save();
  rr(g, x, y, w, h, rad);
  g.clip();
  g.fillStyle = 'rgba(32,27,24,0.9)';
  g.fillRect(x, y, w, tb);
  for (let i = 0; i < 3; i++) {
    g.fillStyle = ['rgba(242,160,74,0.8)', 'rgba(163,154,144,0.5)', 'rgba(163,154,144,0.5)'][i];
    g.beginPath();
    g.arc(x + tb * 0.55 + i * tb * 0.42, y + tb / 2, tb * 0.12, 0, Math.PI * 2);
    g.fill();
  }
  const pad = H * 0.03;
  const cx = x + pad, cy = y + tb + pad, cw = w - pad * 2, ch = h - tb - pad * 2;
  if (kind === 'code') {
    // sidebar + code lines
    g.fillStyle = 'rgba(255,255,255,0.025)';
    g.fillRect(x, y + tb, cw * 0.2, h - tb);
    const lh = H * 0.026;
    for (let i = 0; i < 8; i++) {
      g.fillStyle = 'rgba(242,234,225,0.22)';
      g.fillRect(x + pad * 0.6, cy + i * lh * 1.3, cw * (0.08 + r() * 0.08), lh * 0.42);
    }
    const colors = ['rgba(242,160,74,0.62)', 'rgba(242,234,225,0.42)', 'rgba(160,190,170,0.5)', 'rgba(170,160,210,0.48)'];
    const left = x + cw * 0.2 + pad;
    for (let i = 0; i * lh < ch - lh; i++) {
      let xx = left + (r() < 0.6 ? Math.floor(r() * 3) * lh * 1.2 : 0);
      g.fillStyle = 'rgba(242,234,225,0.14)';
      g.fillRect(left - pad * 0.7, cy + i * lh, lh * 0.6, lh * 0.4);
      const segs = 1 + Math.floor(r() * 4);
      for (let s = 0; s < segs; s++) {
        const sw = lh * (1.5 + r() * 7);
        if (xx + sw > x + w - pad) break;
        g.fillStyle = colors[Math.floor(r() * colors.length)];
        g.fillRect(xx, cy + i * lh, sw, lh * 0.42);
        xx += sw + lh * 0.5;
      }
    }
  } else {
    // a design / CAD canvas: dark artboard with a line drawing of the station, a properties column
    const aw = cw * 0.72;
    g.fillStyle = 'rgba(8,7,7,0.75)';
    g.fillRect(cx, cy, aw, ch);
    g.strokeStyle = 'rgba(242,234,225,0.06)';
    g.lineWidth = 1;
    const step = H * 0.04;
    for (let gx = cx; gx < cx + aw; gx += step) { g.beginPath(); g.moveTo(gx, cy); g.lineTo(gx, cy + ch); g.stroke(); }
    for (let gy = cy; gy < cy + ch; gy += step) { g.beginPath(); g.moveTo(cx, gy); g.lineTo(cx + aw, gy); g.stroke(); }
    // station elevation sketch
    const sx = cx + aw * 0.1, sw = aw * 0.8, base = cy + ch * 0.78;
    g.strokeStyle = 'rgba(242,160,74,0.8)';
    g.lineWidth = Math.max(1.2, H * 0.0022);
    g.strokeRect(sx, base, sw, ch * 0.05);
    g.strokeStyle = 'rgba(242,234,225,0.65)';
    g.beginPath();
    g.moveTo(sx + sw * 0.03, cy + ch * 0.18); g.lineTo(sx + sw * 0.43, cy + ch * 0.12); g.lineTo(sx + sw * 0.43, cy + ch * 0.58);
    g.lineTo(sx + sw * 0.03, cy + ch * 0.62); g.closePath();
    g.moveTo(sx + sw * 0.47, cy + ch * 0.12); g.lineTo(sx + sw * 0.87, cy + ch * 0.18); g.lineTo(sx + sw * 0.87, cy + ch * 0.62);
    g.lineTo(sx + sw * 0.47, cy + ch * 0.58); g.closePath();
    g.moveTo(sx + sw * 0.38, base); g.lineTo(sx + sw * 0.42, cy + ch * 0.6); g.lineTo(sx + sw * 0.48, cy + ch * 0.6); g.lineTo(sx + sw * 0.52, base);
    g.stroke();
    g.strokeStyle = 'rgba(242,160,74,0.9)';
    g.beginPath(); g.moveTo(sx + sw * 0.45, cy + ch * 0.1); g.lineTo(sx + sw * 0.45, cy + ch * 0.6); g.stroke();
    g.strokeRect(sx + sw * 0.92, base - ch * 0.12, sw * 0.08, ch * 0.17);
    // properties column
    const px = cx + aw + pad;
    for (let i = 0; i < 9; i++) {
      g.fillStyle = i % 3 === 0 ? 'rgba(242,160,74,0.55)' : 'rgba(242,234,225,0.25)';
      g.fillRect(px, cy + i * H * 0.05, (cw - aw - pad) * (0.4 + r() * 0.5), H * 0.012);
    }
  }
  g.restore();
}

function paintDock(g, cx, y, H) {
  const n = 6, rD = H * 0.0075, gap = H * 0.028;
  const w = (n - 1) * gap + H * 0.05;
  rr(g, cx - w / 2, y - H * 0.022, w, H * 0.044, H * 0.022);
  g.fillStyle = 'rgba(20,16,14,0.55)';
  g.fill();
  g.strokeStyle = 'rgba(242,234,225,0.08)';
  g.lineWidth = 1;
  g.stroke();
  for (let i = 0; i < n; i++) {
    const x = cx - ((n - 1) * gap) / 2 + i * gap;
    g.beginPath();
    g.arc(x, y, rD, 0, Math.PI * 2);
    if (i === n - 1) {
      g.fillStyle = 'rgba(255,190,120,0.95)';
      g.fill();
    } else {
      g.strokeStyle = 'rgba(242,234,225,0.7)';
      g.lineWidth = Math.max(1, H * 0.0018);
      g.stroke();
    }
  }
}

function frostOf(canvas) {
  // two-step downscale = a wide, cheap blur
  const a = document.createElement('canvas');
  a.width = Math.max(8, canvas.width >> 3); a.height = Math.max(8, canvas.height >> 3);
  const ag = a.getContext('2d');
  ag.imageSmoothingQuality = 'high';
  ag.drawImage(canvas, 0, 0, a.width, a.height);
  const b = document.createElement('canvas');
  b.width = Math.max(4, a.width >> 2); b.height = Math.max(4, a.height >> 2);
  const bg = b.getContext('2d');
  bg.imageSmoothingQuality = 'high';
  bg.drawImage(a, 0, 0, b.width, b.height);
  ag.clearRect(0, 0, a.width, a.height);
  ag.drawImage(b, 0, 0, a.width, a.height);
  return a;
}

/**
 * Paints the desktop for a mode into `canvas`:
 *  work       - wallpaper, a window snapped to each half, menu bars, dock on the left (primary) panel
 *  standalone - wallpaper, menu bars, dock (the compute in the base drives both panels)
 *  stow       - sleep: the wallpaper dimmed right down, a quiet clock and the charging note
 */
export function paintScreen(canvas, mode) {
  const W = canvas.width, H = canvas.height, half = W / 2;
  const g = canvas.getContext('2d');
  g.save();
  g.clearRect(0, 0, W, H);
  paintDunes(g, W, H);
  const r = rng(31);
  if (mode === 'stow') {
    g.fillStyle = 'rgba(4,3,3,0.66)';
    g.fillRect(0, 0, W, H);
    g.fillStyle = 'rgba(242,234,225,0.5)';
    g.textAlign = 'center';
    g.textBaseline = 'alphabetic';
    g.font = `200 ${(H * 0.13).toFixed(0)}px ${FONT}`;
    g.fillText('22:47', half * 0.5, H * 0.42);
    g.font = `${(H * 0.026).toFixed(0)}px ${FONT}`;
    g.fillStyle = 'rgba(163,154,144,0.6)';
    g.fillText('THURSDAY · STOWED', half * 0.5, H * 0.49);
    // charging note on the right panel
    const cx = half * 1.5, cy = H * 0.44;
    g.fillStyle = 'rgba(242,160,74,0.75)';
    for (let i = 0; i < 2; i++) { g.beginPath(); g.arc(cx - H * 0.13 + i * H * 0.15, cy, H * 0.007, 0, Math.PI * 2); g.fill(); }
    g.fillStyle = 'rgba(163,154,144,0.6)';
    g.textAlign = 'left';
    g.font = `${(H * 0.024).toFixed(0)}px ${FONT}`;
    g.fillText('KEYBOARD', cx - H * 0.115, cy + H * 0.009);
    g.fillText('MOUSE', cx + H * 0.035, cy + H * 0.009);
  } else {
    paintMenuBar(g, 0, half, H, false);
    paintMenuBar(g, half, half, H, true);
    if (mode === 'work') {
      // one window snapped to each half (like an OS spans two displays), frosted so the dunes glow through
      const frost = frostOf(canvas);
      const m = half * 0.045, top = H * 0.075, bottom = H * 0.8;
      paintWindow(g, m, top, half - m * 2, bottom - top, H, 'code', r, frost);
      paintWindow(g, half + m, top, half - m * 2, bottom - top, H, 'design', r, frost);
    }
    paintDock(g, half * 0.5, H * 0.935, H);
  }
  g.restore();
  ditherOverlay(g, W, H, 0.4);
}

/**
 * The live desktop texture on `display_screen`. The canvas aspect comes from scene.json screen.canvas
 * (e.g. 5120x1440); its resolution is scaled down for phones. glTF UVs have v = 0 at the top, so flipY = false.
 */
export class ScreenSurface {
  constructor(THREE, screenDef, scale = 1) {
    const canvas = (screenDef && screenDef.canvas) || [5120, 1440];
    this.THREE = THREE;
    this.aspect = canvas[0] / canvas[1];
    this.canvas = document.createElement('canvas');
    this.mode = null;
    this.setScale(scale);
  }

  setScale(scale) {
    const W = Math.round(Math.min(4096, 2560 * scale) / 2) * 2;
    const H = Math.round(W / this.aspect);
    if (this.canvas.width === W && this.canvas.height === H && this.texture) return false;
    this.canvas.width = W;
    this.canvas.height = H;
    if (this.texture) this.texture.dispose();
    const T = this.THREE;
    this.texture = new T.CanvasTexture(this.canvas);
    this.texture.colorSpace = T.SRGBColorSpace;
    this.texture.flipY = false;
    this.texture.anisotropy = 8;
    this.texture.generateMipmaps = true;
    this.texture.minFilter = T.LinearMipmapLinearFilter;
    if (this.mode) this.paint(this.mode, true);
    return true;
  }

  paint(mode, force = false) {
    if (mode === this.mode && !force) return false;
    this.mode = mode;
    paintScreen(this.canvas, mode);
    this.texture.needsUpdate = true;
    return true;
  }
}
