import { useState } from 'react'
import { FileDown, FileSpreadsheet, FileText } from 'lucide-react'
import { downloadFile, fmtInt, fmtTime } from '../api'
import { useApp } from '../context'
import { NoDataset, PageHead } from '../components/ui'

export default function ExportPage() {
  const { activeId, activeMeta, toast } = useApp()
  const [format, setFormat] = useState('csv')
  const [filename, setFilename] = useState('')
  const [includeIndex, setIncludeIndex] = useState(false)
  const [busy, setBusy] = useState(false)

  if (!activeId || !activeMeta) return <NoDataset text="Export downloads the processed data of the active dataset." />

  const baseName = (filename.trim() || activeMeta.name || 'dataset')
    .replace(/[^A-Za-z0-9_-]+/g, '_')
    .replace(/^_+|_+$/g, '') || 'dataset'

  const doExport = async () => {
    setBusy(true)
    try {
      const path = `/datasets/${activeId}/export?format=${format}&include_index=${includeIndex}`
      await downloadFile(path, `${baseName}.${format}`)
      toast(`Exported "${activeMeta.name}" as ${format.toUpperCase()}.`, 'success')
    } catch (e) {
      toast(e.message, 'error')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <PageHead title="Export" sub="Download the current (processed) version of the dataset." />

      <div className="grid-2" style={{ gridTemplateColumns: '1.2fr 1fr', alignItems: 'start' }}>
        <div className="card">
          <div className="card-title"><h3>Choose a format</h3></div>
          <div className="flex gap-12 wrap mb-16">
            <button className={`format-option ${format === 'csv' ? 'active' : ''}`} onClick={() => setFormat('csv')}>
              <h4><FileText size={16} color="#22d3ee" /> CSV</h4>
              <p>Universal plain-text format. Opens anywhere, ideal for further processing.</p>
            </button>
            <button className={`format-option ${format === 'xlsx' ? 'active' : ''}`} onClick={() => setFormat('xlsx')}>
              <h4><FileSpreadsheet size={16} color="#34d399" /> Excel (XLSX)</h4>
              <p>Spreadsheet workbook with typed columns — best for sharing with Excel users.</p>
            </button>
          </div>

          <div className="field">
            <label htmlFor="exp-name">File name</label>
            <input id="exp-name" className="input" value={filename}
              onChange={(e) => setFilename(e.target.value)}
              placeholder={baseName} />
            <span className="small faint">File will be saved as <strong>{baseName}.{format}</strong></span>
          </div>

          <label className="checkbox-row mb-16">
            <input type="checkbox" checked={includeIndex} onChange={(e) => setIncludeIndex(e.target.checked)} />
            Include a row-number column
          </label>

          <button className="btn btn-primary" onClick={doExport} disabled={busy}>
            <FileDown size={15} /> {busy ? 'Preparing…' : `Download ${format.toUpperCase()}`}
          </button>
        </div>

        <div className="card">
          <div className="card-title"><h3>What will be exported?</h3></div>
          <div className="kv"><span className="k">Dataset</span><span className="v">{activeMeta.name}</span></div>
          <div className="kv"><span className="k">Rows</span><span className="v">{fmtInt(activeMeta.rows)}</span></div>
          <div className="kv"><span className="k">Columns</span><span className="v">{activeMeta.cols}</span></div>
          <div className="kv"><span className="k">Last updated</span><span className="v">{fmtTime(activeMeta.updated_at)}</span></div>
          <div className="divider" />
          <p className="small muted">
            The export always reflects the <strong>current, cleaned</strong> version of the data.
            Use the Clean Data page first if you still need to fix missing values or duplicates —
            you can always restore the original there.
          </p>
          <p className="small faint mt-8">
            Need an image of a chart? Open Charts and press <strong>Export PNG</strong>.
          </p>
        </div>
      </div>
    </div>
  )
}
