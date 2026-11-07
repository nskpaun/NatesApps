import { Link } from 'react-router-dom'
import { BOARD_NOTE, MODES, PRINCIPLES, STORIES } from '../lib/content'
import { scene } from '../lib/scene'
import { coreTotal, kit } from '../lib/kit'
import { fmtNum, fmtUsd } from '../lib/format'
import { Kicker, SectionHeader, Still, Tagline } from '../components/ui'
import { useOpenStudio } from '../components/Stage'

export function Explore() {
  const openStudio = useOpenStudio()
  const sc = scene.screen
  const wide = typeof window !== 'undefined' ? window.matchMedia('(min-width: 900px)').matches : false
  return (
    <article className="page explore">
      <header className="hero">
        <Still names={['hero-work.jpg', 'hero-stow.jpg']} alt="Night Array in Work mode at night" />
        <div className="hero-copy">
          <p className="eyebrow">Concept explorer</p>
          <h1>
            Night Array <em>/ Work & Stow</em>
          </h1>
          <p className="lede-kicker">Integrated superwide workstation</p>
          <Tagline>{scene.tagline}</Tagline>
          <div className="row">
            <button type="button" className="btn fill" onClick={() => openStudio({ mode: 'work', camera: 'hero' })}>
              Open the Studio
            </button>
            <Link className="btn" to="/night">
              Night shift
            </Link>
          </div>
        </div>
      </header>

      <section className="measure">
        <p className="intro">
          A double-wide display on a long titanium base, a vertical laptop dock on the right wing, and pockets in the deck that charge your keyboard and mouse while they're put away.
        </p>
        <dl className="stats">
          <div>
            <dt>One canvas</dt>
            <dd>
              {sc.canvasW} × {sc.canvasH}
            </dd>
          </div>
          <div>
            <dt>Mainstream QHD</dt>
            <dd>
              {sc.panels} × {fmtNum(sc.panelInch)}″
            </dd>
          </div>
          <div>
            <dt>The honest seam</dt>
            <dd>{fmtNum(sc.seamMm)} mm</dd>
          </div>
          <div>
            <dt>Cable on the desk</dt>
            <dd>1</dd>
          </div>
        </dl>
        <p className="fine">
          This is a concept study, not a live device. The 3D model, drawings and masses come from the parametric CAD. The shopping list uses the recorded parts and prices. Nothing here connects to hardware.
        </p>
      </section>

      <section className="block">
        <SectionHeader title="Three modes" sub="One footprint, three states" />
        <div className={wide ? 'cards three' : 'cards scroll'}>
          {MODES.map((mode) => (
            <button key={mode.id} type="button" className="card" onClick={() => openStudio({ mode: mode.id, style: 'studio', camera: mode.camera, explode: 0 })}>
              <Still names={[mode.still]} alt="" />
              <div className="card-body">
                <h3>{mode.title}</h3>
                <p className="sub">{mode.sub}</p>
                <p>{mode.body}</p>
                <Kicker>Open in Studio</Kicker>
              </div>
            </button>
          ))}
        </div>
      </section>

      <section className="block">
        <SectionHeader title="Stories" sub="Eight ways into the station" />
        <div className="story-grid">
          {STORIES.map((story) => (
            <Link key={story.id} className="story-row" to={`/story/${story.id}`}>
              <Still names={story.stills.map((s) => s.name)} alt="" />
              <span>
                <span className="micro">
                  {story.number} · {story.kicker}
                </span>
                <strong>{story.title}</strong>
                <em>{story.line}</em>
              </span>
            </Link>
          ))}
        </div>
      </section>

      <section className="block measure">
        <SectionHeader title="Docking" sub="1 Align · 2 Lower · 3 Lift out" />
        <p>The dock is latch-free. Guide the laptop into the open cradle, its own weight seats it, and you lift it straight out.</p>
        <div className="dock-cards">
          {scene.dockSteps.map((step, i) => (
            <button key={step.step} type="button" className="card" onClick={() => openStudio({ mode: 'stow', camera: 'dock', dock: step.step })}>
              <Still names={[`dock-${step.step}.jpg`]} alt="" />
              <div className="card-body">
                <h3>
                  {i + 1} · {step.title}
                </h3>
                <p>{step.caption}</p>
              </div>
            </button>
          ))}
        </div>
      </section>

      <section className="block measure">
        <SectionHeader title="Finishes" sub="The metal, three ways" />
        <div className="finish-row">
          {(
            [
              ['titanium', 'Neutral Titanium', 'finish-titanium.jpg'],
              ['graphite', 'Charcoal Graphite', 'finish-graphite.jpg'],
              ['oxblood', 'Brushed Oxblood', 'finish-oxblood.jpg'],
            ] as const
          ).map(([id, label, still]) => (
            <button key={id} type="button" className="card" onClick={() => openStudio({ mode: 'stow', style: 'studio', finish: id, camera: 'hero' })}>
              <Still names={[still]} alt={label} />
              <div className="card-body">
                <h3>{label}</h3>
                <p>{scene.materials[id]?.spec}</p>
              </div>
            </button>
          ))}
        </div>
      </section>

      <section className="block">
        <SectionHeader title="Principles" sub="How the station was decided" />
        <ol className="principles">
          {PRINCIPLES.map((p) => (
            <li key={p.title}>
              <h3>{p.title}</h3>
              <p>{p.body}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="block measure">
        <SectionHeader title="Where it started" sub="The original concept board" />
        <Link className="card board-card" to="/board">
          <img src="/concept/board.jpg" alt="The original Night Array concept board, a single curved ultrawide" />
          <div className="card-body">
            <p>{BOARD_NOTE}</p>
            <Kicker>Open the board</Kicker>
          </div>
        </Link>
      </section>

      <section className="block measure">
        <SectionHeader title="Build your own" sub="The real parts list" />
        <Link className="card build-card" to="/specs/buy">
          <div className="card-body">
            <p>Two stock 27″ monitors, a USB-C dock, off-the-shelf peripherals, a cut steel frame and printed panels.</p>
            <p className="price">{fmtUsd(coreTotal(kit, false))}</p>
            <p className="sub">Core parts · prices checked {kit.pricesChecked}</p>
            <Kicker>Open the shopping list</Kicker>
          </div>
        </Link>
      </section>

      <section className="block measure">
        <SectionHeader title="Night shift" sub="Ambient mode" />
        <Link className="card" to="/night">
          <Still names={['night.jpg', 'hero-stow.jpg']} alt="Night Array orbiting in the dark" />
          <div className="card-body">
            <Tagline size="1.2rem">Leave it running at the end of the day.</Tagline>
            <p>A slow orbit around the station in the dark, lit only by its own amber.</p>
            <Kicker>Start Night shift</Kicker>
          </div>
        </Link>
      </section>

      <footer className="foot">
        <Tagline>{scene.tagline}</Tagline>
        <p>Night Array · Work & Stow</p>
        <p className="fine">Dimensions come from the parametric CAD model. Masses are concept estimates.</p>
      </footer>
    </article>
  )
}
