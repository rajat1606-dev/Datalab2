/**
 * Hub layouts for the simplified sidebar (DataLab 2.0).
 *
 * Each main navigation item renders a small pill tab bar plus the active
 * feature page below it. Features keep their own PageHead, so the hub only
 * owns the tabs — no duplicated page titles, no duplicated data fetching.
 */
import { Outlet } from 'react-router-dom'
import {
  Database, Download, FileSpreadsheet, History as HistoryIcon, ListChecks,
  PieChart, ScanSearch, Settings2, Sigma, SlidersHorizontal, Sparkles,
  Table2, Upload, Upload as UploadIcon, Wrench,
} from 'lucide-react'
import { TabNav } from '../components/ui'

function Hub({ tabs }) {
  return (
    <div>
      <TabNav tabs={tabs} />
      <Outlet />
    </div>
  )
}

/** Upload Data: file upload (CSV/Excel/JSON) + manual data entry. */
export function UploadHub() {
  return <Hub tabs={[
    { to: '/upload', label: 'Upload file', icon: UploadIcon, end: true },
    { to: '/upload/manual', label: 'Manual entry', icon: Table2 },
  ]} />
}

/** Clean Data: automatic fixes, manual tools, transformation, quality
    report — Pipeline Builder lives here as an advanced feature. */
export function CleanHub() {
  return <Hub tabs={[
    { to: '/clean', label: 'Auto clean', icon: Sparkles, end: true },
    { to: '/clean/manual', label: 'Manual tools', icon: SlidersHorizontal },
    { to: '/clean/transform', label: 'Transform', icon: Settings2 },
    { to: '/clean/report', label: 'Quality report', icon: ScanSearch },
    { to: '/clean/advanced', label: 'Advanced tools', icon: Wrench },
  ]} />
}

/** Visualize Data: profiling, interactive charts, statistics. */
export function VisualizeHub() {
  return <Hub tabs={[
    { to: '/visualize', label: 'Profiling', icon: ScanSearch, end: true },
    { to: '/visualize/charts', label: 'Charts', icon: PieChart },
    { to: '/visualize/statistics', label: 'Statistics', icon: Sigma },
  ]} />
}

/** My Datasets: library management + read-only preview. */
export function DatasetsHub() {
  return <Hub tabs={[
    { to: '/datasets', label: 'Dataset library', icon: Database, end: true },
    { to: '/datasets/preview', label: 'Preview', icon: FileSpreadsheet },
  ]} />
}

/** Export Data: one-click cleaned exports + classic export with options. */
export function ExportHub() {
  return <Hub tabs={[
    { to: '/export', label: 'Export data', icon: Download, end: true },
    { to: '/export/options', label: 'More options', icon: SlidersHorizontal },
  ]} />
}

/** History: the general activity log + detailed cleaning batches. */
export function HistoryHub() {
  return <Hub tabs={[
    { to: '/history', label: 'Activity log', icon: HistoryIcon, end: true },
    { to: '/history/cleaning', label: 'Cleaning batches', icon: ListChecks },
  ]} />
}
