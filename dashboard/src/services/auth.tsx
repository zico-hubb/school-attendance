import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import {
  clearTokens,
  login as apiLogin,
  logout as apiLogout,
  refreshSession,
  setTokens,
  type AuthUser,
  type TokenResponse,
} from './api'

const sessionKey = 'schoolAttendanceSession'

type StoredSession = {
  refresh_token: string
  refresh_expires_at: string
  user: AuthUser
}

type AuthContextValue = {
  user: AuthUser | null
  restoring: boolean
  staffRejected: boolean
  login: (schoolCode: string, username: string, password: string) => Promise<void>
  logout: () => Promise<void>
  clearStaffRejected: () => void
  expireSession: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

function readStoredSession(): StoredSession | null {
  try {
    const value = window.sessionStorage.getItem(sessionKey)
    return value ? JSON.parse(value) as StoredSession : null
  } catch {
    return null
  }
}

function storeSession(tokens: TokenResponse) {
  const stored: StoredSession = {
    refresh_token: tokens.refresh_token,
    refresh_expires_at: tokens.refresh_expires_at,
    user: tokens.user,
  }
  window.sessionStorage.setItem(sessionKey, JSON.stringify(stored))
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [restoring, setRestoring] = useState(true)
  const [staffRejected, setStaffRejected] = useState(false)

  const expireSession = () => {
    clearTokens()
    window.sessionStorage.removeItem(sessionKey)
    setUser(null)
  }

  useEffect(() => {
    let active = true
    const restore = async () => {
      const stored = readStoredSession()
      if (!stored) {
        if (active) setRestoring(false)
        return
      }
      if (new Date(stored.refresh_expires_at).getTime() <= Date.now()) {
        expireSession()
        if (active) setRestoring(false)
        return
      }
      setTokens({ access_token: '', refresh_token: stored.refresh_token })
      try {
        const refreshed = await refreshSession()
        if (!active) return
        if (!refreshed) {
          expireSession()
        } else if (refreshed.user.role === 'STAFF') {
          expireSession()
          setStaffRejected(true)
        } else {
          setUser(refreshed.user)
          storeSession(refreshed)
        }
      } catch {
        if (active) expireSession()
      } finally {
        if (active) setRestoring(false)
      }
    }
    void restore()
    return () => {
      active = false
    }
  }, [])

  const login = async (schoolCode: string, username: string, password: string) => {
    setStaffRejected(false)
    let tokens: TokenResponse
    try {
      tokens = await apiLogin({
        school_code: schoolCode.trim(),
        username: username.trim(),
        password,
      })
    } catch (error) {
      if (error instanceof Error && /network|could not be reached/i.test(error.message)) {
        throw new Error('Unable to reach the authentication service. Check your connection and try again.')
      }
      throw new Error('Invalid school code, username, or password.')
    }

    if (tokens.user.role === 'STAFF') {
      setTokens(tokens)
      try {
        await apiLogout()
      } catch {
        clearTokens()
      }
      expireSession()
      setStaffRejected(true)
      throw new Error('STAFF_ONLY')
    }
    if (tokens.user.role !== 'SCHOOL_ADMIN' && tokens.user.role !== 'ATTENDANCE_MANAGER') {
      expireSession()
      throw new Error('Your account does not have dashboard access.')
    }
    setTokens(tokens)
    storeSession(tokens)
    setUser(tokens.user)
  }

  const logout = async () => {
    try {
      await apiLogout()
    } finally {
      expireSession()
    }
  }

  return (
    <AuthContext.Provider value={{
      user,
      restoring,
      staffRejected,
      login,
      logout,
      clearStaffRejected: () => setStaffRejected(false),
      expireSession,
    }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside AuthProvider')
  return context
}
