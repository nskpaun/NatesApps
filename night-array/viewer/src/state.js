// ViewerState (SPEC.md section 4): defaults, validation and partial merging.

export const MODES = ['work', 'stow', 'standalone'];
export const STYLES = ['studio', 'cad', 'xray', 'blueprint'];
export const FINISHES = ['titanium', 'graphite', 'oxblood'];
export const QUALITIES = ['high', 'balanced', 'battery'];
export const CAMERAS = ['hero', 'front', 'top', 'side', 'back', 'dock', 'trays', 'display'];
export const DOCK_COMMANDS = ['align', 'lower', 'release', 'lift', 'play', 'reset'];

export const DEFAULT_STATE = Object.freeze({
  mode: 'work',
  style: 'studio',
  finish: 'titanium',
  amber: 0.8,
  explode: 0,
  section: null,
  dims: false,
  autorotate: false,
  isolate: null,
  selected: null,
  quality: 'high',
  cinematic: false,
});

const num = (v) => (typeof v === 'number' ? v : typeof v === 'string' && v.trim() !== '' ? Number(v) : NaN);
const unit = (v) => {
  const n = num(v);
  return Number.isFinite(n) ? Math.min(1, Math.max(0, n)) : undefined;
};
const bool = (v) => (typeof v === 'boolean' ? v : v === 'true' ? true : v === 'false' ? false : typeof v === 'number' ? v !== 0 : undefined);
const oneOf = (list) => (v) => (list.includes(v) ? v : undefined);
const groupOrNull = (v) => (v === null || v === '' || v === false ? null : typeof v === 'string' ? v : undefined);

/**
 * Merges a partial state into `current`. Unknown keys and invalid values are ignored (with a note in
 * `rejected`). Returns { state, changed: Set<key>, rejected: string[] }.
 */
export function mergeState(current, partial) {
  const state = { ...current, section: current.section ? { ...current.section } : null };
  const changed = new Set();
  const rejected = [];
  if (!partial || typeof partial !== 'object') return { state, changed, rejected };
  const set = (k, v) => {
    if (v === undefined) {
      rejected.push(k);
      return;
    }
    if (state[k] !== v) {
      state[k] = v;
      changed.add(k);
    }
  };
  for (const [k, v] of Object.entries(partial)) {
    switch (k) {
      case 'mode': set(k, oneOf(MODES)(v)); break;
      case 'style': set(k, oneOf(STYLES)(v)); break;
      case 'finish': set(k, oneOf(FINISHES)(v)); break;
      case 'quality': set(k, oneOf(QUALITIES)(v)); break;
      case 'amber': case 'explode': set(k, unit(v)); break;
      case 'dims': case 'autorotate': case 'cinematic': set(k, bool(v)); break;
      case 'isolate': case 'selected': set(k, groupOrNull(v)); break;
      case 'section': {
        if (v === null || v === false) {
          if (state.section !== null) {
            state.section = null;
            changed.add(k);
          }
          break;
        }
        if (typeof v !== 'object') {
          rejected.push(k);
          break;
        }
        const prev = state.section || { axis: 'x', t: 0.5 };
        const axis = v.axis === undefined ? prev.axis : v.axis === 'x' || v.axis === 'z' ? v.axis : null;
        const t = v.t === undefined ? prev.t : unit(v.t);
        if (axis === null || t === undefined) {
          rejected.push(k);
          break;
        }
        if (!state.section || state.section.axis !== axis || state.section.t !== t) {
          state.section = { axis, t };
          changed.add(k);
        }
        break;
      }
      default:
        rejected.push(k);
    }
  }
  return { state, changed, rejected };
}

/** Reads ?state=<url-encoded JSON> (SPEC) from the page URL. */
export function stateFromUrl(search) {
  try {
    const q = new URLSearchParams(search);
    const raw = q.get('state');
    if (!raw) return null;
    const obj = JSON.parse(raw);
    return obj && typeof obj === 'object' ? obj : null;
  } catch (e) {
    console.info('[NightArray] ignoring malformed ?state=', String(e && e.message));
    return null;
  }
}
