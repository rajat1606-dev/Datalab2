import { useState } from 'react'
import { BrowserRouter, Navigate, Route, Routes, useParams } from 'react-router-dom'
import { AppProvider } from './context'
import Sidebar from './components/Sidebar'
import Topbar from './components/Topbar'
import Dashboard from './pages/Dashboard'
import Settings from './pages/Settings'
import Datasets from './pages/Datasets'
import DataEntry from './pages/DataEntry'
import Preview from './pages/Preview'
import Cleaning from './pages/Cleaning'
import Charts from './pages/Charts'
import Statistics from './pages/Statistics'
import ExportPage from './pages/ExportPage'
import History from './pages/History'
import {
  CleanHub, DatasetsHub, ExportHub, HistoryHub, UploadHub, VisualizeHub,
} from './pages/hubs'
import CFUpload from './pages/cleanflow/CFUpload'
import CFProfiling from './pages/cleanflow/CFProfiling'
import CFAutoClean from './pages/cleanflow/CFAutoClean'
import CFTransform from './pages/cleanflow/CFTransform'
import CFPipeline from './pages/cleanflow/CFPipeline'
import CFReport from './pages/cleanflow/CFReport'
import CFExport from './pages/cleanflow/CFExport'
import CFHistory from './pages/cleanflow/CFHistory'

/** Old CleanFlow wizard URLs → their new home in the simplified navigation. */
const CF_REDIRECTS = {
  upload: '/upload',
  profiling: '/visualize',
  'auto-clean': '/clean',
  transform: '/clean/transform',
  pipeline: '/clean/advanced',
  report: '/clean/report',
  export: '/export',
  history: '/history',
}

function CleanFlowRedirect() {
  const { slug } = useParams()
  return <Navigate to={CF_REDIRECTS[slug] || '/'} replace />
}

export default function App() {
  const [sidebarOpen, setSidebarOpen] = useState(false)

  return (
    <AppProvider>
      <BrowserRouter>
        <div className="layout">
          <Sidebar open={sidebarOpen} onNavigate={() => setSidebarOpen(false)} />
          <div className={`overlay ${sidebarOpen ? 'show' : ''}`} onClick={() => setSidebarOpen(false)} />
          <div className="main">
            <Topbar onToggleSidebar={() => setSidebarOpen((v) => !v)} />
            <main className="content">
              <Routes>
                <Route path="/" element={<Dashboard />} />
                <Route path="/settings" element={<Settings />} />

                {/* Upload Data */}
                <Route path="/upload" element={<UploadHub />}>
                  <Route index element={<CFUpload />} />
                  <Route path="manual" element={<DataEntry />} />
                </Route>

                {/* Clean Data (Pipeline Builder = Advanced tools) */}
                <Route path="/clean" element={<CleanHub />}>
                  <Route index element={<CFAutoClean />} />
                  <Route path="manual" element={<Cleaning />} />
                  <Route path="transform" element={<CFTransform />} />
                  <Route path="report" element={<CFReport />} />
                  <Route path="advanced" element={<CFPipeline />} />
                </Route>

                {/* Visualize Data */}
                <Route path="/visualize" element={<VisualizeHub />}>
                  <Route index element={<CFProfiling />} />
                  <Route path="charts" element={<Charts />} />
                  <Route path="statistics" element={<Statistics />} />
                </Route>

                {/* My Datasets */}
                <Route path="/datasets" element={<DatasetsHub />}>
                  <Route index element={<Datasets />} />
                  <Route path="preview" element={<Preview />} />
                </Route>

                {/* Export Data */}
                <Route path="/export" element={<ExportHub />}>
                  <Route index element={<CFExport />} />
                  <Route path="options" element={<ExportPage />} />
                </Route>

                {/* History */}
                <Route path="/history" element={<HistoryHub />}>
                  <Route index element={<History />} />
                  <Route path="cleaning" element={<CFHistory />} />
                </Route>

                {/* Legacy URLs kept alive with redirects (no broken links) */}
                <Route path="/entry" element={<Navigate to="/upload/manual" replace />} />
                <Route path="/preview" element={<Navigate to="/datasets/preview" replace />} />
                <Route path="/charts" element={<Navigate to="/visualize/charts" replace />} />
                <Route path="/stats" element={<Navigate to="/visualize/statistics" replace />} />
                <Route path="/cleanflow/:slug" element={<CleanFlowRedirect />} />

                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </main>
          </div>
        </div>
      </BrowserRouter>
    </AppProvider>
  )
}
