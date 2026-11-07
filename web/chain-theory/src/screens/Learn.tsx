import { Link } from 'react-router-dom'
import { TopBar, useTitle } from '../components/Chrome'
import { LEVELS, levelDoneId } from '../logic'
import { useStore } from '../store'

export function Learn() {
  const store = useStore()
  useTitle('Learn')
  return (
    <div className="stage-inner">
      <TopBar title="Learn" fallback="/" />
      <div className="pad stack">
        {LEVELS.map((level) => {
          const done = store.earned[levelDoneId(level.route)] != null
          return (
            <Link className="card level" to={level.route} key={level.route}>
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
        })}
        <div className="tool-row">
          <Link className="card tool" to="/calc">
            <span aria-hidden="true">🧮</span>α calculator
          </Link>
          <Link className="card tool" to="/glossary">
            <span aria-hidden="true">📖</span>Glossary
          </Link>
        </div>
      </div>
    </div>
  )
}
