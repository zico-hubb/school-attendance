import { BrowserRouter, Link, Route, Routes } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { getHealth } from './services/api'
import './App.css'

function DashboardHome() {
  const [connection, setConnection] = useState<'checking' | 'connected' | 'unavailable'>('checking')

  useEffect(() => {
    let active = true
    getHealth()
      .then(() => {
        if (active) setConnection('connected')
      })
      .catch(() => {
        if (active) setConnection('unavailable')
      })
    return () => {
      active = false
    }
  }, [])

  return (
    <main className="dashboard-card">
      <p className="eyebrow">School Attendance</p>
      <h1>Administration</h1>
      <p className="intro">
        The administration workspace is ready. School data and management tools will appear here
        as they are implemented.
      </p>
      <section className="connection" aria-live="polite">
        <span className={`connection-indicator connection-indicator--${connection}`} />
        <div>
          <strong>API connection</strong>
          <p>
            {connection === 'checking' && 'Checking the backend...'}
            {connection === 'connected' && 'Backend is reachable.'}
            {connection === 'unavailable' &&
              'Backend is unavailable. Start the Django API to connect this workspace.'}
          </p>
        </div>
      </section>
    </main>
  )
}

function NotFound() {
  return (
    <main className="dashboard-card">
      <h1>Page not found</h1>
      <Link to="/">Return to administration</Link>
    </main>
  )
}

export function App() {
  return (
    <BrowserRouter>
      <div className="app-shell">
        <header className="topbar">
          <Link className="brand" to="/" aria-label="School Attendance home">
            <span className="brand-mark" aria-hidden="true">SA</span>
            <span>School Attendance</span>
          </Link>
          <span className="workspace-label">Administration workspace</span>
        </header>
        <Routes>
          <Route path="/" element={<DashboardHome />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
        <footer>School Attendance Management - Administration</footer>
      </div>
    </BrowserRouter>
  )
}
