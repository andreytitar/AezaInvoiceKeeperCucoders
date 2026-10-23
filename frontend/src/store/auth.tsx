import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { api, onUnauthorized, unwrap, type Me } from '../api/client'

type AuthState = {
  me: Me | null
  loading: boolean
  login: (login: string, password: string) => Promise<void>
  logout: () => Promise<void>
  isAdmin: boolean
}

const AuthCtx = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.GET('/api/v1/auth/me').then((r) => {
      setMe(r.response.ok && r.data ? r.data : null)
      setLoading(false)
    })
    const off = onUnauthorized(() => setMe(null))
    return () => {
      off()
    }
  }, [])

  const login = useCallback(async (login: string, password: string) => {
    const data = unwrap(await api.POST('/api/v1/auth/login', { body: { login, password } }))
    setMe(data.user)
  }, [])

  const logout = useCallback(async () => {
    await api.POST('/api/v1/auth/logout')
    setMe(null)
  }, [])

  return (
    <AuthCtx.Provider value={{ me, loading, login, logout, isAdmin: me?.role === 'admin' }}>{children}</AuthCtx.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthCtx)
  if (!ctx) throw new Error('AuthProvider missing')
  return ctx
}
