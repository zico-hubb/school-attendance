import { useEffect, useState, type FormEvent } from 'react'
import {
  cancelLeaveRecord,
  createLeaveType,
  getLeaveRecords,
  getLeaveTypes,
  reviewLeaveRecord,
  updateLeaveType,
  type LeaveRecord,
  type LeaveType,
} from '../services/api'
import { useAuth } from '../services/auth'

export function LeavePage() {
  const { user } = useAuth()
  const canManage = user?.role === 'SCHOOL_ADMIN'
  const [types, setTypes] = useState<LeaveType[]>([])
  const [records, setRecords] = useState<LeaveRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [formError, setFormError] = useState('')
  const [success, setSuccess] = useState('')
  const [saving, setSaving] = useState(false)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [reviewNotes, setReviewNotes] = useState<Record<string, string>>({})
  const [cancelReasons, setCancelReasons] = useState<Record<string, string>>({})

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      const [typeData, recordData] = await Promise.all([getLeaveTypes(), getLeaveRecords()])
      setTypes(typeData)
      setRecords(recordData)
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Unable to load leave data.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const submitType = async (event: FormEvent) => {
    event.preventDefault()
    setFormError('')
    setSuccess('')
    setSaving(true)
    try {
      await createLeaveType({ name: name.trim(), description: description.trim() })
      setName('')
      setDescription('')
      await load()
      setSuccess('Leave type created.')
    } catch (submitError) {
      setFormError(submitError instanceof Error ? submitError.message : 'Unable to create leave type.')
    } finally {
      setSaving(false)
    }
  }

  const toggleType = async (leaveType: LeaveType) => {
    setError('')
    setSuccess('')
    try {
      await updateLeaveType(leaveType.id, { is_active: !leaveType.is_active })
      await load()
      setSuccess(`Leave type ${leaveType.is_active ? 'deactivated' : 'activated'}.`)
    } catch (updateError) {
      setError(updateError instanceof Error ? updateError.message : 'Unable to update leave type.')
    }
  }

  const review = async (record: LeaveRecord, decision: 'APPROVED' | 'REJECTED') => {
    setFormError('')
    setSuccess('')
    setSaving(true)
    try {
      await reviewLeaveRecord(record.id, {
        status: decision,
        review_comment: reviewNotes[record.id] ?? '',
      })
      await load()
      setSuccess(`Leave request ${decision.toLowerCase()}.`)
    } catch (reviewError) {
      setFormError(reviewError instanceof Error ? reviewError.message : 'Unable to review leave request.')
    } finally {
      setSaving(false)
    }
  }

  const cancel = async (record: LeaveRecord) => {
    const reason = cancelReasons[record.id]?.trim()
    if (!reason) {
      setFormError('Enter a cancellation reason before cancelling leave.')
      return
    }
    setFormError('')
    setSuccess('')
    setSaving(true)
    try {
      await cancelLeaveRecord(record.id, reason)
      await load()
      setSuccess('Leave request cancelled.')
    } catch (cancelError) {
      setFormError(cancelError instanceof Error ? cancelError.message : 'Unable to cancel leave request.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <main className="dashboard-card">
      <header className="page-header">
        <div><p className="eyebrow">Administration</p><h1>Leave Management</h1></div>
        {!canManage && <span className="read-only-badge">Read only</span>}
      </header>
      {success && <div className="feedback feedback--success" role="status">{success}</div>}
      {error && <div className="feedback feedback--error" role="alert">{error}</div>}
      {loading ? <div className="state-card">Loading leave records…</div> : (
        <>
          <section className="module-section">
            <div className="panel-heading"><h2>Leave types</h2></div>
            <div className="ap-list" aria-label="Leave types">
              {types.length === 0 && <div className="state-card">No leave types have been configured.</div>}
              {types.map((leaveType) => (
                <article className="ap-item" key={leaveType.id}>
                  <div className="ap-item__head">
                    <strong>{leaveType.name}</strong>
                    <span className={`status-pill ${leaveType.is_active ? 'status-pill--active' : 'status-pill--inactive'}`}>
                      {leaveType.is_active ? 'Active' : 'Inactive'}
                    </span>
                  </div>
                  {leaveType.description && <p className="ap-item__meta">{leaveType.description}</p>}
                  {canManage && <button
                    type="button"
                    className="secondary-button"
                    onClick={() => void toggleType(leaveType)}
                  >{leaveType.is_active ? 'Deactivate' : 'Activate'}</button>}
                </article>
              ))}
            </div>
            {canManage && (
              <form className="config-form" onSubmit={(event) => void submitType(event)}>
                <h2>Create a leave type</h2>
                <label>Name<input value={name} onChange={(event) => setName(event.target.value)} required maxLength={120} /></label>
                <label>Description<textarea value={description} onChange={(event) => setDescription(event.target.value)} /></label>
                {formError && <div className="feedback feedback--error" role="alert">{formError}</div>}
                <button className="primary-button" disabled={saving}>{saving ? 'Saving…' : 'Create leave type'}</button>
              </form>
            )}
          </section>

          <section className="module-section">
            <div className="panel-heading"><h2>Leave requests</h2></div>
            {records.length === 0 ? <div className="state-card">No leave requests have been submitted.</div> : (
              <div className="ap-list" aria-label="Leave requests">
                {records.map((record) => (
                  <article className="ap-item" key={record.id}>
                    <div className="ap-item__head">
                      <strong>{record.staff_name}</strong>
                      <span className={`status-pill ${record.status === 'APPROVED' ? 'status-pill--active' : record.status === 'PENDING' ? 'status-pill--inactive' : ''}`}>
                        {record.status}
                      </span>
                    </div>
                    <p className="ap-item__meta">{record.leave_type_name} · {record.start_date} to {record.end_date}</p>
                    {record.reason && <p className="ap-item__meta">Request: {record.reason}</p>}
                    {record.review_comment && <p className="ap-item__meta">Review: {record.review_comment}</p>}
                    {record.cancellation_reason && <p className="ap-item__meta">Cancellation: {record.cancellation_reason}</p>}
                    {canManage && record.status === 'PENDING' && (
                      <div className="leave-actions">
                        <label>Review comment
                          <textarea
                            aria-label={`Review comment for ${record.staff_name}`}
                            value={reviewNotes[record.id] ?? ''}
                            onChange={(event) => setReviewNotes((current) => ({ ...current, [record.id]: event.target.value }))}
                          />
                        </label>
                        <div className="button-row">
                          <button type="button" className="primary-button" disabled={saving} onClick={() => void review(record, 'APPROVED')}>Approve</button>
                          <button type="button" className="secondary-button" disabled={saving} onClick={() => void review(record, 'REJECTED')}>Reject</button>
                        </div>
                      </div>
                    )}
                    {canManage && ['PENDING', 'APPROVED'].includes(record.status) && (
                      <div className="leave-actions">
                        <label>Cancellation reason
                          <input
                            aria-label={`Cancellation reason for ${record.staff_name}`}
                            value={cancelReasons[record.id] ?? ''}
                            onChange={(event) => setCancelReasons((current) => ({ ...current, [record.id]: event.target.value }))}
                          />
                        </label>
                        <button type="button" className="secondary-button" disabled={saving} onClick={() => void cancel(record)}>Cancel leave</button>
                      </div>
                    )}
                  </article>
                ))}
              </div>
            )}
          </section>
          {formError && <div className="feedback feedback--error" role="alert">{formError}</div>}
        </>
      )}
    </main>
  )
}
