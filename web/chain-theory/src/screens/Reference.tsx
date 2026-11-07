import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { BlockList } from '../components/Blocks'
import { FontButton, TopBar, useTitle } from '../components/Chrome'
import { useContent } from '../guide'
import {
  LETTER_INPUT,
  alphaInverse,
  consistentWithExperiment,
  formatInverse,
  formatSigma,
  needlePosition,
  sigmaFromMeasurement,
  type AlphaInput,
} from '../logic'
import { useStore } from '../store'
import type { Block, Part } from '../types'

export function MapScreen() {
  const content = useContent()
  const { earn, fontScale } = useStore()
  useTitle('Compendium map')
  useEffect(() => {
    const timer = window.setTimeout(() => earn('l4'), 2500)
    return () => window.clearTimeout(timer)
  }, [earn])
  const intro = content.articles.l4.filter((block) => block.k !== 'kicker')
  return (
    <div className="stage-inner">
      <TopBar title="Compendium map" fallback="/learn" heading={false} actions={<FontButton />} />
      <div className="pad" style={{ ['--scale' as string]: fontScale }}>
        <BlockList blocks={intro} />
        <div className="stack">
          {content.parts.map((part) => (
            <PartCard key={part.title} part={part} />
          ))}
        </div>
      </div>
    </div>
  )
}

function PartCard({ part }: { part: Part }) {
  const [open, setOpen] = useState(false)
  return (
    <article className="card part">
      <button type="button" className="part-toggle" aria-expanded={open} onClick={() => setOpen((value) => !value)}>
        <span>{part.title}</span>
        <span aria-hidden="true">{open ? '▾' : '▸'}</span>
      </button>
      {part.counts ? <GradeBar counts={part.counts} /> : null}
      {open ? (
        <div className="part-body">
          <p>{part.desc}</p>
          {part.page != null ? <Link to={`/reader/comp/${part.page}`}>Read from p. {part.page}</Link> : null}
        </div>
      ) : null}
    </article>
  )
}

function GradeBar({ counts }: { counts: number[] }) {
  const total = Math.max(1, counts.reduce((sum, count) => sum + count, 0))
  const parts = [
    { n: counts[0] ?? 0, tone: 'thm', label: 'thm' },
    { n: counts[1] ?? 0, tone: 'cond', label: 'cond' },
    { n: counts[2] ?? 0, tone: 'open', label: 'open' },
  ]
  return (
    <div className="grades">
      <div className="grade" role="img" aria-label={parts.map((part) => `${part.n} ${part.label}`).join(', ')}>
        {parts.map((part) =>
          part.n > 0 ? <span key={part.tone} className={part.tone} style={{ flexGrow: part.n / total }} /> : null,
        )}
      </div>
      <div className="pills">
        {parts.map((part) => (
          <span key={part.tone} className={`pill ${part.tone}`}>
            {part.n} {part.label}
          </span>
        ))}
      </div>
    </div>
  )
}

export function Calc() {
  const content = useContent()
  const { earn } = useStore()
  const [input, setInput] = useState<AlphaInput>(LETTER_INPUT)
  const [touched, setTouched] = useState(false)
  useTitle('α calculator')
  useEffect(() => {
    if (!touched) return
    const timer = window.setTimeout(() => earn('calc'), 500)
    return () => window.clearTimeout(timer)
  }, [touched, earn])

  const inverse = alphaInverse(input)
  const sigma = sigmaFromMeasurement(inverse)
  const ok = Number.isFinite(inverse) && consistentWithExperiment(sigma)
  const needle = needlePosition(sigma)
  const touch = () => setTouched(true)
  const rest = useMemo(() => dropUntilHeading(content.articles.calc), [content])

  return (
    <div className="stage-inner narrow">
      <TopBar title="α calculator" fallback="/learn" heading={false} />
      <div className="pad">
        <section className={ok ? 'readout ok' : 'readout bad'} aria-live="polite">
          <p className="muted">1 / α =</p>
          <p className="readout-value">{formatInverse(inverse)}</p>
          <p className="fine">measured (CODATA 2022): 137.035999177 ± 21</p>
          <div className="sigma-meter" aria-hidden="true">
            <span className="wing" />
            <span className="band" />
            <span className="wing" />
            <i style={{ left: `${50 + needle * 50}%` }} />
          </div>
          <p className="readout-sigma">{formatSigma(sigma)}</p>
          <p>{ok ? 'Consistent with experiment' : 'Ruled out by experiment'}</p>
        </section>
        <h2 className="section-label">Counts × weights</h2>
        <Stepper label={input.useK ? 'Weight 1 (antisymmetric)' : 'Weight 1 (antisymmetric)'} value={input.c1} step={1} onChange={(c1) => { setInput({ ...input, c1 }); touch() }} />
        <Stepper label={input.useK ? 'Weight 2' : 'Weight √2 (one slot each end)'} value={input.c2} step={1} onChange={(c2) => { setInput({ ...input, c2 }); touch() }} />
        <Stepper label={input.useK ? 'Weight 3' : 'Weight √3 (both slots one kind)'} value={input.c3} step={1} onChange={(c3) => { setInput({ ...input, c3 }); touch() }} />
        <Stepper label={input.useK ? 'Weight 6' : 'Weight √6 (commutators)'} value={input.c6} step={1} onChange={(c6) => { setInput({ ...input, c6 }); touch() }} />
        <Stepper label="Denominator N" value={input.n} step={24} onChange={(n) => { setInput({ ...input, n }); touch() }} />
        <label className="switch">
          <input
            type="checkbox"
            checked={input.useK}
            onChange={(event) => {
              setInput({ ...input, useK: event.target.checked })
              touch()
            }}
          />
          Use weights k instead of √k
        </label>
        <div className="chip-row">
          <button type="button" className="btn" onClick={() => setInput(LETTER_INPUT)}>
            Reset to the Letter
          </button>
          <button
            type="button"
            className="btn"
            onClick={() => {
              setInput({ c1: 172, c2: 0, c3: 0, c6: 0, n: input.n, useK: false })
              touch()
            }}
          >
            No weights
          </button>
          <button
            type="button"
            className="btn"
            onClick={() => {
              setInput({ ...LETTER_INPUT, useK: true })
              touch()
            }}
          >
            k not √k
          </button>
        </div>
        <BlockList blocks={rest} />
      </div>
    </div>
  )
}

function Stepper({ label, value, step, onChange }: { label: string; value: number; step: number; onChange: (value: number) => void }) {
  const id = `step-${label.replace(/\W+/g, '-').toLowerCase()}`
  return (
    <div className="stepper">
      <label htmlFor={id}>{label}</label>
      <button type="button" aria-label={`Decrease ${label}`} onClick={() => onChange(Math.max(0, value - step))}>
        −
      </button>
      <output id={id}>{value}</output>
      <button type="button" aria-label={`Increase ${label}`} onClick={() => onChange(value + step)}>
        +
      </button>
    </div>
  )
}

function dropUntilHeading(blocks: Block[]): Block[] {
  const index = blocks.findIndex((block) => block.k === 'h3')
  return index < 0 ? [] : blocks.slice(index)
}

export function Glossary() {
  const { glossary } = useContent()
  const [query, setQuery] = useState('')
  useTitle('Glossary')
  const folded = query.trim().toLowerCase()
  const terms = glossary.filter((term) => !folded || term.t.toLowerCase().includes(folded) || term.d.toLowerCase().includes(folded))
  return (
    <div className="stage-inner narrow">
      <TopBar title="Glossary" subtitle={`${glossary.length} terms · tap to expand`} fallback="/learn" />
      <div className="pad">
        <label className="search-label" htmlFor="glossary-filter">
          Filter terms
        </label>
        <input id="glossary-filter" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Filter terms…" />
        <div className="stack">
          {terms.map((term) => (
            <TermRow key={term.t} term={term.t} definition={term.d} forceOpen={folded.length > 0} />
          ))}
        </div>
        <p>
          <Link to="/reader/comp/22">AWG&apos;s own Rosetta table, compendium p. 22</Link>
        </p>
      </div>
    </div>
  )
}

function TermRow({ term, definition, forceOpen }: { term: string; definition: string; forceOpen: boolean }) {
  const [open, setOpen] = useState(false)
  const shown = open || forceOpen
  return (
    <article className="card term">
      <button type="button" aria-expanded={shown} onClick={() => setOpen((value) => !value)}>
        {term}
      </button>
      {shown ? <p>{definition}</p> : null}
    </article>
  )
}
