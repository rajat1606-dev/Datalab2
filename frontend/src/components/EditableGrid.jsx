import { Plus, Trash2 } from 'lucide-react'
import { useApp } from '../context'

const TYPES = [
  { value: 'text', label: 'Text' },
  { value: 'number', label: 'Number' },
  { value: 'date', label: 'Date' },
  { value: 'categorical', label: 'Category' },
]

function cellError(value, type) {
  if (value === '' || value === null || value === undefined) return false
  if (type === 'number' && Number.isNaN(Number(String(value).replace(/,/g, '')))) return true
  if (type === 'date' && Number.isNaN(Date.parse(String(value)))) return true
  return false
}

/**
 * Spreadsheet-like editable grid used for manual data entry.
 * Fully controlled: the parent owns { columns, rows } and receives updates.
 */
export default function EditableGrid({ columns, rows, onChange, readOnlyName = false }) {
  const { toast } = useApp()

  const setCell = (r, c, value) => {
    const next = rows.map((row, ri) => (ri === r ? row.map((v, ci) => (ci === c ? value : v)) : row))
    onChange({ columns, rows: next })
  }

  const setColumnName = (c, name) => {
    const next = columns.map((col, ci) => (ci === c ? { ...col, name } : col))
    onChange({ columns: next, rows })
  }

  const setColumnType = (c, type) => {
    const next = columns.map((col, ci) => (ci === c ? { ...col, type } : col))
    onChange({ columns: next, rows })
  }

  const addRow = () => onChange({ columns, rows: [...rows, columns.map(() => '')] })
  const addColumn = () => {
    const name = `Column ${columns.length + 1}`
    onChange({ columns: [...columns, { name, type: 'text' }], rows: rows.map((r) => [...r, '']) })
  }
  const deleteRow = (r) => onChange({ columns, rows: rows.filter((_, ri) => ri !== r) })
  const deleteColumn = (c) => {
    if (columns.length <= 1) {
      toast('A dataset needs at least one column.', 'error')
      return
    }
    onChange({
      columns: columns.filter((_, ci) => ci !== c),
      rows: rows.map((r) => r.filter((_, ci) => ci !== c)),
    })
  }

  return (
    <div>
      <div className="edit-grid-wrap">
        <table className="edit-grid">
          <thead>
            <tr>
              <th className="rownum">#</th>
              {columns.map((col, ci) => (
                <th key={ci}>
                  <input
                    value={col.name}
                    onChange={(e) => setColumnName(ci, e.target.value)}
                    placeholder={`Column ${ci + 1}`}
                    aria-label={`Column ${ci + 1} name`}
                  />
                  <select
                    value={col.type}
                    onChange={(e) => setColumnType(ci, e.target.value)}
                    aria-label={`Column ${ci + 1} type`}
                  >
                    {TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
                  </select>
                </th>
              ))}
              <th style={{ minWidth: 44 }} aria-label="Remove column" />
            </tr>
          </thead>
          <tbody>
            {rows.map((row, ri) => (
              <tr key={ri}>
                <td className="rownum">{ri + 1}</td>
                {columns.map((col, ci) => (
                  <td key={ci}>
                    <input
                      value={row[ci] ?? ''}
                      onChange={(e) => setCell(ri, ci, e.target.value)}
                      className={cellError(row[ci], col.type) ? 'invalid' : ''}
                      aria-label={`Row ${ri + 1}, ${col.name}`}
                    />
                  </td>
                ))}
                <td className="cell-tools">
                  <button className="btn btn-danger btn-icon btn-sm" onClick={() => deleteRow(ri)} title="Delete row" aria-label={`Delete row ${ri + 1}`}>
                    <Trash2 size={13} />
                  </button>
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr><td className="rownum">1</td>{columns.map((_, ci) => <td key={ci} />)}<td /></tr>
            )}
          </tbody>
        </table>
      </div>
      <div className="flex gap-8 mt-8 wrap">
        <button className="btn btn-sm" onClick={addRow}><Plus size={14} /> Add row</button>
        <button className="btn btn-sm" onClick={addColumn}><Plus size={14} /> Add column</button>
        <span className="small faint" style={{ alignSelf: 'center' }}>
          {rows.length} row(s) × {columns.length} column(s) · cells with invalid values are highlighted red
        </span>
      </div>
    </div>
  )
}
