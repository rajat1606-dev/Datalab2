import { useState } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AppProvider } from './context'
import Sidebar from './components/Sidebar'
import Topbar from './components/Topbar'
import Dashboard from './pages/Dashboard'
import Datasets from './pages/Datasets'
import Upload from './pages/Upload'
import DataEntry from './pages/DataEntry'
import Preview from './pages/Preview'
import Cleaning from './pages/Cleaning'
import Charts from './pages/Charts'
import Statistics from './pages/Statistics'
import ExportPage from './pages/ExportPage'
import History from './pages/History'
import CFUpload from './pages/cleanflow/CFUpload'
import CFProfiling from './pages/cleanflow/CFProfiling'
import CFAutoClean from './pages/cleanflow/CFAutoClean'
import CFTransform from './pages/cleanflow/CFTransform'
import CFPipeline from './pages/cleanflow/CFPipeline'
import CFReport from './pages/cleanflow/CFReport'
import CFExport from './pages/cleanflow/CFExport'
import CFHistory from './pages/cleanflow/CFHistory'

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
                <Route path="/datasets" element={<Datasets />} />
                <Route path="/upload" element={<Upload />} />
                <Route path="/entry" element={<DataEntry />} />
                <Route path="/preview" element={<Preview />} />
                <Route path="/clean" element={<Cleaning />} />
                <Route path="/charts" element={<Charts />} />
                <Route path="/stats" element={<Statistics />} />
                <Route path="/export" element={<ExportPage />} />
                <Route path="/history" element={<History />} />

                {/* CleanFlow (DataLab 2.0) */}
                <Route path="/cleanflow/upload" element={<CFUpload />} />
                <Route path="/cleanflow/profiling" element={<CFProfiling />} />
                <Route path="/cleanflow/auto-clean" element={<CFAutoClean />} />
                <Route path="/cleanflow/transform" element={<CFTransform />} />
                <Route path="/cleanflow/pipeline" element={<CFPipeline />} />
                <Route path="/cleanflow/report" element={<CFReport />} />
                <Route path="/cleanflow/export" element={<CFExport />} />
                <Route path="/cleanflow/history" element={<CFHistory />} />

                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </main>
          </div>
        </div>
      </BrowserRouter>
    </AppProvider>
  )
}
