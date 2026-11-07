export type Span = [text: string, style: string, link: string]

export type TextBlock = {
  k: string
  s: Span[]
  n?: number | null
  id?: string | null
}

export type ContainerBlock = {
  k: 'callout' | 'card'
  kind?: string
  blocks: Block[]
}

export type TableCell = { h: boolean; s: Span[] }
export type TableBlock = { k: 'table'; rows: TableCell[][] }
export type Block = TextBlock | ContainerBlock | TableBlock

export type Term = { t: string; d: string }
export type Part = { title: string; desc: string; page: number | null; counts: number[] | null }
export type Question = { q: string; options: string[]; answer: number; explain: string }
export type Deck = { name: string; level: string; desc: string; questions: Question[] }

export type Content = {
  articles: Record<string, Block[]>
  glossary: Term[]
  parts: Part[]
  decks: Deck[]
}

export type OutlineItem = { title: string; depth: number; page: number }

export type Doc = {
  key: string
  title: string
  short: string
  pages: string[]
  lower: string[]
  outline: OutlineItem[]
}

export type Bookmark = { doc: string; page: number; label: string }

export type Hit = {
  where: string
  pre: string
  match: string
  post: string
  route: string
}

export type RawContent = {
  l1: Block[]
  l2: Block[]
  primer: Block[]
  l3: Block[]
  l4: Block[]
  calc: Block[]
  glossary: Term[]
  parts: [string, string, number | null, number[] | null][]
  decks: { name: string; lv: string; desc: string; qs: [string, string[], number, string][] }[]
}

export type RawDoc = {
  title: string
  short: string
  pages: string[]
  outline: { t: string; d: number; p: number }[]
}
