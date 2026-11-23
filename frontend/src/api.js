// Thin fetch wrapper around the FastAPI backend.
// In dev, Vite proxies /api to http://127.0.0.1:8000.
// In production, FastAPI serves this app on the same origin.
// For Capacitor/Android builds, set VITE_API_URL (e.g. http://192.168.x.x:3000/api).
const BASE = import.meta.env.VITE_API_URL || '/api'

// Optional per-browser session id (DataLab 2.0): keeps datasets/pipelines
// isolated between browser sessions. Cleared only when the user clears storage.
const SESSION_KEY = 'datalab.sessionId'
let sessionId = localStorage.getItem(SESSION_KEY)
if (!sessionId) {
  sessionId = (crypto.randomUUID ? crypto.randomUUID() : `s-${Date.now()}-${Math.random()}`)
  localStorage.setItem(SESSION_KEY, sessionId)
}

export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.status = status
  }
}

export async function api(path, { method = 'GET', body, formData } = {}) {
  const opts = { method, headers: { 'X-Session-Id': sessionId } }
  if (formData) {
    opts.body = formData
  } else {
    if (body !== undefined) {
      opts.headers['Content-Type'] = 'application/json'
      opts.body = JSON.stringify(body)
    }
  }
  let res
  try {
    res = await fetch(BASE + path, opts)
  } catch {
    throw new ApiError('Cannot reach the DataLab server. Is the backend running?', 0)
  }
  if (!res.ok) {
    let message = `Request failed (${res.status})`
    try {
      const data = await res.json()
      if (typeof data.detail === 'string') message = data.detail
      else if (Array.isArray(data.detail)) message = data.detail.map((d) => d.msg || JSON.stringify(d)).join('; ')
    } catch { /* keep default message */ }
    throw new ApiError(message, res.status)
  }
  if (res.status === 204) return null
  const ct = res.headers.get('content-type') || ''
  return ct.includes('json') ? res.json() : res.blob()
}

/**
 * Download a file endpoint as a Blob and trigger a save.
 *
 * This path NEVER sniffs the content type (that is how JSON downloads used to
 * come back as parsed objects and crash `URL.createObjectURL` with
 * "Overload resolution failed") — it always takes the raw bytes, validates
 * them, and revokes the object URL afterwards.
 */
export async function downloadFile(path, filename) {
  let res
  try {
    res = await fetch(BASE + path, { headers: { 'X-Session-Id': sessionId } })
  } catch {
    throw new ApiError('Cannot reach the DataLab server. Is the backend running?', 0)
  }
  if (!res.ok) {
    let message = `Download failed (${res.status})`
    try {
      const data = await res.json()
      if (typeof data.detail === 'string') message = data.detail
    } catch { /* keep default message */ }
    throw new ApiError(message, res.status)
  }

  const blob = await res.blob()
  // Validate BEFORE creating an object URL — a null/empty/typed response is a
  // server problem and must surface as a clear error, not a browser crash.
  if (!(blob instanceof Blob)) {
    throw new ApiError('The server returned an unexpected download format.', 500)
  }
  if (blob.size === 0) {
    throw new ApiError('The server produced an empty file — nothing was downloaded.', 500)
  }

  // Prefer the filename the backend suggested (Content-Disposition) when the
  // caller did not pin one, so extensions always match the real format.
  let name = filename
  if (!name) {
    const cd = res.headers.get('content-disposition') || ''
    const m = cd.match(/filename\*?=(?:UTF-8'')?"?([^";]+)"?/i)
    name = m ? decodeURIComponent(m[1]) : 'download'
  }

  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = name
  document.body.appendChild(a)
  a.click()
  a.remove()
  // Revoke once the browser has actually started the download (longer delay
  // on Safari); revoking is safe — an already-saved download is not affected.
  setTimeout(() => URL.revokeObjectURL(url), 10000)
  return { size: blob.size, type: blob.type || 'application/octet-stream', filename: name }
}

export function fmtInt(n) {
  return new Intl.NumberFormat().format(n ?? 0)
}

export function fmtTime(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString(undefined, {
    year: 'numeric', month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}
