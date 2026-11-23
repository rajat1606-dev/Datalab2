import { useCallback, useEffect, useState } from 'react'
import { Eye, Play, SlidersHorizontal, AlertTriangle } from 'lucide-react'
import { api } from '../../api'
import { useApp } from '../../context'
import { NoDataset, PageHead } from '../../components/ui'
import { LoadState, MiniTable, OpForm } from '../../components/cleanflow'

export default function CFTransform() {
  const { activeId, activeMeta, refreshActive, refreshDatasets, toast } = useApp()
  const [catalog, setCatalog] = useState([])
  const [opType, setOpType] = useState('')
  const [params, setParams] = useState({})
  const [preview, setPreview] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    api('/cleanflow/ops').then((r) => setCatalog(r.operations)).catch(() => {})
  }, [])

  const loadColumns = useCallback(() => {
    if (!activeId) return null
    return api(`/datasets/${activeId}/columns`).then((r) => r.columns)
  }, [activeId])

  const [columns, setColumns] = useState([])
  useEffect(() => {
    if (!activeId) { setColumns([]); return }
    loadColumns().then(setColumns).catch(() => setColumns([]))
  }, [activeId, loadColumns])

  const opMeta = catalog.find((o) => o.type === opType)

  const chooseOp = (type) => {
    setOpType(type)
    setPreview(null)
    setError('')
    const meta = catalog.find((o) => o.type === type)
    const init = {}
    for (const f of meta?.fields || []) {
      if (f.default !== undefined && f.default !== null) init[f.name] = f.default
    }
    setParams(init)
  }

  const opPayload = () => {
    // only send fields that belong to this op
    const clean = {}
    for (const f of opMeta?.fields || []) {
      if (params[f.name] !== undefined && params[f.name] !== '' && params[f.name] !== null) {
        clean[f.name] = params[f.name]
      }
    }
    // booleans that were explicitly unticked must still be sent
    for (const f of opMeta?.fields || []) {
      if (f.type === 'bool' && params[f.name] === undefined && f.default !== undefined) {
        clean[f.name] = f.default
      }
    }
    return { type: opType, ...clean, approved: true }
  }

  const doPreview = async () => {
    setBusy(true)
    setError('')
    setPreview(null)
    try {
      const res = await api(`/cleanflow/datasets/${activeId}/pipeline/preview`, {
        method: 'POST',
        body: { steps: [opPayload()] },
      })
      setPreview(res.steps?.[0] || null)
      if (res.steps?.[0]?.status === 'error') setError(res.steps[0].message)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const doApply = async () => {
    setBusy(true)
    setError('')
    try {
      const res = await api(`/cleanflow/datasets/${activeId}/clean`, {
        method: 'POST',
        body: { operations: [opPayload()] },
      })
      toast(res.summary, 'success')
      setPreview(null)
      await refreshActive()
      refreshDatasets()
      // refresh columns (one-hot/rename change the schema)
      loadColumns().then(setColumns).catch(() => {})
    } catch (e) {
      setError(e.message)
      toast(e.message, 'error')
    } finally {
      setBusy(false)
    }
  }

  if (!activeId) return <NoDataset text="Pick a dataset in the top bar to transform it." />

  const groups = [...new Set(catalog.map((o) => o.group))]

  return (
    <div>
      <PageHead
        title="Transform data"
        sub={activeMeta ? `Apply one transformation to "${activeMeta.name}" — preview it first, then apply` : ''}
      />

      <LoadState loading={busy && !preview} error={''} onRetry={() => setError('')} empty={false}>
        {error && (
          <div className="card mb-16" style={{ borderColor: 'rgba(var(--danger-rgb), 0.4)' }}>
            <div className="error-box">
              <AlertTriangle size={20} color="var(--danger)" />
              <div><strong>Operation error</strong><p className="small muted">{error}</p></div>
              <button className="btn btn-sm" onClick={() => setError('')}>Dismiss</button>
            </div>
          </div>
        )}
        <div className="pipeline-layout">
          <div className="card">
            <div className="card-title"><h3>Operations</h3><span className="hint">pick one</span></div>
            {groups.map((g) => (
              <div className="palette-group" key={g}>
                <div className="nav-label">{g}</div>
                {catalog.filter((o) => o.group === g).map((o) => (
                  <button key={o.type} className={`palette-item ${opType === o.type ? 'active' : ''}`}
                    style={opType === o.type ? { borderColor: 'var(--accent)' } : undefined}
                    onClick={() => chooseOp(o.type)}>
                    <SlidersHorizontal size={13} /> {o.label}
                    {o.destructive && <span className="badge red" style={{ marginLeft: 'auto' }}>!</span>}
                  </button>
                ))}
              </div>
            ))}
          </div>

          <div>
            <div className="card mb-16">
              {!opMeta ? (
                <p className="muted small center-load">Choose an operation from the left to configure it.</p>
              ) : (
                <>
                  <div className="card-title">
                    <h3>{opMeta.label}</h3>
                    <span className="hint">{opMeta.destructive ? 'changes data — preview before applying' : 'safe operation'}</span>
                  </div>
                  <OpForm opMeta={opMeta} value={params} onChange={setParams} columns={columns} />
                  <div className="flex gap-8 mt-16 wrap">
                    <button className="btn" onClick={doPreview} disabled={busy}>
                      <Eye size={15} /> Dry-run preview
                    </button>
                    <button className="btn btn-primary" onClick={doApply} disabled={busy || !opType}>
                      <Play size={15} /> Apply to dataset
                    </button>
                  </div>
                  <p className="small faint mt-8">
                    The preview never saves anything — it shows exactly what the first 5 rows
                    would look like afterwards.
                  </p>
                </>
              )}
            </div>

            {preview && (
              <div className="card">
                <div className="card-title">
                  <h3>Preview after “{preview.label}”</h3>
                  <span className={`badge ${preview.status === 'ok' ? 'green' : 'red'}`}>
                    {preview.status === 'ok'
                      ? `${preview.rows_in} → ${preview.rows_out} rows · ${preview.cols_in} → ${preview.cols_out} cols`
                      : 'error'}
                  </span>
                </div>
                {preview.status === 'ok' && (
                  <>
                    <p className="small muted mb-8">{preview.message}</p>
                    <MiniTable columns={preview.columns} rows={preview.preview} />
                  </>
                )}
              </div>
            )}
          </div>
        </div>
      </LoadState>
    </div>
  )
}
