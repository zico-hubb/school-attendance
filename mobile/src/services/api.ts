const apiBaseUrl = (
  import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000/api/v1'
).replace(/\/$/, '')

export type TokenResponse = {
  access_token: string
  refresh_token: string
  expires_in: number
  refresh_expires_at: string
  device_status: string
  password_change_required: boolean
  session_status: string
  user: { id: string; username: string; role: 'STAFF'; school_code: string }
}

export type HealthResponse = { status: string; version: string }

let accessToken: string | null = null

export function setAccessToken(token: string | null) {
  accessToken = token
}

async function request<T>(path: string, init: RequestInit = {}, authenticated = true): Promise<T> {
  const headers = new Headers(init.headers)
  headers.set('Accept', 'application/json')
  if (init.body) headers.set('Content-Type', 'application/json')
  if (authenticated && accessToken) headers.set('Authorization', `Bearer ${accessToken}`)
  let response: Response
  try {
    response = await fetch(`${apiBaseUrl}${path}`, { ...init, headers })
  } catch (error) {
    throw new Error('The backend API could not be reached.', { cause: error })
  }
  if (response.status === 204) return undefined as T
  const body = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = typeof body.detail === 'string' ? body.detail : body.reason_code
    throw new Error(detail || `Request failed with HTTP ${response.status}.`)
  }
  return body as T
}

export const getHealth = () => request<HealthResponse>('/health/', {}, false)
export const login = (payload: { school_code: string; username: string; password: string }) =>
  request<TokenResponse>('/auth/login/', { method: 'POST', body: JSON.stringify(payload) }, false)
export const changePassword = (payload: { current_password: string; new_password: string; new_password_confirm: string }) =>
  request<{ detail: string }>('/auth/password/change/', { method: 'POST', body: JSON.stringify(payload) })
export const getEnrollmentChallenge = () =>
  request<{ challenge: string; expires_at: string; algorithm: string; signature_message: string }>('/devices/enrollment-challenge/', { method: 'POST', body: '{}' })
export const enrollDevice = (payload: Record<string, string>) =>
  request<Record<string, unknown>>('/devices/enroll/', { method: 'POST', body: JSON.stringify(payload) })
export const getDeviceChallenge = () =>
  request<{ challenge: string; expires_at: string; signature_message: string }>('/auth/device-challenge/', { method: 'POST', body: '{}' })
export const createDeviceSession = (payload: { challenge: string; signature: string }) =>
  request<TokenResponse>('/auth/device-session/', { method: 'POST', body: JSON.stringify(payload) })
export const refreshSession = (refreshToken: string) =>
  request<TokenResponse>('/auth/refresh/', { method: 'POST', body: JSON.stringify({ refresh_token: refreshToken }) }, false)
export const logout = () => request<void>('/auth/logout/', { method: 'POST', body: '{}' })

export type AttendanceStatus = {
  attendance_date: string
  status: string | null
  schedule: { source: string | null; is_working_day: boolean | null; start_time: string | null; end_time: string | null; late_after: string | null } | null
  leave: string | null
  checked_in: boolean
  checked_out: boolean
}
export type AttendanceHistory = { attendance_date: string; status: string; check_in: string | null; check_out: string | null; minutes_late: number }
export const getAttendanceStatus = () => request<AttendanceStatus>('/attendance/status/')
export const getAttendanceHistory = () => request<AttendanceHistory[]>('/attendance/history/')
export const getAttendanceChallenge = (attempt_type: 'CHECK_IN' | 'CHECK_OUT') =>
  request<{ challenge: string; expires_at: string; signature_message: string }>('/attendance/challenge/', { method: 'POST', body: JSON.stringify({ attempt_type }) })
export const submitAttendance = (payload: Record<string, unknown>) => {
  const type = payload.attempt_type === 'CHECK_IN' ? 'check-in' : 'check-out'
  return request<Record<string, unknown>>(`/attendance/${type}/`, { method: 'POST', body: JSON.stringify(payload) })
}
export type LeaveType = { id: string; name: string; description: string; is_active: boolean }
export type LeaveRecord = { id: string; leave_type_name: string; start_date: string; end_date: string; reason: string; status: string }
export const getLeaveTypes = () => request<LeaveType[]>('/leave-types/')
export const getLeaveRecords = () => request<LeaveRecord[]>('/leave-records/')
export const submitLeave = (payload: { leave_type: string; start_date: string; end_date: string; reason: string }) =>
  request<LeaveRecord>('/leave-records/', { method: 'POST', body: JSON.stringify(payload) })
