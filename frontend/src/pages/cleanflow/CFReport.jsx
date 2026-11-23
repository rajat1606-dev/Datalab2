import { useCallback, useEffect, useState } from 'react'
import { Download, ShieldCheck } from 'lucide-react'
import { api, downloadFile, fmtInt, fmtTime } from '../../api'
import { useApp } from '../../context'
import { NoDataset, PageHead, StatCard } from '../../components/ui'
import { DeltaChip, LoadState, ScoreRing } from '../../components/cleanflow'

export default function CFReport() {
  const { activeId, activeMeta, toast } = useApp()
  const [report, setReport] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [busyFmt, setBusyFmt] = useState('')   // one download at a time

  const load = useCallback(() => {
    if (!activeId) { setReport(null); return }
    setLoading(true)
    setError('')
    api(`/cleanflow/datasets/${activeId}/report`)
      .then(setReport)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [activeId])

  useEffect(() => { load() }, [load])

  if (!activeId) return <NoDataset text="Pick a dataset in the top bar to see its before/after quality report." />

  const ovB = report?.before?.overview
  const ovA = report?.after?.overview
  const dl = report?.deltas

  const download = async (fmt) => {
    if (busyFmt) return                        // prevents duplicate downloads
    setBusyFmt(fmt)
    try {
      const info = await downloadFile(`/cleanflow/datasets/${activeId}/report/download?format=${fmt}`,
        `quality_report_${(activeMeta?.name || 'dataset').replace(/[^A-Za-z0-9_-]+/g, '_')}.${fmt}`)
      toast(`Quality report (${fmt.toUpperCase()}) downloaded (${info.size.toLocaleString()} bytes).`, 'success')
    } catch (e) {
      toast(e.message, 'error')
    } finally {
      setBusyFmt('')
    }
  }

  return (
    <div>
      <PageHead
        title="CleanFlow · Data quality report"
        sub={activeMeta ? `Before vs after for "${activeMeta.name}" — original upload against the current working copy` : ''}
      >
        <button className="btn btn-ghost" onClick={load} disabled={loading}>Refresh</button>
        <button className="btn" disabled={!!busyFmt} onClick={() => download('json')}>
          {busyFmt === 'json' ? 'Preparing…' : (<><Download size={15} /> JSON</>)}
        </button>
        <button className="btn" disabled={!!busyFmt} onClick={() => download('html')}>
          {busyFmt === 'html' ? 'Preparing…' : (<><Download size={15} /> HTML report</>)}
        </button>
      </PageHead>

      <LoadState loading={loading} error={error} onRetry={load} empty={!report}>
        {report && ovB && ovA && (
          <>
            <div className="card mb-16">
              <div className="before-after">
                <ScoreRing value={ovB.quality_score} size={116} label="Before" sub="before" />
                <div>
                  <h3>Before</h3>
                  <p className="small muted mt-8">
                    {fmtInt(ovB.rows)} rows · {fmtInt(ovB.cols)} cols · {fmtInt(ovB.missing_cells)} missing ·{' '}
                    {fmtInt(ovB.duplicate_rows)} duplicates · {ovB.memory_mb} MB
                  </p>
                  <div className="mt-8"><span className="badge gray">{ovB.grade}</span></div>
                </div>
                <div className="delta-arrow">→</div>
                <div>
                  <div className="flex aic gap-12">
                    <ScoreRing value={ovA.quality_score} size={116} label="After" sub="after" />
                    <div>
                      <h3>After</h3>
                      <p className="small muted mt-8">
                        {fmtInt(ovA.rows)} rows · {fmtInt(ovA.cols)} cols · {fmtInt(ovA.missing_cells)} missing ·{' '}
                        {fmtInt(ovA.duplicate_rows)} duplicates · {ovA.memory_mb} MB
                      </p>
                      <div className="mt-8"><span className="badge cyan">{ovA.grade}</span></div>
                    </div>
                  </div>
                </div>
              </div>
              <div className="divider" />
              <div className="flex aic gap-8 wrap">
                <span className="small muted">Overall change:</span>
                <DeltaChip value={dl.quality_score} suffix=" pts" />
                <span className="small faint">the score compares the original upload with the current data</span>
              </div>
            </div>

            <div className="stat-grid mb-16">
              <StatCard icon={ShieldCheck} label="Missing values handled" value={fmtInt(dl.missing_handled)}
                sub="filled or removed" tone="amber" />
              <StatCard icon={ShieldCheck} label="Duplicates removed" value={fmtInt(dl.duplicates_removed)}
                sub="exact duplicate rows" tone={dl.duplicates_removed ? 'red' : 'green'} />
              <StatCard icon={ShieldCheck} label="Rows removed" value={fmtInt(dl.rows_removed)}
                sub="cleaning + outliers" tone="violet" />
              <StatCard icon={ShieldCheck} label="Outliers detected" value={fmtInt(dl.outliers_detected)}
                sub="in the original data (IQR)" tone="cyan" />
            </div>

            <div className="grid-2 mb-16">
              <div className="card">
                <div className="card-title"><h3>Cleaning operation summary</h3><span className="hint">chronological</span></div>
                {report.operations.length === 0 ? (
                  <p className="muted small">No cleaning operations recorded yet — the after numbers match the original upload.</p>
                ) : (
                  report.operations.map((t, i) => (
                    <div key={i} className="step-item">
                      <div className="step-head">
                        <span className="badge blue">{t.action}</span>
                        <span className="step-title small">{t.summary}</span>
                        <span className="activity-time">{fmtTime(t.time)}</span>
                      </div>
                      {t.operations.length > 0 && (
                        <div className="mt-8">
                          {t.operations.map((o, j) => (
                            <div key={j} className="activity-item">
                              <span className={`badge ${o.destructive ? 'red' : 'cyan'}`}>{o.op}</span>
                              <span style={{ flex: 1 }}>{o.detail}</span>
                              {o.affected > 0 && <span className="badge gray">{fmtInt(o.affected)}</span>}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  ))
                )}
              </div>

              <div className="card">
                <div className="card-title"><h3>Score breakdown</h3><span className="hint">after cleaning</span></div>
                {Object.entries(report.after.scores).map(([k, v]) => {
                  const before = report.before.scores[k]
                  return (
                    <div className="score-bar-row mb-8" key={k} style={{ marginBottom: 10 }}>
                      <span className="lbl" style={{ textTransform: 'capitalize' }}>{k}</span>
                      <div className="score-bar-track"><div className="score-bar-fill" style={{ width: `${v}%` }} /></div>
                      <span className="val">
                        {before} → {v} <DeltaChip value={v - before} />
                      </span>
                    </div>
                  )
                })}
                <div className="divider" />
                <p className="small faint">
                  Completeness = missing values · Uniqueness = duplicates · Validity = types,
                  dates & outliers · Consistency = text formatting.
                </p>
              </div>
            </div>

            <div className="card">
              <div className="card-title"><h3>Remaining issues</h3><span className="hint">in the current working copy</span></div>
              {report.after.issues.length === 0 ? (
                <p className="muted small">Nothing left — every detected problem has been handled. 🎉</p>
              ) : report.after.issues.map((issue, i) => (
                <div key={i} className="activity-item">
                  <span className={`badge ${issue.severity === 'high' ? 'red' : issue.severity === 'medium' ? 'amber' : 'gray'}`}>
                    {issue.severity}
                  </span>
                  <span style={{ flex: 1 }}><strong>{issue.title}</strong> — <span className="muted">{issue.detail}</span></span>
                </div>
              ))}
            </div>
          </>
        )}
      </LoadState>
    </div>
  )
}
