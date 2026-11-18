import { useEffect, useState, type FormEvent } from 'react'
import {
  createDepartment,
  getDepartments,
  updateDepartment,
  type Department,
} from '../services/api'
import { useAuth } from '../services/auth'

export function DepartmentPage() {
  const { user } = useAuth()
  const canManage = user?.role === 'SCHOOL_ADMIN'
  const [departments, setDepartments] = useState<Department[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [formError, setFormError] = useState('')
  const [success, setSuccess] = useState('')
  const [saving, setSaving] = useState(false)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      setDepartments(await getDepartments())
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Unable to load departments.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const selectDepartment = (department: Department) => {
    setSelectedId(department.id)
    setName(department.name)
    setDescription(department.description)
    setFormError('')
    setSuccess('')
  }

  const clearForm = () => {
    setSelectedId(null)
    setName('')
    setDescription('')
    setFormError('')
    setSuccess('')
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setFormError('')
    setSuccess('')
    if (!name.trim()) {
      setFormError('Department name is required.')
      return
    }
    setSaving(true)
    try {
      const successMessage = selectedId ? 'Department updated.' : 'Department created.'
      if (selectedId) {
        await updateDepartment(selectedId, { name: name.trim(), description: description.trim() })
      } else {
        await createDepartment({ name: name.trim(), description: description.trim() })
      }
      clearForm()
      await load()
      setSuccess(successMessage)
    } catch (saveError) {
      setFormError(saveError instanceof Error ? saveError.message : 'Unable to save department.')
    } finally {
      setSaving(false)
    }
  }

  const toggleActive = async (department: Department) => {
    setError('')
    setSuccess('')
    try {
      await updateDepartment(department.id, { is_active: !department.is_active })
      setSuccess(`Department ${department.is_active ? 'deactivated' : 'activated'}.`)
      await load()
    } catch (updateError) {
      setError(updateError instanceof Error ? updateError.message : 'Unable to update department.')
    }
  }

  return (
    <main className="dashboard-card">
      <header className="page-header">
        <div>
          <p className="eyebrow">Administration</p>
          <h1>Departments</h1>
        </div>
        {!canManage && <span className="read-only-badge">Read only</span>}
      </header>

      {success && <div className="feedback feedback--success" role="status">{success}</div>}
      {error && <div className="feedback feedback--error" role="alert">{error}</div>}
      {loading ? (
        <div className="state-card">Loading departments…</div>
      ) : departments.length === 0 ? (
        <div className="state-card">No departments have been configured.</div>
      ) : (
        <div className="ap-list" aria-label="Department list">
          {departments.map((department) => (
            <section className="ap-item" key={department.id}>
              <div className="ap-item__head">
                <strong>{department.name}</strong>
                <span className={`status-pill ${department.is_active ? 'status-pill--active' : 'status-pill--inactive'}`}>
                  {department.is_active ? 'Active' : 'Inactive'}
                </span>
              </div>
              {department.description && <p className="ap-item__meta">{department.description}</p>}
              {canManage && (
                <div className="ap-item__actions">
                  <button type="button" className="secondary-button" onClick={() => selectDepartment(department)}>
                    Edit
                  </button>
                  <button type="button" className="secondary-button" onClick={() => void toggleActive(department)}>
                    {department.is_active ? 'Deactivate' : 'Activate'}
                  </button>
                </div>
              )}
            </section>
          ))}
        </div>
      )}

      {canManage && (
        <form className="config-form" onSubmit={(event) => void submit(event)}>
          <h2>{selectedId ? 'Edit department' : 'Create department'}</h2>
          <label>
            Department name
            <input value={name} onChange={(event) => setName(event.target.value)} maxLength={120} required />
          </label>
          <label>
            Description
            <textarea value={description} onChange={(event) => setDescription(event.target.value)} />
          </label>
          {formError && <div className="feedback feedback--error" role="alert">{formError}</div>}
          <div className="button-row">
            <button type="submit" className="primary-button" disabled={saving}>
              {saving ? 'Saving…' : selectedId ? 'Save department' : 'Create department'}
            </button>
            {selectedId && (
              <button type="button" className="secondary-button" onClick={clearForm}>Cancel</button>
            )}
          </div>
        </form>
      )}
    </main>
  )
}
