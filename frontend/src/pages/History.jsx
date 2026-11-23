import { useCallback, useEffect, useState } from 'react'
import { History as HistoryIcon, Trash2 } from 'lucide-react'
import { api, fmtTime } from '../api'
import { useApp } from '../context'
import { ConfirmDialog, EmptyState, PageHead, Spinner } from '../components/ui'

const ACTION_STYLES = {
  uploaded: 'badge blue',
  created: 'badge blue',
  edited: 'badge violet',
  cleaned: 'badge amber',
  restored: 'badge amber',
  chart: 'badge cyan',
  exported: 'badge green',
  renamed: 'badge gray',
  deleted: 'badge red',
}

export default function History() {
  const { datasets, toast } = useApp()
  const [rows, setRows] = useState(null)
  const [filter, setFilter] = useState('')
  const [loading, setLoading] = useState(false)
  const [confirmClear, setConfirmClear] = useState(false)

  const load = useCallback(() => {
    setLoading(true)
    api(`/history?limit=200${filter ? `&dataset_id=${filter}` : ''}`)
      .then((d) => setRows(d.history))
      .catch((e) => toast(e.message, 'error'))
      .finally(() => setLoading(false))
  }, [filter, toast]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { load() }, [load])

  const clearAll = async () => {
    setConfirmClear(false)
    try {
      await api('/history', { method: 'DELETE' })
      toast('History cleared.', 'success')
      load()
    } catch (e) {
      toast(e.message, 'error')
    }
  }

  return (
    <div>
      <PageHead title="History" sub="Every upload, edit, cleaning step, chart and export is logged here.">
        <select className="select" style={{ width: 240 }} value={filter}
          onChange={(e) => setFilter(e.target.value)} aria-label="Filter by dataset">
          <option value="">All datasets</option>
          {datasets.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
        </select>
        <button className="btn btn-danger" onClick={() => setConfirmClear(true)}>
          <Trash2 size={15} /> Clear history
        </button>
      </PageHead>

      {rows === null ? <Spinner /> : rows.length === 0 ? (
        <EmptyState icon={HistoryIcon} title="No history yet"
          text="Actions like uploading, cleaning, charting and exporting will appear here." />
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr><th>When</th><th>Dataset</th><th>Action</th><th>Details</th></tr>
            </thead>
            <tbody>
              {rows.map((h) => (
                <tr key={h.id}>
                  <td className="small muted" style={{ whiteSpace: 'nowrap' }}>{fmtTime(h.created_at)}</td>
                  <td className="rowhead">{h.dataset_name || (h.dataset_id ? `#${h.dataset_id}` : '—')}</td>
                  <td><span className={ACTION_STYLES[h.action] || 'badge gray'}>{h.action}</span></td>
                  <td className="small muted">{h.detail}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <ConfirmDialog
        open={confirmClear}
        title="Clear all history?"
        message="All history entries will be permanently removed. Datasets are not affected."
        confirmLabel="Clear"
        danger
        onConfirm={clearAll}
        onCancel={() => setConfirmClear(false)}
      />
    </div>
  )
}
