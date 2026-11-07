import { Link } from 'react-router-dom'
import { ChainHero } from '../components/ChainHero'
import { useTitle } from '../components/Chrome'
import { DOC_SHORT, LEVELS, LINKS, levelDoneId, nextLink, resolveLink } from '../logic'
import { useStore } from '../store'

export function Home() {
  const store = useStore()
  const upcoming = nextLink(store.earned)
  useTitle('Chain Theory Explorer')

  return (
    <div className="stage-inner">
      <section className="hero">
        <p className="kicker">Offline field guide</p>
        <h1>Chain Theory</h1>
        <p className="lede">
          Alex Wissner-Gross&apos;s attempt to rebuild physics from entangled qudits, from 60 seconds to all 754 pages.
        </p>
        <ChainHero lit={store.chain} total={LINKS.length} />
        <div className="chain-row">
          <p>
            {store.chain} / {LINKS.length} links forged
          </p>
          <div
            className="meter"
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={LINKS.length}
            aria-valuenow={store.chain}
            aria-label="Chain progress"
          >
            <span style={{ width: `${(store.chain / LINKS.length) * 100}%` }} />
          </div>
        </div>
        {upcoming ? (
          <Link className="next-link" to={resolveLink(upcoming.target)}>
            Next link: {upcoming.label} →
          </Link>
        ) : (
          <p className="done-line">Chain complete.</p>
        )}
      </section>

      {store.lastDoc ? (
        <Link className="card resume" to={`/reader/${store.lastDoc}/${store.lastPage}`}>
          <span className="kicker">Pick up where you left off</span>
          <strong>
            {DOC_SHORT[store.lastDoc] ?? store.lastDoc} · page {store.lastPage}
          </strong>
        </Link>
      ) : null}

      <section className="pad">
        <h2 className="section-label">Choose your depth</h2>
        <div className="stack">
          {LEVELS.map((level) => (
            <LevelCard key={level.route} level={level} done={store.earned[levelDoneId(level.route)] != null} />
          ))}
        </div>
        <h2 className="section-label">Tools</h2>
        <div className="tool-row">
          <Link className="card tool" to="/play">
            <span aria-hidden="true">🎮</span>Quiz
          </Link>
          <Link className="card tool" to="/calc">
            <span aria-hidden="true">🧮</span>α calc
          </Link>
          <Link className="card tool" to="/glossary">
            <span aria-hidden="true">📖</span>Glossary
          </Link>
        </div>
        <details className="chain-list">
          <summary>All {LINKS.length} links</summary>
          <ol>
            {LINKS.map((link) => {
              const forged = store.earned[link.id] != null
              return (
                <li key={link.id}>
                  <Link to={resolveLink(link.target)}>
                    {forged ? 'Forged' : 'Open'} · {link.label}
                  </Link>
                </li>
              )
            })}
          </ol>
        </details>
        <p className="fine">
          Chain Theory is days old (released Oct 23, 2026). The compendium is a &quot;working draft&quot; and the physics
          community hasn&apos;t evaluated it yet. This guide separates AWG&apos;s claims from established physics.
        </p>
      </section>
    </div>
  )
}

function LevelCard({
  level,
  done,
}: {
  level: (typeof LEVELS)[number]
  done: boolean
}) {
  return (
    <Link className="card level" to={level.route}>
      <span className="mark" aria-hidden="true">
        {level.emoji}
      </span>
      <span>
        <span className="kicker">{level.n === 'R' ? 'Refresher' : `Level ${level.n}`} · {level.time}</span>
        <strong>{level.title}</strong>
        <span className="muted">{level.desc}</span>
      </span>
      {done ? <span className="check">Done</span> : null}
    </Link>
  )
}
