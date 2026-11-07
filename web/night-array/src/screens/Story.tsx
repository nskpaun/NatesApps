import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { BOARD_NOTE, storyById, storySpecs } from '../lib/content'
import { displayWidthMm, scene } from '../lib/scene'
import { fmtMm, fmtNum } from '../lib/format'
import { BackLink, Kicker, Still, Tagline } from '../components/ui'
import { useOpenStudio } from '../components/Stage'

export function Story() {
  const { id } = useParams()
  const story = storyById(id)
  const openStudio = useOpenStudio()
  const [frame, setFrame] = useState(0)
  if (!story) {
    return (
      <article className="page measure">
        <BackLink to="/">Explore</BackLink>
        <h1>Story not found</h1>
        <p>That story is not part of this concept.</p>
      </article>
    )
  }
  const specs = storySpecs(story)
  const still = story.stills[frame] ?? story.stills[0]
  return (
    <article className="page story">
      <div className="gallery">
        <Still names={[still.name]} alt={still.caption} />
        {story.stills.length > 1 ? (
          <div className="pager" role="group" aria-label="Story stills">
            {story.stills.map((item, i) => (
              <button key={item.name} type="button" aria-pressed={i === frame} onClick={() => setFrame(i)}>
                {i + 1}
              </button>
            ))}
          </div>
        ) : null}
      </div>
      <div className="measure">
        <BackLink to="/">Explore</BackLink>
        <Kicker>
          {story.number} · {story.kicker}
        </Kicker>
        <h1>{story.title}</h1>
        <Tagline size="1.25rem">{story.line}</Tagline>
        <p className="intro">{story.lede}</p>
        <p className="caption">{still.caption}</p>
        {story.body.map((p) => (
          <p key={p}>{p}</p>
        ))}
        {story.id === 'dual' ? <DualDiagram /> : null}
        {story.id === 'dock' ? (
          <div className="dock-cards">
            {story.stills.map((item) => (
              <button key={item.name} type="button" className="card" onClick={() => openStudio({ mode: 'stow', camera: 'dock', dock: item.name.replace('dock-', '').replace('.jpg', '') })}>
                <Still names={[item.name]} alt={item.caption} />
                <div className="card-body">
                  <p>{item.caption}</p>
                </div>
              </button>
            ))}
          </div>
        ) : null}
        <dl className="spec-list">
          {specs.map((row) => (
            <div key={row.label}>
              <dt>{row.label}</dt>
              <dd>{row.value}</dd>
            </div>
          ))}
        </dl>
        <button type="button" className="btn fill" onClick={() => openStudio(story.preset)}>
          {story.liveLabel}
        </button>
      </div>
    </article>
  )
}

function DualDiagram() {
  const sc = scene.screen
  const toe = (sc.toeInDeg * Math.PI) / 180
  const facet = sc.seamMm / 2 + sc.activeMm[0] + 9
  const ox = facet * Math.cos(toe)
  const fwd = facet * Math.sin(toe)
  return (
    <figure className="diagram">
      <Kicker>Two displays, one canvas</Kicker>
      <svg viewBox="-700 -80 1400 520" role="img" aria-label={`Plan of two panels toed in ${fmtNum(sc.toeInDeg)} degrees with a ${fmtNum(sc.seamMm)} millimetre seam`}>
        <polyline points={`${-ox},${fwd} 0,0 ${ox},${fwd}`} fill="none" stroke="#F2EAE1" strokeWidth="8" strokeLinejoin="round" />
        <circle cx="0" cy="0" r="8" fill="#BDB2A4" />
        <text x="0" y="-24" textAnchor="middle" fill="#F2EAE1">
          {fmtNum(sc.seamMm)} mm seam
        </text>
        <text x={ox + 16} y={fwd / 2} fill="#A39A90">
          {Math.round(fwd)} mm forward
        </text>
        <text x="0" y={fwd + 48} textAnchor="middle" fill="#F2A04A">
          {fmtNum(sc.toeInDeg)}° toe-in · ≈ {fmtMm(displayWidthMm(scene))} mm
        </text>
      </svg>
      <div className="canvas-split" aria-hidden="true">
        <div>
          <span>Display 1</span>
          <span>
            {sc.resEach[0]} × {sc.resEach[1]}
          </span>
        </div>
        <i />
        <div>
          <span>Display 2</span>
          <span>
            {sc.resEach[0]} × {sc.resEach[1]}
          </span>
        </div>
      </div>
      <figcaption>
        Your OS sees two ordinary {fmtNum(sc.panelInch)}-inch displays. Together they make one {sc.canvasW} × {sc.canvasH} desktop, split at the mullion: snap a window to each half, or span one across both.
      </figcaption>
    </figure>
  )
}

export function Board() {
  return (
    <article className="page board">
      <div className="measure board-bar">
        <BackLink to="/">Explore</BackLink>
        <h1>Where it started</h1>
      </div>
      <img src="/concept/board.jpg" alt="Original Night Array concept board showing a single curved ultrawide, the base, trays, dock and amber light" />
      <p className="measure">{BOARD_NOTE}</p>
    </article>
  )
}
