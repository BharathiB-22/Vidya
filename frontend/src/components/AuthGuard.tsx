import { Navigate, Outlet } from 'react-router-dom'
import { useAuth } from '@/lib/auth'
import UnauthorizedPage from '@/pages/UnauthorizedPage'

interface AuthGuardProps {
  allowedRoles?: string[]
}

export function AuthGuard({ allowedRoles }: AuthGuardProps = {}) {
  const { isAuthenticated, isLoading, user } = useAuth()

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-indigo-600 border-t-transparent" />
      </div>
    )
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }

  // When allowedRoles is provided, enforce role membership.
  // The outer AuthGuard (no allowedRoles) already verified authentication,
  // so user should be non-null here; treat null defensively.
  if (allowedRoles) {
    if (!user || !allowedRoles.includes(user.role)) {
      return <UnauthorizedPage />
    }
  }

  return <Outlet />
}
