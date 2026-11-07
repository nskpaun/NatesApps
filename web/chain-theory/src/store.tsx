import { createContext, useCallback, useContext, useEffect, useMemo, useReducer, type ReactNode } from 'react'
import { chainCount, initialProgress, reduceProgress, type Progress } from './logic'

const STORAGE_KEY = 'ct-web-v1'

export type Store = Progress & {
  chain: number
  earn: (id: string) => void
  quizResult: (deck: number, score: number, total: number) => void
  read: (doc: string, page: number) => void
  toggleBookmark: (doc: string, page: number, label: string) => void
  cycleFont: () => void
  knowCard: () => void
  dismissToast: () => void
  notify: (message: string) => void
  position: (doc: string) => number
  bookmarked: (doc: string, page: number) => boolean
}

const StoreContext = createContext<Store | null>(null)

function loadProgress(): Progress {
  const blank = initialProgress()
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return blank
    const saved = JSON.parse(raw) as Partial<Progress> & { v?: number }
    if (saved.v !== 1) return blank
    return {
      ...blank,
      earned: saved.earned ?? {},
      best: saved.best ?? {},
      bookmarks: Array.isArray(saved.bookmarks) ? saved.bookmarks : [],
      lastDoc: typeof saved.lastDoc === 'string' ? saved.lastDoc : null,
      lastPage: typeof saved.lastPage === 'number' ? saved.lastPage : 1,
      fontScale: typeof saved.fontScale === 'number' ? saved.fontScale : 1,
      flashKnown: typeof saved.flashKnown === 'number' ? saved.flashKnown : 0,
      seen: saved.seen ?? {},
      pos: saved.pos ?? {},
    }
  } catch {
    return blank
  }
}

function persist(state: Progress) {
  localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify({
      v: 1,
      earned: state.earned,
      best: state.best,
      bookmarks: state.bookmarks,
      lastDoc: state.lastDoc,
      lastPage: state.lastPage,
      fontScale: state.fontScale,
      flashKnown: state.flashKnown,
      seen: state.seen,
      pos: state.pos,
    }),
  )
}

export function StoreProvider({ children, initial }: { children: ReactNode; initial?: Progress }) {
  const [state, dispatch] = useReducer(reduceProgress, undefined, () => initial ?? loadProgress())

  useEffect(() => {
    persist(state)
  }, [state])

  useEffect(() => {
    if (!state.toast) return
    const timer = window.setTimeout(() => dispatch({ type: 'toast', message: null }), 2800)
    return () => window.clearTimeout(timer)
  }, [state.toast])

  const earn = useCallback((id: string) => dispatch({ type: 'earn', id }), [])
  const quizResult = useCallback(
    (deck: number, score: number, total: number) => dispatch({ type: 'quizResult', deck, score, total }),
    [],
  )
  const read = useCallback((doc: string, page: number) => dispatch({ type: 'read', doc, page }), [])
  const toggleBookmark = useCallback(
    (doc: string, page: number, label: string) => dispatch({ type: 'bookmark', doc, page, label }),
    [],
  )
  const cycleFont = useCallback(() => dispatch({ type: 'font' }), [])
  const knowCard = useCallback(() => dispatch({ type: 'know' }), [])
  const dismissToast = useCallback(() => dispatch({ type: 'toast', message: null }), [])
  const notify = useCallback((message: string) => dispatch({ type: 'toast', message }), [])

  const api = useMemo<Store>(
    () => ({
      ...state,
      chain: chainCount(state.earned),
      earn,
      quizResult,
      read,
      toggleBookmark,
      cycleFont,
      knowCard,
      dismissToast,
      notify,
      position: (doc) => state.pos[doc] ?? 1,
      bookmarked: (doc, page) => state.bookmarks.some((mark) => mark.doc === doc && mark.page === page),
    }),
    [state, earn, quizResult, read, toggleBookmark, cycleFont, knowCard, dismissToast, notify],
  )

  return <StoreContext.Provider value={api}>{children}</StoreContext.Provider>
}

export function useStore(): Store {
  const store = useContext(StoreContext)
  if (!store) throw new Error('useStore must be used inside StoreProvider')
  return store
}
