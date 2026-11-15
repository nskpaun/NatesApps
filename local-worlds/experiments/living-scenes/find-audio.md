## Audio design for Nate's Worlds: generative music and positional scene sounds (Web Audio only)

A working `audio.js` ES module is written and passes offline and realtime runs in Chromium: no NaNs, nothing within 6 dB of clipping, and the seeded mood changes the output as intended. Nobody has listened to it, and it has not run in WKWebView. No project files were touched.

**Files (scratchpad only; copy `audio.js` to `thread/viewer/audio.js` in the build phase):**
- `/private/tmp/claude-501/-Users-rose-NatesApps--claude-worktrees-local-ai-mesh-processing-30d48e/21f9bc40-38be-4264-aecd-a3d9e7cb7f9f/scratchpad/audio/audio.js` (347 lines, no imports, no three.js dependency)
- `/private/tmp/claude-501/-Users-rose-NatesApps--claude-worktrees-local-ai-mesh-processing-30d48e/21f9bc40-38be-4264-aecd-a3d9e7cb7f9f/scratchpad/audio/test.html` (OfflineAudioContext harness; serve the folder over http and open `?set=a` or `?set=b`)

### API
```js
import { createAudio, gust, resolveMood, FEELS } from "./audio.js";
const audio = createAudio({ volume: 0.6 });   // options: music, sfx, limiter, context (inject an OfflineAudioContext for tests)
audio.setMood({ feel, energy, time, setting, style, name, seed });   // also accepts a bare feel string
audio.setNight(bool)
audio.start() / audio.stop()                  // start() must be called inside a click or key handler
const h = audio.attach(object3D, kind, { level, refDistance, rolloff, pitch, seed });   // h.detach(), h.trigger() (creak)
audio.detachAll()
audio.setWind(v)                              // 0..1, the same value that sways foliage
audio.update(camera)                          // once per frame, after renderer.render
audio.setVolume(v) / setMusicVolume(v) / setSfxVolume(v)
gust(t, seed, base)                           // exported deterministic wind curve: slow swell, gusts, flutter
```
- **Lazy graph:** nothing is built until `start()`. `attach` and `setMood` calls made before that are queued.
- **Object positions:** read from `obj.matrixWorld.elements[12..14]`. A function returning `[x,y,z]` also works.
- **Listener:** position and orientation come from the camera's world matrix, with a `setPosition`/`setOrientation` fallback where the listener AudioParams are missing.

### Music
- **Pads:** each chord is four notes in an open voicing (root, fifth, tenth, plus a ninth or upper fifth). Each note is two sawtooths detuned ±5–10 cents, panned ±0.45, through one shared low-pass.
  - Cutoff is `220 + 1500·brightness^1.5` Hz, breathing ±380 cents on a roughly 40 s LFO.
  - A chord lasts 8 beats (about 8–12 s), with attack 42% and release 75% of that, so chords overlap.
  - Roots walk a per-mode list of settled degrees without repeating.
- **Bells:** three sine partials (1, 2.756, 5.404), 8 ms attack, 2.5–5.5 s exponential decay, random pan. Notes come from a five-note subset of the mode, two octaves above the tonic. Trigger probability per beat is `density·0.3`. They feed a dark dotted-beat feedback echo (feedback 0.38, 1.7 kHz low-pass).
- **Drone:** a faint sine one octave below the tonic.
- **Reverb:** a `ConvolverNode` with a stereo impulse generated from seeded noise. It has 12 ms pre-delay, exponential decay, a low-pass that closes along the tail, and unit energy per channel.
  - Length is 4.5 s outdoors and 2.2 s indoors, ×1.25 at night. Wet level is 0.42 outdoors and 0.28 indoors.
- **Master:** music and sfx buses feed a master gain, then a compressor used as a safety limiter (−10 dB threshold, 12:1), then a 0.7 trim.
- **Fades:** 4 s in, 1.5 s out. The context suspends after stop and when the page is hidden.
- **Mood change:** each mood is its own layer with its own reverb, cross-faded over 6 s. Old layers are freed after 9 s.
- **Scheduling:** a 500 ms timer schedules 2.5 s ahead on the audio clock. It is sequential and seeded, so a world always plays the same piece.

### Mood
The layout model would write `"mood": {"feel": ..., "energy": 0..1, "time": "day"|"dusk"|"night"}` and a world-level indoor/outdoor flag.

| feel | mode | brightness | tempo | density |
|---|---|---|---|---|
| calm | ionian | 0.45 | 50 | 0.35 |
| warm | mixolydian | 0.50 | 54 | 0.40 |
| bright | lydian | 0.70 | 60 | 0.55 |
| dreamy | lydian | 0.55 | 46 | 0.45 |
| playful | ionian | 0.75 | 66 | 0.70 |
| mysterious | dorian | 0.35 | 44 | 0.30 |
| melancholy | aeolian | 0.30 | 42 | 0.25 |
| eerie | phrygian | 0.22 | 40 | 0.15 |

- **Seed and key:** the key (tonic G2..F#3) and all note choices come from a hash of name, style and feel.
- **Energy** scales brightness, tempo and density.
- **Night:** mode moves one step darker, brightness ×0.6, tempo ×0.88, density ×0.6, longer reverb, birds silent.
- **Indoor:** short reverb, and all scene sounds are low-passed at 900 Hz and scaled ×0.35, as if heard through walls.
- **Fallback when the model wrote no mood:** a small adjective list matched against the style sentence (for example "sunny spring park, morning light" gives bright/lydian; "foggy ancient garden at night" gives mysterious, darkened to aeolian). This is a keyword list, used only for mood and only as a fallback.

### Scene sounds
The layout model picks an optional `"sound"` per moving piece from `rustle | buzz | rumble | creak | chirp | none`. If it is absent, default from the motion primitive: sway → rustle, swing → creak, wander → buzz, path → rumble. No object names are involved.

Each emitter has its own `PannerNode` (equal-power panning, inverse distance; HRTF avoided for cost).

| kind | synthesis | driven by |
|---|---|---|
| wind (global bed, not positional) | two decorrelated noise loops, left and right, band-pass 260–960 Hz, plus a narrow whistle band that only appears in gusts | `setWind(v)`: gain `0.03 + 0.5·v^1.3`, band-pass frequency rises with v |
| rustle | noise, high-pass 1.8 kHz, band-pass about 4–6 kHz, 2.5–6.5 Hz flutter | gain proportional to wind² |
| buzz | sawtooth at 150–250 Hz (seeded) plus a quiet octave, low-pass 1.5 kHz, 9–19 Hz amplitude flutter, ±60 cent pitch wander; reference distance 0.4 m, so only audible close up | pitch rises up to 200 cents with flight speed |
| rumble | brown noise low-passed at 320 Hz, faint tyre hiss around 1.1 kHz, two sawtooths (46 and 69 Hz) low-passed at 190 Hz | gain and hum pitch follow smoothed speed (full at 8 m/s) |
| creak | one-shot: sawtooth at 230–470 Hz with a pitch glide, chattered by a 26–56 Hz square, through two narrow band-passes | fired automatically when the object's velocity reverses, rate-limited to 0.35 s, louder for bigger swings; `h.trigger()` also available |
| chirp | one-shot: 2–5 quick upward sine sweeps at 2.3–4 kHz, every 3–17 s | seeded timer, silent at night |

Doppler is not modelled.

### What was tested
All runs were in the Claude Browser pane (Chromium) at 44.1 kHz stereo, with objects moved through `update()` at 15–30 Hz via `OfflineAudioContext.suspend`. Levels are dBFS at the default volume 0.6. No run produced a NaN or measurable DC.

| run | peak | RMS | note |
|---|---|---|---|
| music calm / bright / eerie (40 s) | −13.2 / −12.9 / −13.4 | −26.5 / −25.9 / −26.0 | steady after the fade-in; L/R correlation about 0.65–0.7 |
| music, worst case (playful, energy 1, volume 1, limiter off) | −9.1 | −22.7 | |
| wind bed following `gust()` | −19.7 | −40.9 | 10 s windows range −39 to −47; L/R correlation 0.01 |
| buzz circling at 1 m | −23.2 | −38.5 | |
| vehicle pass at 8 m/s, 5 m away | −17.2 | −37.9 | |
| full park scene, 17 emitters plus music, limiter on | −10.6 | −24.7 | 6 rustle, 5 buzz, 2 rumble, 2 creak, 3 chirp |
| full scene, volume 1.0, limiter on / off | −6.7 / −7.4 | −20.3 / −21.5 | |

- **Brightness works:** a high-frequency proxy (RMS of the first difference over RMS) reads 0.033 for eerie, 0.049 calm, 0.053 bright and 0.084 for playful at energy 1.
- **Limiter:** in normal use it never engages hard; it adds about 1.2 dB through Chromium's automatic make-up gain.
- **Levels from the run before retuning** (still indicative): buzz at 6 m was −57.7 RMS (inaudible, as intended); a creak at 3 m peaked at −22; a mood change at 20 s dipped RMS about 2 dB with no spike; indoor wind was about 10 dB below outdoor.
- **Retuning after the first run:** music +4 dB, wind +10 dB, rustle and rumble down, buzz and chirp up, and a 35 Hz high-pass on the rumble, which removed a DC offset of 0.007–0.019.
- **Not re-measured after retuning:** night and indoor music, mood-change, constant and indoor wind, creak and chirp. Their gains changed, so their current absolute levels are not individually confirmed, though the full-scene run includes them.
- **Realtime smoke test:** with a real `AudioContext` at volume 0, I ran start, 40 updates, setMood mid-run, setNight, a creak trigger, detaching all five kinds, and stop. No exceptions; the context went running then suspended.

### Not verified
- **How it sounds.** Only numbers were checked; the timbre and balance need a human ear, especially the creak and the buzz.
- **WKWebView.** Not run in WebKit at all. The code uses `StereoPannerNode`, `PannerNode.positionX` and `OfflineAudioContext.suspend` (tests only); the listener path has a fallback, the others do not. Compressor make-up gain differs by engine, so expect about ±3 dB.
- **The user-gesture rule in the real app.** `start()` calls `resume()` without awaiting it, because without a gesture it never settles. If the wrapper sets `mediaTypesRequiringUserActionForPlayback = []`, sound could start on load. I found no Swift wrapper source in this repo to check.
- **CPU cost.** Timings were unreliable because the Mac was at load average 8. Music-only renders ranged from 21× to 5× realtime; the full 17-emitter scene measured 2–2.5×, the most expensive case. The 4.5 s stereo convolver alone is roughly the whole music cost, and the 17 emitters cost about the same again. If it shows up in the real app, cut the impulse to about 2.5 s or swap in a four-delay feedback reverb.
- **Long sessions.** The longest run was 60 s. One-shot nodes should be collected after they stop, but no hour-long leak check was done.
- **Creak detection** was tested only on sinusoidal motion; jittery motion relies on the 0.35 s rate limit.
- **Distances assume metres.** That holds for prompt worlds, not photo worlds (COLMAP scale), which have no moving parts anyway and would get music only.

### Integration sketch for the build phase
- **`index.html`:** add a "Sound" checkbox and a volume slider to `#bar`. The checkbox handler calls `audio.start()` or `audio.stop()`, which is the required gesture. Remember the choice in `localStorage` and start on the first `pointerdown` in later sessions.
- **`main.js` `load(def)`:** call `audio.detachAll()`, then `audio.setMood({ ...def.mood, name: def.name, style: def.style, setting: def.outdoor ? "outdoor" : "indoor", night: $("#night").checked })`. For each animated object, call `audio.attach(obj, piece.sound ?? DEFAULT_BY_MOTION[piece.motion])`.
- **Night toggle:** call `audio.setNight(checked)` in the existing `#night` change handler.
- **Animation loop** (line 333), after `renderer.render`: `const w = gust(t, seed); /* same w drives foliage sway */ audio.setWind(w); audio.update(camera);`. The loop already returns early when the page is hidden, and the audio suspends itself then too.
- **Stitch editor:** call `audio.stop()` in `enterStitch`.
- **`llm_boxes.py` and `scenes.json`:** add the `mood` object and the per-piece `sound` field to the prompt schema, and carry `mood`, `style` and `outdoor` into the scene entry.

### Optional later, needs the user's approval
A local music model (for example MusicGen-small or Stable Audio Open Small) could pre-render a 30–60 s loop per world at build time, played under the same scene sounds. That is a new model download, so it is not part of this design.