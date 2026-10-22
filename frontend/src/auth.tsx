// Who is logged in, shared across the site. The login itself lives in an HttpOnly cookie
// that page scripts can't read, so we ask the backend (/api/auth/me) instead.

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import * as api from './api'

type AuthContextValue = {
  user: api.User | null
  checking: boolean
  login: (email: string, password: string) => Promise<api.User>
  signup: (data: api.SignupData) => Promise<api.User>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<api.User | null>(null)
  const [checking, setChecking] = useState(true)

  useEffect(() => {
    const controller = new AbortController()
    api.fetchMe(controller.signal)
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setChecking(false))
    return () => controller.abort()
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    const u = await api.login(email, password)
    setUser(u)
    return u
  }, [])

  const signup = useCallback(async (data: api.SignupData) => {
    const u = await api.signup(data)
    setUser(u)
    return u
  }, [])

  const logout = useCallback(async () => {
    await api.logout()
    setUser(null)
  }, [])

  const value = useMemo(() => ({ user, checking, login, signup, logout }), [user, checking, login, signup, logout])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}
