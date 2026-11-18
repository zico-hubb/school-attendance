import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import {
  changePassword,
  createDeviceSession,
  enrollDevice,
  getAttendanceChallenge,
  getAttendanceHistory,
  getAttendanceStatus,
  getDeviceChallenge,
  getEnrollmentChallenge,
  getLeaveRecords,
  getLeaveTypes,
  login,
  logout,
  refreshSession,
  setAccessToken,
  submitAttendance,
  submitLeave,
  type AttendanceHistory,
  type AttendanceStatus,
  type LeaveRecord,
  type LeaveType,
  type TokenResponse,
} from './services/api'
import { deviceIdentityPlugin } from './plugins/device-identity'
import { locationPlugin } from './plugins/location'
import { wifiPlugin } from './plugins/wifi'
import { getPlatformCapabilities } from './platform/capabilities'

type SessionState = TokenResponse & { refresh_token: string }

export function App() {
  const capabilities = getPlatformCapabilities()
  const [session, setSession] = useState<SessionState | null>(null)
  const [schoolCode, setSchoolCode] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [loading, setLoading] = useState(false)
  const [status, setStatus] = useState<AttendanceStatus | null>(null)
  const [history, setHistory] = useState<AttendanceHistory[]>([])
  const [leaveTypes, setLeaveTypes] = useState<LeaveType[]>([])
  const [leaves, setLeaves] = useState<LeaveRecord[]>([])

  useEffect(() => {
    void (async () => {
      try {
      const raw = sessionStorage.getItem('schoolAttendanceMobileSession')
      if (raw) {
        const stored = JSON.parse(raw) as SessionState
        try {
          const refreshed = await refreshSession(stored.refresh_token)
          saveSession(refreshed as SessionState)
        } catch {
          setSession(stored)
          setAccessToken(stored.access_token)
        }
      }
      } catch {
        sessionStorage.removeItem('schoolAttendanceMobileSession')
      }
    })()
  }, [])

  useEffect(() => {
    if (!session || session.password_change_required || session.device_status !== 'ACTIVE') return
    void loadStaffData()
  }, [session])

  async function loadStaffData() {
    setLoading(true)
    setError('')
    try {
      const [nextStatus, nextHistory, nextTypes, nextLeaves] = await Promise.all([
        getAttendanceStatus(),
        getAttendanceHistory(),
        getLeaveTypes(),
        getLeaveRecords(),
      ])
      setStatus(nextStatus)
      setHistory(nextHistory)
      setLeaveTypes(nextTypes)
      setLeaves(nextLeaves)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to load staff data.')
    } finally {
      setLoading(false)
    }
  }

  function saveSession(next: SessionState) {
    setSession(next)
    setAccessToken(next.access_token)
    sessionStorage.setItem('schoolAttendanceMobileSession', JSON.stringify(next))
  }

  async function handleLogin(event: FormEvent) {
    event.preventDefault()
    setLoading(true)
    setError('')
    try {
      const result = await login({ school_code: schoolCode, username, password })
      saveSession(result as SessionState)
      setPassword('')
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Login failed.')
    } finally {
      setLoading(false)
    }
  }

  async function handlePasswordChange(event: FormEvent) {
    event.preventDefault()
    const form = new FormData(event.currentTarget as HTMLFormElement)
    setLoading(true)
    setError('')
    try {
      await changePassword({
        current_password: String(form.get('current_password')),
        new_password: String(form.get('new_password')),
        new_password_confirm: String(form.get('new_password_confirm')),
      })
      if (session) saveSession({ ...session, password_change_required: false })
      setMessage('Password changed successfully.')
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Password change failed.')
    } finally {
      setLoading(false)
    }
  }

  async function handleEnrollment() {
    setLoading(true)
    setError('')
    try {
      const registration = await deviceIdentityPlugin.registerPublicKey()
      if (!registration.available) throw new Error(registration.reason)
      const challenge = await getEnrollmentChallenge()
      const signed = await deviceIdentityPlugin.signChallenge(challenge.signature_message)
      if (!signed.available) throw new Error(signed.reason)
      await enrollDevice({
        platform: capabilities.platform === 'ios' ? 'IOS' : 'ANDROID',
        device_name: capabilities.platform === 'android' ? 'Android staff device' : 'Staff device',
        public_key: registration.value.publicKey,
        challenge: challenge.challenge,
        signature: signed.value.signature,
      })
      setMessage('Device enrollment submitted. Waiting for administrator approval.')
      if (session) saveSession({ ...session, device_status: 'PENDING' })
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Device enrollment failed.')
    } finally {
      setLoading(false)
    }
  }

  async function handleDeviceActivation() {
    setLoading(true)
    setError('')
    try {
      const challenge = await getDeviceChallenge()
      const signed = await deviceIdentityPlugin.signChallenge(challenge.signature_message)
      if (!signed.available) throw new Error(signed.reason)
      const result = await createDeviceSession({ challenge: challenge.challenge, signature: signed.value.signature })
      saveSession(result as SessionState)
      setMessage('Approved device session restored.')
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Device activation failed.')
    } finally {
      setLoading(false)
    }
  }

  async function handleAttendance(attemptType: 'CHECK_IN' | 'CHECK_OUT') {
    setLoading(true)
    setError('')
    try {
      const permission = await locationPlugin.requestPermissions()
      if (!permission.granted) throw new Error(permission.reason || 'Location permission is required for attendance.')
      const location = await locationPlugin.getCurrentLocation()
      if (!location.available) throw new Error(location.reason)
      const wifi = await wifiPlugin.getInfo()
      const challenge = await getAttendanceChallenge(attemptType)
      const signed = await deviceIdentityPlugin.signChallenge(challenge.signature_message)
      if (!signed.available) throw new Error(signed.reason)
      const result = await submitAttendance({
        challenge: challenge.challenge,
        signature: signed.value.signature,
        attempt_type: attemptType,
        idempotency_key: crypto.randomUUID(),
        evidence_timestamp: location.location.timestamp,
        latitude: location.location.latitude,
        longitude: location.location.longitude,
        location_accuracy: location.location.accuracyMeters,
        bssid: wifi.bssid ?? '',
      })
      setMessage(`${attemptType === 'CHECK_IN' ? 'Check-in' : 'Check-out'} ${result.state?.toString().toLowerCase()}.`)
      await loadStaffData()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Attendance submission failed.')
    } finally {
      setLoading(false)
    }
  }

  async function handleLeave(event: FormEvent) {
    event.preventDefault()
    const form = new FormData(event.currentTarget as HTMLFormElement)
    setLoading(true)
    setError('')
    try {
      await submitLeave({
        leave_type: String(form.get('leave_type')),
        start_date: String(form.get('start_date')),
        end_date: String(form.get('end_date')),
        reason: String(form.get('reason')),
      })
      setMessage('Leave request submitted.')
      await loadStaffData()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Leave submission failed.')
    } finally {
      setLoading(false)
    }
  }

  async function handleLogout() {
    try { await logout() } catch { /* Clear local state even if the API is unavailable. */ }
    setAccessToken(null)
    sessionStorage.removeItem('schoolAttendanceMobileSession')
    setSession(null)
  }

  if (!session) {
    return (
      <main className="mobile-shell">
        <section className="welcome-card">
          <p className="eyebrow">Staff application</p>
          <h1>School Attendance</h1>
          <form onSubmit={handleLogin}>
            <label>School code<input value={schoolCode} onChange={(event) => setSchoolCode(event.target.value)} required /></label>
            <label>Username<input value={username} onChange={(event) => setUsername(event.target.value)} required /></label>
            <label>Password<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} required /></label>
            {error && <p role="alert" className="error">{error}</p>}
            <button type="submit" disabled={loading}>{loading ? 'Signing in...' : 'Sign in'}</button>
          </form>
          <p data-testid="platform-name">Platform: {capabilities.platform}</p>
          <p data-testid="capability-status">
            Native verification: {capabilities.nativeVerification.available ? 'available' : 'not available'}
          </p>
        </section>
      </main>
    )
  }

  if (session.password_change_required) {
    return (
      <main className="mobile-shell">
        <section className="welcome-card">
          <h1>Change temporary password</h1>
          <form onSubmit={handlePasswordChange}>
            <label>Current password<input name="current_password" type="password" required /></label>
            <label>New password<input name="new_password" type="password" required /></label>
            <label>Confirm new password<input name="new_password_confirm" type="password" required /></label>
            {error && <p role="alert" className="error">{error}</p>}
            <button type="submit" disabled={loading}>{loading ? 'Changing...' : 'Change password'}</button>
          </form>
          <button type="button" onClick={handleLogout}>Logout</button>
        </section>
      </main>
    )
  }

  if (session.device_status !== 'ACTIVE') {
    return (
      <main className="mobile-shell">
        <section className="welcome-card">
          <h1>Device approval</h1>
          {session.device_status === 'NOT_ENROLLED' && <p>No approved device is registered. Enroll this phone to continue.</p>}
          {session.device_status === 'PENDING' && <p>Device enrollment is pending administrator approval.</p>}
          {session.device_status === 'REJECTED' && <p>Device enrollment was rejected. A new enrollment may be required.</p>}
          {session.device_status === 'REVOKED' && <p>This device was revoked. Re-enrollment requires administrator approval.</p>}
          {error && <p role="alert" className="error">{error}</p>}
          {message && <p aria-live="polite">{message}</p>}
          {session.device_status === 'NOT_ENROLLED' || session.device_status === 'REJECTED' || session.device_status === 'REVOKED'
            ? <button type="button" onClick={handleEnrollment} disabled={loading}>{loading ? 'Enrolling...' : 'Enroll this device'}</button>
            : null}
          {session.device_status === 'PENDING' && <button type="button" onClick={handleEnrollment} disabled={loading}>Refresh enrollment status</button>}
          <button type="button" onClick={handleLogout}>Logout</button>
        </section>
      </main>
    )
  }

  return (
    <main className="mobile-shell">
      <section className="welcome-card">
        <p className="eyebrow">{session.user.school_code}</p>
        <h1>Today&apos;s attendance</h1>
        {loading && <p role="status">Loading...</p>}
        {error && <p role="alert" className="error">{error}</p>}
        {message && <p aria-live="polite">{message}</p>}
        {status && (
          <>
            <p><strong>Status:</strong> {status.status ?? 'No scheduled record'}</p>
            <p><strong>Schedule:</strong> {status.schedule?.start_time ?? 'Not applicable'} - {status.schedule?.end_time ?? ''}</p>
            <button type="button" disabled={loading || status.checked_in} onClick={() => handleAttendance('CHECK_IN')}>Check in</button>
            <button type="button" disabled={loading || !status.checked_in || status.checked_out} onClick={() => handleAttendance('CHECK_OUT')}>Check out</button>
          </>
        )}
        <h2>Attendance history</h2>
        {history.length === 0 ? <p>No attendance records.</p> : (
          <ul>{history.map((record) => <li key={record.attendance_date}>{record.attendance_date}: {record.status}</li>)}</ul>
        )}
        <h2>Leave</h2>
        {leaves.length === 0 ? <p>No leave requests.</p> : (
          <ul>{leaves.map((leave) => <li key={leave.id}>{leave.start_date} to {leave.end_date}: {leave.status}</li>)}</ul>
        )}
        {leaveTypes.length > 0 && (
          <form onSubmit={handleLeave}>
            <label>Leave type
              <select name="leave_type" required>
                {leaveTypes.filter((type) => type.is_active).map((type) => <option key={type.id} value={type.id}>{type.name}</option>)}
              </select>
            </label>
            <label>Start date<input name="start_date" type="date" required /></label>
            <label>End date<input name="end_date" type="date" required /></label>
            <label>Reason<textarea name="reason" /></label>
            <button type="submit" disabled={loading}>Submit leave request</button>
          </form>
        )}
        <button type="button" onClick={handleDeviceActivation}>Restore approved device session</button>
        <button type="button" onClick={handleLogout}>Logout</button>
      </section>
    </main>
  )
}
