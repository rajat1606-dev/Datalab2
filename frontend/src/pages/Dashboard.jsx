import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  AlertCircle, Columns3, CopyX, Database, Layers, Rows3, Table2, Upload,
} from 'lucide-react'
import { api, fmtInt, fmtTime } from '../api'
import { useApp } from '../context'
import { themedLayout } from '../chartTheme'
import ChartRenderer from '../components/ChartRenderer'
import { EmptyState, PageHead, RoleBadge, Spinner, StatCard } from '../components/ui'

export default function Dashboard() {
  const { activeId, activeMeta, datasets, setActiveId } = useApp()
  const [dash, setDash] = useState(null)
  const [recent, setRecent] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let alive = true
    setDash(null)
    setRecent([])
    setError('')
    if (!activeId) return undefined
    setLoading(true)
    Promise.all([
      api(`/datasets/${activeId}/dashboard`),
      api(`/history?dataset_id=${activeId}&limit=8`),
    ])
      .then(([d, h]) => {
        if (!alive) return
        setDash(d)
        setRecent(h.history || [])
      })
      .catch((e) => alive && setError(e.message))
      .finally(() => alive && setLoading(false))
    return () => { alive = false }
  }, [activeId])

  const totalRows = datasets.reduce((s, d) => s + (d.rows || 0), 0)

  const missingFigure = dash && {
    data: [{
      type: 'bar',
      x: dash.column_details.map((c) => c.name),
      y: dash.column_details.map((c) => c.missing),
      marker: { color: '#3b82f6' },
    }],
    layout: themedLayout('Missing values by column', { height: 330 }),
  }

  const rolesFig = dash && {
    data: [{
      type: 'pie',
      labels: Object.entries(dash.roles_summary)
        .filter(([, v]) => v > 0)
        .map(([k]) => k),
      values: Object.entries(dash.roles_summary)
        .filter(([, v]) => v > 0)
        .map(([, v]) => v),
      hole: 0.55,
      marker: { colors: ['#22d3ee', '#a78bfa', '#3b82f6', '#64789a'] },
      textinfo: 'label+value',
    }],
    layout: themedLayout('Column types', { height: 330, margins: { l: 24, r: 24, t: 56, b: 24 } }),
  }

  return (
    <div>
      <PageHead
        title="Dashboard"
        sub={activeMeta ? `${activeMeta.name} — overview, data health and recent activity` : 'Overview of your datasets'}
      />

      {!activeId ? (
        <>
          <div className="stat-grid mb-16">
            <StatCard icon={Database} label="Datasets stored" value={fmtInt(datasets.length)} tone="cyan" />
            <StatCard icon={Rows3} label="Rows across all datasets" value={fmtInt(totalRows)} tone="violet" />
          </div>
          <EmptyState
            icon={Layers}
            title={datasets.length ? 'Select a dataset to see its dashboard' : 'Welcome to DataLab'}
            text={datasets.length
              ? 'Pick one from the "Active dataset" selector in the top bar, or manage them on the Datasets page.'
              : 'Start by uploading a CSV/Excel file or typing data into the manual entry grid.'}
          >
            <Link className="btn btn-primary" to="/upload"><Upload size={15} /> Upload data</Link>
            <Link className="btn" to="/entry"><Table2 size={15} /> Enter manually</Link>
            {datasets.length > 0 && <Link className="btn btn-ghost" to="/datasets">View datasets</Link>}
          </EmptyState>
          {datasets.length > 0 && (
            <div className="card mt-16">
              <div className="card-title"><h3>Your datasets</h3></div>
              <div className="flex gap-8 wrap">
                {datasets.map((d) => (
                  <button key={d.id} className="chip" style={{ cursor: 'pointer' }} onClick={() => setActiveId(d.id)}>
                    <Database size={12} /> {d.name} · {fmtInt(d.rows)} × {d.cols}
                  </button>
                ))}
              </div>
            </div>
          )}
        </>
      ) : loading ? (
        <Spinner />
      ) : error ? (
        <EmptyState icon={AlertCircle} title="Could not load the dashboard" text={error} />
      ) : dash ? (
        <>
          <div className="stat-grid mb-16">
            <StatCard icon={Rows3} label="Total rows" value={fmtInt(dash.rows)} sub={`updated ${fmtTime(dash.updated_at)}`} />
            <StatCard icon={Columns3} label="Columns" value={fmtInt(dash.cols)} sub={`${dash.roles_summary.numeric} numeric · ${dash.roles_summary.categorical} categorical`} tone="cyan" />
            <StatCard icon={AlertCircle} label="Missing values" value={fmtInt(dash.missing_cells)} sub={`${dash.missing_pct}% of all cells`} tone="amber" />
            <StatCard icon={CopyX} label="Duplicate rows" value={fmtInt(dash.duplicate_rows)} sub={`${dash.memory_mb} MB in memory`} tone={dash.duplicate_rows > 0 ? 'red' : 'green'} />
          </div>

          <div className="grid-2 mb-16">
            <div className="chart-card">
              <ChartRenderer figure={missingFigure} emptyText="No columns to analyze." />
            </div>
            <div className="chart-card">
              <ChartRenderer figure={rolesFig} emptyText="No columns to analyze." />
            </div>
          </div>

          <div className="grid-2">
            <div className="card">
              <div className="card-title">
                <h3>Columns</h3>
                <Link to="/preview" className="small">Open preview →</Link>
              </div>
              <div className="table-wrap" style={{ maxHeight: 340 }}>
                <table className="table">
                  <thead>
                    <tr><th>Column</th><th>Type</th><th className="num">Missing</th><th className="num">Unique</th><th>Examples</th></tr>
                  </thead>
                  <tbody>
                    {dash.column_details.map((c) => (
                      <tr key={c.name}>
                        <td className="rowhead">{c.name}</td>
                        <td><RoleBadge role={c.role} /></td>
                        <td className="num">{c.missing ? <span className="na">{fmtInt(c.missing)}</span> : 0}</td>
                        <td className="num">{fmtInt(c.unique)}</td>
                        <td className="small muted">{c.examples.map((v) => String(v)).join(', ') || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="card">
              <div className="card-title">
                <h3>Recent activity</h3>
                <Link to="/history" className="small">Full history →</Link>
              </div>
              {recent.length === 0
                ? <p className="muted small">No activity recorded for this dataset yet.</p>
                : recent.map((h) => (
                  <div className="activity-item" key={h.id}>
                    <span className="activity-time">{fmtTime(h.created_at)}</span>
                    <span className={`badge ${h.action === 'cleaned' ? 'amber' : h.action === 'chart' ? 'cyan' : h.action === 'exported' ? 'green' : 'blue'}`}>{h.action}</span>
                    <span className="muted">{h.detail}</span>
                  </div>
                ))}
            </div>
          </div>
        </>
      ) : null}
    </div>
  )
}
