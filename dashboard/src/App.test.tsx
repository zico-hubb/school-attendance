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

  it('loads real staff backend data and submits staff creation', async () => {
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
      if (input.toString().endsWith('/staff/') && init?.method === 'POST') return jsonResponse({ ...staff[0], id: 'staff-new' }, 201)
      if (input.toString().endsWith('/staff/')) return jsonResponse(staff)
      return jsonResponse({ status: 'ok', version: '1' })
    }))
    render(<App />)
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Staff Management' })).toBeInTheDocument())
    await waitFor(() => expect(screen.getByText('Jane Doe')).toBeInTheDocument())
  })

  it('protected routes require authentication', async () => {
    window.history.pushState({}, '', '/staff')
    render(<App />)
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Sign in' })).toBeInTheDocument())
  })
})
