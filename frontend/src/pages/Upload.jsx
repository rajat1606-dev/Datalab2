import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { CheckCircle2, FileSpreadsheet, Upload as UploadIcon } from 'lucide-react'
import { api } from '../api'
import { useApp } from '../context'
import { PageHead, RoleBadge } from '../components/ui'

const OK_EXT = /\.(csv|tsv|txt|xlsx|xlsm)$/i

export default function Upload() {
  const { setActiveId, refreshDatasets, toast } = useApp()
  const inputRef = useRef(null)
  const [file, setFile] = useState(null)
  const [drag, setDrag] = useState(false)
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)

  const pickFile = (f) => {
    if (!f) return
    if (!OK_EXT.test(f.name)) {
      toast('Unsupported file type. Please choose a .csv or .xlsx file.', 'error')
      return
    }
    if (f.size > 15 * 1024 * 1024) {
      toast('File too large (max 15 MB).', 'error')
      return
    }
    setFile(f)
    setResult(null)
    setName(f.name.replace(/\.[^.]+$/, ''))
  }

  const doUpload = async () => {
    if (!file) {
      toast('Choose a CSV or XLSX file first.', 'error')
      return
    }
    setBusy(true)
    try {
      const fd = new FormData()
      fd.append('file', file)
      if (name.trim()) fd.append('name', name.trim())
      const data = await api('/datasets/upload', { method: 'POST', formData: fd })
      setResult(data)
      setActiveId(data.id)
      await refreshDatasets()
      toast(`Uploaded "${data.name}" — ${data.rows} rows, ${data.cols} columns.`, 'success')
    } catch (e) {
      toast(e.message, 'error')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <PageHead title="Upload data" sub="CSV or Excel (XLSX) files up to 15 MB. Column types are detected automatically." />

      <div className="grid-2" style={{ gridTemplateColumns: '1.2fr 1fr', alignItems: 'start' }}>
        <div className="card">
          <div
            className={`dropzone ${drag ? 'drag' : ''}`}
            onClick={() => inputRef.current?.click()}
            onDragOver={(e) => { e.preventDefault(); setDrag(true) }}
            onDragLeave={() => setDrag(false)}
            onDrop={(e) => { e.preventDefault(); setDrag(false); pickFile(e.dataTransfer.files?.[0]) }}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => e.key === 'Enter' && inputRef.current?.click()}
            aria-label="Choose or drop a data file"
          >
            <div className="dz-icon"><UploadIcon size={22} /></div>
            {file ? (
              <>
                <strong style={{ color: 'var(--text)' }}>{file.name}</strong>
                <div className="small mt-8">{(file.size / 1024).toFixed(1)} KB — click to choose a different file</div>
              </>
            ) : (
              <>
                <strong style={{ color: 'var(--text)' }}>Drop a file here, or click to browse</strong>
                <div className="small mt-8">Accepted: .csv, .tsv, .xlsx, .xlsm — first row is used as column names</div>
              </>
            )}
          </div>
          <input
            ref={inputRef}
            type="file"
            accept=".csv,.tsv,.txt,.xlsx,.xlsm"
            hidden
            onChange={(e) => pickFile(e.target.files?.[0])}
          />

          <div className="field mt-16">
            <label htmlFor="ds-name">Dataset name</label>
            <input id="ds-name" className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="My dataset" />
          </div>
          <button className="btn btn-primary" onClick={doUpload} disabled={busy || !file}>
            {busy ? 'Uploading…' : 'Upload dataset'}
          </button>
        </div>

        <div className="card">
          {result ? (
            <>
              <div className="card-title"><h3><CheckCircle2 size={16} color="#34d399" style={{ verticalAlign: '-3px', marginRight: 6 }} />Upload complete</h3></div>
              <div className="kv"><span className="k">Dataset</span><span className="v">{result.name}</span></div>
              <div className="kv"><span className="k">Rows</span><span className="v">{result.rows}</span></div>
              <div className="kv"><span className="k">Columns</span><span className="v">{result.cols}</span></div>
              <div className="mt-16 mb-8 small muted">Detected column types:</div>
              <div className="flex gap-8 wrap">
                {result.columns.map((c) => (
                  <span key={c.name} className="chip">{c.name} <RoleBadge role={c.role} /></span>
                ))}
              </div>
              <div className="flex gap-8 mt-16 wrap">
                <Link className="btn btn-primary" to="/preview">Open preview</Link>
                <Link className="btn" to="/charts">Go to charts</Link>
                <Link className="btn btn-ghost" to="/clean">Clean data</Link>
              </div>
            </>
          ) : (
            <>
              <div className="card-title"><h3>What happens on upload?</h3></div>
              <p className="muted small mb-8">The file is parsed with pandas, stored in the local SQLite database and profiled:</p>
              <div className="kv"><span className="k">1. Parse</span><span className="v">CSV / Excel → table</span></div>
              <div className="kv"><span className="k">2. Profile</span><span className="v">types, missing values, duplicates</span></div>
              <div className="kv"><span className="k">3. Recommend</span><span className="v">charts that fit your columns</span></div>
              <div className="kv"><span className="k">4. Ready</span><span className="v">clean, chart, analyze & export</span></div>
              <p className="small faint mt-16">Tip: keep headers in the first row. Empty cells are treated as missing values.</p>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
