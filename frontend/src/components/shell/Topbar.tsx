import { useState, useRef, useEffect } from 'react'
import { Menu, LogOut, ChevronDown } from 'lucide-react'
import { useAuth } from '@/lib/auth'
import { useCurrentUser } from '@/hooks/useCurrentUser'

interface TopbarProps {
  onMenuClick: () => void
}

const ROLE_COLORS: Record<string, string> = {
  ADMIN:   'bg-purple-100 text-purple-700',
  DEAN:    'bg-indigo-100 text-indigo-700',
  FACULTY: 'bg-blue-100 text-blue-700',
  STUDENT: 'bg-green-100 text-green-700',
  BOARD:   'bg-orange-100 text-orange-700',
  GUIDE:   'bg-teal-100 text-teal-700',
}

function getInitials(name: string): string {
  const parts = name.trim().split(/\s+/)
  if (parts.length === 1) return parts[0].charAt(0).toUpperCase()
  return (parts[0].charAt(0) + parts[parts.length - 1].charAt(0)).toUpperCase()
}

export function Topbar({ onMenuClick }: TopbarProps) {
  const { logout } = useAuth()
  const user = useCurrentUser()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const displayName = user?.fullName || user?.email || 'User'
  const initials = user?.fullName
    ? getInitials(user.fullName)
    : (user?.email?.charAt(0).toUpperCase() ?? '?')
  const roleColor = user?.role ? (ROLE_COLORS[user.role] ?? 'bg-gray-100 text-gray-700') : ''

  return (
    <header className="h-14 bg-white border-b border-gray-200 flex items-center px-4 gap-3 flex-shrink-0">
      {/* Hamburger — mobile only */}
      <button
        className="p-1.5 rounded-lg text-gray-500 hover:bg-gray-100 lg:hidden"
        onClick={onMenuClick}
        aria-label="Open navigation"
      >
        <Menu className="h-5 w-5" />
      </button>

      {/* Spacer */}
      <div className="flex-1" />

      {/* User menu */}
      <div className="relative" ref={ref}>
        <button
          onClick={() => setOpen((v) => !v)}
          className="flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-gray-50 transition-colors"
        >
          <div className="h-7 w-7 rounded-full bg-indigo-600 text-white text-xs font-bold flex items-center justify-center flex-shrink-0">
            {initials}
          </div>
          <div className="hidden sm:flex flex-col items-start leading-none gap-0.5">
            <span className="text-sm font-medium text-gray-800 max-w-[160px] truncate leading-tight">
              {displayName}
            </span>
            {user?.role && (
              <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded-full ${roleColor}`}>
                {user.role}
              </span>
            )}
          </div>
          <ChevronDown className="h-3.5 w-3.5 text-gray-400 hidden sm:block" />
        </button>

        {open && (
          <div className="absolute right-0 top-full mt-1.5 w-56 bg-white rounded-xl border border-gray-200 shadow-lg z-50 overflow-hidden">
            <div className="px-4 py-3 border-b border-gray-100">
              <p className="text-sm font-semibold text-gray-900 truncate">{displayName}</p>
              <p className="text-xs text-gray-500 truncate mt-0.5">{user?.email}</p>
            </div>
            <button
              onClick={() => { setOpen(false); void logout() }}
              className="w-full flex items-center gap-2.5 px-4 py-2.5 text-sm text-red-600 hover:bg-red-50 transition-colors"
            >
              <LogOut className="h-4 w-4" />
              Sign out
            </button>
          </div>
        )}
      </div>
    </header>
  )
}
