import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { login as apiLogin, getMe } from '../api/reports'
import { getToken, setToken, clearToken, SESSION_EXPIRED_KEY } from '../api/client'

const IDLE_TIMEOUT_MS = 20 * 60 * 1000
const ACTIVITY_EVENTS = ['mousedown', 'keydown', 'touchstart', 'scroll', 'mousemove'] as const

interface AuthContextValue {
  token: string | null
  name: string | null
  isAdmin: boolean
  isLoading: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const [token, setTokenState] = useState<string | null>(() => getToken())
  const [name, setName] = useState<string | null>(() => sessionStorage.getItem('user_name'))
  const [isAdmin, setIsAdmin] = useState(() => sessionStorage.getItem('is_admin') === 'true')
  const [isLoading, setIsLoading] = useState(!!getToken())

  useEffect(() => {
    if (!token) {
      setIsLoading(false)
      return
    }
    getMe()
      .then((user) => {
        setName(user.name)
        setIsAdmin(user.is_admin)
        sessionStorage.setItem('user_name', user.name)
        sessionStorage.setItem('is_admin', String(user.is_admin))
      })
      .catch(() => {
        clearToken()
        setTokenState(null)
        setName(null)
        setIsAdmin(false)
      })
      .finally(() => setIsLoading(false))
  }, [token])

  const login = useCallback(async (username: string, password: string) => {
    const res = await apiLogin(username, password)
    setToken(res.access_token)
    setTokenState(res.access_token)
    setName(res.name)
    setIsAdmin(res.is_admin)
    sessionStorage.setItem('user_name', res.name)
    sessionStorage.setItem('is_admin', String(res.is_admin))
    queryClient.clear()
  }, [queryClient])

  const logout = useCallback(() => {
    clearToken()
    setTokenState(null)
    setName(null)
    setIsAdmin(false)
    queryClient.clear()
  }, [queryClient])

  useEffect(() => {
    if (!token) return
    let timer: number
    const expire = () => {
      sessionStorage.setItem(SESSION_EXPIRED_KEY, '1')
      logout()
    }
    const reset = () => {
      window.clearTimeout(timer)
      timer = window.setTimeout(expire, IDLE_TIMEOUT_MS)
    }
    reset()
    ACTIVITY_EVENTS.forEach((e) => window.addEventListener(e, reset, { passive: true }))
    return () => {
      window.clearTimeout(timer)
      ACTIVITY_EVENTS.forEach((e) => window.removeEventListener(e, reset))
    }
  }, [token, logout])

  return (
    <AuthContext.Provider value={{ token, name, isAdmin, isLoading, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
