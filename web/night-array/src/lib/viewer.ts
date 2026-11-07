import type { CameraId, LiveStatus, Preset, ViewerState } from './types'
import { DEFAULT_STATE } from './types'
import { presetPatch } from './stills'

type HostMessage =
  | { op: 'setState'; partial: Partial<ViewerState> }
  | { op: 'camera'; name: string }
  | { op: 'dock'; step: string }
  | { op: 'frame'; group: string }

type Snap = {
  version: number
  state: ViewerState
  status: LiveStatus
  errorMessage: string | null
  camera: CameraId
  dockStep: string | null
  dockPlaying: boolean
  picked: string | null
  boot: number
}

const DOCK_IDS = new Set(['align', 'lower', 'lift'])

function cloneState(s: ViewerState): ViewerState {
  return { ...s, section: s.section ? { ...s.section } : null }
}

export class ViewerController {
  state: ViewerState
  status: LiveStatus = 'idle'
  errorMessage: string | null = null
  camera: CameraId = 'hero'
  dockStep: string | null = null
  dockPlaying = false
  picked: string | null = null
  boot = 0
  private version = 0
  private snapshot: Snap
  private listeners = new Set<() => void>()
  private queue: HostMessage[] = []
  private pageLoaded = false
  private iframe: HTMLIFrameElement | null = null
  private parking: HTMLElement | null = null
  private beforeNight: Partial<ViewerState> | null = null
  private onWindowMessage = (e: MessageEvent) => this.onMessage(e)

  constructor() {
    const narrow = typeof window !== 'undefined' && window.matchMedia('(max-width: 800px)').matches
    this.state = { ...DEFAULT_STATE, quality: narrow ? 'balanced' : 'high' }
    this.snapshot = this.makeSnap()
  }

  private makeSnap(): Snap {
    return {
      version: this.version,
      state: this.state,
      status: this.status,
      errorMessage: this.errorMessage,
      camera: this.camera,
      dockStep: this.dockStep,
      dockPlaying: this.dockPlaying,
      picked: this.picked,
      boot: this.boot,
    }
  }

  private touch() {
    this.version += 1
    this.snapshot = this.makeSnap()
    for (const fn of this.listeners) fn()
  }

  subscribe = (fn: () => void) => {
    this.listeners.add(fn)
    return () => this.listeners.delete(fn)
  }

  getSnapshot = () => this.snapshot

  mount(parking: HTMLElement) {
    if (this.iframe) return
    this.parking = parking
    const iframe = document.createElement('iframe')
    iframe.className = 'viewer-frame'
    iframe.title = 'Night Array live CAD view'
    iframe.setAttribute('referrerpolicy', 'no-referrer')
    iframe.addEventListener('load', () => {
      this.pageLoaded = true
      this.flush()
    })
    window.addEventListener('message', this.onWindowMessage)
    parking.appendChild(iframe)
    this.iframe = iframe
    this.status = 'loading'
    iframe.src = this.url()
    this.touch()
  }

  destroy() {
    window.removeEventListener('message', this.onWindowMessage)
    this.iframe?.remove()
    this.iframe = null
  }

  attach(slot: HTMLElement) {
    const frame = this.iframe
    if (!frame) return () => {}
    slot.appendChild(frame)
    return () => {
      if (this.parking && frame.isConnected) this.parking.appendChild(frame)
    }
  }

  private url() {
    const json = encodeURIComponent(JSON.stringify(this.state))
    return `/viewer/index.html?state=${json}&boot=${this.boot}`
  }

  private post(msg: HostMessage) {
    if (!this.iframe?.contentWindow || !this.pageLoaded) {
      this.queue.push(msg)
      return
    }
    this.iframe.contentWindow.postMessage({ source: 'night-array-host', ...msg }, window.location.origin)
  }

  private flush() {
    const pending = this.queue.splice(0)
    for (const msg of pending) this.post(msg)
  }

  private merge(partial: Partial<ViewerState>) {
    const next = cloneState(this.state)
    for (const [key, value] of Object.entries(partial) as [keyof ViewerState, ViewerState[keyof ViewerState]][]) {
      if (value === undefined) continue
      ;(next as Record<string, unknown>)[key] = value
    }
    this.state = next
  }

  setState(partial: Partial<ViewerState>) {
    this.merge(partial)
    this.post({ op: 'setState', partial })
    this.touch()
  }

  cameraTo(name: CameraId) {
    this.camera = name
    this.post({ op: 'camera', name })
    this.touch()
  }

  dock(step: string) {
    if (step === 'play') {
      this.dockPlaying = true
      this.dockStep = null
    } else if (step === 'reset') {
      this.dockPlaying = false
      this.dockStep = null
    } else if (DOCK_IDS.has(step)) {
      this.dockPlaying = false
      this.dockStep = step
    } else return
    this.post({ op: 'dock', step })
    this.touch()
  }

  frame(group: string) {
    this.post({ op: 'frame', group })
  }

  apply(p: Preset) {
    const patch = presetPatch(this.state, p)
    if (Object.keys(patch).length) this.setState(patch)
    if (p.camera) this.cameraTo(p.camera)
    if (p.dock) this.dock(p.dock)
    this.picked = null
    this.touch()
  }

  resetView() {
    this.apply({ style: 'studio', explode: 0, dims: false, camera: 'hero' })
    if (this.state.autorotate) this.setState({ autorotate: false })
    this.dock('reset')
  }

  enterNight() {
    if (this.state.cinematic) return
    this.beforeNight = {
      autorotate: this.state.autorotate,
      style: this.state.style,
      explode: this.state.explode,
      dims: this.state.dims,
      section: this.state.section,
      isolate: this.state.isolate,
    }
    this.picked = null
    this.setState({
      cinematic: true,
      autorotate: false,
      style: 'studio',
      explode: 0,
      dims: false,
      section: null,
      isolate: null,
      selected: null,
    })
  }

  exitNight() {
    if (!this.state.cinematic) return
    const b = this.beforeNight
    this.beforeNight = null
    const patch: Partial<ViewerState> = { cinematic: false }
    if (b) {
      patch.autorotate = b.autorotate
      patch.style = b.style
      patch.explode = b.explode
      patch.dims = b.dims
      patch.section = b.section ?? null
      patch.isolate = b.isolate ?? null
    }
    this.setState(patch)
    this.cameraTo(this.camera)
  }

  pickLocal(group: string) {
    this.picked = group
    const partial: Partial<ViewerState> = {}
    if (this.state.selected !== group) partial.selected = group
    if (this.state.isolate && this.state.isolate !== group) partial.isolate = group
    if (Object.keys(partial).length) this.setState(partial)
    else this.touch()
    this.frame(group)
  }

  closeSheet() {
    this.picked = null
    if (this.state.selected) this.setState({ selected: null })
    else this.touch()
  }

  toggleIsolate(group: string) {
    this.setState({ isolate: this.state.isolate === group ? null : group })
  }

  retry() {
    if (!this.iframe) return
    this.pageLoaded = false
    this.queue = []
    this.boot += 1
    this.status = 'loading'
    this.errorMessage = null
    this.iframe.src = this.url()
    this.touch()
  }

  private onMessage(e: MessageEvent) {
    if (e.origin !== window.location.origin) return
    const data = e.data as { source?: string; event?: { type?: string; group?: string | null; step?: string; message?: string } } | null
    if (!data || data.source !== 'night-array-viewer' || !data.event) return
    const evt = data.event
    if (evt.type === 'ready') {
      this.status = 'ready'
      this.errorMessage = null
    } else if (evt.type === 'error') {
      this.status = 'error'
      this.errorMessage = evt.message || 'live view stopped'
    } else if (evt.type === 'pick') {
      if (this.state.cinematic) return
      const group = evt.group ?? null
      this.picked = group
      if (this.state.selected !== group) this.setState({ selected: group })
      else this.touch()
      return
    } else if (evt.type === 'dockStep') {
      if (evt.step === 'done') {
        this.dockStep = null
        this.dockPlaying = false
      } else if (evt.step && DOCK_IDS.has(evt.step)) {
        this.dockStep = evt.step
      }
    } else return
    this.touch()
  }
}

let singleton: ViewerController | null = null

export function getViewer(): ViewerController {
  if (!singleton) singleton = new ViewerController()
  return singleton
}
