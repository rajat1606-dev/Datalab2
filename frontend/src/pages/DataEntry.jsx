import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Eraser, Save, Sparkles } from 'lucide-react'
import { api } from '../api'
import { useApp } from '../context'
import EditableGrid from '../components/EditableGrid'
import { PageHead } from '../components/ui'

const SAMPLE = {
  columns: [
    { name: 'Date', type: 'date' },
    { name: 'Region', type: 'categorical' },
    { name: 'Product', type: 'categorical' },
    { name: 'Units', type: 'number' },
    { name: 'Unit Price', type: 'number' },
    { name: 'Revenue', type: 'number' },
  ],
  rows: [
    ['2025-01-05', 'North', 'Laptop', 12, 899.99, 10799.88],
    ['2025-01-09', 'South', 'Monitor', 30, 249.5, 7485],
    ['2025-01-14', 'East', 'Keyboard', 85, 39.99, 3399.15],
    ['2025-01-21', 'West', 'Desk', 9, 459, 4131],
    ['2025-02-02', 'North', 'Monitor', 22, 249.5, 5489],
    ['2025-02-11', 'South', 'Laptop', 17, 899.99, 15299.83],
    ['2025-02-18', 'East', 'Desk', 14, 459, 6426],
    ['2025-02-25', 'West', 'Keyboard', 60, 39.99, 2399.4],
    ['2025-03-04', 'North', 'Keyboard', 74, 39.99, 2959.26],
    ['2025-03-12', 'South', 'Desk', 11, 459, 5049],
    ['2025-03-19', 'East', 'Laptop', 8, 899.99, 7199.92],
    ['2025-03-27', 'West', 'Monitor', 26, 249.5, 6487],
  ],
}

const blankGrid = () => ({
  columns: [
    { name: 'Name', type: 'text' },
    { name: 'Category', type: 'categorical' },
    { name: 'Value', type: 'number' },
  ],
  rows: Array.from({ length: 4 }, () => ['', '', '']),
})

function validateGrid(grid) {
  const problems = []
  const names = grid.columns.map((c) => c.name.trim())
  if (names.some((n) => !n)) problems.push('Every column needs a name.')
  const lowered = names.map((n) => n.toLowerCase())
  if (new Set(lowered).size !== lowered.length) problems.push('Column names must be unique.')
  grid.columns.forEach((col) => {
    if (col.type === 'number') {
      grid.rows.forEach((row, ri) => {
        const v = row[grid.columns.indexOf(col)]
        if (v !== '' && v != null && Number.isNaN(Number(String(v).replace(/,/g, '')))) {
          problems.push(`Row ${ri + 1}: "${v}" is not a valid number for column "${col.name}".`)
        }
      })
    }
    if (col.type === 'date') {
      grid.rows.forEach((row, ri) => {
        const v = row[grid.columns.indexOf(col)]
        if (v !== '' && v != null && Number.isNaN(Date.parse(String(v)))) {
          problems.push(`Row ${ri + 1}: "${v}" is not a valid date for column "${col.name}".`)
        }
      })
    }
  })
  return problems
}

export default function DataEntry() {
  const { activeId, activeMeta, setActiveId, refreshDatasets, refreshActive, toast } = useApp()
  const [grid, setGrid] = useState(blankGrid())
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [busy, setBusy] = useState(false)

  const loadSample = () => {
    setGrid(JSON.parse(JSON.stringify(SAMPLE)))
    if (!name) setName('Sales Sample')
    toast('Sample data loaded into the grid.', 'info')
  }

  const clearGrid = () => {
    setGrid(blankGrid())
    toast('Grid cleared.', 'info')
  }

  const loadActive = async () => {
    if (!activeId) {
      toast('No active dataset selected — pick one in the top bar first.', 'error')
      return
    }
    setBusy(true)
    try {
      const data = await api(`/datasets/${activeId}/preview?page=1&page_size=20000`)
      const cols = data.columns.map((c) => ({
        name: c.name,
        type: c.role === 'numeric' ? 'number' : c.role === 'datetime' ? 'date' : c.role === 'categorical' ? 'categorical' : 'text',
      }))
      const rows = data.rows.map((r) => r.map((v) => (v === null ? '' : String(v))))
      setGrid({ columns: cols, rows })
      toast(`Loaded "${data.name}" (${data.total_rows} rows) into the grid.`, 'success')
    } catch (e) {
      toast(e.message, 'error')
    } finally {
      setBusy(false)
    }
  }

  const saveNew = async () => {
    const problems = validateGrid(grid)
    if (problems.length) {
      toast(problems[0], 'error')
      return
    }
    if (!name.trim()) {
      toast('Give the dataset a name before saving.', 'error')
      return
    }
    setBusy(true)
    try {
      const data = await api('/datasets/manual', {
        method: 'POST',
        body: {
          name: name.trim(),
          description,
          columns: grid.columns,
          rows: grid.rows,
        },
      })
      ;(data.warnings || []).forEach((w) => toast(w, 'info'))
      setActiveId(data.id)
      await refreshDatasets()
      toast(`Saved "${data.name}" — ${data.rows} rows, ${data.cols} columns.`, 'success')
    } catch (e) {
      toast(e.message, 'error')
    } finally {
      setBusy(false)
    }
  }

  const saveEdits = async () => {
    if (!activeId) {
      toast('No active dataset selected.', 'error')
      return
    }
    const problems = validateGrid(grid)
    if (problems.length) {
      toast(problems[0], 'error')
      return
    }
    setBusy(true)
    try {
      const data = await api(`/datasets/${activeId}/data`, {
        method: 'PUT',
        body: { columns: grid.columns, rows: grid.rows },
      })
      ;(data.warnings || []).forEach((w) => toast(w, 'info'))
      await Promise.all([refreshDatasets(), refreshActive()])
      toast(`Saved changes to "${data.name}" — now ${data.rows} rows.`, 'success')
    } catch (e) {
      toast(e.message, 'error')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <PageHead
        title="Manual data entry"
        sub="Type data into the grid, rename columns, pick a type per column, then save."
      >
        <button className="btn" onClick={loadSample}><Sparkles size={15} /> Load sample</button>
        <button className="btn btn-ghost" onClick={clearGrid}><Eraser size={15} /> Clear</button>
      </PageHead>

      <div className="card mb-16">
        <div className="form-row">
          <div className="field">
            <label htmlFor="entry-name">Dataset name</label>
            <input id="entry-name" className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Q1 Sales" />
          </div>
          <div className="field">
            <label htmlFor="entry-desc">Description (optional)</label>
            <input id="entry-desc" className="input" value={description} onChange={(e) => setDescription(e.target.value)} placeholder="What is this data about?" />
          </div>
        </div>
        <div className="flex gap-8 wrap">
          <button className="btn btn-primary" onClick={saveNew} disabled={busy}>
            <Save size={15} /> Save as new dataset
          </button>
          <button className="btn" onClick={loadActive} disabled={busy}>
            Load active dataset into grid
          </button>
          <button
            className="btn btn-cyan"
            onClick={saveEdits}
            disabled={busy || !activeId}
            title={activeId ? `Overwrite "${activeMeta?.name}" with the grid contents` : 'Select an active dataset first'}
          >
            Save changes to active dataset
          </button>
        </div>
        {activeId && (
          <p className="small faint mt-8">
            Active dataset: <strong style={{ color: 'var(--text)' }}>{activeMeta?.name}</strong> — "Load" pulls its current
            rows into the grid, "Save changes" overwrites it. <Link to="/datasets">Manage datasets →</Link>
          </p>
        )}
      </div>

      <EditableGrid columns={grid.columns} rows={grid.rows} onChange={setGrid} />
    </div>
  )
}
