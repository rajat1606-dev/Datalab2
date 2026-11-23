import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { CheckCircle2, Info, XCircle } from 'lucide-react'
import { api } from './api'

const AppContext = createContext(null)

let toastSeq = 0

const THEME_KEY = 'datalab.theme'

function initialTheme() {
  try {
    return localStorage.getItem(THEME_KEY) === 'day' ? 'day' : 'night'
  } catch {
    return 'night'
  }
}

export function AppProvider({ children }) {
  const [activeId, setActiveIdState] = useState(() => localStorage.getItem('datalab.activeId') || '')
  const [activeMeta, setActiveMeta] = useState(null)
  const [datasets, setDatasets] = useState([])
  const [toasts, setToasts] = useState([])
  const [theme, setTheme] = useState(initialTheme)
  const timers = useRef({})

  // Persist the mode, reflect it on <html> (CSS variables) and keep the
  // browser UI chrome (mobile address bar) in sync.
  useEffect(() => {
    const root = document.documentElement
    root.dataset.theme = theme
    try { localStorage.setItem(THEME_KEY, theme) } catch { /* private mode */ }
    const meta = document.querySelector('meta[name="theme-color"]')
    if (meta) meta.setAttribute('content', theme === 'day' ? '#F4F7FB' : '#0B1220')
    root.classList.add('theme-switching')
    const t = setTimeout(() => root.classList.remove('theme-switching'), 350)
    return () => clearTimeout(t)
  }, [theme])

  const toggleTheme = useCallback(() => {
    setTheme((t) => (t === 'night' ? 'day' : 'night'))
  }, [])

  const toast = useCallback((message, type = 'info') => {
    const id = ++toastSeq
    setToasts((t) => [...t, { id, message, type }])
    timers.current[id] = setTimeout(() => {
      setToasts((t) => t.filter((x) => x.id !== id))
      delete timers.current[id]
    }, 4200)
  }, [])

  const setActiveId = useCallback((id) => {
    const val = id ? String(id) : ''
    localStorage.setItem('datalab.activeId', val)
    setActiveIdState(val)
  }, [])

  const refreshDatasets = useCallback(async () => {
    try {
      const data = await api('/datasets')
      setDatasets(data.datasets || [])
      return data.datasets || []
    } catch {
      return []
    }
  }, [])

  const refreshActive = useCallback(async () => {
    if (!activeId) {
      setActiveMeta(null)
      return
    }
    try {
      const meta = await api(`/datasets/${activeId}`)
      setActiveMeta(meta)
    } catch (err) {
      if (err.status === 404) setActiveId('')
      setActiveMeta(null)
    }
  }, [activeId, setActiveId])

  useEffect(() => { refreshActive() }, [refreshActive])
  useEffect(() => { refreshDatasets() }, [refreshDatasets])
  useEffect(() => () => Object.values(timers.current).forEach(clearTimeout), [])

  const value = {
    activeId, activeMeta, setActiveId, refreshActive,
    datasets, refreshDatasets,
    toast,
    theme, toggleTheme,
  }

  return (
    <AppContext.Provider value={value}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`toast ${t.type}`}>
            {t.type === 'success' && <CheckCircle2 size={16} color="var(--ok)" />}
            {t.type === 'error' && <XCircle size={16} color="var(--danger)" />}
            {!t.type || t.type === 'info' ? <Info size={16} color="var(--accent)" /> : null}
            <span>{t.message}</span>
          </div>
        ))}
      </div>
    </AppContext.Provider>
  )
}

export function useApp() {
  return useContext(AppContext)
}
