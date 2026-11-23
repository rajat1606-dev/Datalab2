import { NavLink } from 'react-router-dom'
import {
  BarChart3, Database, Download, FileSpreadsheet, History, LayoutDashboard,
  PieChart, Settings2, Sigma, Table2, Upload, Workflow,
  ScanSearch, Sparkles, SlidersHorizontal, ShieldCheck, PackageOpen,
} from 'lucide-react'

const SECTIONS = [
  {
    label: 'Overview',
    items: [{ to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true }],
  },
  {
    label: 'Data',
    items: [
      { to: '/datasets', label: 'Datasets', icon: Database },
      { to: '/upload', label: 'Upload File', icon: Upload },
      { to: '/entry', label: 'Manual Entry', icon: Table2 },
    ],
  },
  {
    label: 'Analyze',
    items: [
      { to: '/preview', label: 'Preview', icon: FileSpreadsheet },
      { to: '/clean', label: 'Clean Data', icon: Settings2 },
      { to: '/charts', label: 'Charts', icon: PieChart },
      { to: '/stats', label: 'Statistics', icon: Sigma },
    ],
  },
  {
    label: 'CleanFlow · ELT',
    items: [
      { to: '/cleanflow/upload', label: 'Upload Dataset', icon: Upload },
      { to: '/cleanflow/profiling', label: 'Data Profiling', icon: ScanSearch },
      { to: '/cleanflow/auto-clean', label: 'Auto Cleaning', icon: Sparkles },
      { to: '/cleanflow/transform', label: 'Transformation', icon: SlidersHorizontal },
      { to: '/cleanflow/pipeline', label: 'Pipeline Builder', icon: Workflow },
      { to: '/cleanflow/report', label: 'Quality Report', icon: ShieldCheck },
      { to: '/cleanflow/export', label: 'Export Center', icon: PackageOpen },
      { to: '/cleanflow/history', label: 'Cleaning History', icon: History },
    ],
  },
  {
    label: 'Output',
    items: [
      { to: '/export', label: 'Export', icon: Download },
      { to: '/history', label: 'History', icon: History },
    ],
  },
]

export default function Sidebar({ open, onNavigate }) {
  return (
    <aside className={`sidebar ${open ? 'open' : ''}`}>
      <div className="brand">
        <div className="brand-logo"><BarChart3 size={19} /></div>
        <div>
          <div className="brand-name">DataLab</div>
          <div className="brand-sub">Analytics & ELT Platform</div>
        </div>
      </div>
      <nav className="nav-section" aria-label="Main navigation">
        {SECTIONS.map((sec) => (
          <div key={sec.label}>
            <div className="nav-label">{sec.label}</div>
            {sec.items.map(({ to, label, icon: Icon, end }) => (
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
          </div>
        ))}
      </nav>
      <div className="sidebar-foot">DataLab v2.0 · CleanFlow inside</div>
    </aside>
  )
}
