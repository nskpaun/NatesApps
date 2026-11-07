import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { parseContent, parseDoc } from './content'
import {
  LETTER_INPUT,
  LINKS,
  advanceQueue,
  alphaInverse,
  applyEarn,
  chainCount,
  clearsDeck,
  consistentWithExperiment,
  formatInverse,
  formatSigma,
  initialProgress,
  isHeadingParagraph,
  nextFontScale,
  nextLink,
  readingReward,
  reduceProgress,
  resolveLink,
  resultPresentation,
  searchContent,
  sectionFor,
  sigmaFromMeasurement,
  snippetAround,
} from './logic'
import type { RawContent, RawDoc } from './types'

const assets = resolve(process.cwd(), '../../chain-theory/android/app/src/main/assets')
const content = parseContent(JSON.parse(readFileSync(resolve(assets, 'content.json'), 'utf8')) as RawContent)

describe('alpha calculator', () => {
  it('reproduces the Letter value inside the CODATA error bar', () => {
    const inverse = alphaInverse(LETTER_INPUT)
    expect(formatInverse(inverse)).toBe('137.035999190')
    const sigma = sigmaFromMeasurement(inverse)
    expect(sigma).toBeCloseTo(0.6, 1)
    expect(consistentWithExperiment(sigma)).toBe(true)
    expect(formatSigma(sigma)).toBe('+0.60σ from measurement')
  })

  it('rejects integer weights and an unweighted count', () => {
    const integerWeights = alphaInverse({ ...LETTER_INPUT, useK: true })
    expect(consistentWithExperiment(sigmaFromMeasurement(integerWeights))).toBe(false)
    const unweighted = alphaInverse({ c1: 172, c2: 0, c3: 0, c6: 0, n: 31104, useK: false })
    expect(unweighted).toBeCloseTo(31104 / 172, 8)
    expect(Math.abs(sigmaFromMeasurement(unweighted))).toBeGreaterThan(1e6)
    expect(formatSigma(sigmaFromMeasurement(unweighted))).toMatch(/million σ away/)
  })
})

describe('progress rules', () => {
  it('forges a chain link once, ignores unknown ids, and celebrates a full chain', () => {
    let state = initialProgress()
    state = applyEarn(state, 'nope', 1)
    expect(state.earned).toEqual({})
    state = applyEarn(state, 'l1', 1)
    state = applyEarn(state, 'l1', 2)
    expect(state.toast).toMatch(/Link forged: Read Level 1 · 1\/12/)
    expect(chainCount(state.earned)).toBe(1)
    state = applyEarn(state, 'primer', 3)
    expect(state.earned.primer).toBe(3)
    expect(chainCount(state.earned)).toBe(1)
    for (const link of LINKS) state = applyEarn(state, link.id, 4)
    expect(chainCount(state.earned)).toBe(12)
    expect(state.toast).toMatch(/Full chain/)
    expect(state.confetti).toBeGreaterThan(0)
  })

  it('clears a deck at 70 percent and remembers only a better score', () => {
    expect(clearsDeck(5, 8)).toBe(false)
    expect(clearsDeck(6, 8)).toBe(true)
    expect(clearsDeck(7, 10)).toBe(true)
    let state = reduceProgress(initialProgress(), { type: 'quizResult', deck: 0, score: 5, total: 8, now: 1 })
    expect(state.best[0]).toBe(5)
    expect(state.earned.q0).toBeUndefined()
    state = reduceProgress(state, { type: 'quizResult', deck: 0, score: 6, total: 8, now: 2 })
    expect(state.earned.q0).toBe(2)
    expect(state.confetti).toBe(2)
    state = reduceProgress(state, { type: 'quizResult', deck: 0, score: 4, total: 8, now: 3 })
    expect(state.best[0]).toBe(6)
    expect(resultPresentation(8, 8).emoji).toBe('🏆')
    expect(resultPresentation(6, 8).text).toMatch(/new link/)
    expect(resultPresentation(2, 8).emoji).toBe('🌀')
  })

  it('counts distinct source pages and known flashcards', () => {
    let state = initialProgress()
    for (let page = 1; page <= 4; page += 1) state = reduceProgress(state, { type: 'read', doc: 'alpha', page, now: 1 })
    state = reduceProgress(state, { type: 'read', doc: 'alpha', page: 2, now: 1 })
    expect(state.earned.letter).toBeUndefined()
    expect(readingReward('alpha', 4)).toBeNull()
    state = reduceProgress(state, { type: 'read', doc: 'alpha', page: 5, now: 9 })
    expect(state.earned.letter).toBe(9)
    expect(state.pos.alpha).toBe(5)
    for (let page = 1; page <= 25; page += 1) state = reduceProgress(state, { type: 'read', doc: 'comp', page, now: 3 })
    expect(state.earned.comp).toBe(3)
    for (let i = 0; i < 9; i += 1) state = reduceProgress(state, { type: 'know', now: 1 })
    expect(state.earned.flash).toBeUndefined()
    state = reduceProgress(state, { type: 'know', now: 8 })
    expect(state.flashKnown).toBe(10)
    expect(state.earned.flash).toBe(8)
  })

  it('toggles bookmarks and cycles the font', () => {
    let state = reduceProgress(initialProgress(), { type: 'bookmark', doc: 'comp', page: 46, label: 'Axiom' })
    expect(state.bookmarks).toEqual([{ doc: 'comp', page: 46, label: 'Axiom' }])
    state = reduceProgress(state, { type: 'bookmark', doc: 'comp', page: 46, label: 'Axiom' })
    expect(state.bookmarks).toEqual([])
    expect(nextFontScale(1)).toBe(1.12)
    expect(nextFontScale(1.25)).toBe(0.9)
    expect(nextLink({ l1: 1 })?.id).toBe('l2')
  })
})

describe('navigation and search', () => {
  it('maps in-content links the way the Android app does', () => {
    expect(resolveLink('#l2')).toBe('/article/l2')
    expect(resolveLink('#primer')).toBe('/article/primer')
    expect(resolveLink('#l4')).toBe('/map')
    expect(resolveLink('#read/comp/224')).toBe('/reader/comp/224')
    expect(resolveLink('#read/alpha/8')).toBe('/reader/alpha/8')
    expect(resolveLink('#library')).toBe('/library')
    expect(resolveLink('#home')).toBe('/')
  })

  it('uses 1-based outline pages and the depth-1 section', () => {
    const alpha = parseDoc('alpha', JSON.parse(readFileSync(resolve(assets, 'alpha.json'), 'utf8')) as RawDoc)
    expect(alpha.pages).toHaveLength(24)
    expect(alpha.outline[0]?.page).toBe(1)
    expect(sectionFor(alpha.outline, 1)?.title).toBe('Abstract')
    const comp = JSON.parse(readFileSync(resolve(assets, 'comp.json'), 'utf8')) as RawDoc
    const talk = JSON.parse(readFileSync(resolve(assets, 'talk.json'), 'utf8')) as RawDoc
    expect(comp.pages).toHaveLength(754)
    expect(talk.pages).toHaveLength(71)
  })

  it('finds guide text, snippets, and headings', () => {
    const { hits, total } = searchContent(content, [], '31104', 'guide')
    expect(total).toBeGreaterThan(0)
    expect(hits.some((hit) => hit.route === '/article/l3' && hit.match === '31104')).toBe(true)
    expect(hits.length).toBeLessThanOrEqual(total)
    const snippet = snippetAround('abcdefghij TARGET afterwards', 11, 'TARGET')
    expect(snippet.match).toBe('TARGET')
    expect(isHeadingParagraph('The axiom')).toBe(true)
    expect(isHeadingParagraph('This is a sentence.')).toBe(false)
    expect(content.decks.map((deck) => deck.questions.length)).toEqual([8, 9, 10, 8])
    expect(content.parts).toHaveLength(19)
    expect(content.glossary).toHaveLength(49)
    expect(LINKS).toHaveLength(12)
  })

  it('puts a missed flashcard three cards back', () => {
    expect(advanceQueue(['a', 'b', 'c', 'd', 'e'], false)).toEqual(['b', 'c', 'd', 'a', 'e'])
    expect(advanceQueue(['a', 'b', 'c', 'd', 'e'], true)).toEqual(['b', 'c', 'd', 'e', 'a'])
    expect(advanceQueue(['a', 'b'], false)).toEqual(['b', 'a'])
  })
})
