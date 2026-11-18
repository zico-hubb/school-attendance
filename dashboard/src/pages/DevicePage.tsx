import { useEffect, useState } from 'react'
import {
  approveDevice,
  getDevice,
  getDevices,
  rejectDevice,
  revokeDevice,
  type RegisteredDevice,
} from '../services/api'

function formatDate(value: string | null) {
  if (!value) return 'Not recorded'
  return new Date(value).toLocaleString()
}

export function DevicePage() {
  const [devices, setDevices] = useState<RegisteredDevice[]>([])
  const [selected, setSelected] = useState<RegisteredDevice | null>(null)
  const [reason, setReason] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      setDevices(await getDevices())
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Unable to load devices.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const openDetails = async (deviceId: string) => {
    setError('')
    setSuccess('')
    try {
      setSelected(await getDevice(deviceId))
    } catch (detailError) {
      setError(detailError instanceof Error ? detailError.message : 'Unable to load device details.')
    }
  }

  const decide = async (action: 'approve' | 'reject' | 'revoke') => {
    if (!selected) return
    setSaving(true)
    setError('')
    setSuccess('')
    try {
      const updated = action === 'approve'
        ? await approveDevice(selected.id)
        : action === 'reject'
          ? await rejectDevice(selected.id, reason.trim())
          : await revokeDevice(selected.id, reason.trim())
      setSelected(updated)
      setReason('')
      setSuccess(`Device ${action}d successfully.`)
      await load()
    } catch (decisionError) {
      setError(decisionError instanceof Error ? decisionError.message : `Unable to ${action} device.`)
    } finally {
      setSaving(false)
    }
  }

  return (
    <main className="dashboard-card">
      <header className="page-header">
        <div>
          <p className="eyebrow">Administration</p>
          <h1>Device Management</h1>
        </div>
      </header>

      {success && <div className="feedback feedback--success" role="status">{success}</div>}
      {error && <div className="feedback feedback--error" role="alert">{error}</div>}
      {loading ? (
        <div className="state-card">Loading registered devices…</div>
      ) : devices.length === 0 ? (
        <div className="state-card">No devices have been registered.</div>
      ) : (
        <div className="ap-list" aria-label="Registered devices">
          {devices.map((device) => (
            <section className="ap-item" key={device.id}>
              <div className="ap-item__head">
                <strong>{device.staff_name} ({device.employee_number})</strong>
                <span className={`status-pill status-pill--${device.status === 'ACTIVE' ? 'active' : device.status === 'PENDING' ? 'inactive' : 'inactive'}`}>
                  {device.status}
                </span>
              </div>
              <p className="ap-item__meta">{device.device_name} · {device.platform}</p>
              <p className="ap-item__meta">Enrolled: {formatDate(device.enrolled_at)}</p>
              {device.last_seen_at && <p className="ap-item__meta">Last seen: {formatDate(device.last_seen_at)}</p>}
              <button type="button" className="secondary-button" onClick={() => void openDetails(device.id)}>
                View details and history
              </button>
            </section>
          ))}
        </div>
      )}

      {selected && (
        <section className="panel" aria-label="Device details">
          <div className="panel-heading">
            <h2>{selected.device_name}</h2>
            <button type="button" className="secondary-button" onClick={() => setSelected(null)}>Close</button>
          </div>
          <dl className="detail-grid">
            <div><dt>Staff member</dt><dd>{selected.staff_name} ({selected.employee_number})</dd></div>
            <div><dt>Platform</dt><dd>{selected.platform}</dd></div>
            <div><dt>Status</dt><dd>{selected.status}</dd></div>
            <div><dt>Enrolled</dt><dd>{formatDate(selected.enrolled_at)}</dd></div>
            <div><dt>Revoked</dt><dd>{formatDate(selected.revoked_at)}</dd></div>
          </dl>
          <h3>Registered key metadata</h3>
          {selected.keys.length === 0 ? (
            <p className="ap-item__meta">No key metadata is available.</p>
          ) : selected.keys.map((key) => (
            <div className="state-card" key={`${key.fingerprint}-${key.key_version}`}>
              {key.algorithm} · version {key.key_version} · {key.status} · fingerprint {key.fingerprint}
            </div>
          ))}
          {(selected.history?.length || selected.audit_history?.length) ? (
            <div>
              <h3>Device history</h3>
              <ul>
                {selected.history?.map((event) => (
                  <li key={`${event.event_type}-${event.created_at}`}>{event.event_type} · {formatDate(event.created_at)}</li>
                ))}
                {selected.audit_history?.map((event) => (
                  <li key={`${event.action}-${event.created_at}`}>{event.action} · {formatDate(event.created_at)}</li>
                ))}
              </ul>
            </div>
          ) : <p className="ap-item__meta">No lifecycle history is available.</p>}

          {(selected.status === 'PENDING' || selected.status === 'ACTIVE') && (
            <>
              {selected.status === 'ACTIVE' && (
                <label>
                  Revocation reason
                  <textarea value={reason} onChange={(event) => setReason(event.target.value)} maxLength={500} />
                </label>
              )}
              {selected.status === 'PENDING' && (
                <label>
                  Rejection reason (optional)
                  <textarea value={reason} onChange={(event) => setReason(event.target.value)} maxLength={500} />
                </label>
              )}
              <div className="button-row">
                {selected.status === 'PENDING' && (
                  <>
                    <button type="button" className="primary-button" disabled={saving} onClick={() => void decide('approve')}>
                      {saving ? 'Saving…' : 'Approve device'}
                    </button>
                    <button type="button" className="secondary-button" disabled={saving} onClick={() => void decide('reject')}>
                      Reject device
                    </button>
                  </>
                )}
                {selected.status === 'ACTIVE' && (
                  <button type="button" className="secondary-button" disabled={saving} onClick={() => void decide('revoke')}>
                    {saving ? 'Saving…' : 'Revoke device'}
                  </button>
                )}
              </div>
            </>
          )}
        </section>
      )}
    </main>
  )
}
