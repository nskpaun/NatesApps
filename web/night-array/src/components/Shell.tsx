import { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { subscribeToast } from '../lib/toast'

const TABS = [
  { to: '/', label: 'Explore', end: true },
  { to: '/studio', label: 'Studio', end: false },
  { to: '/files', label: 'Files', end: false },
  { to: '/specs', label: 'Specs', end: false },
]

function tabActive(path: string, to: string) {
  if (to === '/') return path === '/' || path.startsWith('/story') || path.startsWith('/board') || path === '/night'
  if (to === '/files') return path.startsWith('/files')
  if (to === '/specs') return path.startsWith('/specs')
  if (to === '/studio') return path.startsWith('/studio')
  return false
}

export function Shell() {
  const { pathname } = useLocation()
  const [toast, setToast] = useState<string | null>(null)
  useEffect(() => {
    let timer = 0
    return subscribeToast((message) => {
      setToast(message)
      window.clearTimeout(timer)
      timer = window.setTimeout(() => setToast(null), 2800)
    })
  }, [])
  const night = pathname === '/night'
  return (
    <div className={night ? 'app night-open' : 'app'}>
      <a className="skip" href="#content">
        Skip to content
      </a>
      <nav className="rail" aria-label="Sections">
        <p className="mark">N·A</p>
        {TABS.map((tab) => (
          <NavLink key={tab.to} to={tab.to} end={tab.end} className={tabActive(pathname, tab.to) ? 'on' : ''} aria-current={tabActive(pathname, tab.to) ? 'page' : undefined}>
            {tab.label}
          </NavLink>
        ))}
      </nav>
      <main id="content" className="main">
        <Outlet />
      </main>
      <nav className="tabbar" aria-label="Sections">
        {TABS.map((tab) => (
          <NavLink key={tab.to} to={tab.to} end={tab.end} className={tabActive(pathname, tab.to) ? 'on' : ''} aria-current={tabActive(pathname, tab.to) ? 'page' : undefined}>
            {tab.label}
          </NavLink>
        ))}
      </nav>
      {toast ? (
        <p className="toast" role="status">
          {toast}
        </p>
      ) : null}
    </div>
  )
}
