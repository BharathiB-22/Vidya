import { Outlet } from 'react-router-dom'
import { Building2, LogOut } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useAdminAuth } from '@/lib/adminAuth'

export function AdminShell() {
  const { logout } = useAdminAuth()

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between sticky top-0 z-10">
        <div className="flex items-center gap-2">
          <Building2 className="h-5 w-5 text-indigo-600" />
          <span className="text-lg font-semibold text-indigo-700">Vidya Admin Console</span>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={logout}
          className="text-gray-500 hover:text-gray-700 gap-1.5"
        >
          <LogOut className="h-4 w-4" />
          Sign out
        </Button>
      </header>
      <Outlet />
    </div>
  )
}
