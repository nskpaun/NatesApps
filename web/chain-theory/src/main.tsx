import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@fontsource/source-sans-3/400.css'
import '@fontsource/source-sans-3/600.css'
import '@fontsource/source-sans-3/700.css'
import '@fontsource/source-serif-4/400.css'
import '@fontsource/source-serif-4/400-italic.css'
import '@fontsource/source-serif-4/600.css'
import '@fontsource/source-serif-4/700.css'
import { App } from './App'
import './styles.css'

const root = document.getElementById('root')
if (!root) throw new Error('Missing #root')
createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
