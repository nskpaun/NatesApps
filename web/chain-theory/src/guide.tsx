import { createContext, useContext, type ReactNode } from 'react'
import type { Content } from './types'

const ContentContext = createContext<Content | null>(null)

export function ContentProvider({ value, children }: { value: Content; children: ReactNode }) {
  return <ContentContext.Provider value={value}>{children}</ContentContext.Provider>
}

export function useContent(): Content {
  const value = useContext(ContentContext)
  if (!value) throw new Error('Guide content is not loaded')
  return value
}
