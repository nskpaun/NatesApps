import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { NIGHT_LINES } from '../lib/content'
import { getViewer } from '../lib/viewer'
import { Still } from '../components/ui'
import { useViewer, ViewerSlot } from '../components/Stage'

export function Night() {
  const navigate = useNavigate()
  const exitNight = () => {
    const idx = (window.history.state as { idx?: number } | null)?.idx ?? 0
    if (idx > 0) navigate(-1)
    else navigate('/')
  }
  const snap = useViewer()
  const [line, setLine] = useState(0)
  const [chrome, setChrome] = useState(true)
  useEffect(() => {
    const viewer = getViewer()
    viewer.enterNight()
    return () => viewer.exitNight()
  }, [])
  useEffect(() => {
    const id = window.setInterval(() => setLine((n) => (n + 1) % NIGHT_LINES.length), 7000)
    return () => window.clearInterval(id)
  }, [])
  useEffect(() => {
    const id = window.setTimeout(() => setChrome(false), 4000)
    return () => window.clearTimeout(id)
  }, [chrome])
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') exitNight()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [navigate])
  const ready = snap.status === 'ready'
  return (
    <div
      className={ready ? 'night is-ready' : 'night'}
      onPointerDown={() => setChrome(true)}
    >
      <Still names={['night.jpg', 'hero-stow.jpg']} alt={ready ? '' : 'Night Array at night'} />
      <ViewerSlot />
      <div className="night-copy">
        <p className="tagline">{NIGHT_LINES[line]}</p>
      </div>
      {chrome ? (
        <header>
          <div>
            <p>Night shift</p>
            <p className="fine">{ready ? 'Live · slow orbit' : 'Still · the live view is still starting'}</p>
          </div>
          <button type="button" onClick={exitNight}>
            Exit Night shift
          </button>
        </header>
      ) : (
        <button type="button" className="night-show" onClick={() => setChrome(true)}>
          Show controls
        </button>
      )}
    </div>
  )
}
