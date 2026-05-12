import React, { createContext, useContext, useEffect, useState } from 'react'
import api from '@/lib/api'

interface AuthContextType {
  isAuthenticated: boolean
  isLoading: boolean
  login: (tenantSlug: string, email: string, password: string) => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    const token = localStorage.getItem('vidya_token')
    if (!token) {
      setIsLoading(false)
      return
    }
    api
      .get('/auth/me')
      .then((res) => {
        localStorage.setItem('vidya_role', res.data.role)
        setIsAuthenticated(true)
      })
      .catch(() => {
        localStorage.removeItem('vidya_token')
        localStorage.removeItem('vidya_refresh_token')
        localStorage.removeItem('vidya_role')
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

    setIsAuthenticated(true)
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
      setIsAuthenticated(false)
    }
  }

  return (
    <AuthContext.Provider value={{ isAuthenticated, isLoading, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextType {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
