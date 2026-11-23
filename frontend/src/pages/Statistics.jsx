import { useEffect, useState } from 'react'
import { Sigma } from 'lucide-react'
import { api, fmtInt } from '../api'
import { useApp } from '../context'
import { themedLayout } from '../chartTheme'
import ChartRenderer from '../components/ChartRenderer'
import { EmptyState, NoDataset, PageHead, RoleBadge, Spinner } from '../components/ui'

function fmtNum(v) {
  if (v === null || v === undefined) return '—'
  if (typeof v !== 'number') return String(v)
  if (Math.abs(v) >= 100000 || (Math.abs(v) < 0.001 && v !== 0)) return v.toExponential(2)
  return String(Math.round(v * 10000) / 10000)
}

export default function Statistics() {
  const { activeId, activeMeta } = useApp()
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!activeId) { setStats(null); return undefined }
    let alive = true
    setLoading(true)
    setError('')
    api(`/datasets/${activeId}/stats`)
      .then((s) => alive && setStats(s))
      .catch((e) => alive && setError(e.message))
      .finally(() => alive && setLoading(false))
    return () => { alive = false }
  }, [activeId])

  if (!activeId) return <NoDataset text="Statistics are computed for the active dataset. Pick one in the top bar." />

  const corr = stats?.correlation
  const corrFigure = corr && {
    data: [{
      type: 'heatmap',
      z: corr.matrix,
      x: corr.columns,
      y: corr.columns,
      zmin: -1,
      zmax: 1,
      colorscale: 'RdBu',
      reversescale: true,
      text: corr.matrix.map((row) => row.map((v) => (v === null ? '' : v.toFixed(2)))),
      texttemplate: '%{text}',
      hovertemplate: '%{y} × %{x}: %{z}<extra></extra>',
    }],
    layout: themedLayout('Correlation matrix (numeric columns)', {
      height: 420,
      margins: { l: 90, r: 30, t: 56, b: 90 },
    }),
  }

  return (
    <div>
      <PageHead
        title="Statistics"
        sub={activeMeta ? `Mean, median, mode, standard deviation, correlation and more for "${activeMeta.name}"` : ''}
      />

      {loading && !stats ? <Spinner /> : error ? (
        <EmptyState title="Could not compute statistics" text={error} />
      ) : stats ? (
        <>
          <div className="card mb-16">
            <div className="card-title">
              <h3>Summary statistics</h3>
              <span className="hint">hover a column for the full numbers</span>
            </div>
            <div className="table-wrap" style={{ maxHeight: '60vh' }}>
              <table className="table">
                <thead>
                  <tr>
                    <th>Column</th><th>Type</th><th className="num">Count</th><th className="num">Missing</th>
                    <th className="num">Unique</th><th className="num">Mean</th><th className="num">Median</th>
                    <th>Mode(s)</th><th className="num">Std dev</th><th className="num">Min</th>
                    <th className="num">Max</th><th className="num">Skew</th><th>Most common</th>
                  </tr>
                </thead>
                <tbody>
                  {stats.summary.map((s) => (
                    <tr key={s.column}>
                      <td className="rowhead">{s.column}</td>
                      <td><RoleBadge role={s.role} /></td>
                      <td className="num">{fmtInt(s.count)}</td>
                      <td className="num">{s.missing ? <span className="na">{fmtInt(s.missing)}</span> : 0}</td>
                      <td className="num">{fmtInt(s.unique)}</td>
                      <td className="num">{s.mean !== undefined ? fmtNum(s.mean) : '—'}</td>
                      <td className="num">{s.median !== undefined ? fmtNum(s.median) : '—'}</td>
                      <td className="small">{s.modes?.length ? s.modes.join(', ') : '—'}</td>
                      <td className="num">{s.std !== undefined ? fmtNum(s.std) : '—'}</td>
                      <td className="num">{s.min !== undefined ? fmtNum(s.min) : '—'}</td>
                      <td className="num">{s.max !== undefined ? fmtNum(s.max) : '—'}</td>
                      <td className="num">{s.skew !== undefined ? fmtNum(s.skew) : '—'}</td>
                      <td className="small">
                        {s.top !== undefined ? `${s.top} (${fmtInt(s.freq)}×)` : s.modes?.length ? s.modes[0] : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="small faint mt-8">
              Mode lists all values tied for most frequent (up to 3). Std dev is the sample standard deviation.
              Skew &gt; 0 means a long right tail.
            </p>
          </div>

          {corr ? (
            <div className="chart-card">
              <ChartRenderer figure={corrFigure} />
            </div>
          ) : (
            <EmptyState
              icon={Sigma}
              title="No correlation matrix"
              text="Correlation needs at least two numeric columns. Use the Clean Data page to convert columns to numbers if needed."
            />
          )}
        </>
      ) : null}
    </div>
  )
}
