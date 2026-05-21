import React, { createContext, useContext, useEffect, useState } from 'react'
import api from '@/lib/api'

export interface CurrentUser {
  id: string
  email: string
  role: string
  fullName: string
  tenantSlug: string
  schemaName: string | null
  firstLogin: boolean
}

interface AuthContextType {
  isAuthenticated: boolean
  isLoading: boolean
  user: CurrentUser | null
  login: (tenantSlug: string, email: string, password: string) => Promise<void>
  logout: () => Promise<void>
  refreshUser: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | null>(null)

function _meToUser(me: Record<string, unknown>, tenantSlug: string): CurrentUser {
  return {
    id: String(me.id),
    email: me.email as string,
    role: me.role as string,
    fullName: (me.full_name as string) ?? (me.email as string),
    tenantSlug,
    schemaName: (me.schema_name as string) ?? null,
    firstLogin: (me.first_login as boolean) ?? false,
  }
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [isLoading, setIsLoading] = useState(true)
  const [user, setUser] = useState<CurrentUser | null>(null)

  useEffect(() => {
    const token = localStorage.getItem('vidya_token')
    if (!token) {
      setIsLoading(false)
      return
    }
    api
      .get('/auth/me')
      .then((res) => {
        const me = res.data
        const tenantSlug = localStorage.getItem('vidya_tenant_slug') ?? ''
        localStorage.setItem('vidya_role', me.role)
        setUser(_meToUser(me, tenantSlug))
        setIsAuthenticated(true)
      })
      .catch(() => {
        localStorage.removeItem('vidya_token')
        localStorage.removeItem('vidya_refresh_token')
        localStorage.removeItem('vidya_role')
        setUser(null)
        setIsAuthenticated(false)
      })
      .finally(() => setIsLoading(false))
  }, [])

  async function login(tenantSlug: string, email: string, password: string): Promise<void> {
    // Set slug first so the request interceptor can attach X-Tenant-Slug
    localStorage.setItem('vidya_tenant_slug', tenantSlug)

    const { data: tokens } = await api.post('/auth/login', { email, password })
    localStorage.setItem('vidya_token', tokens.access_token)
    if (tokens.refresh_token) {
      localStorage.setItem('vidya_refresh_token', tokens.refresh_token)
    }

    const { data: me } = await api.get('/auth/me')
    localStorage.setItem('vidya_role', me.role)
    setUser(_meToUser(me, tenantSlug))
    setIsAuthenticated(true)
  }

  async function refreshUser(): Promise<void> {
    const tenantSlug = localStorage.getItem('vidya_tenant_slug') ?? ''
    const { data: me } = await api.get('/auth/me')
    localStorage.setItem('vidya_role', me.role)
    setUser(_meToUser(me, tenantSlug))
  }

  async function logout(): Promise<void> {
    const refreshToken = localStorage.getItem('vidya_refresh_token')
    try {
      if (refreshToken) {
        await api.post('/auth/logout', { refresh_token: refreshToken })
      }
    } catch {
      // clear session regardless of server response
    } finally {
      localStorage.removeItem('vidya_token')
      localStorage.removeItem('vidya_refresh_token')
      localStorage.removeItem('vidya_role')
      // Keep vidya_tenant_slug so it pre-fills the login form next time
      setUser(null)
      setIsAuthenticated(false)
    }
  }

  return (
    <AuthContext.Provider value={{ isAuthenticated, isLoading, user, login, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextType {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
