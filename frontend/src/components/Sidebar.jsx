import { NavLink } from 'react-router-dom'
import {
  BarChart3, Database, Download, FileUp, History, LayoutDashboard,
  Settings, Sparkles,
} from 'lucide-react'

/**
 * Simplified main navigation (DataLab 2.1): one flat, workflow-ordered list
 * — Upload → Clean → Visualize → Export — instead of the previous five
 * labelled sections with 20 entries. Sub-navigation (tabs) lives inside the
 * pages themselves, so every feature stays reachable.
 */
const NAV = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/upload', label: 'Upload Data', icon: FileUp },
  { to: '/clean', label: 'Clean Data', icon: Sparkles },
  { to: '/visualize', label: 'Visualize Data', icon: BarChart3 },
  { to: '/datasets', label: 'My Datasets', icon: Database },
  { to: '/export', label: 'Export Data', icon: Download },
  { to: '/history', label: 'History', icon: History },
  { to: '/settings', label: 'Settings', icon: Settings },
]

export default function Sidebar({ open, onNavigate }) {
  return (
    <aside className={`sidebar ${open ? 'open' : ''}`}>
      <div className="brand">
        <div className="brand-logo"><BarChart3 size={19} /></div>
        <div>
          <div className="brand-name">DataLab</div>
          <div className="brand-sub">Analytics &amp; ELT Platform</div>
        </div>
      </div>
      <nav className="nav-section" aria-label="Main navigation">
        {NAV.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
            onClick={onNavigate}
          >
            <Icon size={17} />
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>
      <div className="sidebar-foot">DataLab v2.1 · Upload → Clean → Visualize → Export</div>
    </aside>
  )
}
