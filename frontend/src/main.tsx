import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

if (import.meta.env.VITE_POSTHOG_KEY) {
  import('posthog-js').then(({ default: posthog }) => {
    posthog.init(import.meta.env.VITE_POSTHOG_KEY, {
      api_host: import.meta.env.VITE_POSTHOG_HOST || 'https://us.i.posthog.com',
      person_profiles: 'identified_only',
    })
  }).catch((err) => {
    console.warn('PostHog failed to initialise:', err)
  })
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
