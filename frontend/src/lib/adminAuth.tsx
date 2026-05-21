import React, { createContext, useContext, useEffect, useState } from 'react'
import adminApi from '@/lib/adminApi'

interface AdminAuthContextType {
  isAuthenticated: boolean
  isLoading: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => void
}

const AdminAuthContext = createContext<AdminAuthContextType | null>(null)

export function AdminAuthProvider({ children }: { children: React.ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    const token = localStorage.getItem('vidya_admin_token')
    if (!token) {
      setIsLoading(false)
      return
    }
    // /api/platform/auth/me → backend /platform/auth/me
    adminApi
      .get('/platform/auth/me')
      .then(() => setIsAuthenticated(true))
      .catch(() => {
        localStorage.removeItem('vidya_admin_token')
        setIsAuthenticated(false)
      })
      .finally(() => setIsLoading(false))
  }, [])

  async function login(email: string, password: string): Promise<void> {
    // /api/platform/auth/login → backend /platform/auth/login
    const { data: tokens } = await adminApi.post('/platform/auth/login', { email, password })
    localStorage.setItem('vidya_admin_token', tokens.access_token)
    setIsAuthenticated(true)
  }

  function logout(): void {
    localStorage.removeItem('vidya_admin_token')
    setIsAuthenticated(false)
    window.location.href = '/admin/login'
  }

  return (
    <AdminAuthContext.Provider value={{ isAuthenticated, isLoading, login, logout }}>
      {children}
    </AdminAuthContext.Provider>
  )
}

export function useAdminAuth(): AdminAuthContextType {
  const ctx = useContext(AdminAuthContext)
  if (!ctx) throw new Error('useAdminAuth must be used inside AdminAuthProvider')
  return ctx
}
