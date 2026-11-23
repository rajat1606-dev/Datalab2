import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Database, Moon, RefreshCw, Sun } from 'lucide-react'
import { fmtInt } from '../api'
import { useApp } from '../context'
import { PageHead } from '../components/ui'

/** Settings: appearance (Day/Night), data tools and app info. */
export default function Settings() {
  const { theme, toggleTheme, datasets, refreshDatasets, activeId, activeMeta, toast } = useApp()
  const [busy, setBusy] = useState(false)

  const setMode = (mode) => {
    if (theme !== mode) toggleTheme()
  }

  const refresh = async () => {
    setBusy(true)
    try {
      const list = await refreshDatasets()
      toast(`Dataset list refreshed — ${list.length} dataset(s) found.`, 'success')
    } catch (e) {
      toast(e.message, 'error')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <PageHead title="Settings" sub="Appearance, data tools and information about this DataLab instance." />

      <div className="card mb-16">
        <div className="card-title"><h3>Appearance</h3><span className="hint">applied instantly across every page</span></div>
        <div className="flex gap-12 wrap">
          <button
            className={`format-option ${theme === 'day' ? 'active' : ''}`}
            style={{ maxWidth: 280 }}
            onClick={() => setMode('day')}
            aria-pressed={theme === 'day'}
          >
            <h4><Sun size={16} color="var(--warn)" /> Day mode</h4>
            <p>“Clean Analytics” — bright surfaces for well-lit rooms and daylight work.</p>
            {theme === 'day' && <span className="badge green mt-8" style={{ display: 'inline-flex' }}>Active</span>}
          </button>
          <button
            className={`format-option ${theme === 'night' ? 'active' : ''}`}
            style={{ maxWidth: 280 }}
            onClick={() => setMode('night')}
            aria-pressed={theme === 'night'}
          >
            <h4><Moon size={16} color="var(--accent)" /> Night mode</h4>
            <p>“Midnight Dashboard” — dark surfaces that are easy on the eyes.</p>
            {theme === 'night' && <span className="badge green mt-8" style={{ display: 'inline-flex' }}>Active</span>}
          </button>
        </div>
        <p className="small faint mt-16">
          The same toggle is available at any time in the top bar. Your choice is remembered on this device.
        </p>
      </div>

      <div className="grid-2 mb-16">
        <div className="card">
          <div className="card-title"><h3>Data</h3><span className="hint">stored locally in SQLite</span></div>
          <div className="kv"><span className="k">Datasets stored</span><span className="v">{fmtInt(datasets.length)}</span></div>
          <div className="kv"><span className="k">Active dataset</span><span className="v">{activeMeta ? activeMeta.name : '— none selected —'}</span></div>
          <div className="kv"><span className="k">Storage</span><span className="v">Browser session · local server</span></div>
          <div className="flex gap-8 mt-16 wrap">
            <button className="btn" onClick={refresh} disabled={busy}>
              <RefreshCw size={15} /> Refresh dataset list
            </button>
            <Link className="btn btn-ghost" to="/datasets"><Database size={15} /> Manage datasets</Link>
          </div>
        </div>

        <div className="card">
          <div className="card-title"><h3>Workflow</h3><span className="hint">how DataLab guides you</span></div>
          <div className="kv"><span className="k">1 · Upload Data</span><span className="v">CSV, Excel, JSON or manual entry</span></div>
          <div className="kv"><span className="k">2 · Clean Data</span><span className="v">auto &amp; manual cleaning, transform</span></div>
          <div className="kv"><span className="k">3 · Visualize Data</span><span className="v">profiling, charts, statistics</span></div>
          <div className="kv"><span className="k">4 · Export Data</span><span className="v">CSV, Excel, JSON, PNG, reports</span></div>
          <p className="small faint mt-16">
            Need to retrace a step? Every action is recorded — see <Link to="/history">History</Link>.
          </p>
        </div>
      </div>

      <div className="card">
        <div className="card-title"><h3>About</h3></div>
        <div className="kv"><span className="k">Application</span><span className="v">DataLab 2.1</span></div>
        <div className="kv"><span className="k">Engine</span><span className="v">FastAPI + pandas · React + Plotly</span></div>
        <div className="kv"><span className="k">Data privacy</span><span className="v">Your files never leave this server</span></div>
      </div>
    </div>
  )
}
