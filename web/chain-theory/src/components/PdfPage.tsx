import { useEffect, useRef, useState } from 'react'
import type { PDFDocumentProxy, RenderTask } from 'pdfjs-dist'

const documents = new Map<string, Promise<PDFDocumentProxy>>()
let libraryPromise: Promise<typeof import('pdfjs-dist')> | null = null

function library() {
  if (!libraryPromise) {
    libraryPromise = import('pdfjs-dist').then(async (pdfjs) => {
      const worker = await import('pdfjs-dist/build/pdf.worker.min.mjs?url')
      pdfjs.GlobalWorkerOptions.workerSrc = worker.default
      return pdfjs
    })
  }
  return libraryPromise
}

function documentFor(key: string) {
  let pending = documents.get(key)
  if (!pending) {
    pending = library()
      .then((pdfjs) => pdfjs.getDocument({ url: `/data/${key}.pdf` }).promise)
      .catch((error) => {
        documents.delete(key)
        throw error
      })
    documents.set(key, pending)
  }
  return pending
}

export function PdfPage({ docKey, page }: { docKey: string; page: number }) {
  const boxRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const taskRef = useRef<RenderTask | null>(null)
  const [width, setWidth] = useState(0)
  const [zoom, setZoom] = useState(1)
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')

  useEffect(() => {
    const box = boxRef.current
    if (!box) return
    const measure = () => setWidth(Math.floor(box.clientWidth))
    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(box)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    setZoom(1)
  }, [docKey, page])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || width < 32) return
    let cancel = false
    setStatus('loading')
    void (async () => {
      try {
        const pdf = await documentFor(docKey)
        if (cancel) return
        const pdfPage = await pdf.getPage(Math.min(Math.max(page, 1), pdf.numPages))
        if (cancel) return
        const base = pdfPage.getViewport({ scale: 1 })
        const scale = Math.min(2400, width * Math.min(window.devicePixelRatio || 1, 2)) / base.width
        const viewport = pdfPage.getViewport({ scale })
        const context = canvas.getContext('2d')
        if (!context) throw new Error('Canvas is unavailable')
        canvas.width = Math.floor(viewport.width)
        canvas.height = Math.floor(viewport.height)
        taskRef.current?.cancel()
        const task = pdfPage.render({ canvasContext: context, viewport })
        taskRef.current = task
        await task.promise
        if (!cancel) setStatus('ready')
      } catch (error) {
        const name = error instanceof Error ? error.name : ''
        if (!cancel && name !== 'RenderingCancelledException') setStatus('error')
      }
    })()
    return () => {
      cancel = true
      taskRef.current?.cancel()
    }
  }, [docKey, page, width])

  useEffect(() => {
    const box = boxRef.current
    if (!box) return
    const onWheel = (event: WheelEvent) => {
      if (!event.ctrlKey && !event.metaKey) return
      event.preventDefault()
      setZoom((current) => clampZoom(current * (event.deltaY < 0 ? 1.08 : 0.92)))
    }
    box.addEventListener('wheel', onWheel, { passive: false })
    return () => box.removeEventListener('wheel', onWheel)
  }, [])

  return (
    <div className="pdf-view" ref={boxRef}>
      <div className="pdf-tools">
        <button type="button" onClick={() => setZoom((current) => clampZoom(current / 1.2))} aria-label="Zoom out">
          −
        </button>
        <button type="button" onClick={() => setZoom(1)} aria-label="Reset zoom">
          {Math.round(zoom * 100)}%
        </button>
        <button type="button" onClick={() => setZoom((current) => clampZoom(current * 1.2))} aria-label="Zoom in">
          +
        </button>
        <a href={`/data/${docKey}.pdf#page=${page}`} target="_blank" rel="noopener noreferrer">
          Open PDF
        </a>
      </div>
      {status === 'loading' ? <p className="pdf-status">Rendering page {page}…</p> : null}
      {status === 'error' ? (
        <p className="pdf-status">
          This page couldn’t be drawn here.{' '}
          <a href={`/data/${docKey}.pdf#page=${page}`} target="_blank" rel="noopener noreferrer">
            Open the original PDF
          </a>
          .
        </p>
      ) : null}
      <div className="pdf-stage" style={{ transform: `scale(${zoom})` }}>
        <canvas ref={canvasRef} aria-label={`Original PDF page ${page}`} />
      </div>
      {status === 'ready' && zoom === 1 ? <p className="pdf-hint">Ctrl-scroll or use the zoom buttons</p> : null}
    </div>
  )
}

function clampZoom(value: number): number {
  return Math.min(5, Math.max(1, value))
}
