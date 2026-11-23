import { useCallback, useEffect, useRef, useState } from 'react'
import Plotly from 'plotly.js-dist-min'
import { Download, ImageDown, Play, Sparkles } from 'lucide-react'
import { api } from '../api'
import { useApp } from '../context'
import ChartRenderer from '../components/ChartRenderer'
import { EmptyState, NoDataset, PageHead, Spinner } from '../components/ui'

const CHART_TYPES = [
  { value: 'bar', label: 'Bar', needs: { y: false } },
  { value: 'line', label: 'Line', needs: { y: true } },
  { value: 'pie', label: 'Pie', needs: { y: false } },
  { value: 'histogram', label: 'Histogram', needs: { y: false } },
  { value: 'scatter', label: 'Scatter', needs: { y: true } },
  { value: 'box', label: 'Box plot', needs: { y: true } },
  { value: 'heatmap', label: 'Heatmap', needs: { y: false } },
]

const AGGS = ['mean', 'sum', 'count', 'min', 'max', 'median']

const DEFAULT_PARAMS = {
  chart_type: 'bar', x: '', y: '', z: '', group: '',
  agg: 'mean', bins: 30, heatmap_mode: 'correlation',
}

/** Which columns are selectable for X / Y per chart type. */
function axisOptions(type, columns, params) {
  const nums = columns.filter((c) => c.role === 'numeric')
  const cats = columns.filter((c) => c.role === 'categorical' || c.role === 'text')
  const dates = columns.filter((c) => c.role === 'datetime')
  switch (type) {
    case 'bar':
      return { x: [...cats, ...dates, ...nums], y: nums, yRequired: false }
    case 'line':
      return { x: [...dates, ...nums, ...cats], y: nums, yRequired: true }
    case 'pie':
      return { x: [...cats, ...dates, ...nums], y: nums, yRequired: false }
    case 'histogram':
      return { x: nums, y: [], yRequired: false }
    case 'scatter':
      return { x: nums, y: nums, yRequired: true, group: cats }
    case 'box':
      return { x: cats, y: nums, yRequired: true }
    case 'heatmap':
      return params.heatmap_mode === 'pivot'
        ? { x: cats, y: cats, z: nums, yRequired: false }
        : { x: [], y: [], yRequired: false }
    default:
      return { x: columns, y: columns, yRequired: false }
  }
}

export default function Charts() {
  const { activeId, activeMeta, toast } = useApp()
  const [columns, setColumns] = useState([])
  const [recs, setRecs] = useState([])
  const [params, setParams] = useState(DEFAULT_PARAMS)
  const [figure, setFigure] = useState(null)
  const [generated, setGenerated] = useState('')
  const [loadingCols, setLoadingCols] = useState(false)
  const [busy, setBusy] = useState(false)
  const plotRef = useRef(null)

  const loadDatasetInfo = useCallback(() => {
    if (!activeId) { setColumns([]); setRecs([]); setFigure(null); return }
    setLoadingCols(true)
    Promise.all([
      api(`/datasets/${activeId}/columns`),
      api(`/datasets/${activeId}/recommendations`),
    ])
      .then(([c, r]) => { setColumns(c.columns || []); setRecs(r.recommendations || []) })
      .catch((e) => toast(e.message, 'error'))
      .finally(() => setLoadingCols(false))
  }, [activeId, toast])

  useEffect(() => { loadDatasetInfo() }, [loadDatasetInfo])

  const setParam = (patch) => setParams((p) => ({ ...p, ...patch }))

  const changeType = (type) => {
    setParams((p) => ({ ...DEFAULT_PARAMS, chart_type: type, heatmap_mode: p.heatmap_mode }))
    setFigure(null)
  }

  const generate = async (overrideParams) => {
    const p = overrideParams || params
    if (!activeId) return
    const opts = axisOptions(p.chart_type, columns, p)
    const problems = []
    if (p.chart_type !== 'heatmap' && !p.x) problems.push('Choose an X column.')
    if (p.chart_type === 'heatmap' && p.heatmap_mode === 'pivot' && (!p.x || !p.y || !p.z)) {
      problems.push('Pivot heatmap needs X, Y and Z (value) columns.')
    }
    if (opts.yRequired && !p.y) problems.push('This chart type needs a numeric Y column.')
    if (problems.length) {
      toast(problems[0], 'error')
      return
    }
    setBusy(true)
    try {
      const body = {
        chart_type: p.chart_type,
        x: p.x || null, y: p.y || null, z: p.z || null, group: p.group || null,
        agg: p.agg || 'mean', bins: Number(p.bins) || 30,
        heatmap_mode: p.heatmap_mode || 'correlation',
      }
      const res = await api(`/datasets/${activeId}/chart`, { method: 'POST', body })
      setFigure(res.figure)
      setGenerated(describeChart(body))
    } catch (e) {
      toast(e.message, 'error')
    } finally {
      setBusy(false)
    }
  }

  const applyRecommendation = (rec) => {
    const next = { ...DEFAULT_PARAMS, ...rec.params, x: rec.params.x || '', y: rec.params.y || '', z: rec.params.z || '', group: rec.params.group || '' }
    setParams(next)
    generate(next)
  }

  const exportPng = async () => {
    const el = plotRef.current
    if (!el || !figure) {
      toast('Generate a chart first.', 'error')
      return
    }
    try {
      const dataUrl = await Plotly.toImage(el, { format: 'png', width: 1440, height: 860, scale: 2 })
      const a = document.createElement('a')
      a.href = dataUrl
      a.download = `datalab_${generated ? generated.replace(/[^a-z0-9]+/gi, '_').toLowerCase().slice(0, 60) : 'chart'}.png`
      document.body.appendChild(a)
      a.click()
      a.remove()
      toast('Chart exported as PNG.', 'success')
    } catch (e) {
      toast(`PNG export failed: ${e.message}`, 'error')
    }
  }

  if (!activeId) return <NoDataset text="Charts are generated from the active dataset. Pick one in the top bar, or upload data first." />

  const opts = axisOptions(params.chart_type, columns, params)
  const showAgg = ['bar', 'line', 'pie'].includes(params.chart_type) ||
    (params.chart_type === 'heatmap' && params.heatmap_mode === 'pivot')

  return (
    <div>
      <PageHead
        title="Charts"
        sub={activeMeta ? `Interactive Plotly charts for "${activeMeta.name}" — zoom, pan, hover and export` : ''}
      >
        <button className="btn" onClick={loadDatasetInfo} disabled={loadingCols}>Reload columns</button>
      </PageHead>

      <div className="grid-2 charts-layout" style={{ gridTemplateColumns: '360px 1fr', alignItems: 'start', display: 'grid' }}>
        {/* -------- left: builder -------- */}
        <div>
          <div className="card mb-16">
            <div className="card-title"><h3>Chart type</h3></div>
            <div className="chart-type-grid">
              {CHART_TYPES.map((t) => (
                <button
                  key={t.value}
                  className={`chart-type-btn ${params.chart_type === t.value ? 'active' : ''}`}
                  onClick={() => changeType(t.value)}
                >
                  {t.label}
                </button>
              ))}
            </div>
          </div>

          <div className="card mb-16">
            <div className="card-title"><h3>Options</h3></div>

            {params.chart_type === 'heatmap' && (
              <div className="field">
                <label htmlFor="hm-mode">Heatmap mode</label>
                <select id="hm-mode" className="select" value={params.heatmap_mode}
                  onChange={(e) => setParam({ heatmap_mode: e.target.value })}>
                  <option value="correlation">Correlation between numeric columns</option>
                  <option value="pivot">Pivot table (X × Y → Z)</option>
                </select>
              </div>
            )}

            {params.chart_type !== 'heatmap' && (
              <div className="field">
                <label htmlFor="ax-x">X axis {opts.x.length === 0 && params.chart_type === 'histogram' ? '(numeric)' : ''}</label>
                <select id="ax-x" className="select" value={params.x} onChange={(e) => setParam({ x: e.target.value })}>
                  <option value="">— choose column —</option>
                  {opts.x.map((c) => <option key={c.name} value={c.name}>{c.name} ({c.role})</option>)}
                </select>
              </div>
            )}

            {params.chart_type === 'heatmap' && params.heatmap_mode === 'pivot' && (
              <>
                <div className="field">
                  <label htmlFor="hm-x">X (columns of the grid)</label>
                  <select id="hm-x" className="select" value={params.x} onChange={(e) => setParam({ x: e.target.value })}>
                    <option value="">— choose column —</option>
                    {opts.x.map((c) => <option key={c.name} value={c.name}>{c.name} ({c.role})</option>)}
                  </select>
                </div>
                <div className="field">
                  <label htmlFor="hm-y">Y (rows of the grid)</label>
                  <select id="hm-y" className="select" value={params.y} onChange={(e) => setParam({ y: e.target.value })}>
                    <option value="">— choose column —</option>
                    {opts.y.map((c) => <option key={c.name} value={c.name}>{c.name} ({c.role})</option>)}
                  </select>
                </div>
                <div className="field">
                  <label htmlFor="hm-z">Z value (numeric)</label>
                  <select id="hm-z" className="select" value={params.z} onChange={(e) => setParam({ z: e.target.value })}>
                    <option value="">— choose column —</option>
                    {opts.z.map((c) => <option key={c.name} value={c.name}>{c.name}</option>)}
                  </select>
                </div>
              </>
            )}

            {opts.y.length > 0 && (
              <div className="field">
                <label htmlFor="ax-y">Y axis {opts.yRequired ? '(required, numeric)' : '(optional, numeric)'}</label>
                <select id="ax-y" className="select" value={params.y} onChange={(e) => setParam({ y: e.target.value })}>
                  <option value="">{opts.yRequired ? '— choose numeric column —' : '— none (count records) —'}</option>
                  {opts.y.map((c) => <option key={c.name} value={c.name}>{c.name}</option>)}
                </select>
              </div>
            )}

            {showAgg && (
              <div className="field">
                <label htmlFor="agg">Aggregation</label>
                <select id="agg" className="select" value={params.agg} onChange={(e) => setParam({ agg: e.target.value })}>
                  {AGGS.map((a) => <option key={a} value={a}>{a}</option>)}
                </select>
              </div>
            )}

            {params.chart_type === 'histogram' && (
              <div className="field">
                <label htmlFor="bins">Bins ({params.bins})</label>
                <input id="bins" type="range" min="5" max="100" value={params.bins}
                  onChange={(e) => setParam({ bins: e.target.value })} style={{ width: '100%', accentColor: 'var(--accent)' }} />
              </div>
            )}

            {opts.group && (
              <div className="field">
                <label htmlFor="group">Color points by (optional)</label>
                <select id="group" className="select" value={params.group} onChange={(e) => setParam({ group: e.target.value })}>
                  <option value="">— none —</option>
                  {opts.group.map((c) => <option key={c.name} value={c.name}>{c.name}</option>)}
                </select>
              </div>
            )}

            <button className="btn btn-primary" style={{ width: '100%' }} onClick={() => generate()} disabled={busy}>
              <Play size={15} /> {busy ? 'Generating…' : 'Generate chart'}
            </button>
          </div>

          <div className="card">
            <div className="card-title"><h3><Sparkles size={15} color="var(--accent-2)" style={{ verticalAlign: '-2px', marginRight: 5 }} />Recommended</h3></div>
            {loadingCols ? <Spinner /> : recs.length === 0 ? (
              <p className="small muted">No recommendations yet — add more columns with data.</p>
            ) : recs.map((rec, i) => (
              <button key={i} className="rec-card" onClick={() => applyRecommendation(rec)}>
                <div className="rec-top">
                  <span className="badge cyan">{rec.chart_type}</span>
                  <span className="rec-title">{rec.title}</span>
                </div>
                <div className="rec-reason">{rec.reason}</div>
              </button>
            ))}
          </div>
        </div>

        {/* -------- right: chart -------- */}
        <div>
          <div className="chart-card">
            {busy ? <Spinner /> : (
              <ChartRenderer figure={figure} plotRef={plotRef}
                emptyText="Configure the chart on the left (or click a recommendation) and press Generate." />
            )}
          </div>
          <div className="flex gap-8 aic mt-8 wrap">
            <button className="btn" onClick={exportPng} disabled={!figure}>
              <ImageDown size={15} /> Export PNG
            </button>
            <span className="small muted">{generated}</span>
          </div>
          <p className="small faint mt-8">
            Charts are fully interactive: zoom with the mouse/touch, pan, hover for values, and use the
            camera icon in the toolbar or the Export PNG button to save an image.
          </p>
        </div>
      </div>
    </div>
  )
}

function describeChart(p) {
  const bits = [p.chart_type]
  if (p.chart_type === 'heatmap') bits.push(p.heatmap_mode === 'pivot' ? `pivot: ${p.y} × ${p.x} → ${p.z}` : 'correlation matrix')
  else bits.push(p.x || '')
  if (p.y) bits.push(p.chart_type === 'heatmap' ? '' : `vs ${p.y}`)
  return bits.filter(Boolean).join(' · ')
}
