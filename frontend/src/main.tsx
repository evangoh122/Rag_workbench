import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { getPosthog } from './utils/posthog'

if (import.meta.env.VITE_POSTHOG_KEY) {
  getPosthog().catch((err) => {
    console.warn('PostHog failed to initialise:', err)
  })
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
