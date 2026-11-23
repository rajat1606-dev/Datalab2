import { Menu } from 'lucide-react'
import { useApp } from '../context'
import { fmtInt } from '../api'

/** Top bar with the global active-dataset picker. */
export default function Topbar({ onToggleSidebar }) {
  const { datasets, activeId, setActiveId, activeMeta, refreshDatasets } = useApp()

  return (
    <header className="topbar">
      <button className="hamburger" onClick={onToggleSidebar} aria-label="Toggle navigation">
        <Menu size={18} />
      </button>
      <div className="ds-picker">
        <label htmlFor="ds-select">Active dataset</label>
        <select
          id="ds-select"
          className="select"
          style={{ maxWidth: 320 }}
          value={activeId}
          onChange={(e) => setActiveId(e.target.value)}
        >
          <option value="">— No dataset selected —</option>
          {datasets.map((d) => (
            <option key={d.id} value={d.id}>
              {d.name} ({fmtInt(d.rows)} × {d.cols})
            </option>
          ))}
        </select>
        {activeMeta && (
          <div className="ds-meta">
            <span className="badge blue">{fmtInt(activeMeta.rows)} rows</span>
            <span className="badge cyan">{activeMeta.cols} cols</span>
          </div>
        )}
      </div>
      <button
        className="btn btn-ghost btn-sm"
        onClick={refreshDatasets}
        title="Refresh dataset list"
      >
        Refresh
      </button>
    </header>
  )
}
