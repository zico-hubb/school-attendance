import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { App } from './App'

vi.mock('react-leaflet', () => ({
  MapContainer: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
  TileLayer: () => <div />,
  Circle: () => <div />,
  CircleMarker: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
  Popup: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
  useMapEvents: () => undefined,
}))

const adminTokens = (role: 'SCHOOL_ADMIN' | 'ATTENDANCE_MANAGER' | 'STAFF' = 'SCHOOL_ADMIN') => ({
  access_token: 'access-one',
  refresh_token: 'refresh-one',
  token_type: 'Bearer',
  expires_in: 900,
  refresh_expires_at: '2099-01-01T00:00:00Z',
  device_status: 'NOT_APPLICABLE',
  session_status: 'UNBOUND',
  user: {
    id: 'user-1',
    username: 'school.admin',
    role,
    school_code: 'NAIROBI-001',
  },
})

function jsonResponse(payload: unknown, status = 200): Response {
  return { ok: status >= 200 && status < 300, status, json: async () => payload } as Response
}

describe('administration authentication', () => {
  beforeEach(() => {
    window.localStorage.clear()
    window.sessionStorage.clear()
    window.history.pushState({}, '', '/login')
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it('shows login for unauthenticated users', () => {
    render(<App />)
    expect(screen.getByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
  })

  it('establishes a school admin session', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      if (input.toString().includes('/auth/login/')) return jsonResponse(adminTokens())
      return jsonResponse({ status: 'ok', version: '1' })
    }))
    render(<App />)
    fireEvent.change(screen.getByLabelText('School code'), { target: { value: 'NAIROBI-001' } })
    fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'school.admin' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'Password123!' } })
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Administration' })).toBeInTheDocument())
    expect(screen.getByText('SCHOOL_ADMIN')).toBeInTheDocument()
  })

  it('establishes an attendance manager session with restricted navigation', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      if (input.toString().includes('/auth/login/')) return jsonResponse(adminTokens('ATTENDANCE_MANAGER'))
      return jsonResponse({ status: 'ok', version: '1' })
    }))
    render(<App />)
    fireEvent.change(screen.getByLabelText('School code'), { target: { value: 'NAIROBI-001' } })
    fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'manager' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'Password123!' } })
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    await waitFor(() => expect(screen.getByText('ATTENDANCE_MANAGER')).toBeInTheDocument())
    expect(screen.queryByText('Staff Management')).not.toBeInTheDocument()
  })

  it('rejects staff accounts', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      if (input.toString().includes('/auth/login/')) return jsonResponse(adminTokens('STAFF'))
      if (input.toString().includes('/auth/logout/')) return jsonResponse({}, 204)
      return jsonResponse({})
    }))
    render(<App />)
    fireEvent.change(screen.getByLabelText('School code'), { target: { value: 'NAIROBI-001' } })
    fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'teacher' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'Password123!' } })
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    await waitFor(() => expect(screen.getByText(/Staff attendance is handled through the mobile application/i)).toBeInTheDocument())
  })

  it('shows generic invalid credential feedback', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ detail: 'Invalid school code, username, or password.' }, 401)))
    render(<App />)
    fireEvent.change(screen.getByLabelText('School code'), { target: { value: 'wrong' } })
    fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'wrong' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'wrong' } })
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Invalid school code, username, or password'))
  })

  it('restores an authenticated session from refresh state', async () => {
    window.history.pushState({}, '', '/')
    window.sessionStorage.setItem('schoolAttendanceSession', JSON.stringify({
      refresh_token: 'refresh-one',
      refresh_expires_at: '2099-01-01T00:00:00Z',
      user: adminTokens().user,
    }))
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      if (input.toString().includes('/auth/refresh/')) return jsonResponse(adminTokens())
      return jsonResponse({ status: 'ok', version: '1' })
    }))
    render(<App />)
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Administration' })).toBeInTheDocument())
  })

  it('failed refresh clears the session and returns to login', async () => {
    window.history.pushState({}, '', '/')
    window.sessionStorage.setItem('schoolAttendanceSession', JSON.stringify({
      refresh_token: 'bad-refresh',
      refresh_expires_at: '2099-01-01T00:00:00Z',
      user: adminTokens().user,
    }))
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      if (input.toString().includes('/auth/refresh/')) return jsonResponse({ detail: 'Invalid or expired refresh token.' }, 401)
      return jsonResponse({})
    }))
    render(<App />)
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Sign in' })).toBeInTheDocument())
    expect(window.sessionStorage.getItem('schoolAttendanceSession')).toBeNull()
  })

  it('logout clears local session state even after the network logout fails', async () => {
    window.history.pushState({}, '', '/')
    window.sessionStorage.setItem('schoolAttendanceSession', JSON.stringify({
      refresh_token: 'refresh-one',
      refresh_expires_at: '2099-01-01T00:00:00Z',
      user: adminTokens().user,
    }))
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      if (input.toString().includes('/auth/refresh/')) return jsonResponse(adminTokens())
      if (input.toString().includes('/auth/logout/')) return Promise.reject(new Error('offline'))
      return jsonResponse({ status: 'ok', version: '1' })
    }))
    render(<App />)
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Administration' })).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'Log out' }))
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Sign in' })).toBeInTheDocument())
    expect(window.sessionStorage.getItem('schoolAttendanceSession')).toBeNull()
  })

  it('loads staff and departments then submits staff creation', async () => {
    window.history.pushState({}, '', '/staff')
    window.sessionStorage.setItem('schoolAttendanceSession', JSON.stringify({
      refresh_token: 'refresh-one',
      refresh_expires_at: '2099-01-01T00:00:00Z',
      user: adminTokens().user,
    }))
    const staff = [{
      id: 'staff-1', user_id: 'user-2', username: 'jane.doe', email: 'jane@example.test',
      phone: '', role: 'STAFF', is_active: true, employee_number: 'EMP-1024',
      first_name: 'Jane', last_name: 'Doe', department: null, job_title: 'Teacher',
      employment_status: 'ACTIVE', date_joined: '2025-01-02', date_left: null,
    }]
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (input.toString().includes('/auth/refresh/')) return jsonResponse(adminTokens())
      if (input.toString().endsWith('/departments/')) return jsonResponse([])
      if (input.toString().endsWith('/staff/') && init?.method === 'POST') return jsonResponse({ ...staff[0], id: 'staff-new' }, 201)
      if (input.toString().endsWith('/staff/')) return jsonResponse(staff)
      return jsonResponse({ status: 'ok', version: '1' })
    }))
    render(<App />)
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Staff Management' })).toBeInTheDocument())
    await waitFor(() => expect(screen.getByText('Jane Doe')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'Create staff account' }))
    fireEvent.change(screen.getByLabelText('First name *'), { target: { value: 'Grace' } })
    fireEvent.change(screen.getByLabelText('Last name *'), { target: { value: 'Hopper' } })
    fireEvent.change(screen.getByLabelText('Username *'), { target: { value: 'grace.hopper' } })
    fireEvent.change(screen.getByLabelText('Temporary password *'), { target: { value: 'Grace-Temporary-93!' } })
    fireEvent.change(screen.getByLabelText('Employee number *'), { target: { value: 'EMP-1025' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create account' }))
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Share the temporary password privately'))
  })

  it('manages departments using the school-scoped API', async () => {
    window.history.pushState({}, '', '/departments')
    window.sessionStorage.setItem('schoolAttendanceSession', JSON.stringify({
      refresh_token: 'refresh-one',
      refresh_expires_at: '2099-01-01T00:00:00Z',
      user: adminTokens().user,
    }))
    const departments: Array<{ id: string; name: string; description: string; is_active: boolean }> = []
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (input.toString().includes('/auth/refresh/')) return jsonResponse(adminTokens())
      if (input.toString().endsWith('/departments/') && init?.method === 'POST') {
        const values = JSON.parse(String(init.body)) as { name: string; description: string }
        const department = { id: 'department-1', ...values, is_active: true }
        departments.push(department)
        return jsonResponse(department, 201)
      }
      if (input.toString().endsWith('/departments/')) return jsonResponse(departments)
      return jsonResponse({ status: 'ok', version: '1' })
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<App />)
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Departments' })).toBeInTheDocument())
    fireEvent.change(screen.getByLabelText('Department name'), { target: { value: 'Science' } })
    fireEvent.change(screen.getByLabelText('Description'), { target: { value: 'Science department' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create department' }))
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Department created'))
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/departments/'),
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('lets a school admin review and approve a pending device', async () => {
    window.history.pushState({}, '', '/devices')
    window.sessionStorage.setItem('schoolAttendanceSession', JSON.stringify({
      refresh_token: 'refresh-one',
      refresh_expires_at: '2099-01-01T00:00:00Z',
      user: adminTokens().user,
    }))
    const pendingDevice = {
      id: 'device-1',
      staff_id: 'staff-1',
      employee_number: 'EMP-100',
      staff_name: 'Ada Lovelace',
      platform: 'ANDROID',
      device_name: 'Staff phone',
      status: 'PENDING',
      enrolled_at: '2026-11-18T08:00:00Z',
      created_at: '2026-11-18T08:00:00Z',
      revoked_at: null,
      last_seen_at: null,
      keys: [],
    }
    let approved = false
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = input.toString()
      if (url.includes('/auth/refresh/')) return jsonResponse(adminTokens())
      if (url.endsWith('/devices/')) {
        return jsonResponse([approved ? { ...pendingDevice, status: 'ACTIVE' } : pendingDevice])
      }
      if (url.includes('/devices/device-1/approve/') && init?.method === 'POST') {
        approved = true
        return jsonResponse({ ...pendingDevice, status: 'ACTIVE', history: [], audit_history: [] })
      }
      if (url.includes('/devices/device-1/')) {
        return jsonResponse({ ...pendingDevice, history: [], audit_history: [] })
      }
      return jsonResponse({ status: 'ok', version: '1' })
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<App />)
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Device Management' })).toBeInTheDocument())
    expect(await screen.findByText('Ada Lovelace (EMP-100)')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'View details and history' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Approve device' }))
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Device approved successfully'))
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/devices/device-1/approve/'),
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('creates a weekly schedule through the scheduling API', async () => {
    window.history.pushState({}, '', '/schedules')
    window.sessionStorage.setItem('schoolAttendanceSession', JSON.stringify({
      refresh_token: 'refresh-one',
      refresh_expires_at: '2099-01-01T00:00:00Z',
      user: adminTokens().user,
    }))
    const schedules: Array<Record<string, unknown>> = []
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const requestUrl = input.toString()
      if (requestUrl.includes('/auth/refresh/')) return jsonResponse(adminTokens())
      if (requestUrl.endsWith('/schedules/') && init?.method === 'POST') {
        const values = JSON.parse(String(init.body)) as {
          name: string
          description: string
          effective_from: string
          days: Array<Record<string, unknown>>
        }
        const schedule = {
          id: 'schedule-1',
          name: values.name,
          description: values.description,
          is_active: true,
          versions: [{
            id: 'version-1',
            version_number: 1,
            effective_from: values.effective_from,
            effective_to: null,
            is_active: true,
            days: values.days,
            created_at: '2025-01-01T00:00:00Z',
          }],
          created_at: '2025-01-01T00:00:00Z',
          updated_at: '2025-01-01T00:00:00Z',
        }
        schedules.push(schedule)
        return jsonResponse(schedule, 201)
      }
      if (requestUrl.endsWith('/schedules/')) return jsonResponse(schedules)
      if (requestUrl.endsWith('/schedule-assignments/')) return jsonResponse([])
      if (requestUrl.endsWith('/schedule-exceptions/')) return jsonResponse([])
      if (requestUrl.endsWith('/calendar-events/')) return jsonResponse([])
      if (requestUrl.endsWith('/departments/')) return jsonResponse([])
      if (requestUrl.endsWith('/staff/')) return jsonResponse([])
      return jsonResponse({ status: 'ok', version: '1' })
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<App />)
    await screen.findByLabelText('Schedule name')
    fireEvent.change(screen.getByLabelText('Schedule name'), { target: { value: 'Standard' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create schedule' }))
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Schedule created and activated'))
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/schedules/'),
      expect.objectContaining({ method: 'POST' }),
    )
    expect((schedules[0].versions as Array<{ days: unknown[] }>)[0].days).toHaveLength(7)
  })

  it('lets a school admin approve a pending leave request', async () => {
    window.history.pushState({}, '', '/leave')
    window.sessionStorage.setItem('schoolAttendanceSession', JSON.stringify({
      refresh_token: 'refresh-one',
      refresh_expires_at: '2099-01-01T00:00:00Z',
      user: adminTokens().user,
    }))
    const pending = {
      id: 'leave-1',
      staff_profile: 'staff-1',
      staff_name: 'Ada Lovelace',
      leave_type: 'type-1',
      leave_type_name: 'Annual',
      start_date: '2025-03-03',
      end_date: '2025-03-07',
      reason: 'Family leave',
      status: 'PENDING',
      reviewed_by: null,
      reviewed_by_name: null,
      reviewed_at: null,
      review_comment: '',
      cancelled_by: null,
      cancelled_by_name: null,
      cancelled_at: null,
      cancellation_reason: '',
      created_at: '2025-02-01T00:00:00Z',
      updated_at: '2025-02-01T00:00:00Z',
    }
    let approved = false
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const requestUrl = input.toString()
      if (requestUrl.includes('/auth/refresh/')) return jsonResponse(adminTokens())
      if (requestUrl.endsWith('/leave-types/')) return jsonResponse([{ id: 'type-1', name: 'Annual', description: '', is_active: true }])
      if (requestUrl.endsWith('/leave-records/')) return jsonResponse([approved ? { ...pending, status: 'APPROVED' } : pending])
      if (requestUrl.includes('/leave-records/leave-1/review/') && init?.method === 'POST') {
        approved = true
        return jsonResponse({ ...pending, status: 'APPROVED', reviewed_by: 'admin-1' })
      }
      return jsonResponse({ status: 'ok', version: '1' })
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<App />)
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Leave Management' })).toBeInTheDocument())
    expect(await screen.findByText('Ada Lovelace')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Approve' }))
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Leave request approved'))
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/leave-records/leave-1/review/'),
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('protected routes require authentication', async () => {
    window.history.pushState({}, '', '/staff')
    render(<App />)
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Sign in' })).toBeInTheDocument())
  })
})
