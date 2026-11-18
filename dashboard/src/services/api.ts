const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000/api/v1').replace(/\/$/, '')

export type UserRole = 'SCHOOL_ADMIN' | 'ATTENDANCE_MANAGER' | 'STAFF'
export type AuthUser = { id: string; username: string; role: UserRole; school_code: string }
export type TokenResponse = {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
  refresh_expires_at: string
  device_status: string
  password_change_required: boolean
  session_status: string
  user: AuthUser
}

export type HealthResponse = { status: string; version: string }
export type Department = {
  id: string
  name: string
  description: string
  is_active: boolean
  created_at?: string
  updated_at?: string
}
export type DeviceKey = {
  algorithm: string
  fingerprint: string
  key_version: number
  status: string
  created_at: string
  retired_at: string | null
}
export type RegisteredDevice = {
  id: string
  staff_id: string
  employee_number: string
  staff_name: string
  platform: 'ANDROID' | 'IOS'
  device_name: string
  status: 'PENDING' | 'ACTIVE' | 'REVOKED' | 'REJECTED'
  enrolled_at: string
  created_at: string
  revoked_at: string | null
  last_seen_at: string | null
  keys: DeviceKey[]
  history?: Array<{ event_type: string; created_at: string; metadata: Record<string, unknown> }>
  audit_history?: Array<{
    action: string
    actor_user_id: string | null
    created_at: string
    after_data: Record<string, unknown>
  }>
}
export type AttendanceZone = {
  id: string
  name: string
  latitude: number | string
  longitude: number | string
  radius_meters: number
  is_active: boolean
  created_at?: string
  updated_at?: string
}
export type AccessPoint = {
  id: string
  attendance_zone: string
  bssid: string
  name: string
  location_notes: string
  is_active: boolean
  created_at?: string
  updated_at?: string
}
export type StaffMember = {
  id: string
  user_id: string
  username: string
  email: string
  phone: string
  role: 'STAFF'
  is_active: boolean
  must_change_password: boolean
  employee_number: string
  first_name: string
  last_name: string
  department: string | null
  job_title: string
  employment_status: 'ACTIVE' | 'ON_LEAVE' | 'TERMINATED'
  date_joined: string
  date_left: string | null
  created_at?: string
  updated_at?: string
}
export type ScheduleDay = {
  weekday: number
  is_working_day: boolean
  start_time: string | null
  end_time: string | null
  late_after: string | null
  absence_finalization_time: string | null
}
export type ScheduleVersion = {
  id: string
  version_number: number
  effective_from: string
  effective_to: string | null
  is_active: boolean
  days: ScheduleDay[]
  created_at: string
}
export type WorkSchedule = {
  id: string
  name: string
  description: string
  is_active: boolean
  versions: ScheduleVersion[]
  created_at: string
  updated_at: string
}
export type ScheduleAssignment = {
  id: string
  work_schedule: string
  work_schedule_name: string
  department: string | null
  department_name: string | null
  staff_profile: string | null
  staff_name: string | null
  is_school_default: boolean
  effective_from: string
  effective_to: string | null
}
export type ScheduleException = {
  id: string
  staff_profile: string
  staff_name: string
  exception_date: string
  is_working_day: boolean
  start_time: string | null
  end_time: string | null
  late_after: string | null
  absence_finalization_time: string | null
  reason: string
}
export type SchoolCalendarEvent = {
  id: string
  name: string
  event_type: 'HOLIDAY' | 'CLOSURE' | 'EXCEPTIONAL_WORKING_DAY'
  start_date: string
  end_date: string
  start_time: string | null
  end_time: string | null
  late_after: string | null
  absence_finalization_time: string | null
  department: string | null
  department_name: string | null
  description: string
  created_at: string
  updated_at: string
}
export type LeaveType = {
  id: string
  name: string
  description: string
  is_active: boolean
}
export type LeaveRecord = {
  id: string
  staff_profile: string
  staff_name: string
  leave_type: string
  leave_type_name: string
  start_date: string
  end_date: string
  reason: string
  status: 'PENDING' | 'APPROVED' | 'REJECTED' | 'CANCELLED'
  reviewed_by: string | null
  reviewed_by_name: string | null
  reviewed_at: string | null
  review_comment: string
  cancelled_by: string | null
  cancelled_by_name: string | null
  cancelled_at: string | null
  cancellation_reason: string
  created_at: string
  updated_at: string
}

let accessToken: string | null = null
let refreshToken: string | null = null
let refreshPromise: Promise<TokenResponse> | null = null

export function setTokens(tokens: Pick<TokenResponse, 'access_token' | 'refresh_token'> & Partial<Pick<TokenResponse, 'refresh_expires_at' | 'user'>>) {
  accessToken = tokens.access_token
  refreshToken = tokens.refresh_token
  try {
    const key = 'schoolAttendanceSession'
    const raw = window.sessionStorage.getItem(key)
    const stored = raw ? JSON.parse(raw) as Record<string, unknown> : {}
    stored.refresh_token = tokens.refresh_token
    if (tokens.refresh_expires_at) stored.refresh_expires_at = tokens.refresh_expires_at
    if (tokens.user) stored.user = tokens.user
    window.sessionStorage.setItem(key, JSON.stringify(stored))
  } catch {
    // Session persistence is optional; in-memory authentication still works.
  }
}

export function clearTokens() {
  accessToken = null
  refreshToken = null
  refreshPromise = null
}

export function getRefreshToken() {
  return refreshToken
}

export async function login(payload: { school_code: string; username: string; password: string }): Promise<TokenResponse> {
  return fetchJson<TokenResponse>('/auth/login/', { method: 'POST', body: JSON.stringify(payload) }, false)
}

export async function refreshSession(): Promise<TokenResponse | null> {
  if (!refreshToken) return null
  if (refreshPromise) return refreshPromise
  const currentRefreshToken = refreshToken
  refreshPromise = fetchJson<TokenResponse>(
    '/auth/refresh/',
    { method: 'POST', body: JSON.stringify({ refresh_token: currentRefreshToken }) },
    false,
  ).then((tokens) => {
    setTokens(tokens)
    return tokens
  }).finally(() => {
    refreshPromise = null
  })
  return refreshPromise
}

export async function logout(): Promise<void> {
  try {
    if (accessToken) {
      await fetchJson<void>('/auth/logout/', { method: 'POST' })
    }
  } catch {
    // Local session invalidation must succeed even when the server is unreachable.
  } finally {
    clearTokens()
  }
}

export async function fetchJson<T>(path: string, options: RequestInit = {}, allowRefresh = true): Promise<T> {
  const performRequest = async (): Promise<Response> => {
    const headers = new Headers(options.headers ?? {})
    if (options.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
    if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`)
    try {
      return await fetch(`${apiBaseUrl}${path}`, { ...options, headers })
    } catch (error) {
      throw new Error('The backend API could not be reached.', { cause: error })
    }
  }

  const isAuthOnly = path.startsWith('/auth/login/') || path.startsWith('/auth/refresh/') || path.startsWith('/auth/logout/')
  let response = await performRequest()
  if (response.status === 401 && allowRefresh && !isAuthOnly && refreshToken) {
    try {
      await refreshSession()
      response = await performRequest()
    } catch {
      clearTokens()
      throw new Error('Your session has expired. Please sign in again.')
    }
  }

  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    const detail = payload && typeof payload === 'object'
      ? (
          (typeof (payload as { detail?: unknown }).detail === 'string' && (payload as { detail: string }).detail) ||
          Object.values(payload as Record<string, unknown>).flatMap((entry) =>
            Array.isArray(entry) ? entry.map((item) => String(item)) : [String(entry)],
          ).join(', ')
        )
      : ''
    throw new Error(detail || `The backend API returned HTTP ${response.status}.`)
  }
  if (response.status === 204) return undefined as T
  return await response.json() as T
}

export async function getHealth(): Promise<HealthResponse> { return fetchJson('/health/') }
export async function getAttendanceZones(): Promise<AttendanceZone[]> { return fetchJson('/locations/zones/') }
export async function createAttendanceZone(payload: Record<string, string | number | boolean>): Promise<AttendanceZone> {
  return fetchJson('/locations/zones/', { method: 'POST', body: JSON.stringify(payload) })
}
export async function patchAttendanceZone(zoneId: string, payload: Record<string, string | number | boolean>): Promise<AttendanceZone> {
  return fetchJson(`/locations/zones/${zoneId}/`, { method: 'PATCH', body: JSON.stringify(payload) })
}
export async function getAccessPoints(): Promise<AccessPoint[]> { return fetchJson('/locations/access-points/') }
export async function createAccessPoint(payload: Record<string, string>): Promise<AccessPoint> {
  return fetchJson('/locations/access-points/', { method: 'POST', body: JSON.stringify(payload) })
}
export async function patchAccessPoint(accessPointId: string, payload: Record<string, string | boolean>): Promise<AccessPoint> {
  return fetchJson(`/locations/access-points/${accessPointId}/`, { method: 'PATCH', body: JSON.stringify(payload) })
}
export async function getStaff(): Promise<StaffMember[]> { return fetchJson('/staff/') }
export async function getStaffMember(staffId: string): Promise<StaffMember> { return fetchJson(`/staff/${staffId}/`) }
export async function createStaff(payload: Record<string, unknown>): Promise<StaffMember> {
  return fetchJson('/staff/', { method: 'POST', body: JSON.stringify(payload) })
}
export async function updateStaff(staffId: string, payload: Record<string, unknown>): Promise<StaffMember> {
  return fetchJson(`/staff/${staffId}/`, { method: 'PATCH', body: JSON.stringify(payload) })
}
export async function getDepartments(): Promise<Department[]> {
  return fetchJson('/departments/')
}
export async function createDepartment(payload: Pick<Department, 'name' | 'description'>): Promise<Department> {
  return fetchJson('/departments/', { method: 'POST', body: JSON.stringify(payload) })
}
export async function updateDepartment(
  departmentId: string,
  payload: Partial<Pick<Department, 'name' | 'description' | 'is_active'>>,
): Promise<Department> {
  return fetchJson(`/departments/${departmentId}/`, { method: 'PATCH', body: JSON.stringify(payload) })
}
export async function getDevices(): Promise<RegisteredDevice[]> {
  return fetchJson('/devices/')
}
export async function getDevice(deviceId: string): Promise<RegisteredDevice> {
  return fetchJson(`/devices/${deviceId}/`)
}
export async function approveDevice(deviceId: string): Promise<RegisteredDevice> {
  return fetchJson(`/devices/${deviceId}/approve/`, { method: 'POST', body: JSON.stringify({}) })
}
export async function rejectDevice(deviceId: string, reason: string): Promise<RegisteredDevice> {
  return fetchJson(`/devices/${deviceId}/reject/`, { method: 'POST', body: JSON.stringify({ reason }) })
}
export async function revokeDevice(deviceId: string, reason: string): Promise<RegisteredDevice> {
  return fetchJson(`/devices/${deviceId}/revoke/`, { method: 'POST', body: JSON.stringify({ reason }) })
}
export async function getSchedules(): Promise<WorkSchedule[]> { return fetchJson('/schedules/') }
export async function createSchedule(payload: {
  name: string
  description: string
  effective_from: string
  days: ScheduleDay[]
}): Promise<WorkSchedule> {
  return fetchJson('/schedules/', { method: 'POST', body: JSON.stringify(payload) })
}
export async function updateSchedule(
  scheduleId: string,
  payload: Partial<Pick<WorkSchedule, 'name' | 'description' | 'is_active'>>,
): Promise<WorkSchedule> {
  return fetchJson(`/schedules/${scheduleId}/`, { method: 'PATCH', body: JSON.stringify(payload) })
}
export async function createScheduleVersion(
  scheduleId: string,
  payload: { effective_from: string; days: ScheduleDay[] },
): Promise<WorkSchedule> {
  return fetchJson(`/schedules/${scheduleId}/versions/`, { method: 'POST', body: JSON.stringify(payload) })
}
export async function getScheduleAssignments(): Promise<ScheduleAssignment[]> {
  return fetchJson('/schedule-assignments/')
}
export async function createScheduleAssignment(payload: {
  work_schedule: string
  department?: string
  staff_profile?: string
  is_school_default: boolean
  effective_from: string
}): Promise<ScheduleAssignment> {
  return fetchJson('/schedule-assignments/', { method: 'POST', body: JSON.stringify(payload) })
}
export async function endScheduleAssignment(
  assignmentId: string,
  effective_to: string,
): Promise<ScheduleAssignment> {
  return fetchJson(`/schedule-assignments/${assignmentId}/`, {
    method: 'PATCH',
    body: JSON.stringify({ effective_to }),
  })
}
export async function getScheduleExceptions(): Promise<ScheduleException[]> {
  return fetchJson('/schedule-exceptions/')
}
export async function createScheduleException(payload: {
  staff_profile: string
  exception_date: string
  is_working_day: boolean
  start_time: string | null
  end_time: string | null
  late_after: string | null
  absence_finalization_time: string | null
  reason: string
}): Promise<ScheduleException> {
  return fetchJson('/schedule-exceptions/', { method: 'POST', body: JSON.stringify(payload) })
}
export async function updateScheduleException(
  exceptionId: string,
  payload: Partial<Omit<ScheduleException, 'id' | 'staff_name'>>,
): Promise<ScheduleException> {
  return fetchJson(`/schedule-exceptions/${exceptionId}/`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}
export async function getCalendarEvents(): Promise<SchoolCalendarEvent[]> {
  return fetchJson('/calendar-events/')
}
export async function createCalendarEvent(payload: {
  name: string
  event_type: SchoolCalendarEvent['event_type']
  start_date: string
  end_date: string
  start_time: string | null
  end_time: string | null
  late_after: string | null
  absence_finalization_time: string | null
  department?: string
  description: string
}): Promise<SchoolCalendarEvent> {
  return fetchJson('/calendar-events/', { method: 'POST', body: JSON.stringify(payload) })
}
export async function updateCalendarEvent(
  eventId: string,
  payload: Partial<Omit<SchoolCalendarEvent, 'id' | 'created_at' | 'updated_at' | 'department_name'>>,
): Promise<SchoolCalendarEvent> {
  return fetchJson(`/calendar-events/${eventId}/`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}
export async function getLeaveTypes(): Promise<LeaveType[]> { return fetchJson('/leave-types/') }
export async function createLeaveType(payload: Pick<LeaveType, 'name' | 'description'>): Promise<LeaveType> {
  return fetchJson('/leave-types/', { method: 'POST', body: JSON.stringify(payload) })
}
export async function updateLeaveType(
  leaveTypeId: string,
  payload: Partial<Pick<LeaveType, 'name' | 'description' | 'is_active'>>,
): Promise<LeaveType> {
  return fetchJson(`/leave-types/${leaveTypeId}/`, { method: 'PATCH', body: JSON.stringify(payload) })
}
export async function getLeaveRecords(): Promise<LeaveRecord[]> { return fetchJson('/leave-records/') }
export type AttendanceRegisterRow = {
  attendance_date: string
  staff_id: string
  employee_number: string
  staff_name: string
  department: string | null
  status: string
  check_in: string | null
  check_out: string | null
}
export async function getAttendanceRegister(date: string): Promise<AttendanceRegisterRow[]> {
  return fetchJson(`/attendance/register/?date=${encodeURIComponent(date)}`)
}
export type Overview = {
  date: string
  school: { id: string; name: string; school_code: string; timezone: string; status: string }
  staff: { total: number; by_department: Array<{ department__name: string; count: number }> }
  attendance: Record<string, number>
  devices: { active: number; pending: number; revoked: number }
  leave: { pending: number }
}
export type AttendanceReport = {
  date_from: string
  date_to: string
  summary: Array<{ status: string; count: number }>
  by_staff: Array<{ staff_profile__employee_number: string; staff_profile__first_name: string; staff_profile__last_name: string; staff_profile__department__name: string | null; records: number; present: number; late: number; absent: number; on_leave: number; incomplete: number }>
}
export type AuditLog = {
  id: string
  action: string
  entity_type: string
  entity_id: string
  actor_user_id: string | null
  before_data: Record<string, unknown> | null
  after_data: Record<string, unknown> | null
  reason: string
  created_at: string
}
export type AuditLogResponse = { count: number; page: number; page_size: number; total_pages: number; results: AuditLog[] }
export type SchoolSettings = { id: string; school_code: string; name: string; email: string; phone: string; address: string; timezone: string; status: string }

export async function getOverview(): Promise<Overview> { return fetchJson('/overview/') }
export async function getAttendanceReport(dateFrom: string, dateTo: string): Promise<AttendanceReport> {
  return fetchJson(`/reports/attendance/?date_from=${encodeURIComponent(dateFrom)}&date_to=${encodeURIComponent(dateTo)}`)
}
export async function getAuditLogs(params: { page?: number; pageSize?: number; search?: string; action?: string }): Promise<AuditLogResponse> {
  const query = new URLSearchParams()
  if (params.page) query.set('page', String(params.page))
  if (params.pageSize) query.set('page_size', String(params.pageSize))
  if (params.search) query.set('search', params.search)
  if (params.action) query.set('action', params.action)
  return fetchJson(`/audit-logs/?${query.toString()}`)
}
export async function getSchoolSettings(): Promise<SchoolSettings> { return fetchJson('/school-settings/') }
export async function patchSchoolSettings(payload: Partial<Pick<SchoolSettings, 'name' | 'email' | 'phone' | 'address' | 'timezone'>>): Promise<SchoolSettings> {
  return fetchJson('/school-settings/', { method: 'PATCH', body: JSON.stringify(payload) })
}
export async function reviewLeaveRecord(
  leaveId: string,
  payload: { status: 'APPROVED' | 'REJECTED'; review_comment: string },
): Promise<LeaveRecord> {
  return fetchJson(`/leave-records/${leaveId}/review/`, { method: 'POST', body: JSON.stringify(payload) })
}
export async function cancelLeaveRecord(leaveId: string, cancellation_reason: string): Promise<LeaveRecord> {
  return fetchJson(`/leave-records/${leaveId}/cancel/`, {
    method: 'POST',
    body: JSON.stringify({ cancellation_reason }),
  })
}
