/** Small shared UI pieces used across pages. */
import { Link, NavLink } from 'react-router-dom'
import { AlertTriangle, Inbox, Upload } from 'lucide-react'

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
        <h3><AlertTriangle size={16} color={danger ? 'var(--danger)' : 'var(--warn)'} style={{ verticalAlign: '-2px', marginRight: 6 }} />{title}</h3>
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

/** Pill tab bar for pages that group several features (Upload Data, Clean
    Data, …). `end` marks the tab that must match the URL exactly (index tab). */
export function TabNav({ tabs }) {
  return (
    <div className="tab-nav" role="tablist" aria-label="Page sections">
      {tabs.map(({ to, label, icon: Icon, end }) => (
        <NavLink
          key={to}
          to={to}
          end={end}
          className={({ isActive }) => `tab-item ${isActive ? 'active' : ''}`}
        >
          {Icon ? <Icon size={15} /> : null}
          <span>{label}</span>
        </NavLink>
      ))}
    </div>
  )
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
      text={text || 'Upload a dataset to get started — the whole workflow guides you from there.'}
    >
      <Link className="btn btn-primary" to="/upload"><Upload size={15} /> Upload a dataset</Link>
      {/**
       * "My datasets" is only useful when there is something to pick, but the
       * button is cheap and always correct — the library page shows its own
       * empty state with upload guidance.
       */}
      <Link className="btn" to="/datasets">My datasets</Link>
    </EmptyState>
  )
}
