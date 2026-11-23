import { useEffect, useState } from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { api, fmtInt } from '../api'
import { useApp } from '../context'
import { NoDataset, PageHead, RoleBadge, Spinner } from '../components/ui'

export default function Preview() {
  const { activeId, activeMeta } = useApp()
  const [data, setData] = useState(null)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(50)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!activeId) { setData(null); return undefined }
    let alive = true
    setLoading(true)
    setError('')
    api(`/datasets/${activeId}/preview?page=${page}&page_size=${pageSize}`)
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(e.message))
      .finally(() => alive && setLoading(false))
    return () => { alive = false }
  }, [activeId, page, pageSize])

  if (!activeId) return <NoDataset />

  return (
    <div>
      <PageHead
        title="Preview"
        sub={activeMeta ? `${activeMeta.name} — column names, detected types and the data itself` : ''}
      />
      {loading && !data ? <Spinner /> : error ? (
        <div className="card"><p className="muted">{error}</p></div>
      ) : data ? (
        <>
          <div className="card mb-16">
            <div className="card-title" style={{ marginBottom: 8 }}>
              <h3>Columns ({data.columns.length})</h3>
              <span className="hint">{fmtInt(data.total_rows)} rows total</span>
            </div>
            <div className="flex gap-8 wrap">
              {data.columns.map((c) => (
                <span key={c.name} className="chip" title={`${c.missing} missing · ${c.unique} unique values`}>
                  {c.name} <RoleBadge role={c.role} />
                </span>
              ))}
            </div>
          </div>

          <div className="card">
            <div className="card-title">
              <h3>Data</h3>
              <span className="hint">{loading ? 'Loading…' : `Page ${data.page} of ${data.total_pages}`}</span>
            </div>
            <div className="table-wrap" style={{ maxHeight: '58vh' }}>
              <table className="table">
                <thead>
                  <tr>
                    <th style={{ textAlign: 'right' }}>#</th>
                    {data.columns.map((c) => (
                      <th key={c.name}>{c.name} <RoleBadge role={c.role} /></th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.rows.map((row, ri) => (
                    <tr key={ri}>
                      <td className="num faint">{(data.page - 1) * data.page_size + ri + 1}</td>
                      {row.map((v, ci) => (
                        <td key={ci} className="num">
                          {v === null ? <span className="na" title="missing value">—</span> : String(v)}
                        </td>
                      ))}
                    </tr>
                  ))}
                  {data.rows.length === 0 && (
                    <tr><td colSpan={data.columns.length + 1} className="muted">This dataset has no rows.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
            <div className="pager">
              <span className="info">
                Showing {data.total_rows === 0 ? 0 : (data.page - 1) * data.page_size + 1}–
                {Math.min(data.page * data.page_size, data.total_rows)} of {fmtInt(data.total_rows)} rows
              </span>
              <label className="small muted" htmlFor="pgsize">Rows per page</label>
              <select id="pgsize" className="select" style={{ width: 80 }} value={pageSize}
                onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1) }}>
                <option value={25}>25</option>
                <option value={50}>50</option>
                <option value={100}>100</option>
                <option value={250}>250</option>
              </select>
              <button className="btn btn-sm" disabled={data.page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}><ChevronLeft size={14} /> Prev</button>
              <button className="btn btn-sm" disabled={data.page >= data.total_pages}
                onClick={() => setPage((p) => Math.min(data.total_pages, p + 1))}>Next <ChevronRight size={14} /></button>
            </div>
          </div>
        </>
      ) : null}
    </div>
  )
}
