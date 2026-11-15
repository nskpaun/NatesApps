// audio.js — soft generative music and quiet positional scene sounds for Nate's Worlds.
// Web Audio only: no audio files, no model, no network. No three.js import: objects are read
// through matrixWorld.elements, so this module also runs in an OfflineAudioContext for tests.
//
//   const audio = createAudio();
//   audio.setMood({ feel: "calm", time: "day", setting: "outdoor", seed: "Park|soft morning light" });
//   button.onclick = () => audio.start();                 // must be inside a click/key handler
//   const h = audio.attach(beeObject3D, "buzz");          // rustle | buzz | rumble | creak | chirp
//   each frame: const w = gust(t, seed); audio.setWind(w); audio.update(camera);

const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
const mtof = (m) => 440 * 2 ** ((m - 69) / 12);

export function hash(s) { let h = 2166136261; for (const c of String(s)) { h ^= c.codePointAt(0); h = Math.imul(h, 16777619); } return h >>> 0; }
export function rng(seed) {
  let a = seed >>> 0;
  return () => { a = (a + 0x6D2B79F5) | 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}

// One wind value in 0..1 for both the foliage sway and the wind sound: a slow swell, occasional gusts, a little flutter.
export function gust(t, seed = 0, base = 0.35) {
  const p = (seed % 997) * 0.0131;
  const swell = 0.6 + 0.4 * Math.sin(t * 0.071 + p * 5);
  const g = Math.max(0, Math.sin(t * 0.23 + p * 11) * Math.sin(t * 0.037 + p * 3));
  return clamp(base * swell + 0.45 * g * g + 0.04 * Math.sin(t * 1.3 + p * 17));
}

// ---- mood ---------------------------------------------------------------------------------------------------------
const MODES = {
  lydian: [0, 2, 4, 6, 7, 9, 11], ionian: [0, 2, 4, 5, 7, 9, 11], mixolydian: [0, 2, 4, 5, 7, 9, 10],
  dorian: [0, 2, 3, 5, 7, 9, 10], aeolian: [0, 2, 3, 5, 7, 8, 10], phrygian: [0, 1, 3, 5, 7, 8, 10],
};
const DARKER = { lydian: "ionian", ionian: "mixolydian", mixolydian: "dorian", dorian: "aeolian", aeolian: "aeolian", phrygian: "phrygian" };
const MAJORISH = { lydian: 1, ionian: 1, mixolydian: 1 };
// chord roots (scale degrees) that sound settled in each mode, and the five-note subset the bells use
const ROOTS = { lydian: [0, 1, 4, 5], ionian: [0, 3, 5, 4], mixolydian: [0, 6, 3, 4], dorian: [0, 3, 6, 2], aeolian: [0, 5, 3, 6], phrygian: [0, 1, 5, 3] };
const PENTA = (mode) => (MAJORISH[mode] ? [0, 1, 2, 4, 5] : [0, 2, 3, 4, 6]);
// The small vocabulary the layout model picks "feel" from.
export const FEELS = {
  calm:       { mode: "ionian",     brightness: 0.45, tempo: 50, density: 0.35 },
  warm:       { mode: "mixolydian", brightness: 0.50, tempo: 54, density: 0.40 },
  bright:     { mode: "lydian",     brightness: 0.70, tempo: 60, density: 0.55 },
  dreamy:     { mode: "lydian",     brightness: 0.55, tempo: 46, density: 0.45 },
  playful:    { mode: "ionian",     brightness: 0.75, tempo: 66, density: 0.70 },
  mysterious: { mode: "dorian",     brightness: 0.35, tempo: 44, density: 0.30 },
  melancholy: { mode: "aeolian",    brightness: 0.30, tempo: 42, density: 0.25 },
  eerie:      { mode: "phrygian",   brightness: 0.22, tempo: 40, density: 0.15 },
};
// Fallback only, when the layout model wrote no mood: a few generic adjectives in the style sentence.
const HINTS = {
  calm: /calm|quiet|peace|gentle|soft|still|zen|serene/, warm: /warm|cosy|cozy|rustic|wood|autumn|golden|sunset|candle/,
  bright: /bright|sunny|morning|spring|fresh|airy|clean/, dreamy: /dream|pastel|fairy|magic|mist|cloud|ethereal/,
  playful: /play|fun|toy|colou?rful|cartoon|candy|festiv/, mysterious: /myster|wizard|ancient|fog|shadow|hidden|arcane/,
  melancholy: /rain|grey|gray|lonely|abandon|faded|winter|overcast/, eerie: /eerie|haunt|creep|spooky|dark|gothic|crypt/,
};
export function resolveMood(m = {}) {
  if (typeof m === "string") m = { feel: m };
  const text = `${m.style ?? ""}`.toLowerCase();
  let feel = FEELS[m.feel] ? m.feel : null;
  if (!feel) { let best = 0; for (const [k, re] of Object.entries(HINTS)) { const n = (text.match(new RegExp(re.source, "g")) || []).length; if (n > best) { best = n; feel = k; } } }
  feel ??= "calm";
  const f = FEELS[feel], seed = typeof m.seed === "number" ? m.seed >>> 0 : hash(m.seed ?? `${m.name ?? ""}|${m.style ?? ""}|${feel}`), r = rng(seed);
  const night = m.night ?? (m.time === "night" || (!m.time && /\bnight|moonli|midnight|starlit/.test(text)));
  const outdoor = m.outdoor ?? (m.setting ? m.setting === "outdoor" : false);
  const energy = clamp(m.energy ?? 0.5);
  let mode = MODES[m.mode] ? m.mode : f.mode, brightness = m.brightness ?? f.brightness * (0.8 + 0.4 * energy), tempo = m.tempo ?? f.tempo * (0.9 + 0.2 * energy), density = m.density ?? f.density * (0.6 + 0.8 * energy);
  if (m.time === "dusk") { brightness *= 0.85; tempo *= 0.95; }
  if (night) { mode = m.mode ? mode : DARKER[mode]; brightness *= 0.6; tempo *= 0.88; density *= 0.6; }
  if (!outdoor) brightness *= 0.92;
  return {
    feel, seed, night, outdoor, mode, key: Number.isInteger(m.key) ? ((m.key % 12) + 12) % 12 : Math.floor(r() * 12),
    tempo: clamp(tempo, 36, 76), brightness: clamp(brightness, 0.08, 1), density: clamp(density, 0.05, 1),
    reverbSeconds: (outdoor ? 4.5 : 2.2) * (night ? 1.25 : 1), wet: outdoor ? 0.42 : 0.28,
  };
}

// ---- building blocks ----------------------------------------------------------------------------------------------
function noiseBuffer(ctx, seconds, seed, brown) {
  const n = Math.floor(ctx.sampleRate * seconds), buf = ctx.createBuffer(1, n, ctx.sampleRate), d = buf.getChannelData(0), r = rng(seed);
  let last = 0;
  for (let i = 0; i < n; i++) { const w = r() * 2 - 1; if (brown) { last = (last + 0.02 * w) / 1.02; d[i] = last * 3.5; } else d[i] = w; }
  if (brown) {                                                                                  // close the loop without a click, remove DC
    const k = d[n - 1] - d[0]; let mean = 0; for (let i = 0; i < n; i++) { d[i] -= k * i / n; mean += d[i] / n; }
    for (let i = 0; i < n; i++) d[i] -= mean;
  }
  return buf;
}
// Reverb impulse made from noise: exponential decay, getting darker along the tail, each channel scaled to unit energy.
function impulse(ctx, seconds, seed) {
  const sr = ctx.sampleRate, n = Math.floor(sr * seconds), buf = ctx.createBuffer(2, n, sr), pre = Math.floor(sr * 0.012);
  for (let c = 0; c < 2; c++) {
    const d = buf.getChannelData(c), r = rng(seed + c * 7919); let lp = 0, e = 0;
    for (let i = pre; i < n; i++) {
      const x = (i - pre) / (n - pre), a = 0.55 - 0.47 * Math.sqrt(x);                           // one-pole low-pass that closes over time
      lp += a * ((r() * 2 - 1) - lp);
      d[i] = lp * Math.exp(-6.9 * x) * Math.min(1, (i - pre) / (sr * 0.004)); e += d[i] * d[i];
    }
    const k = 1 / Math.sqrt(e); for (let i = pre; i < n; i++) d[i] *= k;
  }
  return buf;
}
function loop(ctx, buffer, rate, offset) { const s = ctx.createBufferSource(); s.buffer = buffer; s.loop = true; s.playbackRate.value = rate; s.start(0, offset % buffer.duration); return s; }
function filter(ctx, type, f, q = 0.7) { const b = ctx.createBiquadFilter(); b.type = type; b.frequency.value = f; b.Q.value = q; return b; }
function gain(ctx, v) { const g = ctx.createGain(); g.gain.value = v; return g; }
function osc(ctx, type, f, t = 0) { const o = ctx.createOscillator(); o.type = type; o.frequency.value = f; o.start(t); return o; }
function chain(...nodes) { for (let i = 0; i < nodes.length - 1; i++) nodes[i].connect(nodes[i + 1]); return nodes[nodes.length - 1]; }

// ---- music layer: one per mood; a mood change cross-fades two layers ------------------------------------------------
function makeLayer(ctx, out, mood) {
  const L = { mood, out: gain(ctx, 0), t0: null, nextChord: 0, nextBeat: 0, cr: rng(mood.seed ^ 0x9e3779b9), br: rng(mood.seed ^ 0x51ed270b), root: 0, lastBell: -1, live: [] };
  L.out.connect(out);
  const conv = ctx.createConvolver(); conv.normalize = false; conv.buffer = impulse(ctx, mood.reverbSeconds, mood.seed);
  L.send = gain(ctx, 1); chain(L.send, conv, gain(ctx, mood.wet), L.out);
  // pads: two slightly spread buses through one slowly breathing low-pass
  const cutoff = 220 + 1500 * mood.brightness ** 1.5;
  const lp = filter(ctx, "lowpass", cutoff, 0.6);
  const lfo = osc(ctx, "sine", 0.021 + 0.02 * L.cr()); chain(lfo, gain(ctx, 380), lp.detune);    // ±380 cents over ~40 s
  L.padL = ctx.createStereoPanner(); L.padL.pan.value = -0.45; L.padR = ctx.createStereoPanner(); L.padR.pan.value = 0.45;
  L.padL.connect(lp); L.padR.connect(lp); lp.connect(L.out); chain(lp, gain(ctx, 0.7), L.send);
  // bells: dry, plus a dark feedback echo into the reverb
  L.bells = gain(ctx, 1); chain(L.bells, gain(ctx, 0.7), L.out); chain(L.bells, gain(ctx, 0.8), L.send);
  const beat = 60 / mood.tempo, dl = ctx.createDelay(2); dl.delayTime.value = Math.min(1.9, beat * 0.75);
  const fb = gain(ctx, 0.38); chain(L.bells, dl, filter(ctx, "lowpass", 1700), fb, dl); chain(dl, gain(ctx, 0.35), L.out); chain(dl, gain(ctx, 0.5), L.send);
  // a barely-there tonic drone
  L.tonic = 43 + mood.key;                                                                       // G2 .. F#3
  const drone = osc(ctx, "sine", mtof(L.tonic - 12)); chain(drone, gain(ctx, 0.06), L.out);
  L.fixed = [lfo, drone];
  L.scale = MODES[mood.mode]; L.penta = PENTA(mood.mode); L.roots = ROOTS[mood.mode];
  return L;
}
const degree = (L, d) => L.tonic + L.scale[((d % 7) + 7) % 7] + 12 * Math.floor(d / 7);

function padNote(ctx, L, midi, t, dur, peak, r) {
  const att = dur * 0.42, rel = dur * 0.75, f = mtof(midi), cents = 5 + 5 * r();
  for (const [bus, sign] of [[L.padL, -1], [L.padR, 1]]) {
    const o = osc(ctx, "sawtooth", f, t); o.detune.value = sign * cents;
    const g = gain(ctx, 0); g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(peak, t + att); g.gain.setValueAtTime(peak, t + dur); g.gain.linearRampToValueAtTime(0, t + dur + rel);
    chain(o, g, bus); o.stop(t + dur + rel + 0.05);
  }
}
function bell(ctx, L, midi, t, vel, pan, r) {
  const f = mtof(midi), dec = 2.5 + 3 * r(), p = ctx.createStereoPanner(); p.pan.value = pan; p.connect(L.bells);
  for (const [mult, amp, d] of [[1, 1, 1], [2.756, 0.2, 0.45], [5.404, 0.06, 0.2]]) {              // soft, slightly inharmonic
    const o = osc(ctx, "sine", f * mult, t), g = gain(ctx, 0), end = t + dec * d;
    g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(vel * amp, t + 0.008); g.gain.exponentialRampToValueAtTime(vel * amp * 0.001, end); g.gain.linearRampToValueAtTime(0, end + 0.03);
    chain(o, g, p); o.stop(end + 0.05);
  }
}
// Schedule every chord and bell that starts before `until`. Sequential and seeded, so a world always plays the same piece.
function scheduleLayer(ctx, L, until) {
  const m = L.mood, beat = 60 / m.tempo, chordDur = beat * 8;
  L.t0 ??= ctx.currentTime + 0.05;
  for (; L.t0 + L.nextChord * chordDur < until; L.nextChord++) {
    const t = L.t0 + L.nextChord * chordDur, r = L.cr;
    if (L.nextChord > 0) { let n; do n = L.roots[Math.floor(r() * L.roots.length)]; while (n === L.root); L.root = n; }
    const d = L.root, colour = r() < 0.5 ? d + 8 : d + 11;                                       // add a ninth or a fifth above
    const notes = [degree(L, d), degree(L, d + 4), degree(L, d + 9), degree(L, colour)];         // open voicing: root, fifth, tenth
    notes.forEach((n, i) => padNote(ctx, L, n, t + i * beat * 0.5 * r(), chordDur, [0.09, 0.065, 0.055, 0.035][i], r));
  }
  for (; L.t0 + L.nextBeat * beat < until; L.nextBeat++) {
    const r = L.br, t = L.t0 + L.nextBeat * beat, roll = r(), which = r(), oct = r(), vel = r(), pan = r(), late = r();
    if (L.nextBeat < 6 || roll > m.density * 0.3) continue;
    let i = Math.floor(which * L.penta.length); if (i === L.lastBell) i = (i + 1) % L.penta.length; L.lastBell = i;
    bell(ctx, L, degree(L, L.penta[i]) + 24 + (oct < 0.3 ? 12 : 0), t + late * beat * 0.5, 0.05 + 0.05 * vel, pan * 1.4 - 0.7, r);
  }
}

// ---- positional scene sounds ----------------------------------------------------------------------------------------
// Each kind is a sound primitive the layout model can choose, the same way it chooses a motion primitive.
// Sensible defaults by motion: sway -> rustle, swing -> creak, wander -> buzz, path -> rumble.
const KINDS = {
  rustle: { ref: 2.0, rolloff: 1.2, level: 0.3 },
  buzz:   { ref: 0.4, rolloff: 1.5, level: 0.25 },
  rumble: { ref: 4.0, rolloff: 1.0, level: 0.6 },
  creak:  { ref: 1.5, rolloff: 1.2, level: 0.22 },
  chirp:  { ref: 3.0, rolloff: 0.8, level: 0.1 },
};
function makeEmitter(A, obj, kind, o) {
  const ctx = A.ctx, K = KINDS[kind], r = rng(o.seed ?? hash(kind + A.emitters.size * 31 + (obj?.name ?? "")));
  const p = ctx.createPanner(); p.panningModel = "equalpower"; p.distanceModel = "inverse"; p.refDistance = o.refDistance ?? K.ref; p.rolloffFactor = o.rolloff ?? K.rolloff; p.maxDistance = 80;
  const level = (o.level ?? 1) * K.level, em = { obj, kind, r, panner: p, level, nodes: [], pos: null, vel: [0, 0, 0], speed: 0, peak: 0, lastCreak: -9, next: 0, born: ctx.currentTime };
  const vca = gain(ctx, 0); em.vca = vca; chain(vca, p, A.sfx);
  if (kind === "rustle") {            // leaves: bright noise that follows the wind, with a flutter
    const src = loop(ctx, A.white, 0.9 + 0.2 * r(), r() * 4), fl = gain(ctx, 1), lfo = osc(ctx, "sine", 2.5 + 4 * r());
    chain(lfo, gain(ctx, 0.3), fl.gain); chain(src, filter(ctx, "highpass", 1800), filter(ctx, "bandpass", 3800 + 2000 * r(), 0.6), fl, vca); em.nodes.push(src, lfo);
  } else if (kind === "buzz") {       // insect: a sawtooth at the wingbeat rate with fluttering loudness and wandering pitch
    const f = o.pitch ?? 150 + 100 * r(), a = osc(ctx, "sawtooth", f), b = osc(ctx, "sawtooth", f * 2.01), fl = gain(ctx, 1);
    const am = osc(ctx, "sine", 9 + 10 * r()), wob = osc(ctx, "sine", 0.5 + 0.8 * r()), wg = gain(ctx, 60);     // ±60 cents
    chain(am, gain(ctx, 0.35), fl.gain); wob.connect(wg); wg.connect(a.detune); wg.connect(b.detune);
    const lp = filter(ctx, "lowpass", 1500, 1.2); a.connect(lp); chain(b, gain(ctx, 0.3), lp); chain(lp, fl, vca);
    em.oscs = [a, b]; em.nodes.push(a, b, am, wob); vca.gain.value = level;
  } else if (kind === "rumble") {     // vehicle: road noise and tyre hiss plus a low engine hum; loudness and pitch follow speed
    const road = loop(ctx, A.brown, 1, r() * 4), tyre = loop(ctx, A.white, 0.8, r() * 4), h1 = osc(ctx, "sawtooth", 46), h2 = osc(ctx, "sawtooth", 69.4);
    chain(road, filter(ctx, "highpass", 35), filter(ctx, "lowpass", 320), gain(ctx, 0.9), vca); chain(tyre, filter(ctx, "bandpass", 1100, 0.5), gain(ctx, 0.07), vca);
    const hl = filter(ctx, "lowpass", 190); h1.connect(hl); h2.connect(hl); chain(hl, gain(ctx, 0.28), vca);
    em.oscs = [h1, h2]; em.nodes.push(road, tyre, h1, h2); vca.gain.value = level * 0.04;
  }
  // creak and chirp are short one-shots made on demand
  return em;
}
function creak(A, em, t, k) {         // stick-slip: a chattering sawtooth through two narrow resonances
  const ctx = A.ctx, r = em.r, f = 230 + 240 * r(), dur = 0.16 + 0.24 * r(), o = osc(ctx, "sawtooth", f, t), ch = osc(ctx, "square", 26 + 30 * r(), t), v = gain(ctx, 0.55), env = gain(ctx, 0);
  o.frequency.setValueAtTime(f, t); o.frequency.exponentialRampToValueAtTime(f * (r() < 0.5 ? 0.82 : 1.2), t + dur);
  chain(ch, gain(ctx, 0.45), v.gain); o.connect(v);
  for (const [m, q] of [[3.1, 14], [5.3, 10]]) chain(v, filter(ctx, "bandpass", f * m, q), env);
  env.gain.setValueAtTime(0, t); env.gain.linearRampToValueAtTime(em.level * k * 4, t + 0.03); env.gain.linearRampToValueAtTime(0, t + dur);
  env.connect(em.panner); o.stop(t + dur + 0.02); ch.stop(t + dur + 0.02);
}
function chirp(A, em, t) {            // small bird: a few quick upward sine sweeps
  const ctx = A.ctx, r = em.r, n = 2 + Math.floor(r() * 4), f0 = 2300 + 1700 * r(), step = 0.09 + 0.08 * r();
  for (let i = 0; i < n; i++) {
    const s = t + i * step, f = f0 * (0.9 + 0.25 * r()), o = osc(ctx, "sine", f, s), g = gain(ctx, 0);
    o.frequency.setValueAtTime(f, s); o.frequency.exponentialRampToValueAtTime(f * (1.15 + 0.3 * r()), s + 0.06);
    g.gain.setValueAtTime(0, s); g.gain.linearRampToValueAtTime(em.level, s + 0.012); g.gain.linearRampToValueAtTime(0, s + 0.07);
    chain(o, g, em.panner); o.stop(s + 0.08);
  }
}
const worldPos = (obj, out) => {
  if (typeof obj === "function") { const p = obj(); out[0] = p[0]; out[1] = p[1]; out[2] = p[2]; }
  else if (obj.matrixWorld) { const e = obj.matrixWorld.elements; out[0] = e[12]; out[1] = e[13]; out[2] = e[14]; }
  else { out[0] = obj.x; out[1] = obj.y; out[2] = obj.z; }
  return out;
};
// Plain value writes once per frame: no automation events pile up, and per-frame steps are too small to hear.
function setXYZ(node, x, y, z) {
  if (node.positionX) { node.positionX.value = x; node.positionY.value = y; node.positionZ.value = z; }
  else node.setPosition(x, y, z);
}

// ---- the public object -----------------------------------------------------------------------------------------------
export function createAudio(opts = {}) {
  const A = { ctx: opts.context ?? null, emitters: new Set(), layers: [], wind: 0, windSetAt: -9, volume: opts.volume ?? 0.6, mood: resolveMood(opts.mood), moodInput: typeof opts.mood === "string" ? { feel: opts.mood } : { ...opts.mood }, running: false, timer: null, last: null };
  const realtime = !opts.context || typeof opts.context.resume === "function" && !("startRendering" in opts.context);
  const fade = { in: opts.fadeIn ?? 4, out: opts.fadeOut ?? 1.5, mood: opts.moodFade ?? 6 };

  function build() {
    if (A.built) return; A.built = true;
    A.ctx ??= new (globalThis.AudioContext || globalThis.webkitAudioContext)({ latencyHint: "playback" });
    const ctx = A.ctx;
    A.master = gain(ctx, 0); A.music = gain(ctx, opts.music ?? 0.9); A.sfxOut = gain(ctx, opts.sfx ?? 0.8);
    A.sfx = filter(ctx, "lowpass", 16000, 0.5); A.sfxScale = gain(ctx, 1); chain(A.sfx, A.sfxScale, A.sfxOut, A.master); A.music.connect(A.master);
    if (opts.limiter === false) A.master.connect(ctx.destination);
    else {      // a gentle safety limiter; normal levels sit below its threshold
      const c = ctx.createDynamicsCompressor(); c.threshold.value = -10; c.knee.value = 6; c.ratio.value = 12; c.attack.value = 0.004; c.release.value = 0.3;
      chain(A.master, c, gain(ctx, opts.makeup ?? 0.7), ctx.destination);
    }
    A.white = noiseBuffer(ctx, 4, 1234567, false); A.brown = noiseBuffer(ctx, 4, 7654321, true);
    // wind: two uncorrelated bands of noise left and right, plus a faint whistle that only appears in gusts
    const merge = ctx.createChannelMerger(2); A.windGain = gain(ctx, 0); A.windBands = [];
    for (let c = 0; c < 2; c++) {
      const bp = filter(ctx, "bandpass", 400, 0.7), wh = filter(ctx, "bandpass", 800, 7), whg = gain(ctx, 0), src = loop(ctx, A.white, c ? 0.93 : 1, c * 1.7);
      chain(src, bp, filter(ctx, "lowpass", 1400)).connect(merge, 0, c); chain(src, wh, whg).connect(merge, 0, c);
      A.windBands.push({ bp, wh, whg });
    }
    chain(merge, A.windGain, A.sfx);
    applyMood(true);
    for (const q of A.pending ?? []) q(); A.pending = null;
  }
  function applyMood(first) {
    const ctx = A.ctx, t = ctx.currentTime, m = A.mood;
    for (const L of A.layers) { L.out.gain.cancelScheduledValues(t); L.out.gain.setTargetAtTime(0, t, fade.mood / 4); L.dead = t + fade.mood * 1.5; }
    const L = makeLayer(ctx, A.music, m); L.out.gain.setValueAtTime(0, t); L.out.gain.linearRampToValueAtTime(1, t + (first ? 0.05 : fade.mood)); A.layers.push(L);
    // indoors the outside world is heard through the walls: quieter and duller. At night birds stop.
    A.sfx.frequency.setTargetAtTime(m.outdoor ? 16000 : 900, t, 0.5); A.sfxScale.gain.setTargetAtTime(m.outdoor ? 1 : 0.35, t, 0.5);
    setWind(A.wind);
  }
  function setMood(mood) {
    A.moodInput = typeof mood === "string" ? { feel: mood } : { ...mood };
    const m = resolveMood(mood), same = JSON.stringify(m) === JSON.stringify(A.mood); A.mood = m;
    if (A.built && !same) applyMood(false);
    return m;
  }
  function setWind(v) {
    A.wind = clamp(v); if (!A.built) return; const t = A.ctx.currentTime; A.windSetAt = t;
    A.windGain.gain.setTargetAtTime(0.03 + 0.5 * A.wind ** 1.3, t, 0.25);
    for (const [i, b] of A.windBands.entries()) {
      b.bp.frequency.setTargetAtTime(260 + 700 * A.wind + i * 40, t, 0.4); b.wh.frequency.setTargetAtTime(600 + 700 * A.wind + i * 90, t, 0.6); b.whg.gain.setTargetAtTime(0.5 * A.wind ** 3, t, 0.4);
    }
    for (const em of A.emitters) if (em.kind === "rustle") em.vca.gain.setTargetAtTime(em.level * (0.03 + A.wind ** 2), t, 0.3);
  }
  function scheduleAhead(until) {
    const ctx = A.ctx, now = ctx.currentTime;
    A.layers = A.layers.filter((L) => { if (L.dead && now > L.dead) { L.out.disconnect(); for (const n of L.fixed) n.stop(); return false; } return true; });
    for (const L of A.layers) if (!L.dead) scheduleLayer(ctx, L, until);
    for (const em of A.emitters) if (em.kind === "chirp") {
      em.next ||= now + 1 + 6 * em.r();
      for (; em.next < until; em.next += 3 + 14 * em.r()) if (!A.mood.night) chirp(A, em, Math.max(em.next, now + 0.02));
    }
  }
  function attach(obj, kind, o = {}) {
    if (!KINDS[kind]) return null;
    const handle = { kind, detach() { if (handle.em) drop(handle.em); else handle.gone = true; }, trigger(k = 1) { if (handle.em && kind === "creak") creak(A, handle.em, A.ctx.currentTime + 0.01, k); } };
    const make = () => { if (handle.gone) return; handle.em = makeEmitter(A, obj, kind, o); A.emitters.add(handle.em); setWind(A.wind); };
    if (A.built) make(); else (A.pending ??= []).push(make);
    return handle;
  }
  function drop(em) {
    const t = A.ctx.currentTime; A.emitters.delete(em); em.vca.gain.cancelScheduledValues(t); em.vca.gain.setTargetAtTime(0, t, 0.05);
    for (const n of em.nodes) n.stop(t + 0.4);
    if (realtime) setTimeout(() => em.panner.disconnect(), 600);
  }
  const P = [0, 0, 0];
  // Call once per rendered frame, after the scene's world matrices are current.
  function update(camera) {
    if (!A.built) return; const ctx = A.ctx, t = ctx.currentTime, dt = A.last == null ? 0 : t - A.last; A.last = t;
    if (camera?.matrixWorld) {
      const e = camera.matrixWorld.elements, l = ctx.listener;
      setXYZ(l, e[12], e[13], e[14]);
      if (l.forwardX) { l.forwardX.value = -e[8]; l.forwardY.value = -e[9]; l.forwardZ.value = -e[10]; l.upX.value = e[4]; l.upY.value = e[5]; l.upZ.value = e[6]; }
      else l.setOrientation(-e[8], -e[9], -e[10], e[4], e[5], e[6]);
    }
    for (const em of A.emitters) {
      if (!em.obj) continue; worldPos(em.obj, P); setXYZ(em.panner, P[0], P[1], P[2]);
      if (em.pos && dt > 1e-4 && dt < 0.25) {
        const v = [(P[0] - em.pos[0]) / dt, (P[1] - em.pos[1]) / dt, (P[2] - em.pos[2]) / dt], sp = Math.hypot(...v), k = 1 - Math.exp(-dt / 0.15);
        const flip = v[0] * em.vel[0] + v[1] * em.vel[1] + v[2] * em.vel[2] < 0;
        em.vel = v; em.speed += (sp - em.speed) * k; em.peak = Math.max(em.peak, sp);
        const slow = t - em.born > 0.1 && t - (em.tuned ?? -9) > 0.1;                                  // speed-driven changes at 10 Hz at most
        if (slow) em.tuned = t;
        if (em.kind === "rumble" && slow) { const s = clamp(em.speed / 8); em.vca.gain.setTargetAtTime(em.level * (0.04 + 0.96 * s ** 0.7), t, 0.1); em.oscs[0].frequency.setTargetAtTime(40 + 28 * s, t, 0.2); em.oscs[1].frequency.setTargetAtTime(60.4 + 42 * s, t, 0.2); }
        else if (em.kind === "buzz" && slow) { const c = 200 * clamp(em.speed / 3); for (const o of em.oscs) o.detune.setTargetAtTime(c, t, 0.15); }   // faster flight, higher whine
        else if (em.kind === "creak" && flip && em.peak > 0.12 && t - em.lastCreak > 0.35) { creak(A, em, t + 0.01, clamp(em.peak / 1.5, 0.25, 1)); em.lastCreak = t; em.peak = 0; }   // a swing reverses: creak, louder for a bigger swing
      } else if (!em.pos) em.pos = [0, 0, 0];
      em.pos[0] = P[0]; em.pos[1] = P[1]; em.pos[2] = P[2];
    }
  }
  function tick() { if (A.running) scheduleAhead(A.ctx.currentTime + 2.5); }
  function start() {           // call from a click or key handler: WKWebView keeps the context suspended until then
    build(); const ctx = A.ctx; A.running = true;
    if (realtime) { if (ctx.state !== "running") ctx.resume().catch(() => {}); A.timer ??= setInterval(tick, 500); }   // not awaited: without a gesture resume() never settles
    const t = ctx.currentTime; A.master.gain.cancelScheduledValues(t); A.master.gain.setValueAtTime(A.master.gain.value, t); A.master.gain.linearRampToValueAtTime(A.volume, t + fade.in);
    tick();
  }
  async function stop() {
    if (!A.built || !A.running) return; A.running = false; const ctx = A.ctx, t = ctx.currentTime;
    A.master.gain.cancelScheduledValues(t); A.master.gain.setTargetAtTime(0, t, fade.out / 4);
    if (realtime) { clearInterval(A.timer); A.timer = null; setTimeout(() => { if (!A.running) ctx.suspend(); }, fade.out * 1000 + 100); }
  }
  function setVolume(v) { A.volume = clamp(v); if (A.built && A.running) A.master.gain.setTargetAtTime(A.volume, A.ctx.currentTime, 0.1); }
  function setMusicVolume(v) { opts.music = clamp(v); if (A.built) A.music.gain.setTargetAtTime(opts.music, A.ctx.currentTime, 0.1); }
  function setSfxVolume(v) { opts.sfx = clamp(v); if (A.built) A.sfxOut.gain.setTargetAtTime(opts.sfx, A.ctx.currentTime, 0.1); }
  function detachAll() { for (const em of [...A.emitters]) drop(em); A.pending = null; }
  if (realtime && typeof document !== "undefined") document.addEventListener("visibilitychange", () => { if (!A.built || !A.running) return; if (document.hidden) A.ctx.suspend(); else A.ctx.resume(); });

  return { start, stop, setMood, setNight: (n) => setMood({ ...A.moodInput, night: n }), attach, detachAll, setWind, setVolume, setMusicVolume, setSfxVolume, update, scheduleAhead,
    get wind() { return A.wind; }, get mood() { return A.mood; }, get context() { return A.ctx; }, get running() { return A.running; }, _A: A, _build: build };
}
