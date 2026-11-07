import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { TopBar, useTitle } from '../components/Chrome'
import { loadDocs } from '../content'
import { useContent } from '../guide'
import { searchContent } from '../logic'
import { useStore } from '../store'
import type { Doc, Hit } from '../types'

const FILTERS = [
  { id: 'all', label: 'All' },
  { id: 'guide', label: 'Guide' },
  { id: 'talk', label: 'Talk' },
  { id: 'alpha', label: 'Letter' },
  { id: 'comp', label: 'Compendium' },
]
const SUGGESTIONS = ['Higgs', 'Born rule', 'confinement', 'dark matter', 'Lorentz', 'three generations', 'Koide', 'cosmological', 'proton']

let rememberedQuery = ''
let rememberedFilter = 'all'

export function Search() {
  const content = useContent()
  const { earn } = useStore()
  const [query, setQuery] = useState(rememberedQuery)
  const [filter, setFilter] = useState(rememberedFilter)
  const [hits, setHits] = useState<Hit[]>([])
  const [total, setTotal] = useState(0)
  const [busy, setBusy] = useState(false)
  useTitle('Search')

  useEffect(() => {
    rememberedQuery = query
    rememberedFilter = filter
    const trimmed = query.trim()
    if (trimmed.length < 2) {
      setHits([])
      setTotal(0)
      setBusy(false)
      return
    }
    let cancel = false
    setBusy(true)
    const timer = window.setTimeout(() => {
      void loadDocs(filter)
        .then((docs: Doc[]) => {
          if (cancel) return
          const result = searchContent(content, docs, trimmed, filter)
          setHits(result.hits)
          setTotal(result.total)
          setBusy(false)
          if (result.total > 0) earn('search')
        })
        .catch(() => {
          if (!cancel) {
            setBusy(false)
            setHits([])
            setTotal(0)
          }
        })
    }, 250)
    return () => {
      cancel = true
      window.clearTimeout(timer)
    }
  }, [query, filter, content, earn])

  return (
    <div className="stage-inner">
      <TopBar title="Search" subtitle="Every word of the guide and all three documents" fallback="/" />
      <div className="pad">
        <form role="search" onSubmit={(event) => event.preventDefault()}>
          <label className="search-label" htmlFor="search-q">
            Search
          </label>
          <input
            id="search-q"
            type="search"
            value={query}
            placeholder="e.g. Higgs, Born rule, 31104, confinement"
            onChange={(event) => setQuery(event.target.value)}
          />
        </form>
        <div className="chip-row" role="group" aria-label="Limit search to">
          {FILTERS.map((item) => (
            <button key={item.id} type="button" className={filter === item.id ? 'btn on' : 'btn'} aria-pressed={filter === item.id} onClick={() => setFilter(item.id)}>
              {item.label}
            </button>
          ))}
        </div>
        {busy ? <p className="muted">Searching…</p> : null}
        {query.trim().length >= 2 && !busy ? (
          <p className="muted" role="status">
            {total === 0 ? 'No matches.' : `${total} matches${hits.length >= 300 ? ' (showing first 300)' : ''}`}
          </p>
        ) : null}
        {query.trim() === '' ? (
          <div>
            <p className="muted">Try:</p>
            <div className="chip-row">
              {SUGGESTIONS.map((suggestion) => (
                <button key={suggestion} type="button" className="btn" onClick={() => setQuery(suggestion)}>
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        ) : null}
        <div className="stack hits">
          {hits.map((hit, index) => (
            <Link key={`${hit.route}-${index}`} className="card hit" to={hit.route}>
              <span className="where">{hit.where}</span>
              <span>
                {hit.pre}
                <mark>{hit.match}</mark>
                {hit.post}
              </span>
            </Link>
          ))}
        </div>
      </div>
    </div>
  )
}
