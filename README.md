# DataLab 2.0 — Analytics & Intelligent ELT Platform

A responsive data analytics and visualization web application, now upgraded with
**CleanFlow** — an intelligent ELT and automated data-cleaning module. Users can
upload CSV/Excel/JSON files or type data into an editable spreadsheet grid, then
automatically profile, clean, transform, chart, analyze, pipeline and export
that data.

| Layer | Technology |
|---|---|
| Frontend | React 18 + Vite 5, react-router, Plotly.js (interactive charts), custom dark-navy CSS design system, PWA manifest + service worker |
| Backend | Python FastAPI, Uvicorn (modular routers + services) |
| Data processing | pandas + NumPy (profiling, cleaning, ELT pipelines, statistics) |
| Visualization | Plotly (figures generated server-side, rendered/zoomed client-side) |
| Database | SQLite (datasets, history, undo stack, pipelines, pipeline runs, CleanFlow log) |
| Mobile-ready | Responsive layout, touch-friendly controls, PWA installable, Capacitor config included |

---

## Features

1. **Dashboard** — total rows, columns, missing values, duplicate rows, per-column
   missing-value chart, column-type donut and recent activity.
2. **Manual data entry** — spreadsheet-like editable grid (add/remove rows and
   columns, per-column types, inline validation, sample data loader).
3. **Upload CSV / XLSX** — drag & drop or browse, type auto-detection, 15 MB limit.
4. **Dataset preview** — paginated table with column names, detected types and
   missing-value highlighting.
5. **Data cleaning** — fill missing values (mean / median / mode / forward /
   backward / custom), drop incomplete rows, remove duplicates, convert column
   types (number / date / text / category) and restore the original snapshot.
6. **Chart recommendations** — ranked suggestions with one-click apply, based on
   column types (date → line, category+number → bar, 2 numbers → scatter, …).
7. **Manual chart selection** — Bar, Line, Pie, Histogram, Scatter, Box plot,
   Heatmap (correlation matrix or pivot table).
8. **Statistics** — mean, median, mode(s), standard deviation, quartiles, skew,
   value counts and a correlation matrix per dataset.
9. **Interactive charts** — full Plotly interactions (zoom, pan, hover, camera)
   that also work with touch on tablets/phones.
10. **Export** — processed data as CSV or Excel, any chart as PNG.
11. **History** — every upload, edit, cleaning step, chart and export is logged.
12. **Error handling & validation** — server-side Pydantic models + friendly
    toasts in the UI; invalid cells are highlighted before saving.

## Intelligent cleaning & ELT (new in 2.0, reorganized in 2.1)

Since 2.1 the sidebar follows the natural workflow — **Dashboard · Upload Data ·
Clean Data · Visualize Data · My Datasets · Export Data · History · Settings** —
and groups these features into tabs inside those pages instead of exposing every
tool as its own menu entry:

1. **Upload Data → Upload file** — CSV, TSV, TXT, XLSX, XLSM, legacy XLS and
   JSON (array of objects / object of columns / JSON Lines). Size & format
   validation with clear error messages; every upload gets an immutable original
   snapshot and becomes the active dataset for the whole workflow.
2. **Upload Data → Manual entry** — type data into an editable grid, load the
   active dataset for editing, or save a new dataset from scratch.
3. **Clean Data → Auto clean** — tick the recommended fixes you accept;
   destructive ones (removing rows/columns, overwriting values) require explicit
   approval and are always undoable. Shows a before/after result panel per batch
   with a link straight to Visualize Data.
4. **Clean Data → Manual tools** — per-column missing-value strategies,
   duplicate removal, drop-incomplete-rows and type conversion, plus restore.
5. **Clean Data → Transform** — one operation at a time with a dry-run preview:
   text cleaning, date parsing/unification, renaming, dropping, category
   standardization, normalization (0-1), z-score standardization, label
   encoding, one-hot encoding, invalid-value handling.
6. **Clean Data → Advanced tools (Pipeline Builder)** — arrange operations into
   an execution sequence, dry-run it (per-step status, row counts and data
   previews), then run it: the result becomes a **separate dataset** (the source
   is never modified). Save/reload/delete reusable pipeline configurations;
   every run is logged with status and row counts.
7. **Clean Data → Quality report** — before/after score rings, deltas (missing
   handled, duplicates removed, outliers detected, rows affected),
   chronological operation summary and remaining issues. Downloadable as JSON
   or printable HTML.
8. **Visualize Data** — data profiling (quality score, per-column statistics,
   issue detection), interactive Plotly charts (bar, line, pie, histogram,
   scatter, box, heatmap incl. correlation) and full summary statistics.
9. **My Datasets** — the dataset library (set active, preview, edit, delete)
   plus a paginated read-only preview.
10. **Export Data** — cleaned data as CSV / Excel / JSON (column names and date
    types preserved), the quality report, and a custom export with file-name
    and row-number options; charts export as PNG.
11. **History** — the general activity log plus a detailed view of every
    cleaning batch with before→after scores, filterable per dataset.
12. **Settings** — Day/Night theme selection, dataset tools and app info.

**Safety rules:** the original upload is never modified; original and cleaned
datasets stay separate; suspicious values are flagged instead of guessed;
outlier treatment, invalid-date nulling and e-mail nulling always need explicit
approval (flagging is the safe default); up to 10 undo steps are kept per
dataset; every cleaning batch reports the exact modified cells.

**Session isolation:** the frontend sends an `X-Session-Id` header; datasets and
pipelines are only listed for the session that created them (legacy rows created
without a session remain shared, and clients that never send the header see the
classic behaviour).

---

## Project structure

```
datalab/
├── start.sh                  # builds frontend (first run) + serves everything on :3000
├── backend/
│   ├── main.py               # FastAPI app, CORS, /api/health, SPA static serving
│   ├── database.py           # SQLite schema + connection helpers
│   ├── models.py             # Pydantic request models (core DataLab)
│   ├── models_cleanflow.py   # Pydantic request models (CleanFlow)
│   ├── requirements.txt
│   ├── routers/
│   │   ├── datasets.py       # upload, manual entry, CRUD, dashboard, preview, restore
│   │   ├── cleaning.py       # batch cleaning operations (v1)
│   │   ├── charts.py         # recommendations + figure generation
│   │   ├── stats.py          # summary statistics + correlation
│   │   ├── export.py         # CSV / XLSX download (v1)
│   │   ├── history.py        # activity log
│   │   ├── cleanflow_core.py     # upload, profile, clean, undo, ops registry, history
│   │   ├── cleanflow_pipeline.py # ELT pipeline preview/run + saved pipelines + runs
│   │   └── cleanflow_report.py   # quality report + report/CSV/XLSX/JSON downloads
│   ├── services/
│   │   ├── dataframe.py      # parsing, type-role inference, JSON serialization
│   │   ├── store.py          # DataFrame ⇄ SQLite persistence
│   │   ├── session.py        # optional X-Session-Id isolation
│   │   ├── cleaning.py       # v1 cleaning operations (pandas)
│   │   ├── charts.py         # Plotly figure builders + dark theme
│   │   ├── stats.py          # statistics computations
│   │   ├── recommend.py      # chart recommendation heuristics
│   │   └── cleanflow/
│   │       ├── parser.py     # CSV/XLSX/XLS/JSON parsing + validation
│   │       ├── profiler.py   # profiling, issue detection, quality score
│   │       ├── cleaner.py    # 16-operation registry + approval rules + undo
│   │       ├── pipeline.py   # ELT step engine (dry-run + run)
│   │       └── report.py     # before/after report + JSON/HTML builders
│   └── tests/                # pytest: CleanFlow suite + v1 regression suite
└── frontend/
    ├── index.html  ·  vite.config.js  ·  capacitor.config.json
    ├── public/               # manifest.webmanifest, sw.js, icons
    └── src/
        ├── main.jsx  App.jsx  api.js  context.jsx  theme.css  chartTheme.js
        ├── components/       # Sidebar, Topbar, ChartRenderer, EditableGrid, ui, cleanflow
        └── pages/            # Dashboard, Datasets, Upload, DataEntry, Preview,
                              # Cleaning, Charts, Statistics, ExportPage, History
                              # pages/cleanflow/ — CFUpload, CFProfiling, CFAutoClean,
                              # CFTransform, CFPipeline, CFReport, CFExport, CFHistory
```

---

## Quick start (local machine)

### 1. Backend

```bash
cd datalab/backend
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn main:app --reload --port 8000
```

The API is now at `http://localhost:8000` (docs at `/docs`).
A SQLite file `datalab.db` is created automatically on first start.

### 2. Frontend (development, hot reload)

In a second terminal:

```bash
cd datalab/frontend
npm install
npm run dev
```

Open `http://localhost:5173` — Vite proxies `/api` requests to the backend on
port 8000.

### 3. Production mode (single port — recommended)

Build the frontend once and let FastAPI serve both the UI and the API:

```bash
cd datalab/frontend
npm install
npm run build            # outputs frontend/dist/

cd ../
bash start.sh            # serves everything on http://localhost:3000
# or manually:
cd backend && python -m uvicorn main:app --host 0.0.0.0 --port 3000
```

> In this sandbox the app is already wired this way: `datalab/start.sh` builds
> the frontend if needed and runs the API + UI together on **port 3000**.

---

## API overview

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/health` | Service status |
| GET | `/api/datasets` | List datasets |
| POST | `/api/datasets/upload` | Upload CSV/XLSX (multipart) |
| POST | `/api/datasets/manual` | Create dataset from manual grid |
| GET | `/api/datasets/{id}` | Dataset metadata |
| PUT | `/api/datasets/{id}` | Rename / edit description |
| PUT | `/api/datasets/{id}/data` | Replace table data (grid editing) |
| DELETE | `/api/datasets/{id}` | Delete dataset |
| POST | `/api/datasets/{id}/restore` | Restore original snapshot |
| GET | `/api/datasets/{id}/dashboard` | Rows, columns, missing, duplicates |
| GET | `/api/datasets/{id}/columns` | Column names + roles |
| GET | `/api/datasets/{id}/preview` | Paginated data preview |
| POST | `/api/datasets/{id}/clean` | Apply cleaning operations |
| GET | `/api/datasets/{id}/recommendations` | Chart recommendations |
| POST | `/api/datasets/{id}/chart` | Generate Plotly figure |
| GET | `/api/datasets/{id}/stats` | Summary statistics + correlation |
| GET | `/api/datasets/{id}/export` | Download CSV/XLSX |
| GET/DELETE | `/api/history` | Activity log (list / clear) |

### CleanFlow API

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/cleanflow/ops` | Operation registry (drives the UI forms) |
| POST | `/api/cleanflow/datasets/upload` | Upload CSV/XLSX/XLS/JSON (multipart) |
| GET | `/api/cleanflow/datasets/{id}/profile` | Automatic profiling (read-only) |
| POST | `/api/cleanflow/datasets/{id}/clean` | Apply cleaning/transformation ops |
| POST | `/api/cleanflow/datasets/{id}/undo` | Undo the last batch |
| GET | `/api/cleanflow/datasets/{id}/undo-count` | Undo steps available |
| POST | `/api/cleanflow/datasets/{id}/pipeline/preview` | Dry-run a step sequence |
| POST | `/api/cleanflow/datasets/{id}/pipeline/run` | Run pipeline → new dataset |
| GET/POST | `/api/cleanflow/pipelines` | List / save pipeline configurations |
| GET/PUT/DELETE | `/api/cleanflow/pipelines/{id}` | Load / update / delete a pipeline |
| GET | `/api/cleanflow/runs` | Pipeline run history (status per run) |
| GET | `/api/cleanflow/datasets/{id}/report` | Before/after quality report (JSON) |
| GET | `/api/cleanflow/datasets/{id}/report/download` | Report as JSON or HTML file |
| GET | `/api/cleanflow/datasets/{id}/export` | Cleaned data as CSV/XLSX/JSON |
| GET | `/api/cleanflow/history` | Cleaning history (filter by dataset) |

Interactive API docs: open `/docs` on the running backend.

---

## Tests

68 pytest tests cover the CleanFlow spec (incl. a 28-category regression suite
added in 2.0.1) and protect the v1 features:

```bash
cd datalab/backend
python -m pytest tests/ -v
```

Covered: missing-value strategies, key-based & flagged duplicates, type
correction, mixed/invalid/ambiguous dates (invalid values are kept and
flagged — nulled only with approval), invalid e-mails, negatives & implausible
values, outliers (IQR & Z-score, flag-first, approval-gated treatment), valid
values never falsely treated, text/category standardization, encodings, undo,
approval enforcement, pipeline preview/run/failure reporting, saved pipelines,
empty datasets, invalid/oversized uploads, JSON/XLSX uploads, 30,000-row
datasets, CSV/XLSX/JSON export byte-verification (workbooks re-opened with
openpyxl), report downloads (no local paths leaked), session isolation — plus
regression tests for every v1 feature (dashboard, all 7 chart types,
statistics, manual entry, export, pagination).

Browser-tested end-to-end (headless Chromium): upload → profile → auto-clean →
all five downloads produce valid Blobs with correct MIME types and no
`createObjectURL` errors.

---

## Deployment (Render)

The repository is Render-ready in two flavours:

**A. Single service (what `start.sh` does)** — one web service running
`bash start.sh`: builds the frontend if `dist/` is missing, then serves the API
and the built SPA together on port 3000 (set `$PORT` on Render).

- Build command: `npm install --prefix frontend && npm run build --prefix frontend`
- Start command: `cd backend && python -m uvicorn main:app --host 0.0.0.0 --port $PORT`
- Health check path: `/api/health`

**B. Two services** — frontend as a **Static Site**
(`npm install && npm run build`, publish `frontend/dist`, rewrite `/*` →
`/index.html`) and backend as a **Web Service** (uvicorn). Point the frontend at
the API with `VITE_API_URL=https://<backend>.onrender.com/api` at build time and
add the frontend origin to `allow_origins` in `backend/main.py`.

The SQLite file persists on the service disk; attach a Render disk if you need
the data to survive deploys. The service worker is network-first, so users
always get the newest build after a deploy.

---

## Android (Capacitor) — prepared, not required to run

The frontend is built mobile-first (responsive grids, off-canvas sidebar,
44px touch targets, Plotly touch interactions, no browser-only APIs).
`frontend/capacitor.config.json` is already in place. To produce an APK later:

```bash
cd datalab/frontend
npm install @capacitor/core @capacitor/cli @capacitor/android
npm run build
npx cap add android
npx cap sync android
npx cap open android        # build the APK in Android Studio
```

If the backend runs on another machine, point the app at it before building:

```bash
VITE_API_URL=http://<server-ip>:3000/api npm run build
```

---

## Notes

- Column types are inferred on upload (numeric / categorical / datetime / text)
  and can be corrected on the **Clean Data** page.
- Values that cannot be converted are set to missing and reported in the result
  toast and history log.
- Table data is stored as CSV text inside SQLite — ideal for interactive use;
  for very large files (>100k rows) use the paginated preview.
- "Restore original" reverts to the version first uploaded/created.
