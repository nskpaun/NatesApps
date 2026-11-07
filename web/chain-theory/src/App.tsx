import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Outlet, RouterProvider, createBrowserRouter, useLocation } from 'react-router-dom'
import { BottomNav, Confetti, Missing, SideNav, Toast } from './components/Chrome'
import { loadContent } from './content'
import { ContentProvider } from './guide'
import { Article } from './screens/Article'
import { Home } from './screens/Home'
import { Learn } from './screens/Learn'
import { Library } from './screens/Library'
import { Flash, Play, Quiz } from './screens/Play'
import { Reader } from './screens/Reader'
import { Calc, Glossary, MapScreen } from './screens/Reference'
import { Search } from './screens/Search'
import { StoreProvider, useStore } from './store'
import type { Content } from './types'

const router = createBrowserRouter([
  {
    path: '/',
    element: <Frame />,
    children: [
      { index: true, element: <Home /> },
      { path: 'learn', element: <Learn /> },
      { path: 'article/:key', element: <Article /> },
      { path: 'map', element: <MapScreen /> },
      { path: 'calc', element: <Calc /> },
      { path: 'glossary', element: <Glossary /> },
      { path: 'play', element: <Play /> },
      { path: 'quiz/:deck', element: <Quiz /> },
      { path: 'flash', element: <Flash /> },
      { path: 'library', element: <Library /> },
      { path: 'reader/:doc/:page', element: <Reader /> },
      { path: 'search', element: <Search /> },
      { path: '*', element: <Missing title="Page not found" body="That address is not part of the Chain Theory guide." /> },
    ],
  },
])

function Frame() {
  const { pathname } = useLocation()
  const store = useStore()
  const stageRef = useRef<HTMLDivElement>(null)
  const immersive = /^\/(reader|quiz|flash)(\/|$)/.test(pathname)
  useLayoutEffect(() => {
    stageRef.current?.scrollTo(0, 0)
  }, [pathname])

  return (
    <div className={immersive ? 'shell immersive' : 'shell'} style={{ ['--scale' as string]: String(store.fontScale) }}>
      <a className="skip" href="#content">
        Skip to content
      </a>
      {immersive ? null : <SideNav />}
      <main className="stage" id="content" ref={stageRef} tabIndex={-1}>
        <Outlet />
      </main>
      {immersive ? null : <BottomNav />}
      <Toast message={store.toast} />
      <Confetti trigger={store.confetti} />
    </div>
  )
}

export function App() {
  const [content, setContent] = useState<Content | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let live = true
    setError(null)
    loadContent()
      .then((value) => {
        if (live) setContent(value)
      })
      .catch((reason: unknown) => {
        if (live) setError(reason instanceof Error ? reason.message : 'Could not load the guide.')
      })
    return () => {
      live = false
    }
  }, [attempt])

  if (error) {
    return (
      <div className="boot">
        <h1>Chain Theory</h1>
        <p>{error}</p>
        <button type="button" className="btn primary" onClick={() => setAttempt((value) => value + 1)}>
          Try again
        </button>
      </div>
    )
  }
  if (!content) {
    return (
      <div className="boot">
        <p className="kicker">Field guide</p>
        <h1>Chain Theory</h1>
        <p>Opening the guide…</p>
      </div>
    )
  }

  return (
    <ContentProvider value={content}>
      <StoreProvider>
        <RouterProvider router={router} />
      </StoreProvider>
    </ContentProvider>
  )
}
