import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { CheckCircle2, Database, Pencil, PieChart, Trash2 } from 'lucide-react'
import { api, fmtInt, fmtTime } from '../api'
import { useApp } from '../context'
import { ConfirmDialog, EmptyState, PageHead, Spinner } from '../components/ui'

export default function Datasets() {
  const { activeId, setActiveId, refreshDatasets, toast } = useApp()
  const navigate = useNavigate()
  const [rows, setRows] = useState(null)
  const [toDelete, setToDelete] = useState(null)
  const [busy, setBusy] = useState(false)

  const load = () => api('/datasets').then((d) => setRows(d.datasets)).catch((e) => toast(e.message, 'error'))

  useEffect(() => { load() }, [])

  const makeActive = (id) => {
    setActiveId(id)
    toast('Active dataset selected.', 'success')
  }

  const doDelete = async () => {
    if (!toDelete) return
    setBusy(true)
    try {
      await api(`/datasets/${toDelete.id}`, { method: 'DELETE' })
      if (String(toDelete.id) === activeId) setActiveId('')
      toast(`Deleted "${toDelete.name}".`, 'success')
      setToDelete(null)
      await refreshDatasets()
      load()
    } catch (e) {
      toast(e.message, 'error')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <PageHead title="Datasets" sub="Everything stored in the DataLab database (SQLite)">
        <Link to="/upload" className="btn btn-primary">Upload file</Link>
        <Link to="/entry" className="btn">Manual entry</Link>
      </PageHead>

      {!rows ? <Spinner /> : rows.length === 0 ? (
        <EmptyState
          icon={Database}
          title="No datasets yet"
          text="Upload a CSV or Excel file, or create a dataset with the manual entry grid."
        >
          <Link className="btn btn-primary" to="/upload">Upload file</Link>
          <Link className="btn" to="/entry">Enter manually</Link>
        </EmptyState>
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Name</th><th className="num">Rows</th><th className="num">Cols</th>
                <th>Created</th><th>Updated</th><th>Status</th><th style={{ minWidth: 250 }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((d) => (
                <tr key={d.id}>
                  <td>
                    <div className="rowhead">{d.name}</div>
                    {d.description ? <div className="small faint">{d.description}</div> : null}
                  </td>
                  <td className="num">{fmtInt(d.rows)}</td>
                  <td className="num">{d.cols}</td>
                  <td className="small muted">{fmtTime(d.created_at)}</td>
                  <td className="small muted">{fmtTime(d.updated_at)}</td>
                  <td>{String(d.id) === activeId ? <span className="badge green">Active</span> : <span className="badge gray">—</span>}</td>
                  <td>
                    <div className="flex gap-8 wrap">
                      {String(d.id) !== activeId && (
                        <button className="btn btn-sm" onClick={() => makeActive(d.id)}><CheckCircle2 size={13} /> Set active</button>
                      )}
                      <button className="btn btn-sm" onClick={() => { makeActive(d.id); navigate('/preview') }}>Preview</button>
                      <button className="btn btn-sm" onClick={() => { makeActive(d.id); navigate('/charts') }}><PieChart size={13} /> Charts</button>
                      <button className="btn btn-sm" onClick={() => { makeActive(d.id); navigate('/entry') }}><Pencil size={13} /> Edit</button>
                      <button className="btn btn-danger btn-sm" onClick={() => setToDelete(d)}><Trash2 size={13} /></button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <ConfirmDialog
        open={!!toDelete}
        title="Delete dataset?"
        message={toDelete ? `"${toDelete.name}" (${fmtInt(toDelete.rows)} rows) will be permanently removed from the database.` : ''}
        confirmLabel="Delete"
        danger
        busy={busy}
        onConfirm={doDelete}
        onCancel={() => setToDelete(null)}
      />
    </div>
  )
}
