import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.tsx'
import './index.css'
import { loadTheme } from './theme/theme'
import { bootstrapTelegramWebApp } from './telegram/webApp'

if (!bootstrapTelegramWebApp()) {
  document.documentElement.dataset.theme = loadTheme()
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
