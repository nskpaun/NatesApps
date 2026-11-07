import { useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import type { Preset } from '../lib/types'
import { getViewer } from '../lib/viewer'
import { stillsFor } from '../lib/stills'
import { groupOf, scene } from '../lib/scene'
import { MODE_TABS, STYLES, dockUi } from '../lib/content'
import { Still } from './ui'
import { useSyncExternalStore } from 'react'

export function ViewerPark() {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (ref.current) getViewer().mount(ref.current)
  }, [])
  return <div ref={ref} className="viewer-park" />
}

export function ViewerSlot() {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    return getViewer().attach(el)
  }, [])
  return <div ref={ref} className="viewer-slot" />
}

export function useViewer() {
  return useSyncExternalStore(getViewer().subscribe, getViewer().getSnapshot, getViewer().getSnapshot)
}

export function Stage({ showChrome = true }: { showChrome?: boolean }) {
  const snap = useViewer()
  const viewer = getViewer()
  const names = stillsFor(snap.state, snap.camera, snap.dockStep)
  const ready = snap.status === 'ready'
  const group = snap.picked ? groupOf(scene, snap.picked) : undefined
  const mode = MODE_TABS.find((m) => m[0] === snap.state.mode)?.[1] ?? snap.state.mode
  const style = STYLES.find((s) => s[0] === snap.state.style)?.[1] ?? snap.state.style
  const status =
    snap.status === 'ready' ? `Live · ${mode} · ${style}` : snap.status === 'error' ? 'Still image' : 'Still · live view loading'
  return (
    <div className={ready ? 'stage is-ready' : 'stage'} data-status={snap.status}>
      <Still names={names} alt={ready ? '' : `Still render of the station, ${mode}, ${style}`} />
      <ViewerSlot />
      {showChrome ? (
        <div className="stage-chrome">
          <div className="stage-top">
            <div>
              <p className="stage-kicker">Studio</p>
              <p className="status-line">
                <span className={`dot ${snap.status}`} />
                {status}
              </p>
            </div>
            <div className="stage-actions">
              <button type="button" className="icon-btn" onClick={() => viewer.resetView()}>
                Reset view
              </button>
            </div>
          </div>
          {snap.state.isolate ? (
            <p className="notice">
              Isolated · {groupOf(scene, snap.state.isolate)?.name ?? snap.state.isolate}
              <button type="button" onClick={() => viewer.setState({ isolate: null })}>
                Show all
              </button>
            </p>
          ) : null}
          <div className="stage-bottom">
            {snap.dockPlaying && snap.dockStep ? (
              <p className="notice">
                {(() => {
                  const step = dockUi().find((s) => s.id === snap.dockStep)
                  return step ? `${step.n} · ${step.title}: ${step.caption}` : snap.dockStep
                })()}
              </p>
            ) : null}
            {snap.status !== 'ready' ? (
              <p className="notice" role="status">
                {snap.status === 'error'
                  ? `Still image · ${snap.errorMessage ?? 'live view stopped'}`
                  : 'Still image · starting the live view'}
                <button type="button" onClick={() => viewer.retry()}>
                  Retry
                </button>
              </p>
            ) : null}
          </div>
        </div>
      ) : null}
      <span className="sr-only">{group ? `${group.name} selected` : ''}</span>
    </div>
  )
}

export function useOpenStudio() {
  const navigate = useNavigate()
  return (preset?: Preset) => {
    if (preset) getViewer().apply(preset)
    navigate('/studio')
  }
}
