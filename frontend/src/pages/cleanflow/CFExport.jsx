import { useState } from 'react'
import { Download, FileJson, FileSpreadsheet, FileText, PackageOpen } from 'lucide-react'
import { downloadFile, fmtInt, fmtTime } from '../../api'
import { useApp } from '../../context'
import { NoDataset, PageHead } from '../../components/ui'

const FORMATS = [
  { key: 'csv', label: 'Cleaned CSV', desc: 'Universal, preserves column names & values', icon: FileText, ext: 'csv' },
  { key: 'xlsx', label: 'Cleaned Excel', desc: '.xlsx workbook with typed columns', icon: FileSpreadsheet, ext: 'xlsx' },
  { key: 'json', label: 'Cleaned JSON', desc: 'Array of records, ISO dates', icon: FileJson, ext: 'json' },
]

export default function CFExport() {
  const { activeId, activeMeta, toast } = useApp()
  const [busyKey, setBusyKey] = useState('')   // only one download at a time

  if (!activeId) return <NoDataset text="Pick a dataset in the top bar to export it from the Export Center." />

  const download = async (key, path, filename, label) => {
    if (busyKey) return                        // prevents duplicate downloads
    setBusyKey(key)
    try {
      const info = await downloadFile(path, filename)
      toast(`${label} downloaded (${info.size.toLocaleString()} bytes).`, 'success')
    } catch (e) {
      toast(e.message, 'error')
    } finally {
      setBusyKey('')
    }
  }

  const base = (activeMeta?.name || 'dataset').replace(/[^A-Za-z0-9_-]+/g, '_').slice(0, 40)

  return (
    <div>
      <PageHead
        title="CleanFlow · Export center"
        sub={activeMeta ? `Download the cleaned working copy of "${activeMeta.name}" and its quality report` : ''}
      />

      <div className="cf-meta-strip mb-16">
        <span className="badge blue">{activeMeta?.name}</span>
        <span className="badge cyan">{fmtInt(activeMeta?.rows)} rows</span>
        <span className="badge violet">{activeMeta?.cols} columns</span>
        <span className="small faint">last updated {fmtTime(activeMeta?.updated_at)}</span>
      </div>

      <div className="grid-3 mb-16">
        {FORMATS.map(({ key, label, desc, icon: Icon, ext }) => (
          <button key={key} className="format-option" disabled={!!busyKey}
            onClick={() => download(`data-${key}`,
              `/cleanflow/datasets/${activeId}/export?format=${key}`, `${base}_cleaned.${ext}`, label)}>
            <h4><Icon size={16} /> {label}</h4>
            <p>{desc}</p>
            <span className="btn btn-sm btn-primary mt-16" style={{ display: 'inline-flex' }}>
              {busyKey === `data-${key}` ? 'Preparing…' : (<><Download size={13} /> Download .{ext}</>)}
            </span>
          </button>
        ))}
      </div>

      <div className="card">
        <div className="card-title">
          <h3><PackageOpen size={15} style={{ verticalAlign: '-2px', marginRight: 6 }} />Data quality report</h3>
          <span className="hint">the before/after story of this dataset</span>
        </div>
        <div className="grid-2">
          <button className="format-option" disabled={!!busyKey} onClick={() =>
            download('report-json', `/cleanflow/datasets/${activeId}/report/download?format=json`,
              `quality_report_${base}.json`, 'Quality report (JSON)')
          }>
            <h4><FileJson size={16} /> Quality report — JSON</h4>
            <p>Full machine-readable report: scores, deltas, issues, operation history.</p>
            <span className="btn btn-sm mt-16" style={{ display: 'inline-flex' }}>
              {busyKey === 'report-json' ? 'Preparing…' : (<><Download size={13} /> Download .json</>)}
            </span>
          </button>
          <button className="format-option" disabled={!!busyKey} onClick={() =>
            download('report-html', `/cleanflow/datasets/${activeId}/report/download?format=html`,
              `quality_report_${base}.html`, 'Quality report (HTML)')
          }>
            <h4><FileText size={16} /> Quality report — HTML</h4>
            <p>Printable, shareable summary page — ideal for attaching to emails.</p>
            <span className="btn btn-sm mt-16" style={{ display: 'inline-flex' }}>
              {busyKey === 'report-html' ? 'Preparing…' : (<><Download size={13} /> Download .html</>)}
            </span>
          </button>
        </div>
        <p className="small faint mt-16">
          Column names, dates (ISO 8601) and value types are preserved in every format.
          Exports always reflect the current working copy — the original upload stays untouched.
        </p>
      </div>
    </div>
  )
}
