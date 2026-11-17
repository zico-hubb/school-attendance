import { useEffect, useState, type FormEvent } from 'react'
import { createStaff, getStaff, getStaffMember, updateStaff, type StaffMember } from '../services/api'

const emptyCreate = {
  first_name: '',
  last_name: '',
  username: '',
  employee_number: '',
  department: '',
  job_title: '',
  date_joined: new Date().toISOString().slice(0, 10),
  email: '',
  phone: '',
  password: '',
}

export function StaffPage() {
  const [staff, setStaff] = useState<StaffMember[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState<'all' | 'active' | 'inactive'>('all')
  const [createOpen, setCreateOpen] = useState(false)
  const [createValues, setCreateValues] = useState(emptyCreate)
  const [createError, setCreateError] = useState('')
  const [createSuccess, setCreateSuccess] = useState('')
  const [saving, setSaving] = useState(false)
  const [selected, setSelected] = useState<StaffMember | null>(null)
  const [detailError, setDetailError] = useState('')

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      setStaff(await getStaff())
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Unable to load staff.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const submitCreate = async (event: FormEvent) => {
    event.preventDefault()
    setCreateError('')
    setCreateSuccess('')
    if (!createValues.first_name.trim() || !createValues.last_name.trim() || !createValues.username.trim()
      || !createValues.employee_number.trim() || !createValues.password || !createValues.date_joined) {
      setCreateError('Complete the required staff account fields.')
      return
    }
    setSaving(true)
    try {
      const payload: Record<string, unknown> = {
        first_name: createValues.first_name.trim(),
        last_name: createValues.last_name.trim(),
        username: createValues.username.trim(),
        employee_number: createValues.employee_number.trim(),
        password: createValues.password,
        date_joined: createValues.date_joined,
      }
      if (createValues.department.trim()) payload.department = createValues.department.trim()
      if (createValues.job_title.trim()) payload.job_title = createValues.job_title.trim()
      if (createValues.email.trim()) payload.email = createValues.email.trim()
      if (createValues.phone.trim()) payload.phone = createValues.phone.trim()
      await createStaff(payload)
      setCreateSuccess('Staff account created successfully.')
      setCreateValues(emptyCreate)
      await load()
    } catch (createApiError) {
      setCreateError(createApiError instanceof Error ? createApiError.message : 'Unable to create staff account.')
    } finally {
      setSaving(false)
    }
  }

  const openDetails = async (member: StaffMember) => {
    setDetailError('')
    try {
      setSelected(await getStaffMember(member.id))
    } catch (detailLoadError) {
      setDetailError(detailLoadError instanceof Error ? detailLoadError.message : 'Unable to load staff details.')
    }
  }

  const toggleActive = async () => {
    if (!selected) return
    setDetailError('')
    try {
      const updated = await updateStaff(selected.id, { is_active: !selected.is_active })
      setSelected(updated)
      await load()
    } catch (detailUpdateError) {
      setDetailError(detailUpdateError instanceof Error ? detailUpdateError.message : 'Unable to update account.')
    }
  }

  const query = search.trim().toLowerCase()
  const filtered = staff.filter((member) => {
    const matchesSearch = !query || [
      member.first_name,
      member.last_name,
      member.employee_number,
      member.username,
      member.department ?? '',
    ].some((value) => value.toLowerCase().includes(query))
    const matchesStatus = status === 'all' || (status === 'active' ? member.is_active : !member.is_active)
    return matchesSearch && matchesStatus
  })

  return (
    <main className="dashboard-card staff-page">
      <div className="page-header">
        <div>
          <p className="eyebrow">Administration</p>
          <h1>Staff Management</h1>
        </div>
        <button type="button" className="primary-button" onClick={() => setCreateOpen(true)}>
          Create staff account
        </button>
      </div>

      {createOpen && (
        <section className="staff-create panel" aria-label="Create staff account">
          <div className="panel-heading">
            <h2>New staff account</h2>
            <button type="button" className="secondary-button" onClick={() => setCreateOpen(false)}>Close</button>
          </div>
          <form className="config-form" onSubmit={submitCreate}>
            <div className="field-row field-row--split">
              <label>First name *<input value={createValues.first_name} onChange={(event) => setCreateValues({ ...createValues, first_name: event.target.value })} required /></label>
              <label>Last name *<input value={createValues.last_name} onChange={(event) => setCreateValues({ ...createValues, last_name: event.target.value })} required /></label>
            </div>
            <div className="field-row field-row--split">
              <label>Username *<input value={createValues.username} onChange={(event) => setCreateValues({ ...createValues, username: event.target.value })} required /></label>
              <label>Initial password *<input type="password" value={createValues.password} onChange={(event) => setCreateValues({ ...createValues, password: event.target.value })} required /></label>
            </div>
            <div className="field-row field-row--split">
              <label>Employee number *<input value={createValues.employee_number} onChange={(event) => setCreateValues({ ...createValues, employee_number: event.target.value })} required /></label>
              <label>Date joined *<input type="date" value={createValues.date_joined} onChange={(event) => setCreateValues({ ...createValues, date_joined: event.target.value })} required /></label>
            </div>
            <div className="field-row field-row--split">
              <label>Department ID<input value={createValues.department} onChange={(event) => setCreateValues({ ...createValues, department: event.target.value })} /></label>
              <label>Job title<input value={createValues.job_title} onChange={(event) => setCreateValues({ ...createValues, job_title: event.target.value })} /></label>
            </div>
            <div className="field-row field-row--split">
              <label>Email<input type="email" value={createValues.email} onChange={(event) => setCreateValues({ ...createValues, email: event.target.value })} /></label>
              <label>Phone<input value={createValues.phone} onChange={(event) => setCreateValues({ ...createValues, phone: event.target.value })} /></label>
            </div>
            {createError && <div className="feedback feedback--error" role="alert">{createError}</div>}
            {createSuccess && <div className="feedback feedback--success" role="status">{createSuccess}</div>}
            <button type="submit" className="primary-button" disabled={saving}>{saving ? 'Creating…' : 'Create account'}</button>
          </form>
        </section>
      )}

      <div className="staff-toolbar">
        <label>Search<input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Name, username or employee number" /></label>
        <label>Account status
          <select value={status} onChange={(event) => setStatus(event.target.value as typeof status)}>
            <option value="all">All accounts</option>
            <option value="active">Active</option>
            <option value="inactive">Inactive</option>
          </select>
        </label>
      </div>

      {loading && <div className="state-card">Loading staff…</div>}
      {!loading && error && <div className="state-card state-card--error" role="alert">{error}</div>}
      {!loading && !error && filtered.length === 0 && <div className="state-card">No staff accounts match this view.</div>}

      {!loading && !error && filtered.length > 0 && (
        <div className="staff-table" role="table" aria-label="Staff directory">
          {filtered.map((member) => (
            <button type="button" className="staff-row" key={member.id} onClick={() => void openDetails(member)}>
              <span><strong>{member.first_name} {member.last_name}</strong><small>{member.employee_number}</small></span>
              <span>{member.username}<small>{member.job_title || 'No job title'}</small></span>
              <span className={`status-pill ${member.is_active ? 'status-pill--active' : 'status-pill--inactive'}`}>
                {member.is_active ? 'Active' : 'Inactive'}
              </span>
            </button>
          ))}
        </div>
      )}

      {selected && (
        <section className="staff-details panel" aria-label="Staff details">
          <div className="panel-heading">
            <h2>{selected.first_name} {selected.last_name}</h2>
            <button type="button" className="secondary-button" onClick={() => setSelected(null)}>Close</button>
          </div>
          {detailError && <div className="feedback feedback--error" role="alert">{detailError}</div>}
          <dl className="detail-grid">
            <div><dt>Username</dt><dd>{selected.username}</dd></div>
            <div><dt>Employee number</dt><dd>{selected.employee_number}</dd></div>
            <div><dt>Email</dt><dd>{selected.email || 'Not provided'}</dd></div>
            <div><dt>Phone</dt><dd>{selected.phone || 'Not provided'}</dd></div>
            <div><dt>Department ID</dt><dd>{selected.department || 'Not assigned'}</dd></div>
            <div><dt>Job title</dt><dd>{selected.job_title || 'Not provided'}</dd></div>
            <div><dt>Employment status</dt><dd>{selected.employment_status}</dd></div>
            <div><dt>Account status</dt><dd>{selected.is_active ? 'Active' : 'Inactive'}</dd></div>
          </dl>
          <button type="button" className="secondary-button" onClick={() => void toggleActive()}>
            {selected.is_active ? 'Deactivate account' : 'Activate account'}
          </button>
        </section>
      )}
    </main>
  )
}
