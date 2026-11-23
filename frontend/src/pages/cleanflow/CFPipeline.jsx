import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  AlertTriangle, ArrowDown, ArrowUp, Eye, Plus, Rocket, Save, Trash2, X,
} from 'lucide-react'
import { api, fmtInt, fmtTime } from '../../api'
import { useApp } from '../../context'
import { NoDataset, PageHead } from '../../components/ui'
import { LoadState, MiniTable, OpForm } from '../../components/cleanflow'

export default function CFPipeline() {
  const { activeId, activeMeta, refreshDatasets, setActiveId, toast } = useApp()
  const [catalog, setCatalog] = useState([])
  const [columns, setColumns] = useState([])
  const [steps, setSteps] = useState([])
  const [editing, setEditing] = useState(null)          // step index being edited
  const [preview, setPreview] = useState(null)          // dry-run result
  const [runResult, setRunResult] = useState(null)      // run result
  const [pipelines, setPipelines] = useState([])
  const [runs, setRuns] = useState([])
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    api('/cleanflow/ops').then((r) => setCatalog(r.operations)).catch(() => {})
  }, [])

  const loadSide = useCallback(() => {
    api('/cleanflow/pipelines').then((r) => setPipelines(r.pipelines)).catch(() => {})
    api('/cleanflow/runs').then((r) => setRuns(r.runs.slice(0, 8))).catch(() => {})
  }, [])
  useEffect(() => { loadSide() }, [loadSide])

  useEffect(() => {
    if (!activeId) { setColumns([]); return }
    api(`/datasets/${activeId}/columns`).then((r) => setColumns(r.columns)).catch(() => setColumns([]))
  }, [activeId])

  const addStep = (opType) => {
    const meta = catalog.find((o) => o.type === opType)
    if (!meta) return
    const init = { type: opType }
    for (const f of meta.fields || []) {
      if (f.default !== undefined && f.default !== null) init[f.name] = f.default
    }
    setSteps((s) => [...s, init])
    setEditing(steps.length)
    setPreview(null)
    setRunResult(null)
  }

  const updateStep = (idx, params) => {
    setSteps((s) => s.map((st, i) => (i === idx ? params : st)))
  }

  const removeStep = (idx) => {
    setSteps((s) => s.filter((_, i) => i !== idx))
    setEditing(null)
    setPreview(null)
  }

  const move = (idx, dir) => {
    setSteps((s) => {
      const next = [...s]
      const j = idx + dir
      if (j < 0 || j >= next.length) return s
      ;[next[idx], next[j]] = [next[j], next[idx]]
      return next
    })
    setPreview(null)
  }

  const dryRun = async () => {
    if (!steps.length) { toast('Add at least one step first.', 'error'); return }
    setBusy(true)
    setError('')
    setPreview(null)
    try {
      const res = await api(`/cleanflow/datasets/${activeId}/pipeline/preview`, {
        method: 'POST', body: { steps },
      })
      setPreview(res)
      if (res.summary.status === 'error') toast('Pipeline stopped at a failing step — see below.', 'error')
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const runPipeline = async () => {
    if (!steps.length) { toast('Add at least one step first.', 'error'); return }
    setBusy(true)
    setError('')
    try {
      const res = await api(`/cleanflow/datasets/${activeId}/pipeline/run`, {
        method: 'POST', body: { steps, result_name: name.trim() ? `${activeMeta?.name || 'Dataset'} · ${name.trim()}` : undefined },
      })
      setRunResult(res)
      setPreview(null)
      toast(`Pipeline finished — created "${res.result.name}".`, 'success')
      await refreshDatasets()
      loadSide()
    } catch (e) {
      setError(e.message)
      toast(e.message, 'error')
      loadSide()
    } finally {
      setBusy(false)
    }
  }

  const savePipeline = async () => {
    if (!steps.length) { toast('Nothing to save — add steps first.', 'error'); return }
    if (!name.trim()) { toast('Give the pipeline a name first.', 'error'); return }
    setBusy(true)
    try {
      await api('/cleanflow/pipelines', {
        method: 'POST',
        body: { name: name.trim(), description: description.trim(), steps },
      })
      toast(`Pipeline "${name.trim()}" saved.`, 'success')
      loadSide()
    } catch (e) {
      toast(e.message, 'error')
    } finally {
      setBusy(false)
    }
  }

  const loadPipeline = async (pid) => {
    try {
      const p = await api(`/cleanflow/pipelines/${pid}`)
      setSteps(p.steps)
      setName(p.name)
      setDescription(p.description || '')
      setPreview(null)
      setRunResult(null)
      toast(`Loaded "${p.name}" — review the source dataset, then run it.`, 'info')
    } catch (e) {
      toast(e.message, 'error')
    }
  }

  const deletePipeline = async (pid) => {
    try {
      await api(`/cleanflow/pipelines/${pid}`, { method: 'DELETE' })
      loadSide()
    } catch (e) {
      toast(e.message, 'error')
    }
  }

  if (!activeId) return <NoDataset text="Pick a source dataset in the top bar, then arrange cleaning steps and run them." />

  const groups = [...new Set(catalog.map((o) => o.group))]

  return (
    <div>
      <PageHead
        title="CleanFlow · ELT pipeline builder"
        sub={activeMeta ? `Extract → Load → Transform on "${activeMeta.name}" — the source stays untouched; results become a new dataset` : ''}
      />

      <LoadState loading={false} error={''} onRetry={() => setError('')} empty={false}>
        <div className="pipeline-layout">
          <div className="card">
            <div className="card-title"><h3>Add a step</h3></div>
            {groups.map((g) => (
              <div className="palette-group" key={g}>
                <div className="nav-label">{g}</div>
                {catalog.filter((o) => o.group === g).map((o) => (
                  <button key={o.type} className="palette-item" onClick={() => addStep(o.type)}>
                    <Plus size={13} /> {o.label}
                  </button>
                ))}
              </div>
            ))}
          </div>

          <div>
            {error && (
              <div className="card mb-16" style={{ borderColor: 'rgba(248,113,113,0.4)' }}>
                <div className="error-box">
                  <AlertTriangle size={20} color="var(--danger)" />
                  <div><strong>Pipeline error</strong><p className="small muted">{error}</p></div>
                  <button className="btn btn-sm" onClick={() => setError('')}>Dismiss</button>
                </div>
              </div>
            )}
            <div className="card mb-16">
              <div className="card-title">
                <h3>Execution sequence</h3>
                <span className="hint">{steps.length} step(s) · run top → bottom</span>
              </div>

              {steps.length === 0 && (
                <p className="muted small">No steps yet — click operations on the left to build your pipeline.</p>
              )}

              {steps.map((step, idx) => {
                const meta = catalog.find((o) => o.type === step.type)
                return (
                  <div className="step-item" key={idx}>
                    <div className="step-head">
                      <span className="step-num">{idx + 1}</span>
                      <span className="step-title">{meta?.label || step.type}</span>
                      {meta?.destructive && <span className="badge red">destructive</span>}
                      <div className="step-tools">
                        <button className="btn btn-icon btn-sm" title="Move up" onClick={() => move(idx, -1)} disabled={idx === 0}><ArrowUp size={13} /></button>
                        <button className="btn btn-icon btn-sm" title="Move down" onClick={() => move(idx, 1)} disabled={idx === steps.length - 1}><ArrowDown size={13} /></button>
                        <button className="btn btn-icon btn-sm" title="Edit" onClick={() => setEditing(editing === idx ? null : idx)}>✎</button>
                        <button className="btn btn-icon btn-sm btn-danger" title="Remove" onClick={() => removeStep(idx)}><X size={13} /></button>
                      </div>
                    </div>
                    {editing === idx && meta && (
                      <div className="mt-8">
                        <OpForm opMeta={meta} value={step} onChange={(v) => updateStep(idx, v)} columns={columns} />
                      </div>
                    )}
                    {editing !== idx && (
                      <p className="small faint mt-8">{describeStep(step)}</p>
                    )}
                  </div>
                )
              })}

              <div className="form-row mt-16">
                <div className="field">
                  <label htmlFor="pl-name">Pipeline name (also used for the result dataset)</label>
                  <input id="pl-name" className="input" value={name} placeholder="e.g. Standard monthly clean"
                    onChange={(e) => setName(e.target.value)} />
                </div>
                <div className="field">
                  <label htmlFor="pl-desc">Description (optional)</label>
                  <input id="pl-desc" className="input" value={description} placeholder="What this pipeline does"
                    onChange={(e) => setDescription(e.target.value)} />
                </div>
              </div>

              <div className="flex gap-8 wrap mt-8">
                <button className="btn" onClick={dryRun} disabled={busy || !steps.length}>
                  <Eye size={15} /> Dry run (preview every step)
                </button>
                <button className="btn btn-cyan" onClick={runPipeline} disabled={busy || !steps.length}>
                  <Rocket size={15} /> Run pipeline
                </button>
                <button className="btn btn-ghost" onClick={savePipeline} disabled={busy || !steps.length || !name.trim()}>
                  <Save size={15} /> Save configuration
                </button>
              </div>
              <p className="small faint mt-8">
                Running never modifies the source dataset — the cleaned output is saved as a
                separate dataset you can chart and export.
              </p>
            </div>

            {preview && (
              <div className="card mb-16">
                <div className="card-title">
                  <h3>Dry run result</h3>
                  <span className={`badge ${preview.summary.status === 'ok' ? 'green' : 'red'}`}>
                    {preview.summary.steps_ok}/{preview.summary.steps_total} steps ok ·
                    {' '}{fmtInt(preview.summary.rows_in)} → {fmtInt(preview.summary.rows_out)} rows
                  </span>
                </div>
                {preview.steps.map((s) => (
                  <div key={s.index} className={`step-item preview-step ${s.status === 'error' ? 'error' : ''}`}>
                    <div className="step-head">
                      <span className="step-num">{s.index}</span>
                      <span className="step-title">{s.label}</span>
                      <span className={`badge ${s.status === 'ok' ? 'green' : 'red'}`}>{s.status}</span>
                      <span className="small muted">{fmtInt(s.rows_in)} → {fmtInt(s.rows_out || s.rows_in)} rows</span>
                    </div>
                    <p className="small muted mt-8">{s.message}</p>
                    {s.status === 'ok' && s.preview && (
                      <div className="step-previews">
                        <MiniTable columns={s.columns} rows={s.preview} />
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}

            {runResult && (
              <div className="card mb-16">
                <div className="card-title">
                  <h3>Pipeline output</h3>
                  <span className="badge green">{runResult.summary.steps_ok} steps applied</span>
                </div>
                <div className="flex aic gap-12 wrap">
                  <span className="badge blue">{runResult.result.name}</span>
                  <span className="small muted">{fmtInt(runResult.result.rows)} rows × {runResult.result.cols} cols</span>
                  <button className="btn btn-sm" onClick={() => { setActiveId(runResult.result.id) }}>
                    Make active dataset
                  </button>
                  <Link className="btn btn-sm btn-primary" to="/cleanflow/report">View quality report</Link>
                  <Link className="btn btn-sm" to="/cleanflow/export">Export it</Link>
                </div>
              </div>
            )}

            <div className="grid-2 mb-16">
              <div className="card">
                <div className="card-title"><h3>Saved pipelines</h3><span className="hint">reusable configurations</span></div>
                {pipelines.length === 0 ? (
                  <p className="muted small">No saved pipelines yet. Build a sequence and click “Save configuration”.</p>
                ) : pipelines.map((p) => (
                  <div className="saved-pipeline-item" key={p.id}>
                    <div>
                      <div className="sp-name">{p.name}</div>
                      <div className="sp-meta">{p.steps_count} steps · saved {fmtTime(p.updated_at)}</div>
                    </div>
                    <div className="sp-actions">
                      <button className="btn btn-sm" onClick={() => loadPipeline(p.id)}>Load</button>
                      <button className="btn btn-sm btn-danger" onClick={() => deletePipeline(p.id)}><Trash2 size={12} /></button>
                    </div>
                  </div>
                ))}
              </div>

              <div className="card">
                <div className="card-title"><h3>Recent pipeline runs</h3><span className="hint">execution status</span></div>
                {runs.length === 0 ? (
                  <p className="muted small">No runs yet.</p>
                ) : (
                  <div className="table-wrap">
                    <table className="table">
                      <thead><tr><th>When</th><th>Dataset</th><th>Status</th><th className="num">Steps</th><th className="num">Rows</th></tr></thead>
                      <tbody>
                        {runs.map((r) => (
                          <tr key={r.id}>
                            <td className="small">{fmtTime(r.created_at)}</td>
                            <td className="small">{r.dataset_name}</td>
                            <td><span className={`badge ${r.status === 'ok' ? 'green' : 'red'}`}>{r.status}</span></td>
                            <td className="num">{r.steps_ok}/{r.steps_total}</td>
                            <td className="num">{fmtInt(r.rows_in)} → {fmtInt(r.rows_out)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </LoadState>
    </div>
  )
}

function describeStep(step) {
  const bits = []
  if (step.columns?.length) bits.push(`columns: ${step.columns.join(', ')}`)
  if (step.column) bits.push(`column: ${step.column}`)
  if (step.strategy) bits.push(`strategy: ${step.strategy}`)
  if (step.target) bits.push(`target: ${step.target}`)
  if (step.method) bits.push(`method: ${step.method} (${step.action})`)
  if (step.case && step.case !== 'none') bits.push(`case: ${step.case}`)
  if (step.new_name) bits.push(`→ "${step.new_name}"`)
  if (step.values?.length) bits.push(`values: ${step.values.join(', ')}`)
  return bits.length ? bits.join(' · ') : 'default parameters'
}
