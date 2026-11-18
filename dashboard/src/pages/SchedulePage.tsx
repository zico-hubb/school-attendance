import { useEffect, useState, type FormEvent } from 'react'
import {
  createCalendarEvent,
  createSchedule,
  createScheduleAssignment,
  createScheduleException,
  createScheduleVersion,
  endScheduleAssignment,
  getCalendarEvents,
  getDepartments,
  getScheduleAssignments,
  getScheduleExceptions,
  getSchedules,
  getStaff,
  updateSchedule,
  updateCalendarEvent,
  updateScheduleException,
  type Department,
  type ScheduleDay,
  type ScheduleAssignment,
  type ScheduleException,
  type SchoolCalendarEvent,
  type StaffMember,
  type WorkSchedule,
} from '../services/api'
import { useAuth } from '../services/auth'

type ScheduleTab = 'schedules' | 'assignments' | 'exceptions' | 'calendar'
type AssignmentScope = 'school' | 'department' | 'staff'

const weekdays = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

function initialDays(): ScheduleDay[] {
  return weekdays.map((_, weekday) => ({
    weekday,
    is_working_day: weekday < 5,
    start_time: weekday < 5 ? '08:00' : null,
    end_time: weekday < 5 ? '16:00' : null,
    late_after: weekday < 5 ? '08:15' : null,
    absence_finalization_time: weekday < 5 ? '10:00' : null,
  }))
}

function today(): string {
  const date = new Date()
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

export function SchedulePage() {
  const { user } = useAuth()
  const canManage = user?.role === 'SCHOOL_ADMIN'
  const [tab, setTab] = useState<ScheduleTab>('schedules')
  const [schedules, setSchedules] = useState<WorkSchedule[]>([])
  const [assignments, setAssignments] = useState<ScheduleAssignment[]>([])
  const [exceptions, setExceptions] = useState<ScheduleException[]>([])
  const [events, setEvents] = useState<SchoolCalendarEvent[]>([])
  const [departments, setDepartments] = useState<Department[]>([])
  const [staff, setStaff] = useState<StaffMember[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [formError, setFormError] = useState('')
  const [success, setSuccess] = useState('')
  const [saving, setSaving] = useState(false)

  const [scheduleName, setScheduleName] = useState('')
  const [scheduleDescription, setScheduleDescription] = useState('')
  const [effectiveFrom, setEffectiveFrom] = useState(today())
  const [days, setDays] = useState(initialDays)
  const [versionScheduleId, setVersionScheduleId] = useState('')
  const [versionFrom, setVersionFrom] = useState(today())

  const [assignmentScheduleId, setAssignmentScheduleId] = useState('')
  const [assignmentScope, setAssignmentScope] = useState<AssignmentScope>('school')
  const [assignmentTarget, setAssignmentTarget] = useState('')
  const [assignmentFrom, setAssignmentFrom] = useState(today())
  const [assignmentEndDates, setAssignmentEndDates] = useState<Record<string, string>>({})

  const [selectedExceptionId, setSelectedExceptionId] = useState<string | null>(null)
  const [exceptionStaffId, setExceptionStaffId] = useState('')
  const [exceptionDate, setExceptionDate] = useState(today())
  const [exceptionWorking, setExceptionWorking] = useState(true)
  const [exceptionStart, setExceptionStart] = useState('')
  const [exceptionEnd, setExceptionEnd] = useState('')
  const [exceptionLate, setExceptionLate] = useState('')
  const [exceptionDeadline, setExceptionDeadline] = useState('')
  const [exceptionReason, setExceptionReason] = useState('')

  const [selectedEventId, setSelectedEventId] = useState<string | null>(null)
  const [eventName, setEventName] = useState('')
  const [eventType, setEventType] = useState<SchoolCalendarEvent['event_type']>('HOLIDAY')
  const [eventStart, setEventStart] = useState(today())
  const [eventEnd, setEventEnd] = useState(today())
  const [eventStartTime, setEventStartTime] = useState('08:00')
  const [eventEndTime, setEventEndTime] = useState('16:00')
  const [eventLateAfter, setEventLateAfter] = useState('08:15')
  const [eventAbsenceDeadline, setEventAbsenceDeadline] = useState('10:00')
  const [eventDepartment, setEventDepartment] = useState('')
  const [eventDescription, setEventDescription] = useState('')

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      const [scheduleData, assignmentData, exceptionData, eventData] = await Promise.all([
        getSchedules(),
        getScheduleAssignments(),
        getScheduleExceptions(),
        getCalendarEvents(),
      ])
      setSchedules(scheduleData)
      setAssignments(assignmentData)
      setExceptions(exceptionData)
      setEvents(eventData)
      if (canManage) {
        const [departmentData, staffData] = await Promise.all([getDepartments(), getStaff()])
        setDepartments(departmentData)
        setStaff(staffData.filter((member) => member.employment_status === 'ACTIVE'))
      }
      const activeSchedule = scheduleData.find((schedule) => schedule.is_active)
      if (!versionScheduleId && scheduleData.length > 0) setVersionScheduleId(scheduleData[0].id)
      if (!assignmentScheduleId && activeSchedule) setAssignmentScheduleId(activeSchedule.id)
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Unable to load scheduling data.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const refreshAfterSave = async (message: string) => {
    await load()
    setSuccess(message)
    setFormError('')
  }

  const submitSchedule = async (event: FormEvent) => {
    event.preventDefault()
    setFormError('')
    setSuccess('')
    setSaving(true)
    try {
      const created = await createSchedule({
        name: scheduleName.trim(),
        description: scheduleDescription.trim(),
        effective_from: effectiveFrom,
        days,
      })
      setScheduleName('')
      setScheduleDescription('')
      setVersionScheduleId(created.id)
      setAssignmentScheduleId(created.id)
      await refreshAfterSave('Schedule created and activated.')
    } catch (submitError) {
      setFormError(submitError instanceof Error ? submitError.message : 'Unable to create schedule.')
    } finally {
      setSaving(false)
    }
  }

  const submitVersion = async (event: FormEvent) => {
    event.preventDefault()
    if (!versionScheduleId) return
    setFormError('')
    setSuccess('')
    setSaving(true)
    try {
      await createScheduleVersion(versionScheduleId, { effective_from: versionFrom, days })
      await refreshAfterSave('Schedule version created.')
    } catch (submitError) {
      setFormError(submitError instanceof Error ? submitError.message : 'Unable to create schedule version.')
    } finally {
      setSaving(false)
    }
  }

  const submitAssignment = async (event: FormEvent) => {
    event.preventDefault()
    if (!assignmentScheduleId) return
    setFormError('')
    setSuccess('')
    setSaving(true)
    try {
      const payload: {
        work_schedule: string
        department?: string
        staff_profile?: string
        is_school_default: boolean
        effective_from: string
      } = {
        work_schedule: assignmentScheduleId,
        is_school_default: assignmentScope === 'school',
        effective_from: assignmentFrom,
      }
      if (assignmentScope === 'department') payload.department = assignmentTarget
      if (assignmentScope === 'staff') payload.staff_profile = assignmentTarget
      await createScheduleAssignment(payload)
      setAssignmentTarget('')
      await refreshAfterSave('Schedule assignment created.')
    } catch (submitError) {
      setFormError(submitError instanceof Error ? submitError.message : 'Unable to assign schedule.')
    } finally {
      setSaving(false)
    }
  }

  const submitException = async (event: FormEvent) => {
    event.preventDefault()
    if (!exceptionStaffId) return
    setFormError('')
    setSuccess('')
    setSaving(true)
    try {
      const payload = {
        staff_profile: exceptionStaffId,
        exception_date: exceptionDate,
        is_working_day: exceptionWorking,
        start_time: exceptionWorking && exceptionStart ? exceptionStart : null,
        end_time: exceptionWorking && exceptionEnd ? exceptionEnd : null,
        late_after: exceptionWorking && exceptionLate ? exceptionLate : null,
        absence_finalization_time: exceptionWorking && exceptionDeadline ? exceptionDeadline : null,
        reason: exceptionReason.trim(),
      }
      if (selectedExceptionId) {
        await updateScheduleException(selectedExceptionId, payload)
      } else {
        await createScheduleException(payload)
      }
      setSelectedExceptionId(null)
      setExceptionStaffId('')
      setExceptionDate(today())
      setExceptionWorking(true)
      setExceptionStart('')
      setExceptionEnd('')
      setExceptionLate('')
      setExceptionDeadline('')
      setExceptionReason('')
      await refreshAfterSave(`Schedule exception ${selectedExceptionId ? 'updated' : 'created'}.`)
    } catch (submitError) {
      setFormError(submitError instanceof Error ? submitError.message : 'Unable to create exception.')
    } finally {
      setSaving(false)
    }
  }

  const submitEvent = async (event: FormEvent) => {
    event.preventDefault()
    setFormError('')
    setSuccess('')
    setSaving(true)
    try {
      const payload = {
        name: eventName.trim(),
        event_type: eventType,
        start_date: eventStart,
        end_date: eventEnd,
        start_time: eventType === 'EXCEPTIONAL_WORKING_DAY' ? eventStartTime : null,
        end_time: eventType === 'EXCEPTIONAL_WORKING_DAY' ? eventEndTime : null,
        late_after: eventType === 'EXCEPTIONAL_WORKING_DAY' ? eventLateAfter : null,
        absence_finalization_time: eventType === 'EXCEPTIONAL_WORKING_DAY' ? eventAbsenceDeadline : null,
        ...(eventDepartment ? { department: eventDepartment } : {}),
        description: eventDescription.trim(),
      }
      if (selectedEventId) {
        await updateCalendarEvent(selectedEventId, payload)
      } else {
        await createCalendarEvent(payload)
      }
      setSelectedEventId(null)
      setEventName('')
      setEventType('HOLIDAY')
      setEventStart(today())
      setEventEnd(today())
      setEventStartTime('08:00')
      setEventEndTime('16:00')
      setEventLateAfter('08:15')
      setEventAbsenceDeadline('10:00')
      setEventDepartment('')
      setEventDescription('')
      await refreshAfterSave(`Calendar event ${selectedEventId ? 'updated' : 'created'}.`)
    } catch (submitError) {
      setFormError(submitError instanceof Error ? submitError.message : 'Unable to create calendar event.')
    } finally {
      setSaving(false)
    }
  }

  const toggleSchedule = async (schedule: WorkSchedule) => {
    setError('')
    setSuccess('')
    try {
      await updateSchedule(schedule.id, { is_active: !schedule.is_active })
      await load()
      setSuccess(`Schedule ${schedule.is_active ? 'deactivated' : 'activated'}.`)
    } catch (updateError) {
      setError(updateError instanceof Error ? updateError.message : 'Unable to update schedule.')
    }
  }

  const closeAssignment = async (assignment: ScheduleAssignment) => {
    const effectiveTo = assignmentEndDates[assignment.id] ?? today()
    setError('')
    setSuccess('')
    try {
      await endScheduleAssignment(assignment.id, effectiveTo)
      await load()
      setSuccess('Schedule assignment end date saved.')
    } catch (updateError) {
      setError(updateError instanceof Error ? updateError.message : 'Unable to end schedule assignment.')
    }
  }

  const editException = (exception: ScheduleException) => {
    setSelectedExceptionId(exception.id)
    setExceptionStaffId(exception.staff_profile)
    setExceptionDate(exception.exception_date)
    setExceptionWorking(exception.is_working_day)
    setExceptionStart(exception.start_time ?? '')
    setExceptionEnd(exception.end_time ?? '')
    setExceptionLate(exception.late_after ?? '')
    setExceptionDeadline(exception.absence_finalization_time ?? '')
    setExceptionReason(exception.reason)
    setFormError('')
    setSuccess('')
  }

  const clearEventForm = () => {
    setSelectedEventId(null)
    setEventName('')
    setEventType('HOLIDAY')
    setEventStart(today())
    setEventEnd(today())
    setEventStartTime('08:00')
    setEventEndTime('16:00')
    setEventLateAfter('08:15')
    setEventAbsenceDeadline('10:00')
    setEventDepartment('')
    setEventDescription('')
  }

  const clearExceptionForm = () => {
    setSelectedExceptionId(null)
    setExceptionStaffId('')
    setExceptionDate(today())
    setExceptionWorking(true)
    setExceptionStart('')
    setExceptionEnd('')
    setExceptionLate('')
    setExceptionDeadline('')
    setExceptionReason('')
  }

  const editEvent = (calendarEvent: SchoolCalendarEvent) => {
    setSelectedEventId(calendarEvent.id)
    setEventName(calendarEvent.name)
    setEventType(calendarEvent.event_type)
    setEventStart(calendarEvent.start_date)
    setEventEnd(calendarEvent.end_date)
    setEventStartTime(calendarEvent.start_time ?? '')
    setEventEndTime(calendarEvent.end_time ?? '')
    setEventLateAfter(calendarEvent.late_after ?? '')
    setEventAbsenceDeadline(calendarEvent.absence_finalization_time ?? '')
    setEventDepartment(calendarEvent.department ?? '')
    setEventDescription(calendarEvent.description)
    setFormError('')
    setSuccess('')
  }

  const updateDay = (weekday: number, patch: Partial<ScheduleDay>) => {
    setDays((current) => current.map((day) => {
      if (day.weekday !== weekday) return day
      const next = { ...day, ...patch }
      if (patch.is_working_day === false) {
        next.start_time = null
        next.end_time = null
        next.late_after = null
        next.absence_finalization_time = null
      } else if (patch.is_working_day === true) {
        next.start_time = '08:00'
        next.end_time = '16:00'
        next.late_after = '08:15'
        next.absence_finalization_time = '10:00'
      }
      return next
    }))
  }

  const renderDays = () => (
    <div className="schedule-days">
      {days.map((day) => (
        <fieldset className="schedule-day" key={day.weekday}>
          <legend>{weekdays[day.weekday]}</legend>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={day.is_working_day}
              onChange={(event) => updateDay(day.weekday, { is_working_day: event.target.checked })}
            />
            Working day
          </label>
          {day.is_working_day && (
            <div className="schedule-day__times">
              <label>Start<input type="time" value={day.start_time ?? ''} onChange={(event) => updateDay(day.weekday, { start_time: event.target.value })} /></label>
              <label>End<input type="time" value={day.end_time ?? ''} onChange={(event) => updateDay(day.weekday, { end_time: event.target.value })} /></label>
              <label>Late after<input type="time" value={day.late_after ?? ''} onChange={(event) => updateDay(day.weekday, { late_after: event.target.value })} /></label>
              <label>Absence deadline<input type="time" value={day.absence_finalization_time ?? ''} onChange={(event) => updateDay(day.weekday, { absence_finalization_time: event.target.value })} /></label>
            </div>
          )}
        </fieldset>
      ))}
    </div>
  )

  const tabs: Array<{ id: ScheduleTab; title: string }> = [
    { id: 'schedules', title: 'Schedules' },
    { id: 'assignments', title: 'Assignments' },
    { id: 'exceptions', title: 'Exceptions' },
    { id: 'calendar', title: 'School calendar' },
  ]

  return (
    <main className="dashboard-card">
      <header className="page-header">
        <div><p className="eyebrow">Administration</p><h1>Schedules</h1></div>
        {!canManage && <span className="read-only-badge">Read only</span>}
      </header>
      <div className="module-tabs" role="tablist" aria-label="Scheduling sections">
        {tabs.map((item) => (
          <button
            type="button"
            role="tab"
            aria-selected={tab === item.id}
            className={tab === item.id ? 'module-tab module-tab--active' : 'module-tab'}
            key={item.id}
            onClick={() => { setTab(item.id); setFormError(''); setSuccess('') }}
          >
            {item.title}
          </button>
        ))}
      </div>
      {success && <div className="feedback feedback--success" role="status">{success}</div>}
      {error && <div className="feedback feedback--error" role="alert">{error}</div>}
      {loading ? <div className="state-card">Loading scheduling data…</div> : (
        <>
          {tab === 'schedules' && (
            <section className="module-section">
              <div className="ap-list" aria-label="Work schedules">
                {schedules.length === 0 && <div className="state-card">No schedules have been configured.</div>}
                {schedules.map((schedule) => (
                  <article className="ap-item" key={schedule.id}>
                    <div className="ap-item__head">
                      <strong>{schedule.name}</strong>
                      <span className={`status-pill ${schedule.is_active ? 'status-pill--active' : 'status-pill--inactive'}`}>
                        {schedule.is_active ? 'Active' : 'Inactive'}
                      </span>
                    </div>
                    {schedule.description && <p className="ap-item__meta">{schedule.description}</p>}
                    <div className="ap-item__meta">
                      {schedule.versions.map((version) => (
                        <div key={version.id}>
                          Version {version.version_number}: {version.effective_from} to {version.effective_to ?? 'open-ended'}
                        </div>
                      ))}
                    </div>
                    {canManage && (
                      <div className="ap-item__actions">
                        <button type="button" className="secondary-button" onClick={() => setVersionScheduleId(schedule.id)}>
                          Add version
                        </button>
                        <button type="button" className="secondary-button" onClick={() => void toggleSchedule(schedule)}>
                          {schedule.is_active ? 'Deactivate' : 'Activate'}
                        </button>
                      </div>
                    )}
                  </article>
                ))}
              </div>
              {canManage && (
                <>
                  <form className="config-form" onSubmit={(event) => void submitSchedule(event)}>
                    <h2>Create a work schedule</h2>
                    <label>Schedule name<input value={scheduleName} onChange={(event) => setScheduleName(event.target.value)} required maxLength={120} /></label>
                    <label>Description<textarea value={scheduleDescription} onChange={(event) => setScheduleDescription(event.target.value)} /></label>
                    <label>Effective from<input type="date" value={effectiveFrom} onChange={(event) => setEffectiveFrom(event.target.value)} required /></label>
                    {renderDays()}
                    {formError && <div className="feedback feedback--error" role="alert">{formError}</div>}
                    <button className="primary-button" disabled={saving}>{saving ? 'Saving…' : 'Create schedule'}</button>
                  </form>
                  {schedules.length > 0 && (
                    <form className="config-form" onSubmit={(event) => void submitVersion(event)}>
                      <h2>Add schedule version</h2>
                      <label>Schedule
                        <select value={versionScheduleId} onChange={(event) => setVersionScheduleId(event.target.value)} required>
                          {schedules.map((schedule) => <option key={schedule.id} value={schedule.id}>{schedule.name}</option>)}
                        </select>
                      </label>
                      <label>Effective from<input type="date" value={versionFrom} onChange={(event) => setVersionFrom(event.target.value)} required /></label>
                      {renderDays()}
                      {formError && <div className="feedback feedback--error" role="alert">{formError}</div>}
                      <button className="primary-button" disabled={saving || !versionScheduleId}>{saving ? 'Saving…' : 'Add version'}</button>
                    </form>
                  )}
                </>
              )}
            </section>
          )}

          {tab === 'assignments' && (
            <section className="module-section">
              <div className="ap-list" aria-label="Schedule assignments">
                {assignments.length === 0 && <div className="state-card">No schedules have been assigned.</div>}
                {assignments.map((assignment) => (
                  <article className="ap-item" key={assignment.id}>
                    <div className="ap-item__head"><strong>{assignment.work_schedule_name}</strong></div>
                    <p className="ap-item__meta">
                      {assignment.is_school_default ? 'School default' : assignment.department_name ?? assignment.staff_name}
                      {' · '}{assignment.effective_from} to {assignment.effective_to ?? 'open-ended'}
                    </p>
                    {canManage && !assignment.effective_to && (
                      <div className="button-row">
                        <label>End date
                          <input
                            type="date"
                            aria-label={`End date for ${assignment.work_schedule_name}`}
                            min={assignment.effective_from}
                            value={assignmentEndDates[assignment.id] ?? today()}
                            onChange={(event) => setAssignmentEndDates((current) => ({ ...current, [assignment.id]: event.target.value }))}
                          />
                        </label>
                        <button type="button" className="secondary-button" onClick={() => void closeAssignment(assignment)}>Save end date</button>
                      </div>
                    )}
                  </article>
                ))}
              </div>
              {canManage && schedules.length > 0 && (
                <form className="config-form" onSubmit={(event) => void submitAssignment(event)}>
                  <h2>Assign a schedule</h2>
                  <label>Schedule<select value={assignmentScheduleId} onChange={(event) => setAssignmentScheduleId(event.target.value)} required>
                    {schedules.filter((schedule) => schedule.is_active).map((schedule) => <option key={schedule.id} value={schedule.id}>{schedule.name}</option>)}
                  </select></label>
                  <label>Assignment scope<select value={assignmentScope} onChange={(event) => { setAssignmentScope(event.target.value as AssignmentScope); setAssignmentTarget('') }}>
                    <option value="school">School default</option><option value="department">Department</option><option value="staff">Staff member</option>
                  </select></label>
                  {assignmentScope !== 'school' && (
                    <label>{assignmentScope === 'department' ? 'Department' : 'Staff member'}
                      <select value={assignmentTarget} onChange={(event) => setAssignmentTarget(event.target.value)} required>
                        <option value="">Select…</option>
                        {assignmentScope === 'department'
                          ? departments.filter((department) => department.is_active).map((department) => <option key={department.id} value={department.id}>{department.name}</option>)
                          : staff.map((member) => <option key={member.id} value={member.id}>{member.first_name} {member.last_name} ({member.employee_number})</option>)}
                      </select>
                    </label>
                  )}
                  <label>Effective from<input type="date" value={assignmentFrom} onChange={(event) => setAssignmentFrom(event.target.value)} required /></label>
                  {formError && <div className="feedback feedback--error" role="alert">{formError}</div>}
                  <button className="primary-button" disabled={saving || (assignmentScope !== 'school' && !assignmentTarget)}>{saving ? 'Saving…' : 'Assign schedule'}</button>
                </form>
              )}
            </section>
          )}

          {tab === 'exceptions' && (
            <section className="module-section">
              <div className="ap-list" aria-label="Schedule exceptions">
                {exceptions.length === 0 && <div className="state-card">No date-specific exceptions are configured.</div>}
                {exceptions.map((exception) => (
                  <article className="ap-item" key={exception.id}>
                    <div className="ap-item__head"><strong>{exception.staff_name} · {exception.exception_date}</strong></div>
                    <p className="ap-item__meta">
                      {exception.is_working_day ? `Working day${exception.start_time ? ` · ${exception.start_time}–${exception.end_time}` : ''}` : 'Non-working day'}
                      {exception.reason && ` · ${exception.reason}`}
                    </p>
                    {canManage && <button type="button" className="secondary-button" onClick={() => editException(exception)}>Edit exception</button>}
                  </article>
                ))}
              </div>
              {canManage && (
                <form className="config-form" onSubmit={(event) => void submitException(event)}>
                  <h2>{selectedExceptionId ? 'Edit staff date exception' : 'Add staff date exception'}</h2>
                  <label>Staff member<select value={exceptionStaffId} onChange={(event) => setExceptionStaffId(event.target.value)} required>
                    <option value="">Select…</option>
                    {staff.map((member) => <option key={member.id} value={member.id}>{member.first_name} {member.last_name} ({member.employee_number})</option>)}
                  </select></label>
                  <label>Date<input type="date" value={exceptionDate} onChange={(event) => setExceptionDate(event.target.value)} required /></label>
                  <label className="checkbox-label"><input type="checkbox" checked={exceptionWorking} onChange={(event) => setExceptionWorking(event.target.checked)} />Working day</label>
                  {exceptionWorking && <div className="field-row field-row--split">
                    <label>Start<input type="time" value={exceptionStart} onChange={(event) => setExceptionStart(event.target.value)} /></label>
                    <label>End<input type="time" value={exceptionEnd} onChange={(event) => setExceptionEnd(event.target.value)} /></label>
                    <label>Late after<input type="time" value={exceptionLate} onChange={(event) => setExceptionLate(event.target.value)} /></label>
                    <label>Absence deadline<input type="time" value={exceptionDeadline} onChange={(event) => setExceptionDeadline(event.target.value)} /></label>
                  </div>}
                  <label>Reason<input value={exceptionReason} onChange={(event) => setExceptionReason(event.target.value)} maxLength={255} /></label>
                  {formError && <div className="feedback feedback--error" role="alert">{formError}</div>}
                  <div className="button-row">
                    <button className="primary-button" disabled={saving || !exceptionStaffId}>{saving ? 'Saving…' : selectedExceptionId ? 'Save exception' : 'Create exception'}</button>
                    {selectedExceptionId && <button type="button" className="secondary-button" onClick={clearExceptionForm}>Cancel edit</button>}
                  </div>
                </form>
              )}
            </section>
          )}

          {tab === 'calendar' && (
            <section className="module-section">
              <div className="ap-list" aria-label="School calendar events">
                {events.length === 0 && <div className="state-card">No school calendar events are configured.</div>}
                {events.map((calendarEvent) => (
                  <article className="ap-item" key={calendarEvent.id}>
                    <div className="ap-item__head"><strong>{calendarEvent.name}</strong><span className="read-only-badge">{calendarEvent.event_type.replaceAll('_', ' ')}</span></div>
                    <p className="ap-item__meta">{calendarEvent.start_date} to {calendarEvent.end_date}{calendarEvent.department_name ? ` · ${calendarEvent.department_name}` : ' · Whole school'}</p>
                    {calendarEvent.event_type === 'EXCEPTIONAL_WORKING_DAY' && <p className="ap-item__meta">{calendarEvent.start_time}–{calendarEvent.end_time} · Late after {calendarEvent.late_after} · Absence deadline {calendarEvent.absence_finalization_time}</p>}
                    {calendarEvent.description && <p className="ap-item__meta">{calendarEvent.description}</p>}
                    {canManage && <button type="button" className="secondary-button" onClick={() => editEvent(calendarEvent)}>Edit event</button>}
                  </article>
                ))}
              </div>
              {canManage && (
                <form className="config-form" onSubmit={(event) => void submitEvent(event)}>
                  <h2>{selectedEventId ? 'Edit school calendar event' : 'Add school calendar event'}</h2>
                  <label>Event name<input value={eventName} onChange={(event) => setEventName(event.target.value)} required maxLength={160} /></label>
                  <label>Event type<select value={eventType} onChange={(event) => setEventType(event.target.value as SchoolCalendarEvent['event_type'])}>
                    <option value="HOLIDAY">Holiday</option><option value="CLOSURE">Closure</option><option value="EXCEPTIONAL_WORKING_DAY">Exceptional working day</option>
                  </select></label>
                  <div className="field-row field-row--split">
                    <label>Start date<input type="date" value={eventStart} onChange={(event) => setEventStart(event.target.value)} required /></label>
                    <label>End date<input type="date" value={eventEnd} onChange={(event) => setEventEnd(event.target.value)} required /></label>
                  </div>
                  {eventType === 'EXCEPTIONAL_WORKING_DAY' && <div className="field-row field-row--split">
                    <label>Start time<input type="time" value={eventStartTime} onChange={(event) => setEventStartTime(event.target.value)} required /></label>
                    <label>End time<input type="time" value={eventEndTime} onChange={(event) => setEventEndTime(event.target.value)} required /></label>
                    <label>Late after<input type="time" value={eventLateAfter} onChange={(event) => setEventLateAfter(event.target.value)} required /></label>
                    <label>Absence deadline<input type="time" value={eventAbsenceDeadline} onChange={(event) => setEventAbsenceDeadline(event.target.value)} required /></label>
                  </div>}
                  <label>Department (optional)<select value={eventDepartment} onChange={(event) => setEventDepartment(event.target.value)}>
                    <option value="">Whole school</option>
                    {departments.filter((department) => department.is_active).map((department) => <option key={department.id} value={department.id}>{department.name}</option>)}
                  </select></label>
                  <label>Description<textarea value={eventDescription} onChange={(event) => setEventDescription(event.target.value)} /></label>
                  {formError && <div className="feedback feedback--error" role="alert">{formError}</div>}
                  <div className="button-row">
                    <button className="primary-button" disabled={saving}>{saving ? 'Saving…' : selectedEventId ? 'Save calendar event' : 'Create calendar event'}</button>
                    {selectedEventId && <button type="button" className="secondary-button" onClick={clearEventForm}>Cancel edit</button>}
                  </div>
                </form>
              )}
            </section>
          )}
        </>
      )}
    </main>
  )
}
