import { useCallback, useEffect, useState } from 'react'
import { History as HistoryIcon, Trash2 } from 'lucide-react'
import { api, fmtInt, fmtTime } from '../../api'
import { useApp } from '../../context'
import { EmptyState, PageHead } from '../../components/ui'

const ACTION_LABEL = {
  clean: 'Cleaning applied',
  undo: 'Undo',
  pipeline_run: 'Pipeline run',
}

export default function CFHistory() {
  const { datasets, activeId } = useApp()
  const [rows, setRows] = useState([])
  const [filter, setFilter] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(() => {
    setLoading(true)
    setError('')
    const q = filter ? `?dataset_id=${filter}` : ''
    api(`/cleanflow/history${q}`)
      .then((r) => setRows(r.history))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [filter])

  useEffect(() => { load() }, [load])

  return (
    <div>
      <PageHead
        title="CleanFlow · Cleaning history"
        sub="Every automatic and manual cleaning batch, with before/after scores — full accountability for your data"
      >
        <select className="select" style={{ maxWidth: 260 }} value={filter}
          onChange={(e) => setFilter(e.target.value)} aria-label="Filter by dataset">
          <option value="">All datasets</option>
          {datasets.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
        </select>
        <button className="btn btn-ghost" onClick={load}>Refresh</button>
      </PageHead>

      {loading ? (
        <div className="card"><p className="muted small center-load">Loading history…</p></div>
      ) : error ? (
        <div className="card"><p className="small" style={{ color: 'var(--danger)' }}>{error}</p></div>
      ) : rows.length === 0 ? (
        <EmptyState
          icon={HistoryIcon}
          title="No cleaning history yet"
          text={filter
            ? 'This dataset has no recorded cleaning operations. Run Auto Cleaning or a pipeline first.'
            : 'Run Auto Cleaning, a Transformation or an ELT pipeline and every step will be logged here.'}
        />
      ) : (
        <div className="card">
          {rows.map((r) => (
            <div key={r.id} className="step-item">
              <div className="step-head">
                <span className="badge blue">{ACTION_LABEL[r.action] || r.action}</span>
                <span className="step-title">{r.dataset_name}</span>
                {r.score_before !== null && r.score_after !== null && (
                  <span className="badge cyan">{r.score_before} → {r.score_after} pts</span>
                )}
                {r.rows_before !== null && r.rows_after !== null && r.rows_before !== r.rows_after && (
                  <span className="badge violet">{fmtInt(r.rows_before)} → {fmtInt(r.rows_after)} rows</span>
                )}
                <span className="activity-time">{fmtTime(r.created_at)}</span>
              </div>
              {r.summary && <p className="small muted mt-8">{r.summary}</p>}
              {r.operations.length > 0 && (
                <div className="mt-8">
                  {r.operations.map((o, i) => (
                    <div key={i} className="activity-item">
                      <span className={`badge ${o.destructive ? 'red' : 'cyan'}`}>{o.label || o.op}</span>
                      <span style={{ flex: 1 }}>{o.detail}</span>
                      {o.affected > 0 && <span className="badge gray">{fmtInt(o.affected)}</span>}
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
