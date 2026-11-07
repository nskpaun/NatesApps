import type { CameraId, Preset, ViewerState } from './types'
import { DEFAULT_STATE } from './types'

const DOCK_IDS = new Set(['align', 'lower', 'lift'])

/** Candidate stills for the current viewer state, best match first. Mirrors Viewer.kt stillsFor. */
export function stillsFor(s: ViewerState, camera: CameraId | string = 'hero', dockStep: string | null = null): string[] {
  const names: string[] = []
  if (s.isolate) names.push(`part-${s.isolate}.jpg`)
  if (s.cinematic) names.push('night.jpg')
  if (dockStep && DOCK_IDS.has(dockStep)) names.push(`dock-${dockStep}.jpg`)
  if (s.style === 'cad') names.push('cad.jpg')
  if (s.style === 'xray') names.push('xray.jpg')
  if (s.style === 'blueprint') names.push('blueprint.jpg')
  if (s.section) names.push('section.jpg')
  if (s.explode > 0.25) names.push('exploded.jpg')
  if (s.style === 'studio') {
    if (camera === 'dock' && (dockStep == null || dockStep === 'lower')) names.push('dock-lower.jpg')
    if (camera === 'trays') names.push('trays.jpg')
    if (camera === 'display') names.push('display.jpg')
  }
  if (s.finish !== 'titanium') names.push(`finish-${s.finish}.jpg`)
  if (s.amber < 0.05) names.push('amber-off.jpg')
  names.push(`hero-${s.mode}.jpg`)
  names.push('hero-work.jpg')
  return names
}

export function stillUrl(name: string): string {
  if (name.includes('/')) return `/${name.replace(/^\/+/, '')}`
  return `/renders/${name}`
}

export function presetPatch(current: ViewerState, p: Preset): Partial<ViewerState> {
  const patch: Partial<ViewerState> = {}
  if (p.mode) patch.mode = p.mode
  if (p.style) patch.style = p.style
  if (p.finish) patch.finish = p.finish
  if (p.amber != null) patch.amber = p.amber
  if (p.explode != null) patch.explode = p.explode
  if (p.dims != null) patch.dims = p.dims
  if (p.section) patch.section = { axis: p.section, t: 0.5 }
  else if (current.section) patch.section = null
  if (p.isolate) patch.isolate = p.isolate
  else if ((p.clearIsolate ?? true) && current.isolate) patch.isolate = null
  if (current.selected) patch.selected = null
  return patch
}

export function stateForStill(partial: Partial<ViewerState> = {}): ViewerState {
  return { ...DEFAULT_STATE, ...partial, section: partial.section === undefined ? DEFAULT_STATE.section : partial.section }
}
