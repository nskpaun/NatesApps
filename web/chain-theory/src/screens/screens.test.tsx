import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { parseContent } from '../content'
import { ContentProvider } from '../guide'
import { initialProgress } from '../logic'
import { StoreProvider } from '../store'
import type { RawContent } from '../types'
import type { ReactNode } from 'react'
import { Article } from './Article'
import { Home } from './Home'
import { Glossary } from './Reference'
import { Calc } from './Reference'
import { Quiz } from './Play'

const assets = resolve(process.cwd(), '../../chain-theory/android/app/src/main/assets/content.json')
const content = parseContent(JSON.parse(readFileSync(assets, 'utf8')) as RawContent)

function renderAt(path: string, pattern: string, ui: ReactNode) {
  return render(
    <ContentProvider value={content}>
      <StoreProvider initial={initialProgress()}>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route path={pattern} element={ui} />
          </Routes>
        </MemoryRouter>
      </StoreProvider>
    </ContentProvider>,
  )
}

beforeEach(() => localStorage.clear())
afterEach(() => cleanup())

describe('screens', () => {
  it('shows the chain and the six depths on the home screen', () => {
    renderAt('/', '/', <Home />)
    expect(screen.getByRole('heading', { name: 'Chain Theory' })).toBeInTheDocument()
    expect(screen.getByText('0 / 12 links forged')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /The 60-second version/ })).toHaveAttribute('href', '/article/l1')
    expect(screen.getByRole('link', { name: /Compendium map/ })).toHaveAttribute('href', '/map')
    expect(screen.getByRole('link', { name: 'α calc' })).toHaveAttribute('href', '/calc')
  })

  it('renders a guide article from the bundled content', () => {
    renderAt('/article/l1', '/article/:key', <Article />)
    expect(screen.getByRole('heading', { name: 'Chain Theory in a minute' })).toBeInTheDocument()
    expect(screen.getAllByText(/fine-structure constant/i).length).toBeGreaterThan(0)
  })

  it('moves 1/α when a count changes and can reset', async () => {
    const user = userEvent.setup()
    renderAt('/calc', '/calc', <Calc />)
    expect(screen.getByText('137.035999190')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Increase Weight 1 (antisymmetric)' }))
    expect(screen.queryByText('137.035999190')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Reset to the Letter' }))
    expect(screen.getByText('137.035999190')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'k not √k' }))
    expect(screen.getByText(/Ruled out by experiment/)).toBeInTheDocument()
  })

  it('filters and expands a glossary term', async () => {
    const user = userEvent.setup()
    renderAt('/glossary', '/glossary', <Glossary />)
    await user.type(screen.getByLabelText('Filter terms'), 'Bound ent')
    expect(screen.getByText(/cannot be distilled/)).toBeInTheDocument()
  })

  it('marks a right answer and a wrong answer', async () => {
    const user = userEvent.setup()
    renderAt('/quiz/0', '/quiz/:deck', <Quiz />)
    const asked = document.getElementById('q-text')?.textContent ?? ''
    const question = content.decks[0].questions.find((item) => item.q === asked)
    expect(question).toBeTruthy()
    await user.click(screen.getByRole('button', { name: question!.options[question!.answer] }))
    expect(screen.getByText('Correct!')).toBeInTheDocument()
    expect(screen.getByText(question!.explain)).toBeInTheDocument()

    cleanup()
    renderAt('/quiz/0', '/quiz/:deck', <Quiz />)
    const againText = document.getElementById('q-text')?.textContent ?? ''
    const again = content.decks[0].questions.find((item) => item.q === againText)!
    const miss = again.options.find((_, index) => index !== again.answer)!
    await user.click(screen.getByRole('button', { name: miss }))
    expect(screen.getByText('Not quite.')).toBeInTheDocument()
  })
})
