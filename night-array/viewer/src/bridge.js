// JS -> Kotlin events (SPEC.md section 4): window.NightArrayHost.post(JSON.stringify(evt)),
// or console.log when the page runs outside the app.

const listeners = new Set();

export function hasHost() {
  try {
    return !!(window.NightArrayHost && typeof window.NightArrayHost.post === 'function');
  } catch (e) {
    return false;
  }
}

export function post(evt) {
  const json = JSON.stringify(evt);
  for (const fn of listeners) {
    try {
      fn(evt);
    } catch (e) { /* listeners are diagnostics only */ }
  }
  if (hasHost()) {
    try {
      window.NightArrayHost.post(json);
      return;
    } catch (e) { /* fall through to console */ }
  }
  console.log('[NightArray]', json);
}

/** In-page listeners (used by the stills tool and tests through NA.on). */
export function onEvent(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}
