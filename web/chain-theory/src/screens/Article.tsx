import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { BlockList } from '../components/Blocks'
import { FontButton, Missing, TopBar, useTitle } from '../components/Chrome'
import { useContent } from '../guide'
import { nextUp, quizForArticle } from '../logic'
import { useStore } from '../store'
import type { Block, TextBlock } from '../types'

export function Article() {
  const { key = '' } = useParams()
  const content = useContent()
  const { earn, earned } = useStore()
  const blocks = content.articles[key]
  const [toc, setToc] = useState(false)
  const title = blocks ? headingOf(blocks) : 'Guide'
  useTitle(title)
  const done = earned[key] != null

  useEffect(() => {
    if (!blocks || done) return
    if (key !== 'l1' && key !== 'l2' && key !== 'l3' && key !== 'primer') return
    const scroller = document.getElementById('content')
    if (!scroller) return
    const check = () => {
      if (scroller.scrollHeight > 80 && scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight < 48) earn(key)
    }
    check()
    scroller.addEventListener('scroll', check, { passive: true })
    return () => scroller.removeEventListener('scroll', check)
  }, [blocks, key, earn, done])

  if (!blocks) return <Missing title="Missing page" body="That guide page is not in this edition." />

  const sections = blocks.flatMap((block, index) =>
    isText(block) && block.k === 'h2' ? [{ id: block.id || `section-${index}`, title: plain(block) }] : [],
  )
  const following = nextUp(key)
  const quiz = quizForArticle(key)

  return (
    <div className="stage-inner narrow">
      <TopBar
        title={title}
        fallback="/learn"
        heading={false}
        actions={
          <>
            {sections.length > 0 ? (
              <button type="button" className="icon-btn wide" aria-expanded={toc} onClick={() => setToc(true)}>
                Sections
              </button>
            ) : null}
            <FontButton />
          </>
        }
      />
      <BlockList blocks={blocks} />
      <div className="stack next-up">
        <Link className="card" to={following.route}>
          <span className="kicker">Up next</span>
          <strong>{following.label}</strong>
        </Link>
        {quiz ? (
          <Link className="card" to={quiz}>
            <strong>{key === 'primer' ? 'Quiz yourself: the Refresher deck' : 'Quiz yourself on this level'}</strong>
          </Link>
        ) : null}
      </div>
      <SectionDialog open={toc} sections={sections} onClose={() => setToc(false)} />
    </div>
  )
}

function SectionDialog({
  open,
  sections,
  onClose,
}: {
  open: boolean
  sections: { id: string; title: string }[]
  onClose: () => void
}) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const dialog = ref.current
    if (!dialog) return
    if (open && !dialog.open) dialog.showModal()
    if (!open && dialog.open) dialog.close()
  }, [open])

  return (
    <dialog ref={ref} className="sheet" aria-labelledby="toc-title" onClose={onClose}>
      <header className="sheet-bar">
        <h2 id="toc-title">Sections</h2>
        <button type="button" className="btn" onClick={onClose}>
          Close
        </button>
      </header>
      <ul className="toc">
        {sections.map((section) => (
          <li key={section.id}>
            <a href={`#${section.id}`} onClick={onClose}>
              {section.title}
            </a>
          </li>
        ))}
      </ul>
    </dialog>
  )
}

function isText(block: Block): block is TextBlock {
  return block.k !== 'table' && block.k !== 'callout' && block.k !== 'card'
}

function plain(block: TextBlock): string {
  return block.s.map((span) => span[0]).join('')
}

function headingOf(blocks: Block[]): string {
  const found = blocks.find((block) => isText(block) && block.k === 'h1')
  return found && isText(found) ? plain(found) : 'Guide'
}
