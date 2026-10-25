import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { api, onUnauthorized, unwrap, type Me } from '../api/client'
import { getTelegramWebApp } from '../telegram/webApp'

type AuthState = {
  me: Me | null
  loading: boolean
  login: (login: string, password: string) => Promise<void>
  adopt: (user: Me) => void
  enterAsEmployee: () => Promise<void>
  logout: () => Promise<void>
  isAdmin: boolean
}

const AuthCtx = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    const finish = (user: Me | null) => {
      if (!cancelled) {
        setMe(user)
        setLoading(false)
      }
    }

    ;(async () => {
      const meRes = await api.GET('/api/v1/auth/me')
      if (cancelled) return
      if (meRes.response.ok && meRes.data) {
        finish(meRes.data)
        return
      }
      const webApp = getTelegramWebApp()
      if (webApp?.initData) {
        try {
          const data = unwrap(
            await api.POST('/api/v1/auth/telegram/webapp', { body: { init_data: webApp.initData } }),
          )
          if (data.status === 'authenticated' && data.user) {
            finish(data.user)
            return
          }
        } catch {
          /* остаёмся на экране входа */
        }
      }
      finish(null)
    })()

    const off = onUnauthorized(() => setMe(null))
    return () => {
      cancelled = true
      off()
    }
  }, [])

  const login = useCallback(async (login: string, password: string) => {
    const data = unwrap(await api.POST('/api/v1/auth/login', { body: { login, password } }))
    setMe(data.user)
  }, [])

  const adopt = useCallback((user: Me) => {
    setMe(user)
  }, [])

  const enterAsEmployee = useCallback(async () => {
    const data = unwrap(await api.POST('/api/v1/auth/sandbox/employee'))
    setMe(data.user)
  }, [])

  const logout = useCallback(async () => {
    await api.POST('/api/v1/auth/logout')
    setMe(null)
  }, [])

  return (
    <AuthCtx.Provider value={{ me, loading, login, adopt, enterAsEmployee, logout, isAdmin: me?.role === 'admin' }}>
      {children}
    </AuthCtx.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthCtx)
  if (!ctx) throw new Error('AuthProvider missing')
  return ctx
}
