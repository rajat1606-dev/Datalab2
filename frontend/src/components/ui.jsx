/** Small shared UI pieces used across pages. */
import { AlertTriangle, Inbox } from 'lucide-react'

export function StatCard({ icon: Icon, label, value, sub, tone = '' }) {
  return (
    <div className="stat-card">
      <div className={`stat-icon ${tone}`}><Icon size={20} /></div>
      <div>
        <div className="stat-value">{value}</div>
        <div className="stat-label">{label}</div>
        {sub ? <div className="stat-sub">{sub}</div> : null}
      </div>
    </div>
  )
}

export function EmptyState({ title, text, children, icon: Icon = Inbox }) {
  return (
    <div className="card">
      <div className="empty-state">
        <div className="es-icon"><Icon size={26} /></div>
        <h3>{title}</h3>
        <p className="small">{text}</p>
        {children ? <div className="es-actions">{children}</div> : null}
      </div>
    </div>
  )
}

export function Spinner() {
  return <div className="spinner" role="progressbar" aria-label="Loading" />
}

export function ConfirmDialog({ open, title, message, confirmLabel = 'Confirm', danger, onConfirm, onCancel }) {
  if (!open) return null
  return (
    <div className="modal-overlay" onClick={onCancel} role="dialog" aria-modal="true">
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h3><AlertTriangle size={16} color={danger ? '#f87171' : '#fbbf24'} style={{ verticalAlign: '-2px', marginRight: 6 }} />{title}</h3>
        <p>{message}</p>
        <div className="modal-actions">
          <button className="btn btn-ghost" onClick={onCancel}>Cancel</button>
          <button className={`btn ${danger ? 'btn-danger' : 'btn-primary'}`} onClick={onConfirm}>
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}

const ROLE_BADGE = {
  numeric: 'badge cyan',
  categorical: 'badge violet',
  datetime: 'badge blue',
  text: 'badge gray',
}

export function RoleBadge({ role }) {
  return <span className={ROLE_BADGE[role] || 'badge gray'}>{role}</span>
}

export function PageHead({ title, sub, children }) {
  return (
    <div className="page-head">
      <div>
        <h1>{title}</h1>
        {sub ? <p className="sub">{sub}</p> : null}
      </div>
      {children ? <div className="page-actions">{children}</div> : null}
    </div>
  )
}

export function NoDataset({ text }) {
  return (
    <EmptyState
      title="No dataset selected"
      text={text || 'Pick a dataset in the top bar, upload a file, or create one by hand to get started.'}
    />
  )
}
