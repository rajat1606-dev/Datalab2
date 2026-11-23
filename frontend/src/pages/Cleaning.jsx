import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertCircle, CopyX, Eraser, RotateCcw, Wand2 } from 'lucide-react'
import { api, fmtInt } from '../api'
import { useApp } from '../context'
import { ConfirmDialog, NoDataset, PageHead, RoleBadge, Spinner, StatCard } from '../components/ui'

const STRATEGIES = [
  { value: 'mean', label: 'Fill with mean (numeric only)' },
  { value: 'median', label: 'Fill with median (numeric only)' },
  { value: 'mode', label: 'Fill with most frequent' },
  { value: 'ffill', label: 'Fill forward' },
  { value: 'bfill', label: 'Fill backward' },
  { value: 'constant', label: 'Fill with custom value' },
]

const TARGETS = [
  { value: 'number', label: 'Number' },
  { value: 'date', label: 'Date' },
  { value: 'text', label: 'Text' },
  { value: 'categorical', label: 'Category' },
]

const defaultStrategy = (role) => (role === 'numeric' ? 'mean' : 'mode')

export default function Cleaning() {
  const { activeId, activeMeta, refreshActive, refreshDatasets, toast } = useApp()
  const [dash, setDash] = useState(null)
  const [loading, setLoading] = useState(false)
  const [busy, setBusy] = useState(false)
  const [fillPlan, setFillPlan] = useState({})
  const [dupKeep, setDupKeep] = useState('first')
  const [dropHow, setDropHow] = useState('any')
  const [convPlan, setConvPlan] = useState({})
  const [confirmRestore, setConfirmRestore] = useState(false)

  const load = useCallback(() => {
    if (!activeId) { setDash(null); return }
    setLoading(true)
    api(`/datasets/${activeId}/dashboard`)
      .then((d) => {
        setDash(d)
        const plan = {}
        d.column_details.forEach((c) => {
          if (c.missing > 0) plan[c.name] = { strategy: defaultStrategy(c.role), value: '' }
        })
        setFillPlan(plan)
        setConvPlan({})
      })
      .catch((e) => toast(e.message, 'error'))
      .finally(() => setLoading(false))
  }, [activeId, toast])

  useEffect(() => { load() }, [load])

  const apply = async (operations, okMessage) => {
    setBusy(true)
    try {
      const res = await api(`/datasets/${activeId}/clean`, { method: 'POST', body: { operations } })
      toast(okMessage || res.summary, 'success')
      load()
      refreshActive()
      refreshDatasets()
    } catch (e) {
      toast(e.message, 'error')
    } finally {
      setBusy(false)
    }
  }

  if (!activeId) return <NoDataset text="Pick a dataset in the top bar to start cleaning it." />

  const missingCols = dash ? dash.column_details.filter((c) => c.missing > 0) : []

  const applyFills = () => {
    const ops = []
    const constByCol = {}
    missingCols.forEach((c) => {
      const p = fillPlan[c.name]
      if (!p || p.strategy === 'skip') return
      if (p.strategy === 'constant') {
        if (!constByCol[p.value ?? '']) constByCol[p.value ?? ''] = []
        constByCol[p.value ?? ''].push(c.name)
      } else {
        ops.push({ type: 'fill_missing', columns: [c.name], strategy: p.strategy })
      }
    })
    Object.entries(constByCol).forEach(([value, cols]) => {
      ops.push({ type: 'fill_missing', columns: cols, strategy: 'constant', value: value === '' ? null : value })
    })
    if (!ops.length) {
      toast('Choose a strategy for at least one column first.', 'error')
      return
    }
    apply(ops, 'Missing values handled.')
  }

  return (
    <div>
      <PageHead title="Manual cleaning tools" sub={activeMeta ? `Fix missing values, duplicates and wrong types in "${activeMeta.name}"` : ''}>
        <button className="btn btn-ghost" onClick={load} disabled={loading}>Reload</button>
      </PageHead>

      {loading && !dash ? <Spinner /> : dash ? (
        <>
          <div className="stat-grid mb-16">
            <StatCard icon={CopyX} label="Rows" value={fmtInt(dash.rows)} />
            <StatCard icon={AlertCircle} label="Missing cells" value={fmtInt(dash.missing_cells)} sub={`${missingCols.length} column(s) affected`} tone="amber" />
            <StatCard icon={CopyX} label="Duplicate rows" value={fmtInt(dash.duplicate_rows)} tone={dash.duplicate_rows ? 'red' : 'green'} />
            <StatCard icon={Wand2} label="Columns" value={fmtInt(dash.cols)} tone="cyan" />
          </div>

          {/* ---- missing values ---- */}
          <div className="card mb-16">
            <div className="card-title"><h3>1 · Missing values</h3><span className="hint">choose a strategy per column</span></div>
            {missingCols.length === 0 ? (
              <p className="muted small">No missing values in this dataset — nice and tidy.</p>
            ) : (
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr><th>Column</th><th>Type</th><th className="num">Missing</th><th>Strategy</th><th>Custom value</th></tr>
                  </thead>
                  <tbody>
                    {missingCols.map((c) => {
                      const p = fillPlan[c.name] || { strategy: defaultStrategy(c.role), value: '' }
                      return (
                        <tr key={c.name}>
                          <td className="rowhead">{c.name}</td>
                          <td><RoleBadge role={c.role} /></td>
                          <td className="num">{fmtInt(c.missing)}</td>
                          <td>
                            <select className="select" style={{ minWidth: 220 }}
                              value={p.strategy}
                              onChange={(e) => setFillPlan({ ...fillPlan, [c.name]: { ...p, strategy: e.target.value } })}>
                              {STRATEGIES.map((s) => (
                                <option key={s.value} value={s.value} disabled={(s.value === 'mean' || s.value === 'median') && c.role !== 'numeric'}>
                                  {s.label}
                                </option>
                              ))}
                            </select>
                          </td>
                          <td>
                            <input className="input" style={{ minWidth: 120 }} placeholder="value…"
                              disabled={p.strategy !== 'constant'}
                              value={p.value}
                              onChange={(e) => setFillPlan({ ...fillPlan, [c.name]: { ...p, value: e.target.value } })} />
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
            {missingCols.length > 0 && (
              <button className="btn btn-primary mt-16" onClick={applyFills} disabled={busy}>
                <Wand2 size={15} /> Apply selected fills
              </button>
            )}
          </div>

          <div className="grid-2 mb-16">
            {/* ---- duplicates ---- */}
            <div className="card">
              <div className="card-title"><h3>2 · Duplicate rows</h3></div>
              <p className="small muted mb-8">
                {dash.duplicate_rows > 0
                  ? `${fmtInt(dash.duplicate_rows)} exact duplicate row(s) detected across all columns.`
                  : 'No duplicate rows detected.'}
              </p>
              <div className="form-row">
                <div className="field">
                  <label htmlFor="dupkeep">Keep</label>
                  <select id="dupkeep" className="select" value={dupKeep} onChange={(e) => setDupKeep(e.target.value)}>
                    <option value="first">First occurrence</option>
                    <option value="last">Last occurrence</option>
                  </select>
                </div>
              </div>
              <button className="btn btn-primary" disabled={busy || dash.duplicate_rows === 0}
                onClick={() => apply([{ type: 'drop_duplicates', keep: dupKeep }], 'Duplicate rows removed.')}>
                <CopyX size={15} /> Remove duplicates
              </button>
            </div>

            {/* ---- drop rows ---- */}
            <div className="card">
              <div className="card-title"><h3>3 · Drop rows with missing values</h3></div>
              <p className="small muted mb-8">Delete entire rows instead of filling them.</p>
              <div className="form-row">
                <div className="field">
                  <label htmlFor="drophow">Row is removed when</label>
                  <select id="drophow" className="select" value={dropHow} onChange={(e) => setDropHow(e.target.value)}>
                    <option value="any">Any column is empty</option>
                    <option value="all">All columns are empty</option>
                  </select>
                </div>
              </div>
              <button className="btn btn-danger" disabled={busy || dash.missing_cells === 0}
                onClick={() => apply([{ type: 'drop_missing', how: dropHow }], 'Rows with missing values dropped.')}>
                <Eraser size={15} /> Drop incomplete rows
              </button>
            </div>
          </div>

          {/* ---- type conversion ---- */}
          <div className="card mb-16">
            <div className="card-title"><h3>4 · Incorrect data types</h3><span className="hint">convert a column to the type it should be</span></div>
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr><th>Column</th><th>Detected type</th><th className="num">Unique</th><th>Convert to</th><th /></tr>
                </thead>
                <tbody>
                  {dash.column_details.map((c) => (
                    <tr key={c.name}>
                      <td className="rowhead">{c.name}</td>
                      <td><RoleBadge role={c.role} /></td>
                      <td className="num">{fmtInt(c.unique)}</td>
                      <td>
                        <select className="select" style={{ minWidth: 130 }}
                          value={convPlan[c.name] || (c.role === 'numeric' ? 'number' : 'text')}
                          onChange={(e) => setConvPlan({ ...convPlan, [c.name]: e.target.value })}>
                          {TARGETS.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
                        </select>
                      </td>
                      <td>
                        <button className="btn btn-sm" disabled={busy}
                          onClick={() => apply(
                            [{ type: 'convert_type', columns: [c.name], target: convPlan[c.name] || 'text' }],
                            `Column "${c.name}" converted.`,
                          )}>
                          Convert
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="small faint mt-8">
              Values that cannot be converted are set to missing — check the <Link to="/history/cleaning">cleaning history</Link> for every change that was applied.
            </p>
          </div>

          {/* ---- danger zone ---- */}
          <div className="card">
            <div className="card-title"><h3>Restore original data</h3></div>
            <p className="small muted mb-8">
              Revert this dataset to the version that was first uploaded/created, undoing all cleaning steps.
            </p>
            <button className="btn btn-danger" disabled={busy} onClick={() => setConfirmRestore(true)}>
              <RotateCcw size={15} /> Restore original
            </button>
          </div>

          <ConfirmDialog
            open={confirmRestore}
            title="Restore original data?"
            message="All cleaning steps applied to this dataset will be undone. This cannot be undone itself."
            confirmLabel="Restore"
            danger
            onConfirm={async () => {
              setConfirmRestore(false)
              setBusy(true)
              try {
                await api(`/datasets/${activeId}/restore`, { method: 'POST' })
                toast('Original data restored.', 'success')
                load()
                refreshActive()
                refreshDatasets()
              } catch (e) {
                toast(e.message, 'error')
              } finally {
                setBusy(false)
              }
            }}
            onCancel={() => setConfirmRestore(false)}
          />
        </>
      ) : null}
    </div>
  )
}
