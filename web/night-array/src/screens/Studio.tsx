import { useState } from 'react'
import { Link } from 'react-router-dom'
import { CAMERAS, FINISHES, MODE_TABS, QUALITIES, STYLES, dockUi } from '../lib/content'
import { fmtBox, fmtMass } from '../lib/format'
import { groupOf, materialLabel, partsOf, scene } from '../lib/scene'
import type { CameraId, FinishId, QualityId, ViewerMode, ViewerStyle } from '../lib/types'
import { getViewer } from '../lib/viewer'
import { Stage, useViewer } from '../components/Stage'
import { Chip, Segmented, Slider, Swatch, Toggle, useMedia } from '../components/ui'

const PANELS = [
  ['view', 'View'],
  ['finish', 'Finish'],
  ['tools', 'Tools'],
  ['dock', 'Dock'],
  ['parts', 'Parts'],
] as const

type PanelId = (typeof PANELS)[number][0]

export function Studio() {
  const snap = useViewer()
  const viewer = getViewer()
  const wide = useMedia('(min-width: 1100px)')
  const [panel, setPanel] = useState<PanelId | null>(wide ? 'view' : 'view')
  const group = snap.picked ? groupOf(scene, snap.picked) : undefined
  const open = panel ?? (wide ? 'view' : null)
  return (
    <div className="studio">
      <Stage />
      <aside className="controls" aria-label="Studio controls">
        <Segmented label="Mode" value={snap.state.mode} options={MODE_TABS} onChange={(mode) => viewer.setState({ mode: mode as ViewerMode })} />
        {group ? (
          <section className="part-sheet" aria-label={`${group.name} details`}>
            <header>
              <p className="kicker">Selected</p>
              <h2>{group.name}</h2>
              <button type="button" className="text-btn" onClick={() => viewer.closeSheet()}>
                Close
              </button>
            </header>
            <p>{group.summary}</p>
            <ul className="materials">
              {group.materials.map((m) => (
                <li key={m}>
                  <Swatch material={m} /> {materialLabel(scene, m)}
                </li>
              ))}
            </ul>
            <dl className="spec-list tight">
              <div>
                <dt>Size</dt>
                <dd>{fmtBox(group.bboxMm)}</dd>
              </div>
              <div>
                <dt>Mass</dt>
                <dd>{fmtMass(group.massG)}{group.massG > 0 ? ' (concept)' : ''}</dd>
              </div>
              <div>
                <dt>Parts</dt>
                <dd>
                  {group.parts.length}
                  {partsOf(scene, group.id).some((p) => p.internal) ? `, ${partsOf(scene, group.id).filter((p) => p.internal).length} internal` : ''}
                </dd>
              </div>
            </dl>
            <div className="row">
              <button type="button" className="btn fill" onClick={() => viewer.toggleIsolate(group.id)}>
                {snap.state.isolate === group.id ? 'Show all' : 'Isolate'}
              </button>
              <button type="button" className="btn" onClick={() => viewer.frame(group.id)}>
                Frame
              </button>
              <Link className="btn" to={`/files/${group.id}`}>
                Files
              </Link>
            </div>
          </section>
        ) : (
          <>
            <div className="panel-tabs" role="tablist" aria-label="Studio panels">
              {PANELS.map(([id, label]) => (
                <button
                  key={id}
                  type="button"
                  role="tab"
                  aria-selected={open === id}
                  className={open === id ? 'on' : ''}
                  onClick={() => setPanel(open === id && !wide ? null : id)}
                >
                  {label}
                </button>
              ))}
            </div>
            {open ? (
              <div className="panel" role="tabpanel">
                {open === 'view' ? <ViewPanel /> : null}
                {open === 'finish' ? <FinishPanel /> : null}
                {open === 'tools' ? <ToolsPanel /> : null}
                {open === 'dock' ? <DockPanel /> : null}
                {open === 'parts' ? <PartsPanel /> : null}
              </div>
            ) : (
              <p className="fine panel-hint">Show controls to change style, finish, tools, the dock, or a part.</p>
            )}
          </>
        )}
        <p className="fine">
          Drag to orbit, scroll or pinch to zoom. These controls call the same viewer the Android app uses. They do not talk to a physical station.
        </p>
      </aside>
    </div>
  )
}

function ViewPanel() {
  const snap = useViewer()
  const viewer = getViewer()
  return (
    <>
      <p className="micro">Style</p>
      <div className="chips">
        {STYLES.map(([id, label]) => (
          <Chip key={id} pressed={snap.state.style === id} onClick={() => viewer.setState({ style: id as ViewerStyle })}>
            {label}
          </Chip>
        ))}
      </div>
      <p className="micro">Camera</p>
      <div className="chips">
        {CAMERAS.map(([id, label]) => (
          <Chip key={id} pressed={snap.camera === id} onClick={() => viewer.cameraTo(id as CameraId)}>
            {label}
          </Chip>
        ))}
      </div>
    </>
  )
}

function FinishPanel() {
  const snap = useViewer()
  const viewer = getViewer()
  const amber = snap.state.amber
  return (
    <>
      <p className="micro">Metal finish</p>
      <div className="finish-picks">
        {FINISHES.map(([id, label]) => (
          <button key={id} type="button" className={snap.state.finish === id ? 'finish on' : 'finish'} aria-pressed={snap.state.finish === id} onClick={() => viewer.setState({ finish: id as FinishId })}>
            <span className={`metal ${id}`} />
            {label}
          </button>
        ))}
      </div>
      <Slider label="Amber lighting" value={amber} text={amber < 0.02 ? 'Off' : `${Math.round(amber * 100)} %`} onChange={(v) => viewer.setState({ amber: v })} />
      <div className="amber-line" style={{ opacity: Math.max(amber, 0.05) }} />
    </>
  )
}

function ToolsPanel() {
  const snap = useViewer()
  const viewer = getViewer()
  const st = snap.state
  return (
    <>
      <Slider label="Explode" value={st.explode} text={st.explode < 0.01 ? 'Assembled' : `${Math.round(st.explode * 100)} %`} onChange={(v) => viewer.setState({ explode: v })} />
      <Toggle label="Section" sub="Cut the station open with a clipping plane" on={!!st.section} onChange={(on) => viewer.setState({ section: on ? { axis: st.section?.axis ?? 'x', t: st.section?.t ?? 0.5 } : null })} />
      {st.section ? (
        <>
          <Segmented
            label="Section axis"
            value={st.section.axis}
            options={[
              ['x', 'Across (X)'],
              ['z', 'Front–back (Z)'],
            ]}
            onChange={(axis) => viewer.setState({ section: { axis, t: st.section?.t ?? 0.5 } })}
          />
          <Slider label="Plane position" value={st.section.t} text={`${Math.round(st.section.t * 100)} %`} onChange={(t) => viewer.setState({ section: { axis: st.section?.axis ?? 'x', t } })} />
        </>
      ) : null}
      <Toggle label="Dimensions" sub="Overall size, display, seam, work offset" on={st.dims} onChange={(dims) => viewer.setState({ dims })} />
      <Toggle label="Auto-rotate" on={st.autorotate} onChange={(autorotate) => viewer.setState({ autorotate })} />
      <p className="micro">Render quality</p>
      <Segmented label="Render quality" value={st.quality} options={QUALITIES} onChange={(quality) => viewer.setState({ quality: quality as QualityId })} />
    </>
  )
}

function DockPanel() {
  const snap = useViewer()
  const viewer = getViewer()
  const steps = dockUi()
  const active = steps.find((s) => s.id === snap.dockStep)
  return (
    <>
      <p className="micro">Docking sequence</p>
      <div className="dock-steps">
        {steps.map((step) => (
          <button key={step.id} type="button" className={snap.dockStep === step.id ? 'on' : ''} aria-pressed={snap.dockStep === step.id} onClick={() => viewer.dock(step.id)}>
            <span>{step.n}</span>
            {step.title}
          </button>
        ))}
      </div>
      <p>{active ? active.caption : snap.dockPlaying ? 'Starting…' : 'Choose a step, or play the whole sequence.'}</p>
      <div className="row">
        <button
          type="button"
          className="btn fill"
          disabled={snap.dockPlaying}
          onClick={() => {
            viewer.cameraTo('dock')
            viewer.dock('play')
          }}
        >
          {snap.dockPlaying ? 'Playing…' : 'Play sequence'}
        </button>
        <button type="button" className="btn" onClick={() => viewer.dock('reset')}>
          Reset
        </button>
      </div>
    </>
  )
}

function PartsPanel() {
  const snap = useViewer()
  const viewer = getViewer()
  return (
    <>
      <p className="micro">Tap a part group, or tap the model</p>
      <div className="chips">
        {scene.groups.map((g) => (
          <Chip key={g.id} pressed={snap.state.selected === g.id} onClick={() => viewer.pickLocal(g.id)}>
            <Swatch material={g.materials[0] ?? 'titanium'} /> {g.name}
          </Chip>
        ))}
      </div>
    </>
  )
}
