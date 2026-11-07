import { Link } from 'react-router-dom'
import { TopBar, useTitle } from '../components/Chrome'
import { DOC_INFO, DOC_SHORT } from '../logic'
import { useStore } from '../store'

export function Library() {
  const store = useStore()
  useTitle('Library')
  return (
    <div className="stage-inner">
      <TopBar title="Library" subtitle="Full text and original PDFs, bundled with this site" fallback="/" />
      <div className="pad stack">
        {DOC_INFO.map((doc) => {
          const page = store.position(doc.key)
          return (
            <article key={doc.key} className="card doc">
              <span className="cover" aria-hidden="true">
                {doc.mark}
              </span>
              <div className="doc-copy">
                <Link to={`/reader/${doc.key}/${page}`}>
                  <strong>{doc.title}</strong>
                  <span className="muted">{doc.desc}</span>
                  <span className="meter thin" aria-hidden="true">
                    <span style={{ width: `${Math.min(100, (page / doc.pages) * 100)}%` }} />
                  </span>
                  <span className="continue">{page > 1 ? `Continue · page ${page} of ${doc.pages}` : `${doc.pages} pages`}</span>
                </Link>
                <a className="text-link" href={`/data/${doc.key}.pdf`} target="_blank" rel="noopener noreferrer">
                  Open original PDF
                </a>
              </div>
            </article>
          )
        })}
        <section>
          <h2 className="section-label">Bookmarks</h2>
          {store.bookmarks.length === 0 ? (
            <p className="muted">None yet. Use the bookmark button in the reader to save a page.</p>
          ) : (
            <div className="stack">
              {store.bookmarks.map((mark) => (
                <Link key={`${mark.doc}-${mark.page}`} className="card bookmark" to={`/reader/${mark.doc}/${mark.page}`}>
                  <span className="kicker">
                    {DOC_SHORT[mark.doc] ?? mark.doc} · p. {mark.page}
                  </span>
                  {mark.label ? <strong>{mark.label}</strong> : null}
                </Link>
              ))}
            </div>
          )}
        </section>
        <p className="fine">
          Sources: alexwg.org/publications, downloaded Nov 3, 2026. Copyright their author; bundled for personal reading.
          Extracted text scrambles some equations, so open the PDF when a formula looks garbled.
        </p>
      </div>
    </div>
  )
}
