import { useEffect, useRef, type ReactNode } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { LINKS, resolveLink, tabOf } from '../logic'
import { useStore } from '../store'

const TABS = [
  { to: '/', id: 'home', label: 'Home', icon: HomeIcon },
  { to: '/learn', id: 'learn', label: 'Learn', icon: LearnIcon },
  { to: '/play', id: 'play', label: 'Play', icon: PlayIcon },
  { to: '/library', id: 'library', label: 'Library', icon: BookIcon },
  { to: '/search', id: 'search', label: 'Search', icon: SearchIcon },
] as const

export function useTitle(title: string) {
  useEffect(() => {
    document.title = title === 'Chain Theory Explorer' ? title : `${title} · Chain Theory`
  }, [title])
}

export function useGoBack(fallback: string) {
  const navigate = useNavigate()
  return () => {
    const index = typeof window.history.state?.idx === 'number' ? window.history.state.idx : 0
    if (index > 0) navigate(-1)
    else navigate(fallback)
  }
}

export function TopBar({
  title,
  subtitle,
  fallback,
  heading = true,
  actions,
}: {
  title: string
  subtitle?: string
  fallback: string
  heading?: boolean
  actions?: ReactNode
}) {
  const back = useGoBack(fallback)
  const { pathname } = useLocation()
  const root = pathname === '/' || pathname === '/learn' || pathname === '/play' || pathname === '/library' || pathname === '/search'
  const Title = heading ? 'h1' : 'p'
  return (
    <header className="topbar">
      {root ? (
        <span className="back-spacer" />
      ) : (
        <button type="button" className="icon-btn" onClick={back} aria-label="Back">
          <BackIcon />
        </button>
      )}
      <div className="topbar-text">
        <Title className="topbar-title">{title}</Title>
        {subtitle ? <p className="topbar-sub">{subtitle}</p> : null}
      </div>
      <div className="topbar-actions">{actions}</div>
    </header>
  )
}

export function FontButton() {
  const { fontScale, cycleFont } = useStore()
  return (
    <button type="button" className="icon-btn" onClick={cycleFont} aria-label={`Text size, currently ${Math.round(fontScale * 100)} percent`}>
      <span aria-hidden="true">Aa</span>
    </button>
  )
}

export function NavLinks({ className }: { className?: string }) {
  const { pathname } = useLocation()
  const current = tabOf(pathname)
  return (
    <nav className={className} aria-label="Primary">
      {TABS.map((tab) => {
        const Icon = tab.icon
        const selected = current === tab.id
        return (
          <Link key={tab.id} to={tab.to} aria-current={selected ? 'page' : undefined} className={selected ? 'on' : undefined}>
            <Icon />
            <span>{tab.label}</span>
          </Link>
        )
      })}
    </nav>
  )
}

export function SideNav() {
  const store = useStore()
  return (
    <aside className="sidebar">
      <Link to="/" className="brand">
        <span aria-hidden="true">⛓</span> Chain Theory
      </Link>
      <NavLinks className="side-links" />
      <div className="side-chain">
        <p className="kicker">
          {store.chain} / {LINKS.length} links
        </p>
        <ol>
          {LINKS.map((link) => {
            const forged = store.earned[link.id] != null
            return (
              <li key={link.id}>
                <Link to={resolveLink(link.target)}>
                  <span aria-hidden="true">{forged ? '●' : '○'}</span>
                  <span className="sr-only">{forged ? 'Forged: ' : 'Open: '}</span>
                  {link.label}
                </Link>
              </li>
            )
          })}
        </ol>
      </div>
    </aside>
  )
}

export function BottomNav() {
  return <NavLinks className="bottom-nav" />
}

export function Toast({ message }: { message: string | null }) {
  return (
    <>
      <div className="sr-only" role="status">
        {message ?? ''}
      </div>
      {message ? (
        <div className="toast show" aria-hidden="true">
          {message}
        </div>
      ) : null}
    </>
  )
}

type Bit = { x: number; y: number; vx: number; vy: number; color: string; s: number; r: number; vr: number }

export function Confetti({ trigger }: { trigger: number }) {
  const ref = useRef<HTMLCanvasElement>(null)
  useEffect(() => {
    if (trigger === 0) return
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    const canvas = ref.current
    const ctx = canvas?.getContext('2d')
    if (!canvas || !ctx) return
    const colors = ['#E39A5F', '#F2C29A', '#7CC48A', '#E2C062', '#E88A98', '#B59CF0']
    const bits: Bit[] = Array.from({ length: 110 }, (_, index) => ({
      x: Math.random(),
      y: -0.05 - Math.random() * 0.3,
      vx: (Math.random() - 0.5) * 0.004,
      vy: 0.004 + Math.random() * 0.006,
      color: colors[index % colors.length],
      s: 6 + Math.random() * 8,
      r: Math.random() * 360,
      vr: (Math.random() - 0.5) * 14,
    }))
    let raf = 0
    const draw = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2)
      const width = canvas.clientWidth || window.innerWidth
      const height = canvas.clientHeight || window.innerHeight
      canvas.width = Math.max(1, Math.floor(width * dpr))
      canvas.height = Math.max(1, Math.floor(height * dpr))
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      ctx.clearRect(0, 0, width, height)
      for (const bit of bits) {
        bit.x += bit.vx
        bit.y += bit.vy
        bit.vy += 0.00012
        bit.r += bit.vr
        ctx.save()
        ctx.translate(bit.x * width, bit.y * height)
        ctx.rotate((bit.r * Math.PI) / 180)
        ctx.fillStyle = bit.color
        ctx.fillRect(0, 0, bit.s * 0.45, bit.s)
        ctx.restore()
      }
      for (let i = bits.length - 1; i >= 0; i--) if (bits[i].y > 1.1) bits.splice(i, 1)
      if (bits.length > 0) raf = requestAnimationFrame(draw)
    }
    raf = requestAnimationFrame(draw)
    return () => cancelAnimationFrame(raf)
  }, [trigger])
  return <canvas ref={ref} className="confetti" aria-hidden="true" />
}

export function Missing({ title, body }: { title: string; body: string }) {
  useTitle(title)
  return (
    <div className="stage-inner narrow">
      <h1>{title}</h1>
      <p>{body}</p>
      <Link className="btn" to="/">
        Back to the start
      </Link>
    </div>
  )
}

function HomeIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M4 10.5 12 4l8 6.5V20a1 1 0 0 1-1 1h-5v-6H10v6H5a1 1 0 0 1-1-1z" />
    </svg>
  )
}
function LearnIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M3 8.5 12 4l9 4.5-9 4.5L3 8.5z" />
      <path d="M7 11.2V16c0 .8 2.2 2.2 5 2.2s5-1.4 5-2.2v-4.8" />
    </svg>
  )
}
function PlayIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <rect x="3" y="7" width="18" height="11" rx="3" />
      <path d="M8 7V5.5A1.5 1.5 0 0 1 9.5 4h5A1.5 1.5 0 0 1 16 5.5V7" />
    </svg>
  )
}
function BookIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M5 4.5h9.5A3.5 3.5 0 0 1 18 8v11.5H8A3 3 0 0 0 5 16.5z" />
      <path d="M5 4.5A3 3 0 0 0 8 7.5h10" />
    </svg>
  )
}
function SearchIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="11" cy="11" r="6" />
      <path d="M16 16.5 20 20.5" />
    </svg>
  )
}
function BackIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M14.5 5.5 8 12l6.5 6.5" />
    </svg>
  )
}
