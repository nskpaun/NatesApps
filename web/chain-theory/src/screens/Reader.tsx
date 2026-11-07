import { useEffect, useRef, useState, type ReactNode } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { FontButton, Missing, useGoBack, useTitle } from '../components/Chrome'
import { PdfPage } from '../components/PdfPage'
import { isDocKey, loadDoc } from '../content'
import { DOC_SHORT, compFrontMatter, isHeadingParagraph, pageParagraphs, sectionFor } from '../logic'
import { useStore } from '../store'
import type { Doc, OutlineItem } from '../types'

export function Reader() {
  const { doc: key = '', page: pageParam = '1' } = useParams()
  const [params] = useSearchParams()
  const highlight = params.get('q')
  const parsed = Number(pageParam)
  const requested = Number.isFinite(parsed) ? Math.floor(parsed) : 1
  const [doc, setDoc] = useState<Doc | null>(null)
  const [failed, setFailed] = useState(false)
  const store = useStore()

  useEffect(() => {
    if (!isDocKey(key)) {
      setFailed(true)
      setDoc(null)
      return
    }
    let live = true
    setFailed(false)
    setDoc(null)
    loadDoc(key)
      .then((loaded) => {
        if (live) setDoc(loaded)
      })
      .catch(() => {
        if (live) setFailed(true)
      })
    return () => {
      live = false
    }
  }, [key])

  if (!isDocKey(key) || failed) {
    return <Missing title="Missing document" body="That source is not bundled with this guide." />
  }
  if (!doc) {
    return (
      <div className="boot">
        <p>Opening {DOC_SHORT[key] ?? 'document'}…</p>
      </div>
    )
  }
  const page = Math.min(Math.max(requested, 1), doc.pages.length)
  return <ReaderBody doc={doc} page={page} requested={requested} highlight={highlight} bookmarked={store.bookmarked(key, page)} />
}

function ReaderBody({
  doc,
  page,
  requested,
  highlight,
  bookmarked,
}: {
  doc: Doc
  page: number
  requested: number
  highlight: string | null
  bookmarked: boolean
}) {
  const navigate = useNavigate()
  const back = useGoBack('/library')
  const store = useStore()
  const [pdf, setPdf] = useState(doc.key === 'talk')
  const [toc, setToc] = useState(false)
  const [jump, setJump] = useState(false)
  const bodyRef = useRef<HTMLDivElement>(null)
  const section = sectionFor(doc.outline, page)
  useTitle(`${doc.short} · p. ${page}`)

  useEffect(() => {
    store.read(doc.key, page)
  }, [doc.key, page, store.read])

  useEffect(() => {
    bodyRef.current?.scrollTo(0, 0)
  }, [doc.key, page, pdf])

  useEffect(() => {
    if (requested !== page) {
      navigate(readerPath(doc.key, page, highlight), { replace: true })
    }
  }, [requested, page, doc.key, highlight, navigate])

  function go(nextPage: number) {
    const target = Math.min(Math.max(nextPage, 1), doc.pages.length)
    navigate(readerPath(doc.key, target, highlight), { replace: true })
  }

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (toc || jump) return
      const tag = (event.target as HTMLElement | null)?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA') return
      if (event.key === 'ArrowRight') {
        event.preventDefault()
        go(page + 1)
      }
      if (event.key === 'ArrowLeft') {
        event.preventDefault()
        go(page - 1)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  const start = useRef<{ x: number; y: number } | null>(null)

  return (
    <div className="reader">
      <header className="reader-bar">
        <button type="button" className="icon-btn" onClick={back} aria-label="Back">
          ←
        </button>
        <button type="button" className="reader-title" onClick={() => setJump(true)}>
          <span>
            {doc.short} · p. {page} / {doc.pages.length}
          </span>
          <small>{section?.title ?? doc.title}</small>
        </button>
        <button type="button" className={pdf ? 'icon-btn on' : 'icon-btn'} aria-pressed={pdf} onClick={() => setPdf((value) => !value)}>
          {pdf ? 'Text' : 'PDF'}
        </button>
        {doc.outline.length > 0 ? (
          <button type="button" className="icon-btn wide" onClick={() => setToc(true)}>
            Contents
          </button>
        ) : null}
        <button
          type="button"
          className={bookmarked ? 'icon-btn on' : 'icon-btn'}
          aria-pressed={bookmarked}
          aria-label={bookmarked ? 'Remove bookmark' : 'Bookmark this page'}
          onClick={() => store.toggleBookmark(doc.key, page, section?.title ?? '')}
        >
          {bookmarked ? '★' : '☆'}
        </button>
      </header>
      <div className="meter thin" aria-hidden="true">
        <span style={{ width: `${(page / doc.pages.length) * 100}%` }} />
      </div>
      <div
        className="reader-body"
        ref={bodyRef}
        onPointerDown={(event) => {
          const target = event.target as HTMLElement
          if (target.closest('button, a, input')) return
          start.current = { x: event.clientX, y: event.clientY }
        }}
        onPointerUp={(event) => {
          if (!start.current) return
          const dx = event.clientX - start.current.x
          const dy = event.clientY - start.current.y
          start.current = null
          if (Math.abs(dx) < 64 || Math.abs(dx) < Math.abs(dy)) return
          go(dx < 0 ? page + 1 : page - 1)
        }}
      >
        {pdf ? (
          <PdfPage docKey={doc.key} page={page} />
        ) : (
          <PageText text={doc.pages[page - 1] ?? ''} talk={doc.key === 'talk'} highlight={highlight} scale={store.fontScale} />
        )}
      </div>
      <footer className="reader-foot">
        <button type="button" onClick={() => go(page - 1)} disabled={page <= 1} aria-label="Previous page">
          Previous
        </button>
        <p>Arrow keys or swipe for pages</p>
        <FontButton />
        <button type="button" onClick={() => go(page + 1)} disabled={page >= doc.pages.length} aria-label="Next page">
          Next
        </button>
      </footer>
      <ContentsDialog
        open={toc}
        doc={doc}
        page={page}
        onClose={() => setToc(false)}
        onPick={(target) => {
          setToc(false)
          go(target)
        }}
      />
      <JumpDialog
        open={jump}
        doc={doc}
        page={page}
        onClose={() => setJump(false)}
        onPick={(target) => {
          setJump(false)
          go(target)
        }}
      />
    </div>
  )
}

function PageText({ text, talk, highlight, scale }: { text: string; talk: boolean; highlight: string | null; scale: number }) {
  const paragraphs = pageParagraphs(text)
  if (paragraphs.length === 0) {
    return <p className="muted pad">This page is mostly a figure or table. Switch to PDF to see the original.</p>
  }
  return (
    <article className="page-text" style={{ ['--scale' as string]: String(scale) }}>
      {paragraphs.map((paragraph, index) => {
        const heading = isHeadingParagraph(paragraph)
        const Tag = heading ? 'h2' : 'p'
        return (
          <Tag key={index} className={heading ? 'heading' : talk ? 'talk' : undefined}>
            <Highlighted text={paragraph} query={highlight} />
          </Tag>
        )
      })}
    </article>
  )
}

function Highlighted({ text, query }: { text: string; query: string | null }) {
  if (!query) return <>{text}</>
  const needle = query.toLowerCase()
  const lower = text.toLowerCase()
  if (!needle || lower.length !== text.length) return <>{text}</>
  const parts: ReactNode[] = []
  let cursor = 0
  while (cursor < text.length) {
    const found = lower.indexOf(needle, cursor)
    if (found < 0) {
      parts.push(text.slice(cursor))
      break
    }
    if (found > cursor) parts.push(text.slice(cursor, found))
    parts.push(<mark key={found}>{text.slice(found, found + query.length)}</mark>)
    cursor = found + query.length
  }
  return <>{parts}</>
}

function ContentsDialog({
  open,
  doc,
  page,
  onClose,
  onPick,
}: {
  open: boolean
  doc: Doc
  page: number
  onClose: () => void
  onPick: (page: number) => void
}) {
  const ref = useRef<HTMLDialogElement>(null)
  const [query, setQuery] = useState('')
  useEffect(() => {
    const dialog = ref.current
    if (!dialog) return
    if (open && !dialog.open) dialog.showModal()
    if (!open && dialog.open) dialog.close()
  }, [open])
  const front = doc.key === 'comp' && query.trim() === '' ? compFrontMatter() : []
  const items = [...front, ...doc.outline.filter((item) => query.trim() === '' || item.title.toLowerCase().includes(query.trim().toLowerCase()))]
  const current = query.trim() === '' ? Math.max(0, findLastIndex(items, (item) => item.page <= page)) : -1
  return (
    <dialog ref={ref} className="sheet" aria-labelledby="contents-title" onClose={onClose}>
      <header className="sheet-bar">
        <h2 id="contents-title">Contents</h2>
        <button type="button" className="btn" onClick={onClose}>
          Close
        </button>
      </header>
      <label className="sr-only" htmlFor="toc-filter">
        Filter sections
      </label>
      <input id="toc-filter" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Filter sections…" />
      <ul className="toc">
        {items.map((item, index) => (
          <li key={`${item.title}-${item.page}-${index}`} className={index === current ? 'current' : undefined} style={{ paddingLeft: `${Math.min(item.depth, 2) * 14}px` }}>
            <button type="button" className={item.depth === 0 ? 'depth-0' : undefined} onClick={() => onPick(item.page)}>
              <span>{item.title}</span>
              <span>{item.page}</span>
            </button>
          </li>
        ))}
      </ul>
    </dialog>
  )
}

function JumpDialog({
  open,
  doc,
  page,
  onClose,
  onPick,
}: {
  open: boolean
  doc: Doc
  page: number
  onClose: () => void
  onPick: (page: number) => void
}) {
  const ref = useRef<HTMLDialogElement>(null)
  const [draft, setDraft] = useState(page)
  useEffect(() => {
    const dialog = ref.current
    if (!dialog) return
    if (open && !dialog.open) {
      setDraft(page)
      dialog.showModal()
    }
    if (!open && dialog.open) dialog.close()
  }, [open, page])
  const section = sectionFor(doc.outline, draft)
  return (
    <dialog ref={ref} className="sheet jump" aria-labelledby="jump-title" onClose={onClose}>
      <header className="sheet-bar">
        <h2 id="jump-title">Go to page {draft}</h2>
        <button type="button" className="btn" onClick={onClose}>
          Cancel
        </button>
      </header>
      <label className="sr-only" htmlFor="page-slider">
        Page number
      </label>
      <input
        id="page-slider"
        type="range"
        min={1}
        max={doc.pages.length}
        value={draft}
        onChange={(event) => setDraft(Number(event.target.value))}
      />
      <p className="muted">{section?.title ?? doc.title}</p>
      <button type="button" className="btn primary" onClick={() => onPick(draft)}>
        Go
      </button>
    </dialog>
  )
}

function readerPath(key: string, page: number, highlight: string | null): string {
  const path = `/reader/${key}/${page}`
  return highlight ? `${path}?q=${encodeURIComponent(highlight)}` : path
}

function findLastIndex(items: OutlineItem[], test: (item: OutlineItem) => boolean): number {
  let found = -1
  items.forEach((item, index) => {
    if (test(item)) found = index
  })
  return found
}
