import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ScanSearch } from 'lucide-react'
import { api, fmtInt } from '../../api'
import { useApp } from '../../context'
import { NoDataset, PageHead, RoleBadge, StatCard } from '../../components/ui'
import { IssueCard, LoadState, ScoreRing, SeverityBadge } from '../../components/cleanflow'

export default function CFProfiling() {
  const { activeId, activeMeta } = useApp()
  const [profile, setProfile] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const load = useCallback(() => {
    if (!activeId) { setProfile(null); return }
    setLoading(true)
    setError('')
    api(`/cleanflow/datasets/${activeId}/profile`)
      .then(setProfile)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [activeId])

  useEffect(() => { load() }, [load])

  if (!activeId) return <NoDataset text="Pick a dataset in the top bar (or upload one under CleanFlow → Upload Dataset) to profile it." />

  const ov = profile?.overview
  const scores = profile?.scores

  return (
    <div>
      <PageHead
        title="CleanFlow · Data profiling"
        sub={activeMeta ? `Read-only inspection of "${activeMeta.name}" — nothing is modified here` : ''}
      >
        <button className="btn btn-ghost" onClick={load} disabled={loading}>Re-profile</button>
      </PageHead>

      <LoadState loading={loading} error={error} onRetry={load} empty={!profile}>
        {profile && ov && (
          <>
            <div className="stat-grid mb-16">
              <StatCard icon={ScanSearch} label="Rows" value={fmtInt(ov.rows)} sub={`${fmtInt(ov.cols)} columns`} />
              <StatCard icon={ScanSearch} label="Missing cells" value={fmtInt(ov.missing_cells)} tone={ov.missing_cells ? 'amber' : 'green'} />
              <StatCard icon={ScanSearch} label="Duplicate rows" value={fmtInt(ov.duplicate_rows)} tone={ov.duplicate_rows ? 'red' : 'green'} />
              <StatCard icon={ScanSearch} label="Memory usage" value={`${ov.memory_mb} MB`} tone="cyan" />
            </div>

            <div className="card mb-16">
              <div className="before-after">
                <ScoreRing value={ov.quality_score} size={116} sub={ov.grade} />
                <div>
                  <h3 style={{ marginBottom: 10 }}>
                    Data-quality score
                    <span className="badge cyan" style={{ marginLeft: 10 }}>{ov.grade}</span>
                  </h3>
                  <div className="score-bars">
                    {Object.entries(scores).map(([k, v]) => (
                      <div className="score-bar-row" key={k}>
                        <span className="lbl" style={{ textTransform: 'capitalize' }}>{k}</span>
                        <div className="score-bar-track"><div className="score-bar-fill" style={{ width: `${v}%` }} /></div>
                        <span className="val">{v}</span>
                      </div>
                    ))}
                  </div>
                </div>
                <div className="delta-arrow">→</div>
                <div>
                  <div className="small muted mb-8">Detected issues by severity</div>
                  <div className="flex gap-8 wrap">
                    {['high', 'medium', 'low'].map((sev) => {
                      const n = profile.issues.filter((i) => i.severity === sev).length
                      return n ? <span key={sev} className={`badge ${sev === 'high' ? 'red' : sev === 'medium' ? 'amber' : 'gray'}`}>{n} {sev}</span> : null
                    })}
                    {profile.issues.length === 0 && <span className="badge green">No issues 🎉</span>}
                  </div>
                  <Link to="/cleanflow/auto-clean" className="btn btn-primary btn-sm mt-16" style={{ display: 'inline-flex' }}>
                    Fix them in Auto Cleaning →
                  </Link>
                </div>
              </div>
            </div>

            <div className="card mb-16">
              <div className="card-title"><h3>Detected problems & recommended fixes</h3><span className="hint">recommendations are one click away</span></div>
              {profile.issues.length === 0 ? (
                <p className="muted small">No quality problems detected — this dataset looks clean.</p>
              ) : profile.issues.map((issue, i) => (
                <IssueCard key={i} issue={issue} />
              ))}
            </div>

            <div className="card">
              <div className="card-title"><h3>Column profile</h3><span className="hint">statistics per column</span></div>
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Column</th><th>Type</th><th>dtype</th>
                      <th className="num">Missing</th><th className="num">Unique</th>
                      <th className="num">Outliers (IQR)</th><th>Highlights</th><th>Example values</th>
                    </tr>
                  </thead>
                  <tbody>
                    {profile.columns.map((c) => (
                      <tr key={c.name}>
                        <td className="rowhead">{c.name}</td>
                        <td><RoleBadge role={c.role} /></td>
                        <td className="small muted">{c.dtype}</td>
                        <td className="num">{c.missing > 0 ? `${c.missing} (${c.missing_pct}%)` : '0'}</td>
                        <td className="num">{fmtInt(c.unique)}</td>
                        <td className="num">{c.outliers ? c.outliers.iqr : '—'}</td>
                        <td>
                          <div className="flex gap-6 wrap">
                            {c.constant && <span className="badge amber">constant</span>}
                            {c.unique_pct >= 98 && <span className="badge violet">ID-like</span>}
                            {c.invalid_dates > 0 && <span className="badge red">{c.invalid_dates} bad dates</span>}
                            {c.ambiguous_dates > 0 && <span className="badge violet">{c.ambiguous_dates} ambiguous dates</span>}
                            {c.invalid_emails > 0 && <span className="badge amber">{c.invalid_emails} bad e-mails</span>}
                            {c.invalid_values > 0 && <span className="badge red">{c.invalid_values} invalid values</span>}
                            {c.negative_values?.length > 0 && <span className="badge amber">negatives</span>}
                            {c.implausible_values?.length > 0 && <span className="badge red">implausible</span>}
                          </div>
                        </td>
                        <td className="small muted">{c.examples.map((v) => (v === null ? 'null' : String(v))).slice(0, 3).join(', ')}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {profile.issues.length > 0 && (
                <div className="mt-16 small faint">
                  Severity legend: <SeverityBadge severity="high" /> likely to break analysis ·
                  {' '}<SeverityBadge severity="medium" /> worth fixing · <SeverityBadge severity="low" /> cosmetic
                </div>
              )}
            </div>
          </>
        )}
      </LoadState>
    </div>
  )
}
