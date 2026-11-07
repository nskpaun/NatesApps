import type { Content, Doc, RawContent, RawDoc } from './types'
import { DOC_KEYS, type DocKey } from './logic'

export function parseContent(raw: RawContent): Content {
  return {
    articles: {
      l1: raw.l1,
      l2: raw.l2,
      primer: raw.primer,
      l3: raw.l3,
      l4: raw.l4,
      calc: raw.calc,
    },
    glossary: raw.glossary,
    parts: raw.parts.map(([title, desc, page, counts]) => ({ title, desc, page, counts })),
    decks: raw.decks.map((deck) => ({
      name: deck.name,
      level: deck.lv,
      desc: deck.desc,
      questions: deck.qs.map(([q, options, answer, explain]) => ({ q, options, answer, explain })),
    })),
  }
}

export function parseDoc(key: string, raw: RawDoc): Doc {
  return {
    key,
    title: raw.title,
    short: raw.short,
    pages: raw.pages,
    lower: raw.pages.map((page) => page.toLowerCase()),
    outline: raw.outline.map((item) => ({ title: item.t, depth: item.d, page: item.p + 1 })),
  }
}

let contentPromise: Promise<Content> | null = null
const docPromises = new Map<string, Promise<Doc>>()

export function loadContent(): Promise<Content> {
  if (!contentPromise) {
    contentPromise = fetch('/data/content.json')
      .then((response) => {
        if (!response.ok) throw new Error('Could not load the guide.')
        return response.json() as Promise<RawContent>
      })
      .then(parseContent)
      .catch((error) => {
        contentPromise = null
        throw error
      })
  }
  return contentPromise
}

export function loadDoc(key: string): Promise<Doc> {
  let pending = docPromises.get(key)
  if (!pending) {
    pending = fetch(`/data/${key}.json`)
      .then((response) => {
        if (!response.ok) throw new Error(`Could not open ${key}.`)
        return response.json() as Promise<RawDoc>
      })
      .then((raw) => parseDoc(key, raw))
      .catch((error) => {
        docPromises.delete(key)
        throw error
      })
    docPromises.set(key, pending)
  }
  return pending
}

export function loadDocs(filter: string): Promise<Doc[]> {
  const keys: DocKey[] =
    filter === 'guide'
      ? []
      : filter === 'all'
        ? [...DOC_KEYS]
        : DOC_KEYS.includes(filter as DocKey)
          ? [filter as DocKey]
          : []
  return Promise.all(keys.map((key) => loadDoc(key)))
}

export function isDocKey(value: string): value is DocKey {
  return (DOC_KEYS as readonly string[]).includes(value)
}
