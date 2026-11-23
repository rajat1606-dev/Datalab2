import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './theme.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)

// PWA: register the service worker in production builds only (never in dev,
// where it would cache hot-reloaded modules).
if ('serviceWorker' in navigator && import.meta.env.PROD) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => { /* offline mode optional */ })
  })
}
