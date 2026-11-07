import type { Block, Bookmark, Content, Doc, Hit, OutlineItem, TextBlock } from './types'

/** The twelve progress links, in the order the Android app forges and displays them. */
export const LINKS = [
  { id: 'l1', label: 'Read Level 1', target: '#l1' },
  { id: 'l2', label: 'Read Level 2', target: '#l2' },
  { id: 'l3', label: 'Read Level 3', target: '#l3' },
  { id: 'l4', label: 'Explore the compendium map', target: '#l4' },
  { id: 'calc', label: 'Break the formula in the α calculator', target: '#calc' },
  { id: 'q0', label: 'Clear the Basics quiz', target: '#play' },
  { id: 'q1', label: 'Clear the Big Picture quiz', target: '#play' },
  { id: 'q2', label: 'Clear the Math quiz', target: '#play' },
  { id: 'flash', label: 'Know 10 flashcards', target: '#flash' },
  { id: 'letter', label: 'Read 5 pages of the alpha Letter', target: '#read/alpha/1' },
  { id: 'comp', label: 'Read 25 compendium pages', target: '#read/comp/2' },
  { id: 'search', label: 'Search the sources', target: '#search' },
] as const

export const DOC_KEYS = ['talk', 'alpha', 'comp'] as const
export type DocKey = (typeof DOC_KEYS)[number]

export const DOC_SHORT: Record<string, string> = { talk: 'Talk', alpha: 'Letter', comp: 'Compendium' }

export const DOC_INFO: { key: DocKey; title: string; desc: string; mark: string; pages: number }[] = [
  {
    key: 'talk',
    title: 'An Introduction to Chain Theory',
    desc: 'The talk slides. The best structured walk-through: motivation, axiom, the α count, Lean, the compendium.',
    mark: '🎤',
    pages: 71,
  },
  {
    key: 'alpha',
    title: 'A Parameter-Free Candidate for the Fine-Structure Constant',
    desc: 'The alpha Letter plus Supplemental Material. The sharp, short claim.',
    mark: 'α',
    pages: 24,
  },
  {
    key: 'comp',
    title: 'Chain Theory: A Compendium of Preliminary Findings',
    desc: 'Working draft, release 0.1. Sixteen Parts, appendices, and 52 instrument chapters.',
    mark: '📚',
    pages: 754,
  },
]

export const LEVELS = [
  {
    n: '1',
    title: 'The 60-second version',
    desc: "What it says, why it matters, and whether it's settled. No physics needed.",
    route: '/article/l1',
    emoji: '⚡',
    time: '2 min',
  },
  {
    n: '2',
    title: 'The big picture',
    desc: "The 50-year drought, three clues, one axiom, chains vs strings, six kinds of link, proved vs conjectured.",
    route: '/article/l2',
    emoji: '🔭',
    time: '20 min',
  },
  {
    n: 'R',
    title: 'Kets & cross products',
    desc: 'A refresher: ket notation, entanglement, the transpose trick, and the cross product as an antisymmetric pair. Read before Level 3.',
    route: '/article/primer',
    emoji: '⟨ψ|',
    time: '15 min',
  },
  {
    n: '3',
    title: 'The math of α',
    desc: 'Qudits, the read cap at d₁d₂ ≤ 6, the gauge group, and the 172-record count step by step.',
    route: '/article/l3',
    emoji: '∑',
    time: '45 min',
  },
  {
    n: '4',
    title: 'Compendium map',
    desc: 'All sixteen Parts: what each claims and how its results are graded.',
    route: '/map',
    emoji: '🗺',
    time: 'browse',
  },
  {
    n: '5',
    title: 'The primary sources',
    desc: 'The talk, the alpha Letter, and the full 754-page compendium, plus the original PDFs.',
    route: '/library',
    emoji: '📚',
    time: 'the flight',
  },
] as const

export const DECK_MARKS = ['⚡', '🔭', '∑', '🧠']

export const FONT_STEPS = [0.9, 1, 1.12, 1.25]

export const MEASURED_INVERSE_ALPHA = 137.035999177
export const MEASURED_UNCERTAINTY = 0.000000021

export const FULL_CHAIN_TOAST = '🏆 Full chain! You are now dangerously qualified to argue about α on a plane.'

export type AlphaInput = {
  c1: number
  c2: number
  c3: number
  c6: number
  n: number
  useK: boolean
}

export const LETTER_INPUT: AlphaInput = { c1: 79, c2: 48, c3: 42, c6: 3, n: 31104, useK: false }

const WS = /\s+/g

export function alphaInverse(input: AlphaInput): number {
  const w2 = input.useK ? 2 : Math.sqrt(2)
  const w3 = input.useK ? 3 : Math.sqrt(3)
  const w6 = input.useK ? 6 : Math.sqrt(6)
  const numerator = input.c1 + input.c2 * w2 + input.c3 * w3 + input.c6 * w6
  if (numerator === 0) return Number.POSITIVE_INFINITY
  return input.n / numerator
}

export function sigmaFromMeasurement(inverse: number): number {
  return (inverse - MEASURED_INVERSE_ALPHA) / MEASURED_UNCERTAINTY
}

export function consistentWithExperiment(sigma: number): boolean {
  return Math.abs(sigma) < 2
}

export function formatInverse(inverse: number): string {
  if (!Number.isFinite(inverse)) return '—'
  return inverse.toFixed(9)
}

export function formatSigma(sigma: number): string {
  if (Math.abs(sigma) < 1e4) {
    const sign = sigma >= 0 ? '+' : ''
    return `${sign}${sigma.toFixed(2)}σ from measurement`
  }
  return `${(Math.abs(sigma) / 1e6).toFixed(1)} million σ away`
}

export function needlePosition(sigma: number): number {
  return Math.max(-1, Math.min(1, sigma / 6))
}

export function clearsDeck(score: number, total: number): boolean {
  return score >= total * 0.7
}

export function resultPresentation(score: number, total: number): { emoji: string; text: string } {
  const pct = total === 0 ? 0 : score / total
  if (pct === 1) return { emoji: '🏆', text: 'Flawless. Maximally entangled with the material.' }
  if (pct >= 0.7) return { emoji: '⛓', text: 'Deck cleared! A new link is forged.' }
  if (pct >= 0.4) {
    return { emoji: '🤔', text: 'You need 70% to forge this link. Review the level and try again.' }
  }
  return { emoji: '🌀', text: 'You need 70% to forge this link. Review the level and try again.' }
}

export function streakToast(streak: number): string | null {
  if (streak === 3) return '🔥 3 in a row!'
  if (streak === 5) return '🔥🔥 5 streak. Entangled with the truth.'
  return null
}

export function nextFontScale(current: number): number {
  const index = FONT_STEPS.findIndex((step) => Math.abs(step - current) < 0.01)
  return FONT_STEPS[(Math.max(index, 0) + 1) % FONT_STEPS.length]
}

export function chainCount(earned: Record<string, number>): number {
  return LINKS.filter((link) => earned[link.id] != null).length
}

export function nextLink(earned: Record<string, number>) {
  return LINKS.find((link) => earned[link.id] == null) ?? null
}

export function levelDoneId(route: string): string {
  switch (route) {
    case '/article/l1':
      return 'l1'
    case '/article/l2':
      return 'l2'
    case '/article/l3':
      return 'l3'
    case '/map':
      return 'l4'
    case '/article/primer':
      return 'primer'
    default:
      return 'comp'
  }
}

export function resolveLink(href: string): string {
  const bare = href.replace(/^#/, '').split('?')[0]
  if (bare === 'l1' || bare === 'l2' || bare === 'l3' || bare === 'primer') return `/article/${bare}`
  if (bare === 'l4') return '/map'
  if (bare.startsWith('read/')) return `/reader/${bare.slice('read/'.length)}`
  if (bare === '' || bare === 'home') return '/'
  if (bare.startsWith('/')) return bare
  return `/${bare}`
}

export function tabOf(pathname: string): string {
  if (
    pathname.startsWith('/article') ||
    pathname === '/map' ||
    pathname === '/calc' ||
    pathname === '/glossary' ||
    pathname === '/learn'
  ) {
    return 'learn'
  }
  if (pathname.startsWith('/quiz') || pathname === '/flash' || pathname === '/play') return 'play'
  if (pathname.startsWith('/reader') || pathname === '/library') return 'library'
  if (pathname === '/search') return 'search'
  return 'home'
}

export function guideName(key: string): string {
  return (
    {
      primer: 'Refresher',
      l1: 'Level 1',
      l2: 'Level 2',
      l3: 'Level 3',
      l4: 'Compendium map',
      calc: 'α calculator',
    }[key] ?? key
  )
}

export function nextUp(key: string): { label: string; route: string } {
  switch (key) {
    case 'l1':
      return { label: 'Level 2 · The big picture', route: '/article/l2' }
    case 'l2':
      return { label: 'Refresher · Kets & cross products', route: '/article/primer' }
    case 'primer':
      return { label: 'Level 3 · The math', route: '/article/l3' }
    case 'l3':
      return { label: 'Test yourself: the Math quiz', route: '/quiz/2' }
    default:
      return { label: 'The full compendium', route: '/reader/comp/2' }
  }
}

export function quizForArticle(key: string): string | null {
  if (key === 'l1') return '/quiz/0'
  if (key === 'l2') return '/quiz/1'
  if (key === 'primer') return '/quiz/3'
  return null
}

export function sectionFor(outline: OutlineItem[], page: number): OutlineItem | null {
  let found: OutlineItem | null = null
  for (const item of outline) {
    if (item.page <= page && item.depth <= 1) found = item
  }
  return found
}

export function compFrontMatter(): OutlineItem[] {
  return [
    { title: 'Preface', depth: 1, page: 2 },
    { title: 'Contents', depth: 1, page: 6 },
    { title: 'Abstract & Introduction', depth: 1, page: 20 },
    { title: 'Rosetta glossary', depth: 1, page: 22 },
    { title: 'Register matrix', depth: 1, page: 36 },
  ]
}

export function shuffle<T>(items: readonly T[], random: () => number = Math.random): T[] {
  const copy = items.slice()
  for (let i = copy.length - 1; i > 0; i--) {
    const j = Math.floor(random() * (i + 1))
    const swap = copy[i]
    copy[i] = copy[j]
    copy[j] = swap
  }
  return copy
}

export function advanceQueue<T>(queue: readonly T[], known: boolean): T[] {
  if (queue.length === 0) return []
  const [card, ...rest] = queue
  if (known) return [...rest, card]
  const next = rest.slice()
  next.splice(Math.min(3, next.length), 0, card)
  return next
}

export function readingReward(doc: string, seenCount: number): string | null {
  if (doc === 'alpha' && seenCount >= 5) return 'letter'
  if (doc === 'comp' && seenCount >= 25) return 'comp'
  return null
}

export function isHeadingParagraph(paragraph: string): boolean {
  const first = paragraph[0]
  return (
    paragraph.length < 90 &&
    !paragraph.endsWith('.') &&
    (first != null && (first === first.toUpperCase() && first !== first.toLowerCase() || /\d/.test(first)))
  )
}

export function snippetAround(text: string, index: number, query: string): { pre: string; match: string; post: string } {
  const start = Math.max(0, index - 80)
  const end = Math.min(text.length, index + query.length + 130)
  const pre = (start > 0 ? '…' : '') + text.slice(start, index).replace(WS, ' ')
  const post = text.slice(index + query.length, end).replace(WS, ' ') + (end < text.length ? '…' : '')
  return { pre, match: text.slice(index, index + query.length), post }
}

function occurrences(haystack: string, needle: string): number[] {
  const found: number[] = []
  if (!needle) return found
  let index = haystack.indexOf(needle)
  while (index >= 0) {
    found.push(index)
    index = haystack.indexOf(needle, index + needle.length)
  }
  return found
}

function spanText(spans: TextBlock['s']): string {
  let text = ''
  for (const span of spans) text += span[0]
  return text
}

function pushHit(hits: Hit[], totalBox: { n: number }, where: string, text: string, index: number, query: string, route: string, cap: boolean) {
  totalBox.n += 1
  if (cap && hits.length >= 300) return
  const parts = snippetAround(text, index, query)
  hits.push({ where, route, ...parts })
}

export function searchContent(content: Content, docs: Doc[], queryRaw: string, filter: string): { hits: Hit[]; total: number } {
  const query = queryRaw.trim()
  const folded = query.toLowerCase()
  const hits: Hit[] = []
  const totalBox = { n: 0 }
  if (!folded || folded.length < 2) return { hits, total: 0 }

  if (filter === 'all' || filter === 'guide') {
    const walk = (blocks: Block[], key: string) => {
      for (const block of blocks) {
        if ((block.k === 'callout' || block.k === 'card') && 'blocks' in block) {
          walk(block.blocks, key)
          continue
        }
        if (block.k === 'table' && 'rows' in block) {
          for (const row of block.rows) {
            for (const cell of row) {
              const text = spanText(cell.s)
              const index = text.toLowerCase().indexOf(folded)
              if (index >= 0) pushHit(hits, totalBox, `Guide · ${guideName(key)}`, text, index, query, `/article/${key}`, true)
            }
          }
          continue
        }
        if (!('s' in block)) continue
        const text = spanText(block.s)
        const index = text.toLowerCase().indexOf(folded)
        if (index < 0) continue
        const route = key === 'l4' ? '/map' : key === 'calc' ? '/calc' : `/article/${key}`
        pushHit(hits, totalBox, `Guide · ${guideName(key)}`, text, index, query, route, true)
      }
    }
    for (const [key, blocks] of Object.entries(content.articles)) walk(blocks, key)
    for (const term of content.glossary) {
      const text = `${term.t} — ${term.d}`
      const index = text.toLowerCase().indexOf(folded)
      if (index >= 0) pushHit(hits, totalBox, 'Glossary', text, index, query, '/glossary', false)
    }
  }

  for (const doc of docs) {
    if (filter !== 'all' && filter !== doc.key) continue
    doc.lower.forEach((lower, pageIndex) => {
      const found = occurrences(lower, folded)
      if (found.length === 0) return
      totalBox.n += found.length
      if (hits.length >= 300) return
      const section = sectionFor(doc.outline, pageIndex + 1)
      const where =
        `${doc.short} · p. ${pageIndex + 1}` +
        (section ? ` · ${section.title}` : '') +
        (found.length > 1 ? ` · ${found.length} hits` : '')
      const parts = snippetAround(doc.pages[pageIndex], found[0], query)
      hits.push({
        where,
        route: `/reader/${doc.key}/${pageIndex + 1}?q=${encodeURIComponent(query)}`,
        ...parts,
      })
    })
  }

  return { hits, total: totalBox.n }
}

export type Progress = {
  earned: Record<string, number>
  best: Record<string, number>
  bookmarks: Bookmark[]
  lastDoc: string | null
  lastPage: number
  fontScale: number
  flashKnown: number
  seen: Record<string, string[]>
  pos: Record<string, number>
  toast: string | null
  confetti: number
}

export function initialProgress(): Progress {
  return {
    earned: {},
    best: {},
    bookmarks: [],
    lastDoc: null,
    lastPage: 1,
    fontScale: 1,
    flashKnown: 0,
    seen: {},
    pos: {},
    toast: null,
    confetti: 0,
  }
}

export type ProgressAction =
  | { type: 'earn'; id: string; now?: number }
  | { type: 'quizResult'; deck: number; score: number; total: number; now?: number }
  | { type: 'read'; doc: string; page: number; now?: number }
  | { type: 'bookmark'; doc: string; page: number; label: string }
  | { type: 'font' }
  | { type: 'know'; now?: number }
  | { type: 'toast'; message: string | null }
  | { type: 'confetti' }

function chainToast(id: string, count: number): string {
  if (count === LINKS.length) return FULL_CHAIN_TOAST
  const label = LINKS.find((link) => link.id === id)?.label ?? id
  return `⛓ Link forged: ${label} · ${count}/${LINKS.length}`
}

export function applyEarn(state: Progress, id: string, now = Date.now()): Progress {
  if (state.earned[id] != null) return state
  const chainLink = LINKS.some((link) => link.id === id)
  const marksRefresher = id === 'primer'
  if (!chainLink && !marksRefresher) return state
  const earned = { ...state.earned, [id]: now }
  if (!chainLink) return { ...state, earned }
  const count = chainCount(earned)
  return {
    ...state,
    earned,
    toast: chainToast(id, count),
    confetti: state.confetti + (count === LINKS.length ? 3 : 1),
  }
}

export function reduceProgress(state: Progress, action: ProgressAction): Progress {
  switch (action.type) {
    case 'earn':
      return applyEarn(state, action.id, action.now)
    case 'quizResult': {
      const previous = state.best[action.deck] ?? -1
      let next = state
      if (previous < action.score) next = { ...next, best: { ...next.best, [action.deck]: action.score } }
      if (clearsDeck(action.score, action.total)) {
        next = { ...next, confetti: next.confetti + 1 }
        next = applyEarn(next, `q${action.deck}`, action.now)
      }
      return next
    }
    case 'read': {
      const key = String(action.page)
      const previous = state.seen[action.doc] ?? []
      const already = previous.includes(key)
      if (already && state.lastDoc === action.doc && state.lastPage === action.page && state.pos[action.doc] === action.page) {
        return state
      }
      const seenList = already ? previous : [...previous, key]
      let next: Progress = {
        ...state,
        seen: already ? state.seen : { ...state.seen, [action.doc]: seenList },
        lastDoc: action.doc,
        lastPage: action.page,
        pos: { ...state.pos, [action.doc]: action.page },
      }
      const reward = readingReward(action.doc, seenList.length)
      if (reward) next = applyEarn(next, reward, action.now)
      return next
    }
    case 'bookmark': {
      const exists = state.bookmarks.some((mark) => mark.doc === action.doc && mark.page === action.page)
      const bookmarks = exists
        ? state.bookmarks.filter((mark) => !(mark.doc === action.doc && mark.page === action.page))
        : [...state.bookmarks, { doc: action.doc, page: action.page, label: action.label }]
      return { ...state, bookmarks }
    }
    case 'font':
      return { ...state, fontScale: nextFontScale(state.fontScale) }
    case 'know': {
      const flashKnown = state.flashKnown + 1
      let next: Progress = { ...state, flashKnown }
      if (flashKnown >= 10) next = applyEarn(next, 'flash', action.now)
      return next
    }
    case 'toast':
      return { ...state, toast: action.message }
    case 'confetti':
      return { ...state, confetti: state.confetti + 1 }
    default:
      return state
  }
}

export function pageParagraphs(text: string): string[] {
  return text.split('\n\n').filter((paragraph) => paragraph.trim().length > 0)
}
