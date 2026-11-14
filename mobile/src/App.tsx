import { getPlatformCapabilities } from './platform/capabilities'

export function App() {
  const capabilities = getPlatformCapabilities()

  return (
    <main className="mobile-shell">
      <section className="welcome-card">
        <span className="brand-mark" aria-hidden="true">SA</span>
        <p className="eyebrow">Staff application</p>
        <h1>School Attendance</h1>
        <p className="intro">
          The shared staff app is ready for development. Sign-in and attendance workflows are not
          available yet.
        </p>
        <section className="platform-status" aria-label="Native capability status">
          <h2>Device capabilities</h2>
          <p data-testid="platform-name">Platform: {capabilities.platform}</p>
          <p data-testid="capability-status">
            Native verification: {capabilities.nativeVerification.available ? 'available' : 'not available'}
          </p>
          {!capabilities.nativeVerification.available && (
            <p className="note">{capabilities.nativeVerification.reason}</p>
          )}
        </section>
      </section>
      <footer>School Attendance Management - Staff</footer>
    </main>
  )
}
