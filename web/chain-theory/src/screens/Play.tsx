import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Missing, TopBar, useGoBack, useTitle } from '../components/Chrome'
import { useContent } from '../guide'
import { DECK_MARKS, advanceQueue, clearsDeck, resultPresentation, shuffle, streakToast } from '../logic'
import { useStore } from '../store'
import type { Deck, Term } from '../types'

export function Play() {
  const { decks, glossary } = useContent()
  const store = useStore()
  useTitle('Play')
  return (
    <div className="stage-inner">
      <TopBar title="Play" subtitle="Clear a deck with 70%+ to forge a link" fallback="/" />
      <div className="pad stack">
        {decks.map((deck, index) => {
          const done = store.earned[`q${index}`] != null
          const best = store.best[index]
          return (
            <Link key={deck.name} className={done ? 'card deck done' : 'card deck'} to={`/quiz/${index}`}>
              <span className="mark" aria-hidden="true">
                {DECK_MARKS[index % DECK_MARKS.length]}
              </span>
              <span>
                <span className="kicker">
                  {deck.level} · {deck.questions.length} questions
                </span>
                <strong>{deck.name}</strong>
                <span className="muted">{deck.desc}</span>
                {best != null ? (
                  <span className="best">
                    Best: {best}/{deck.questions.length}
                  </span>
                ) : null}
              </span>
              {done ? <span className="check">Link forged</span> : null}
            </Link>
          )
        })}
        <Link className="card deck" to="/flash">
          <span className="mark violet" aria-hidden="true">
            🃏
          </span>
          <span>
            <span className="kicker">Flashcards · {glossary.length} cards</span>
            <strong>Glossary flip cards</strong>
            <span className="muted">Tap to flip. Cards you miss come back sooner. Known so far: {store.flashKnown}</span>
          </span>
        </Link>
      </div>
    </div>
  )
}

export function Quiz() {
  const { deck: deckParam = '' } = useParams()
  const index = Number(deckParam)
  const { decks } = useContent()
  const deck = Number.isInteger(index) ? decks[index] : undefined
  const [round, setRound] = useState(0)
  if (!deck) return <Missing title="Missing deck" body="That quiz is not in this edition." />
  return <QuizRound key={`${index}-${round}`} deck={deck} deckIndex={index} onAgain={() => setRound((value) => value + 1)} />
}

function QuizRound({ deck, deckIndex, onAgain }: { deck: Deck; deckIndex: number; onAgain: () => void }) {
  const store = useStore()
  const back = useGoBack('/play')
  const order = useMemo(() => shuffle(deck.questions.map((_, questionIndex) => questionIndex)), [deck])
  const [at, setAt] = useState(0)
  const [score, setScore] = useState(0)
  const [streak, setStreak] = useState(0)
  const [picked, setPicked] = useState<number | null>(null)
  const [finished, setFinished] = useState(false)
  const scoreRef = useRef(0)
  const optionOrder = useMemo(
    () => shuffle(deck.questions[order[at]].options.map((_, optionIndex) => optionIndex)),
    [deck, order, at],
  )
  const question = deck.questions[order[at]]
  const progress = (at + (picked != null ? 1 : 0)) / deck.questions.length
  useTitle(deck.name)

  function choose(option: number) {
    if (picked != null) return
    setPicked(option)
    if (option === question.answer) {
      const nextStreak = streak + 1
      scoreRef.current += 1
      setScore(scoreRef.current)
      setStreak(nextStreak)
      const note = streakToast(nextStreak)
      if (note) store.notify(note)
      pulse(true)
    } else {
      setStreak(0)
      pulse(false)
    }
  }

  function continueRound() {
    if (at + 1 < deck.questions.length) {
      setPicked(null)
      setAt((value) => value + 1)
      return
    }
    setFinished(true)
    store.quizResult(deckIndex, scoreRef.current, deck.questions.length)
  }

  return (
    <div className="quiz">
      <header className="quiz-bar">
        <button type="button" className="icon-btn" onClick={back} aria-label="Quit">
          ✕
        </button>
        <div className="meter" role="progressbar" aria-valuemin={0} aria-valuemax={deck.questions.length} aria-valuenow={at + (picked != null ? 1 : 0)}>
          <span style={{ width: `${progress * 100}%` }} />
        </div>
        <p className="streak">{streak >= 2 ? `🔥 ${streak}` : `⭐ ${score}`}</p>
      </header>
      {finished ? (
        <Results deck={deck} score={score} onAgain={onAgain} onBack={() => back()} />
      ) : (
        <div className="stage-inner narrow pad">
          <p className="kicker">
            {deck.name} · {at + 1} of {deck.questions.length}
          </p>
          <p id="q-text" className="question">
            {question.q}
          </p>
          <div className="options" role="group" aria-labelledby="q-text">
            {optionOrder.map((option) => {
              const state = picked == null ? 'idle' : option === question.answer ? 'right' : option === picked ? 'wrong' : 'dim'
              return (
                <button key={option} type="button" className={`option ${state}`} aria-disabled={picked != null} onClick={() => choose(option)}>
                  <span>{question.options[option]}</span>
                  {state === 'right' ? <span className="flag">Correct</span> : null}
                  {state === 'wrong' ? <span className="flag">Incorrect</span> : null}
                </button>
              )
            })}
          </div>
          {picked != null ? (
            <div className={picked === question.answer ? 'explain ok' : 'explain bad'}>
              <p className="explain-title">{picked === question.answer ? 'Correct!' : 'Not quite.'}</p>
              <p>{question.explain}</p>
              <button type="button" className="btn primary" onClick={continueRound}>
                {at + 1 < deck.questions.length ? 'Next' : 'See results'}
              </button>
            </div>
          ) : null}
        </div>
      )}
    </div>
  )
}

function Results({ deck, score, onAgain, onBack }: { deck: Deck; score: number; onAgain: () => void; onBack: () => void }) {
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  const [shown, setShown] = useState(reduce ? score : 0)
  const result = resultPresentation(score, deck.questions.length)
  useEffect(() => {
    if (reduce || score === 0) return
    let current = 0
    const timer = window.setInterval(() => {
      current += 1
      setShown(current)
      if (current >= score) window.clearInterval(timer)
    }, 90)
    return () => window.clearInterval(timer)
  }, [reduce, score])
  return (
    <div className="results">
      <p className="results-emoji" aria-hidden="true">
        {result.emoji}
      </p>
      <p className="results-score">
        {shown} / {deck.questions.length}
      </p>
      <p>{result.text}</p>
      {!clearsDeck(score, deck.questions.length) ? null : <p className="sr-only">Deck cleared.</p>}
      <button type="button" className="btn primary" onClick={onAgain}>
        Play again
      </button>
      <button type="button" className="btn" onClick={onBack}>
        All decks
      </button>
    </div>
  )
}

function pulse(correct: boolean) {
  if (typeof navigator.vibrate === 'function') navigator.vibrate(correct ? 12 : 40)
}

export function Flash() {
  const { glossary } = useContent()
  const store = useStore()
  const back = useGoBack('/play')
  const [queue, setQueue] = useState<Term[]>(() => shuffle(glossary))
  const [flipped, setFlipped] = useState(false)
  const [leaving, setLeaving] = useState<'left' | 'right' | null>(null)
  const lock = useRef(false)
  const advanceRef = useRef<(known: boolean) => void>(() => undefined)
  useTitle('Flashcards')

  function advance(known: boolean) {
    if (lock.current || queue.length === 0) return
    lock.current = true
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    setLeaving(known ? 'right' : 'left')
    window.setTimeout(() => {
      setQueue((current) => advanceQueue(current, known))
      if (known) store.knowCard()
      setFlipped(false)
      setLeaving(null)
      lock.current = false
    }, reduce ? 0 : 180)
  }
  advanceRef.current = advance

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const tag = (event.target as HTMLElement | null)?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA') return
      if (event.key === 'ArrowLeft') advanceRef.current(false)
      if (event.key === 'ArrowRight') advanceRef.current(true)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const card = queue[0]
  return (
    <div className="flash">
      <header className="quiz-bar">
        <button type="button" className="icon-btn" onClick={back} aria-label="Close">
          ✕
        </button>
        <h1>Flashcards</h1>
        <p className="streak">Known {store.flashKnown}</p>
      </header>
      {card ? (
        <button
          type="button"
          className={`flash-card${flipped ? ' back' : ''}${leaving ? ` leave-${leaving}` : ''}`}
          aria-pressed={flipped}
          onClick={() => setFlipped((value) => !value)}
        >
          {flipped ? <span className="def">{card.d}</span> : <span className="term">{card.t}</span>}
          <span className="hint">{flipped ? 'Tap for the term' : 'Tap to flip'}</span>
        </button>
      ) : (
        <p className="pad">No cards in this glossary.</p>
      )}
      <p className="fine center">Arrow left: again. Arrow right: knew it.</p>
      <div className="flash-actions">
        <button type="button" className="btn" onClick={() => advance(false)}>
          Again
        </button>
        <button type="button" className="btn primary" onClick={() => advance(true)}>
          Knew it
        </button>
      </div>
    </div>
  )
}
