/** Shared CleanFlow UI pieces (DataLab 2.0). */
import { AlertTriangle, Check, Loader2 } from 'lucide-react'

/** SVG donut showing the 0-100 data-quality score. */
export function ScoreRing({ value = 0, size = 96, label = 'Quality', sub }) {
  const v = Math.max(0, Math.min(100, Math.round(value)))
  const stroke = 8
  const r = (size - stroke) / 2
  const c = 2 * Math.PI * r
  const color = v >= 90 ? '#34d399' : v >= 75 ? '#22d3ee' : v >= 55 ? '#fbbf24' : '#f87171'
  return (
    <div className="score-ring" style={{ width: size, height: size }}>
      <svg width={size} height={size} role="img" aria-label={`${label}: ${v} out of 100`}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#1c2a4a" strokeWidth={stroke} />
        <circle
          cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={stroke}
          strokeLinecap="round" strokeDasharray={c}
          strokeDashoffset={c * (1 - v / 100)}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
          style={{ transition: 'stroke-dashoffset 0.6s ease' }}
        />
        <text x="50%" y="47%" textAnchor="middle" dominantBaseline="middle"
          fill="var(--text)" fontWeight="700" fontSize={size * 0.24}>{v}</text>
        <text x="50%" y="66%" textAnchor="middle" dominantBaseline="middle"
          fill="var(--faint)" fontSize={size * 0.115}>{sub || '/100'}</text>
      </svg>
    </div>
  )
}

const SEV = {
  high: { cls: 'red', label: 'High' },
  medium: { cls: 'amber', label: 'Medium' },
  low: { cls: 'gray', label: 'Low' },
}

export function SeverityBadge({ severity }) {
  const s = SEV[severity] || SEV.low
  return <span className={`badge ${s.cls}`}>{s.label}</span>
}

/** One detected issue with its recommendation. */
export function IssueCard({ issue, selected, onToggle, children }) {
  const rec = issue.recommendation
  return (
    <div className={`issue-card ${selected ? 'selected' : ''}`}>
      <label className="issue-head">
        <input
          type="checkbox"
          checked={!!selected}
          disabled={!rec && !children}
          onChange={(e) => onToggle?.(e.target.checked)}
        />
        <div className="issue-title">
          <strong>{issue.title}</strong>
          <SeverityBadge severity={issue.severity} />
          {issue.count > 0 && <span className="badge gray">{issue.count.toLocaleString()} affected</span>}
        </div>
      </label>
      <p className="small muted">{issue.detail}</p>
      {rec && (
        <div className="issue-rec">
          <span className="badge cyan">{rec.label}</span>
          {rec.destructive && <span className="badge red">needs approval</span>}
          {issue.alternative && (
            <span className="badge gray">alt: {issue.alternative.label}</span>
          )}
        </div>
      )}
      {children}
    </div>
  )
}

/** Tiny read-only data table used for previews. */
export function MiniTable({ columns, rows, maxRows = 5 }) {
  if (!columns?.length) return <p className="small muted">No columns to display.</p>
  const shown = (rows || []).slice(0, maxRows)
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>{columns.map((c) => <th key={c}>{c}</th>)}</tr>
        </thead>
        <tbody>
          {shown.length === 0 && (
            <tr><td colSpan={columns.length} className="muted">No rows.</td></tr>
          )}
          {shown.map((r, i) => (
            <tr key={i}>
              {r.map((v, j) => (
                <td key={j} className={v === null ? 'na' : ''}>{v === null ? 'null' : String(v)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** +/- delta chip (green when positive is good). */
export function DeltaChip({ value, positiveIsGood = true, suffix = '' }) {
  if (value === null || value === undefined || value === 0) {
    return <span className="badge gray">no change</span>
  }
  const good = positiveIsGood ? value > 0 : value < 0
  const sign = value > 0 ? '+' : ''
  return <span className={`badge ${good ? 'green' : 'red'}`}>{sign}{value}{suffix}</span>
}

/** Renders the parameter form for one CleanFlow operation (registry-driven). */
export function OpForm({ opMeta, value, onChange, columns }) {
  const set = (name, v) => onChange({ ...value, [name]: v })
  const multi = (name, col) => {
    const arr = value[name] || []
    return arr.includes(col)
      ? arr.filter((c) => c !== col)
      : [...arr, col]
  }
  return (
    <div className="op-form">
      {(opMeta.fields || []).map((f) => {
        if (f.type === 'columns') {
          return (
            <div key={f.name} className="field">
              <label>{f.label}</label>
              <div className="col-picker">
                {columns.map((c) => (
                  <button
                    type="button" key={c.name || c}
                    className={`chip pick ${(value[f.name] || []).includes(c.name || c) ? 'on' : ''}`}
                    onClick={() => set(f.name, multi(f.name, c.name || c))}
                  >
                    {(value[f.name] || []).includes(c.name || c) ? <Check size={11} /> : null}
                    {c.name || c}
                  </button>
                ))}
              </div>
            </div>
          )
        }
        if (f.type === 'column') {
          return (
            <div key={f.name} className="field">
              <label>{f.label}</label>
              <select className="select" value={value[f.name] || ''}
                onChange={(e) => set(f.name, e.target.value)}>
                <option value="">— choose —</option>
                {columns.map((c) => <option key={c.name || c} value={c.name || c}>{c.name || c}</option>)}
              </select>
            </div>
          )
        }
        if (f.type === 'select') {
          return (
            <div key={f.name} className="field">
              <label>{f.label}</label>
              <select className="select" value={value[f.name] ?? f.default ?? ''}
                onChange={(e) => set(f.name, e.target.value)}>
                {(f.options || []).map((o) => <option key={o} value={o}>{o}</option>)}
              </select>
            </div>
          )
        }
        if (f.type === 'bool') {
          return (
            <label key={f.name} className="checkbox-row">
              <input type="checkbox"
                checked={value[f.name] !== undefined ? !!value[f.name] : !!f.default}
                onChange={(e) => set(f.name, e.target.checked)} />
              <span>{f.label}</span>
            </label>
          )
        }
        if (f.type === 'number') {
          return (
            <div key={f.name} className="field">
              <label>{f.label}</label>
              <input className="input" type="number" step="any" placeholder={f.default ?? ''}
                value={value[f.name] ?? ''}
                onChange={(e) => set(f.name, e.target.value === '' ? null : Number(e.target.value))} />
            </div>
          )
        }
        return (
          <div key={f.name} className="field">
            <label>{f.label}</label>
            <input className="input" value={value[f.name] ?? ''}
              onChange={(e) => set(f.name, e.target.value)} />
          </div>
        )
      })}
    </div>
  )
}

/** Loading / error / empty wrapper with consistent states. */
export function LoadState({ loading, error, empty, onRetry, children, emptyText }) {
  if (loading) {
    return (
      <div className="card"><div className="center-load">
        <Loader2 size={22} className="spin" />
        <span className="muted small">Working…</span>
      </div></div>
    )
  }
  if (error) {
    return (
      <div className="card">
        <div className="error-box">
          <AlertTriangle size={20} color="var(--danger)" />
          <div>
            <strong>Something went wrong</strong>
            <p className="small muted">{error}</p>
          </div>
          {onRetry && <button className="btn btn-sm" onClick={onRetry}>Retry</button>}
        </div>
      </div>
    )
  }
  if (empty) {
    return (
      <div className="card"><p className="muted small center-load">{emptyText || 'Nothing here yet.'}</p></div>
    )
  }
  return children
}
