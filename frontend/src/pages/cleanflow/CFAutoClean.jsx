import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertTriangle, CheckCheck, RotateCcw, Sparkles, Undo2 } from 'lucide-react'
import { api, fmtInt } from '../../api'
import { useApp } from '../../context'
import { ConfirmDialog, NoDataset, PageHead, StatCard } from '../../components/ui'
import { DeltaChip, IssueCard, LoadState, MiniTable, ScoreRing } from '../../components/cleanflow'

export default function CFAutoClean() {
  const { activeId, activeMeta, refreshActive, refreshDatasets, toast } = useApp()
  const [profile, setProfile] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [checked, setChecked] = useState({})      // issue index -> true
  const [strategy, setStrategy] = useState({})    // issue index -> override op params
  const [approveDestructive, setApproveDestructive] = useState(false)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)
  const [confirmRestore, setConfirmRestore] = useState(false)
  const [undoCount, setUndoCount] = useState(0)

  const load = useCallback(() => {
    if (!activeId) { setProfile(null); return }
    setLoading(true)
    setError('')
    api(`/cleanflow/datasets/${activeId}/profile`)
      .then((p) => {
        setProfile(p)
        setChecked({})
        setStrategy({})
        api(`/cleanflow/datasets/${activeId}/undo-count`)
          .then((r) => setUndoCount(r.count)).catch(() => {})
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [activeId])

  useEffect(() => { load() }, [load])

  const fixable = useMemo(
    () => (profile ? profile.issues.filter((i) => i.recommendation) : []),
    [profile])

  const buildOp = (issue, idx) => {
    const rec = issue.recommendation
    const override = strategy[idx]
    if (!override) return { ...rec.params, type: rec.type, approved: !!rec.destructive && approveDestructive }
    return { ...rec.params, ...override, type: rec.type, approved: !!rec.destructive && approveDestructive }
  }

  const selectedDestructive = fixable.some((issue, idx) =>
    checked[idx] && issue.recommendation.destructive)

  const applySelected = async () => {
    const ops = fixable.flatMap((issue, idx) => (checked[idx] ? [buildOp(issue, idx)] : []))
    if (!ops.length) {
      toast('Tick at least one fix first.', 'error')
      return
    }
    if (selectedDestructive && !approveDestructive) {
      toast('Your selection includes destructive fixes — tick the approval box first.', 'error')
      return
    }
    setBusy(true)
    try {
      const res = await api(`/cleanflow/datasets/${activeId}/clean`, { method: 'POST', body: { operations: ops } })
      setResult(res)
      toast(res.summary === 'No changes were needed' ? 'Nothing needed changing.' : 'Cleaning applied.', 'success')
      await refreshActive()
      refreshDatasets()
      api(`/cleanflow/datasets/${activeId}/undo-count`)
        .then((r) => setUndoCount(r.count)).catch(() => {})
      load()
    } catch (e) {
      toast(e.message, 'error')
    } finally {
      setBusy(false)
    }
  }

  const undo = async () => {
    setBusy(true)
    try {
      const res = await api(`/cleanflow/datasets/${activeId}/undo`, { method: 'POST' })
      toast('Last cleaning batch undone.', 'success')
      setResult(null)
      await refreshActive()
      refreshDatasets()
      setUndoCount(Math.max(0, undoCount - 1))
      load()
    } catch (e) {
      toast(e.message, 'error')
    } finally {
      setBusy(false)
    }
  }

  if (!activeId) return <NoDataset text="Pick a dataset in the top bar to run intelligent cleaning on it." />

  const selectedCount = Object.values(checked).filter(Boolean).length

  return (
    <div>
      <PageHead
        title="Auto cleaning"
        sub={activeMeta ? `Review the recommended fixes for "${activeMeta.name}" and approve the ones you want` : ''}
      >
        <button className="btn btn-ghost" onClick={load} disabled={loading}>Reload</button>
        <button className="btn" onClick={undo} disabled={busy || undoCount === 0}>
          <Undo2 size={15} /> Undo last ({undoCount})
        </button>
      </PageHead>

      <LoadState loading={loading} error={error} onRetry={load} empty={!profile}>
        {profile && (
          <>
            {result && (
              <div className="card mb-16">
                <div className="card-title"><h3>Last cleaning result</h3><span className="hint">{result.summary}</span></div>
                <div className="before-after">
                  <ScoreRing value={result.before.quality_score} size={92} />
                  <div className="kv"><span className="k">Rows</span><span className="v">{fmtInt(result.before.rows)}</span></div>
                  <div className="delta-arrow">→</div>
                  <div>
                    <div className="flex aic gap-8">
                      <ScoreRing value={result.after.quality_score} size={92} />
                      <div>
                        <div className="mb-8"><DeltaChip value={result.after.quality_score - result.before.quality_score} suffix=" pts" /></div>
                        <div className="small muted">Rows now: {fmtInt(result.after.rows)}<br />
                          Missing cells: {fmtInt(result.after.missing_cells)}<br />
                          Duplicates: {fmtInt(result.after.duplicate_rows)}</div>
                      </div>
                    </div>
                  </div>
                </div>
                <div className="mt-16">
                  {result.operations.map((op, i) => (
                    <div key={i} className="activity-item">
                      <span className={`badge ${op.destructive ? 'red' : 'cyan'}`}>{op.label}</span>
                      <span style={{ flex: 1 }}>{op.detail}</span>
                      {op.affected > 0 && <span className="badge gray">{fmtInt(op.affected)}</span>}
                    </div>
                  ))}
                </div>
                <div className="flex gap-8 mt-16 wrap">
                  <Link className="btn btn-cyan btn-sm" to="/visualize/charts">Visualize the cleaned data →</Link>
                  <Link className="btn btn-sm" to="/export">Export result</Link>
                </div>
                {result.changes && (
                  <div className="mt-16">
                    <div className="flex aic gap-8 wrap mb-8">
                      <span className="badge violet">{fmtInt(result.changes.cells_changed)} cell(s) changed</span>
                      {result.changes.rows_removed > 0 && <span className="badge red">{fmtInt(result.changes.rows_removed)} row(s) removed</span>}
                      {result.changes.rows_added > 0 && <span className="badge green">{fmtInt(result.changes.rows_added)} row(s) added</span>}
                      {result.changes.columns_added?.length > 0 && <span className="badge cyan">+{result.changes.columns_added.length} column(s)</span>}
                      {result.changes.columns_removed?.length > 0 && <span className="badge amber">-{result.changes.columns_removed.length} column(s)</span>}
                      {result.changes.columns_retyped?.length > 0 && <span className="badge gray">retyped: {result.changes.columns_retyped.join(', ')}</span>}
                    </div>
                    {result.changes.modified_cells?.length > 0 ? (
                      <>
                        <p className="small muted mb-8">Individual changes (inspect each one):</p>
                        <MiniTable columns={['Row', 'Column', 'Before', 'After']}
                          rows={result.changes.modified_cells.map((c) => [c.row, c.column, c.before, c.after])}
                          maxRows={12} />
                      </>
                    ) : (
                      <p className="small faint">{result.changes.note || 'No individual cell values changed.'}</p>
                    )}
                  </div>
                )}
              </div>
            )}

            <div className="card mb-16">
              <div className="card-title">
                <h3>Recommended fixes</h3>
                <span className="hint">{fixable.length} fixable · {profile.issues.length - fixable.length} informational</span>
              </div>
              {profile.issues.length === 0 && (
                <div className="flex aic gap-12">
                  <span className="badge green">No issues detected</span>
                  <span className="small muted">This dataset is already clean. Head to Visualize Data or export the result.</span>
                  <Link className="btn btn-sm" to="/export">Export data</Link>
                </div>
              )}
              {profile.issues.filter((i) => !i.recommendation).map((issue, i) => (
                <IssueCard key={`info-${i}`} issue={issue} />
              ))}
              {fixable.map((issue, idx) => (
                <IssueCard
                  key={`fix-${idx}`}
                  issue={issue}
                  selected={!!checked[idx]}
                  onToggle={(v) => setChecked({ ...checked, [idx]: v })}
                >
                  {issue.recommendation.type === 'fill_missing' && checked[idx] && (
                    <div className="form-row mt-8">
                      <div className="field">
                        <label>Fill strategy</label>
                        <select className="select" value={strategy[idx]?.strategy || issue.recommendation.params.strategy}
                          onChange={(e) => setStrategy({ ...strategy, [idx]: { ...strategy[idx], strategy: e.target.value } })}>
                          <option value="mean">Mean (numeric)</option>
                          <option value="median">Median (numeric)</option>
                          <option value="mode">Most frequent</option>
                          <option value="ffill">Forward fill</option>
                          <option value="bfill">Backward fill</option>
                          <option value="constant">Custom constant…</option>
                        </select>
                      </div>
                      {(strategy[idx]?.strategy || issue.recommendation.params.strategy) === 'constant' && (
                        <div className="field">
                          <label>Custom value</label>
                          <input className="input" value={strategy[idx]?.value ?? ''}
                            onChange={(e) => setStrategy({ ...strategy, [idx]: { ...strategy[idx], value: e.target.value } })} />
                        </div>
                      )}
                    </div>
                  )}
                  {issue.recommendation.type === 'handle_outliers' && checked[idx] && (
                    <div className="form-row mt-8">
                      <div className="field">
                        <label>Action</label>
                        <select className="select" value={strategy[idx]?.action || issue.recommendation.params.action}
                          onChange={(e) => setStrategy({ ...strategy, [idx]: { ...strategy[idx], action: e.target.value } })}>
                          <option value="flag">Only flag in a new column (safe)</option>
                          <option value="nullify">Set outliers to missing (needs approval)</option>
                          <option value="remove">Remove those rows (needs approval)</option>
                        </select>
                      </div>
                    </div>
                  )}
                  {issue.recommendation.type === 'parse_dates'
                    && issue.recommendation.params.dayfirst !== undefined && checked[idx] && (
                    <div className="form-row mt-8">
                      <div className="field">
                        <label>Date convention (for ambiguous values like 12-05-2024)</label>
                        <select className="select"
                          value={String(strategy[idx]?.dayfirst ?? issue.recommendation.params.dayfirst)}
                          onChange={(e) => setStrategy({ ...strategy, [idx]: { ...strategy[idx], dayfirst: e.target.value === 'true' } })}>
                          <option value="true">Day-first (DD-MM-YYYY) — 12-05-2024 = 12 May</option>
                          <option value="false">Month-first (MM-DD-YYYY) — 12-05-2024 = 5 Dec</option>
                        </select>
                      </div>
                    </div>
                  )}
                </IssueCard>
              ))}
            </div>

            {fixable.length > 0 && (
              <div className="card">
                <div className="flex aic gap-12 wrap">
                  <button className="btn btn-primary" onClick={applySelected} disabled={busy || selectedCount === 0}>
                    <CheckCheck size={15} /> Apply {selectedCount || ''} selected fix{selectedCount === 1 ? '' : 'es'}
                  </button>
                  <button className="btn btn-sm" disabled={busy}
                    onClick={() => setChecked(Object.fromEntries(fixable.map((i, idx) => [idx, !i.recommendation.destructive])))}>
                    <Sparkles size={13} /> Select all safe fixes
                  </button>
                </div>
                {selectedDestructive && (
                  <>
                    <div className="divider" />
                    <label className="checkbox-row" style={{ color: 'var(--warn)' }}>
                      <input type="checkbox" checked={approveDestructive}
                        onChange={(e) => setApproveDestructive(e.target.checked)} />
                      <AlertTriangle size={14} color="var(--warn)" />
                      <span>I approve the destructive changes (rows/columns will be removed or overwritten). Everything stays undoable.</span>
                    </label>
                  </>
                )}
                <p className="small faint mt-8">
                  The original upload snapshot is kept untouched — use “Restore original” for a full reset.
                </p>
                <button className="btn btn-danger btn-sm mt-8" disabled={busy} onClick={() => setConfirmRestore(true)}>
                  <RotateCcw size={13} /> Restore original data
                </button>
              </div>
            )}
          </>
        )}
      </LoadState>

      <ConfirmDialog
        open={confirmRestore}
        title="Restore original data?"
        message="All cleaning steps applied to this dataset will be undone, returning it to the first upload. This cannot be undone."
        confirmLabel="Restore"
        danger
        onConfirm={async () => {
          setConfirmRestore(false)
          setBusy(true)
          try {
            await api(`/datasets/${activeId}/restore`, { method: 'POST' })
            toast('Original data restored.', 'success')
            setResult(null)
            await refreshActive()
            load()
          } catch (e) {
            toast(e.message, 'error')
          } finally {
            setBusy(false)
          }
        }}
        onCancel={() => setConfirmRestore(false)}
      />
    </div>
  )
}
