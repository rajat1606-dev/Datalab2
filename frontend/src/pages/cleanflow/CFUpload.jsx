import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { CheckCircle2, FileJson, FileSpreadsheet, Upload as UploadIcon } from 'lucide-react'
import { api } from '../../api'
import { useApp } from '../../context'
import { PageHead, RoleBadge } from '../../components/ui'
import { ScoreRing } from '../../components/cleanflow'

const OK_EXT = /\.(csv|tsv|txt|xlsx|xlsm|xls|json|jsonl)$/i
const MAX_BYTES = 15 * 1024 * 1024

export default function CFUpload() {
  const { setActiveId, refreshDatasets, toast } = useApp()
  const inputRef = useRef(null)
  const [file, setFile] = useState(null)
  const [drag, setDrag] = useState(false)
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')

  const pickFile = (f) => {
    setError('')
    setResult(null)
    if (!f) return
    if (!OK_EXT.test(f.name)) {
      setError('Unsupported file type. Accepted: .csv, .tsv, .txt, .xlsx, .xlsm, .xls, .json')
      return
    }
    if (f.size > MAX_BYTES) {
      setError(`File too large (${(f.size / 1048576).toFixed(1)} MB). The limit is 15 MB.`)
      return
    }
    setFile(f)
    setName(f.name.replace(/\.[^.]+$/, ''))
  }

  const doUpload = async () => {
    if (!file) {
      setError('Choose a file first.')
      return
    }
    setBusy(true)
    setError('')
    try {
      const fd = new FormData()
      fd.append('file', file)
      if (name.trim()) fd.append('name', name.trim())
      const data = await api('/cleanflow/datasets/upload', { method: 'POST', formData: fd })
      setResult(data)
      setActiveId(data.id)
      await refreshDatasets()
      toast(`Uploaded "${data.name}" — ${data.rows} rows, ${data.cols} columns.`, 'success')
    } catch (e) {
      setError(e.message)
      toast(e.message, 'error')
    } finally {
      setBusy(false)
    }
  }

  const ov = result?.profile?.overview

  return (
    <div>
      <PageHead
        title="CleanFlow · Upload dataset"
        sub="CSV, Excel (.xlsx/.xls) or JSON — validated, parsed and profiled automatically."
      />

      <div className="grid-2" style={{ gridTemplateColumns: '1.15fr 1fr', alignItems: 'start' }}>
        <div className="card">
          <div
            className={`dropzone ${drag ? 'drag' : ''}`}
            onClick={() => inputRef.current?.click()}
            onDragOver={(e) => { e.preventDefault(); setDrag(true) }}
            onDragLeave={() => setDrag(false)}
            onDrop={(e) => { e.preventDefault(); setDrag(false); pickFile(e.dataTransfer.files?.[0]) }}
            role="button" tabIndex={0}
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
                <div className="small mt-8">Accepted: .csv, .tsv, .txt, .xlsx, .xlsm, .xls, .json · max 15 MB</div>
              </>
            )}
          </div>
          <input ref={inputRef} type="file" hidden
            accept=".csv,.tsv,.txt,.xlsx,.xlsm,.xls,.json,.jsonl"
            onChange={(e) => pickFile(e.target.files?.[0])} />

          <div className="field mt-16">
            <label htmlFor="cf-name">Dataset name</label>
            <input id="cf-name" className="input" value={name}
              onChange={(e) => setName(e.target.value)} placeholder="My dataset" />
          </div>

          {error && (
            <div className="badge red mb-16" style={{ display: 'flex', maxWidth: '100%', whiteSpace: 'normal', textAlign: 'left' }}>
              {error}
            </div>
          )}

          <button className="btn btn-primary" onClick={doUpload} disabled={busy || !file}>
            {busy ? 'Uploading & profiling…' : 'Upload dataset'}
          </button>
        </div>

        <div className="card">
          {result ? (
            <>
              <div className="card-title">
                <h3><CheckCircle2 size={16} color="#34d399" style={{ verticalAlign: '-3px', marginRight: 6 }} />Upload complete</h3>
              </div>
              <div className="flex gap-16 aic">
                <ScoreRing value={ov?.quality_score ?? 0} size={92} sub={ov?.grade} />
                <div style={{ flex: 1 }}>
                  <div className="kv"><span className="k">Dataset</span><span className="v">{result.name}</span></div>
                  <div className="kv"><span className="k">Rows × Cols</span><span className="v">{result.rows} × {result.cols}</span></div>
                  <div className="kv"><span className="k">Issues detected</span><span className="v">{result.profile.issues_count}</span></div>
                </div>
              </div>
              <div className="mt-16 mb-8 small muted">Detected column types:</div>
              <div className="flex gap-8 wrap">
                {result.columns.map((c) => (
                  <span key={c.name} className="chip">{c.name} <RoleBadge role={c.role} /></span>
                ))}
              </div>
              <div className="flex gap-8 mt-16 wrap">
                <Link className="btn btn-primary" to="/cleanflow/profiling">Open profiling</Link>
                <Link className="btn" to="/cleanflow/auto-clean">Auto clean</Link>
                <Link className="btn btn-ghost" to="/cleanflow/pipeline">Build a pipeline</Link>
              </div>
            </>
          ) : (
            <>
              <div className="card-title"><h3>What CleanFlow does on upload</h3></div>
              <div className="kv"><span className="k"><FileSpreadsheet size={13} style={{ verticalAlign: '-2px' }} /> 1 · Extract</span><span className="v">CSV / Excel / JSON → table</span></div>
              <div className="kv"><span className="k">2 · Validate</span><span className="v">size, format & structure checks</span></div>
              <div className="kv"><span className="k">3 · Load</span><span className="v">stored with an immutable original snapshot</span></div>
              <div className="kv"><span className="k"><FileJson size={13} style={{ verticalAlign: '-2px' }} /> 4 · Profile</span><span className="v">issues, statistics & quality score</span></div>
              <p className="small faint mt-16">
                Your original file is never modified — cleaning produces a separate, undoable
                working copy. JSON files accept an array of objects, an object of columns, or
                JSON Lines.
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
