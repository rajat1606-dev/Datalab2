import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { CheckCircle2, Info, XCircle } from 'lucide-react'
import { api } from './api'

const AppContext = createContext(null)

let toastSeq = 0

export function AppProvider({ children }) {
  const [activeId, setActiveIdState] = useState(() => localStorage.getItem('datalab.activeId') || '')
  const [activeMeta, setActiveMeta] = useState(null)
  const [datasets, setDatasets] = useState([])
  const [toasts, setToasts] = useState([])
  const timers = useRef({})

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
  }

  return (
    <AppContext.Provider value={value}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`toast ${t.type}`}>
            {t.type === 'success' && <CheckCircle2 size={16} color="#34d399" />}
            {t.type === 'error' && <XCircle size={16} color="#f87171" />}
            {!t.type || t.type === 'info' ? <Info size={16} color="#60a5fa" /> : null}
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
