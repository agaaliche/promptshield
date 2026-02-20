import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { initSentry } from './sentry'
import './i18n'          // i18next — must be imported before any component
import '@fortawesome/fontawesome-pro/css/all.min.css'
import './index.css'
import App from './App.tsx'

// Initialize crash reporting before rendering
initSentry();

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
