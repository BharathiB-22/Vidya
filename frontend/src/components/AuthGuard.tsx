import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth, hasAnyRole } from '@/lib/auth'
import UnauthorizedPage from '@/pages/UnauthorizedPage'

interface AuthGuardProps {
  allowedRoles?: string[]
}

export function AuthGuard({ allowedRoles }: AuthGuardProps = {}) {
  const { isAuthenticated, isLoading, user } = useAuth()
  const location = useLocation()

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

  // Force first-login users to change their password before accessing the app.
  // Skip this check when already on /first-login to prevent an infinite redirect.
  if (!allowedRoles && user?.firstLogin && location.pathname !== '/first-login') {
    return <Navigate to="/first-login" replace />
  }

  // When allowedRoles is provided, enforce role membership.
  // The outer AuthGuard (no allowedRoles) already verified authentication,
  // so user should be non-null here; treat null defensively.
  if (allowedRoles) {
    // Access is granted by the base login role OR an active responsibility grant
    // (single FACULTY account may act as GUIDE / EVALUATOR / BOARD / DEAN).
    if (!hasAnyRole(user, allowedRoles)) {
      return <UnauthorizedPage />
    }
  }

  return <Outlet />
}
