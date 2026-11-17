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
  session_status: string
  user: AuthUser
}

export type HealthResponse = { status: string; version: string }
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
