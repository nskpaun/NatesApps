import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { assemblyFiles } from '../lib/content'
import { FORMAT_NOTES, assetUrl, downloadName, fmtBox, fmtBytes, fmtMass, fmtMm } from '../lib/format'
import { filesOf, groupOf, materialLabel, overallMm, partsOf, scene, type CadFile, type Group } from '../lib/scene'
import { toast } from '../lib/toast'
import { getViewer } from '../lib/viewer'
import { BackLink, Kicker, SectionHeader, Still, Swatch } from '../components/ui'

export function Files() {
  const navigate = useNavigate()
  const o = overallMm(scene)
  return (
    <article className="page files">
      <header className="measure">
        <p className="kicker">Files</p>
        <h1>CAD library</h1>
        <p>Every part of the station as STEP, STL, drawing sheets and DXF outlines, all generated from one parametric model.</p>
      </header>
      <section className="card measure assembly">
        <Still names={['exploded.jpg', 'hero-stow.jpg', 'cad.jpg']} alt="Exploded view of the Night Array assembly" />
        <div className="card-body">
          <Kicker>Full assembly</Kicker>
          <h2>{scene.name.split('—')[0].trim()}</h2>
          <p>
            Stow pose · {fmtBox(o)} · {scene.groups.length} groups, {scene.parts.length} parts.
          </p>
          {assemblyFiles().map((file) => (
            <FileRow key={file.id} file={file} />
          ))}
          <button
            type="button"
            className="btn"
            onClick={() => {
              getViewer().apply({ mode: 'stow', style: 'cad', camera: 'hero', explode: 0.6 })
              navigate('/studio')
            }}
          >
            Open in Studio
          </button>
        </div>
      </section>
      <section className="measure">
        <SectionHeader title="Part groups" sub={`${scene.groups.length} groups · ${scene.parts.length} parts`} />
        <ul className="group-list">
          {scene.groups.map((g) => (
            <li key={g.id}>
              <Link to={`/files/${g.id}`}>
                <Still names={[`part-${g.id}.jpg`]} alt="" />
                <span>
                  <strong>{g.name}</strong>
                  <em>{g.summary}</em>
                  <small>{[fmtBox(g.bboxMm), fmtMass(g.massG)].filter((v) => v !== '—').join(' · ')}</small>
                </span>
              </Link>
            </li>
          ))}
        </ul>
        <h2 className="micro">Formats</h2>
        <ul className="formats">
          {Object.entries(FORMAT_NOTES).map(([k, v]) => (
            <li key={k}>
              <span className="badge">{k}</span> {v}
            </li>
          ))}
        </ul>
        <p className="fine">STEP and STL are in millimetres, Z up, so they open upright in CAD tools and slicers. SVG and DXF are in millimetres. GLB is in metres, Y up. Download saves that file from this site.</p>
      </section>
    </article>
  )
}

export function GroupPage() {
  const { groupId } = useParams()
  const g = groupOf(scene, groupId)
  const navigate = useNavigate()
  if (!g) {
    return (
      <article className="page measure">
        <BackLink to="/files">Files</BackLink>
        <h1>Group not found</h1>
      </article>
    )
  }
  const parts = partsOf(scene, g.id)
  const files = filesOf(scene, g.id)
  return (
    <article className="page group">
      <div className="group-hero">
        <Still names={[`part-${g.id}.jpg`]} alt={`Render of ${g.name}`} />
      </div>
      <div className="measure">
        <BackLink to="/files">Files</BackLink>
        <Kicker>Part group · {g.id}</Kicker>
        <h1>{g.name}</h1>
        <p className="tagline">{g.summary}</p>
        {g.description ? <p>{g.description}</p> : null}
        <dl className="spec-list">
          <div>
            <dt>Size</dt>
            <dd>{fmtBox(g.bboxMm)}</dd>
          </div>
          <div>
            <dt>Mass</dt>
            <dd>{fmtMass(g.massG)}{g.massG > 0 ? ' (concept estimate)' : ''}</dd>
          </div>
          <div>
            <dt>Volume</dt>
            <dd>{g.volumeCm3 > 0 ? `${fmtMm(g.volumeCm3)} cm³` : '—'}</dd>
          </div>
          <div>
            <dt>Parts</dt>
            <dd>{g.parts.length}</dd>
          </div>
        </dl>
        <ul className="materials">
          {g.materials.map((m) => (
            <li key={m}>
              <Swatch material={m} /> {materialLabel(scene, m)}
            </li>
          ))}
        </ul>
        <button
          type="button"
          className="btn fill"
          onClick={() => {
            getViewer().apply({ isolate: g.id, style: g.id === 'internals' ? 'xray' : 'studio', explode: 0 })
            getViewer().frame(g.id)
            navigate('/studio')
          }}
        >
          View in Studio
        </button>
        <SectionHeader title="Drawing sheet" sub="Three views, iso, title block" />
        <Drawing group={g} />
        <p>
          <Link to={`/files/${g.id}/drawing`}>Open the drawing full screen</Link>
        </p>
        <SectionHeader title="Parts" sub={`${parts.length} in this group`} />
        <ul className="part-lines">
          {parts.map((p) => (
            <li key={p.id}>
              <Swatch material={p.material} />
              <span>
                <strong>{p.name}</strong>
                {p.internal ? <em> Internal</em> : null}
                <small>
                  {materialLabel(scene, p.material)}
                  {p.massNote ? ` · ${p.massNote}` : ''}
                </small>
              </span>
              <b>{fmtMass(p.massG)}</b>
            </li>
          ))}
        </ul>
        <SectionHeader title="Files" sub="Download the CAD export, in millimetres" />
        {files.map((file) => (
          <FileRow key={file.id} file={file} />
        ))}
      </div>
    </article>
  )
}

export function DrawingPage() {
  const { groupId } = useParams()
  const g = groupOf(scene, groupId) ?? scene.groups[0]
  const svg = filesOf(scene, g.id).find((f) => f.format === 'SVG')
  return (
    <article className="page drawing-page">
      <header>
        <BackLink to={`/files/${g.id}`}>{g.name}</BackLink>
        <h1>Drawing · {g.name}</h1>
        <p className="fine">Use the zoom buttons, or scroll while the pointer is over the sheet.</p>
        {svg ? <FileRow file={svg} /> : null}
      </header>
      <Drawing group={g} fill />
    </article>
  )
}

function Drawing({ group, fill = false }: { group: Group; fill?: boolean }) {
  const [scale, setScale] = useState(1)
  const src = `/${scene.drawings[group.id] ?? `drawings/${group.id}.png`}`
  return (
    <div className={fill ? 'drawing fill' : 'drawing'}>
      <div className="zoom" role="group" aria-label="Drawing zoom">
        <button type="button" onClick={() => setScale((s) => Math.max(0.5, Math.round((s - 0.25) * 100) / 100))}>
          Zoom out
        </button>
        <button type="button" onClick={() => setScale(1)}>
          {Math.round(scale * 100)}%
        </button>
        <button type="button" onClick={() => setScale((s) => Math.min(4, Math.round((s + 0.25) * 100) / 100))}>
          Zoom in
        </button>
      </div>
      <div
        className="sheet"
        onWheel={(e) => {
          if (!e.ctrlKey && Math.abs(e.deltaY) < 1) return
          e.preventDefault()
          setScale((s) => Math.min(4, Math.max(0.5, s * (e.deltaY > 0 ? 0.9 : 1.1))))
        }}
      >
        <img src={src} alt={`Engineering drawing sheet for ${group.name}: three views, isometric and title block`} style={{ transform: `scale(${scale})` }} />
      </div>
    </div>
  )
}

function FileRow({ file }: { file: CadFile }) {
  const href = assetUrl(file.path)
  const name = downloadName(file.path)
  return (
    <div className="file-row">
      <span className="badge">{file.format}</span>
      <span>
        <strong>{FORMAT_NOTES[file.format] ?? file.label}</strong>
        <small>
          {fmtBytes(file.bytes)} · {name}
        </small>
      </span>
      <a className="btn" href={href} download={name}>
        Download
      </a>
      <button type="button" className="btn" onClick={() => shareFile(file)}>
        Share
      </button>
    </div>
  )
}

async function shareFile(file: CadFile) {
  const url = new URL(assetUrl(file.path), window.location.origin).href
  const title = `Night Array · ${file.label || file.format} (${file.format})`
  if (navigator.share) {
    try {
      await navigator.share({ title, url })
      return
    } catch (err) {
      if ((err as Error).name === 'AbortError') return
    }
  }
  try {
    await navigator.clipboard.writeText(url)
    toast(`Link copied · ${downloadName(file.path)}`)
  } catch {
    toast('Could not share this file')
  }
}
