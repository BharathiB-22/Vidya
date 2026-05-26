import { useState, useRef, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { Menu, LogOut, ChevronDown, Bell, Search, Settings } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { useAuth } from '@/lib/auth'
import { useCurrentUser } from '@/hooks/useCurrentUser'
import { listNotifications } from '@/lib/api/notifications'
import { Breadcrumbs } from './Breadcrumbs'
import { NotificationsDrawer } from './NotificationsDrawer'

interface TopbarProps {
  onMenuClick: () => void
}

const ROLE_COLORS: Record<string, string> = {
  ADMIN:     'bg-purple-100 text-purple-700',
  DEAN:      'bg-sv-light text-sv-primary',
  FACULTY:   'bg-blue-100 text-blue-700',
  STUDENT:   'bg-emerald-100 text-emerald-700',
  BOARD:     'bg-orange-100 text-orange-700',
  GUIDE:     'bg-teal-100 text-teal-700',
  EVALUATOR: 'bg-gray-100 text-gray-600',
}

function getInitials(name: string): string {
  const parts = name.trim().split(/\s+/)
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
}

export function Topbar({ onMenuClick }: TopbarProps) {
  const { logout } = useAuth()
  const user = useCurrentUser()
  const [userMenuOpen, setUserMenuOpen] = useState(false)
  const [notifOpen, setNotifOpen]       = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function onOutsideClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setUserMenuOpen(false)
      }
    }
    document.addEventListener('mousedown', onOutsideClick)
    return () => document.removeEventListener('mousedown', onOutsideClick)
  }, [])

  const { data: notifData } = useQuery({
    queryKey: ['notifications-count'],
    queryFn:  () => listNotifications({ page: 1, page_size: 1 }),
    refetchInterval: 60000,
  })
  const unreadCount = notifData?.unread_count ?? 0

  const displayName = user?.fullName || user?.email || 'User'
  const initials    = user?.fullName
    ? getInitials(user.fullName)
    : (user?.email?.[0]?.toUpperCase() ?? '?')
  const roleColor   = user?.role ? (ROLE_COLORS[user.role] ?? 'bg-gray-100 text-gray-600') : ''

  return (
    <>
      <header className="h-14 bg-white border-b border-gray-100 shadow-sm z-10 flex items-center px-4 gap-2 flex-shrink-0">

        {/* ── Mobile hamburger ───────────────────────────────── */}
        <button
          className="p-1.5 rounded-lg text-gray-500 hover:bg-gray-100 transition-colors lg:hidden flex-shrink-0"
          onClick={onMenuClick}
          aria-label="Open navigation"
        >
          <Menu className="h-5 w-5" />
        </button>

        {/* ── Desktop separator ──────────────────────────────── */}
        <div className="hidden lg:block w-px h-5 bg-gray-200 flex-shrink-0" />

        {/* ── Breadcrumbs ────────────────────────────────────── */}
        <div className="hidden sm:flex flex-1 min-w-0 items-center">
          <Breadcrumbs />
        </div>

        {/* Mobile spacer */}
        <div className="flex-1 sm:hidden" />

        {/* ── Global search placeholder ──────────────────────── */}
        <button
          className="hidden md:flex items-center gap-2 bg-gray-50 hover:bg-gray-100 border border-gray-200 rounded-lg px-3 py-[7px] text-sm text-gray-400 transition-colors w-52 lg:w-64 flex-shrink-0"
          aria-label="Search"
          tabIndex={0}
        >
          <Search className="h-3.5 w-3.5 flex-shrink-0 text-gray-400" />
          <span className="flex-1 text-left text-[13px] text-gray-400">Search...</span>
          <kbd className="hidden lg:inline-flex items-center text-[9px] font-semibold bg-white px-1.5 py-0.5 rounded border border-gray-200 text-gray-400">
            ⌘K
          </kbd>
        </button>

        {/* ── Notification bell ──────────────────────────────── */}
        <button
          onClick={() => setNotifOpen(true)}
          className="relative p-2 rounded-lg text-gray-500 hover:bg-gray-100 transition-colors flex-shrink-0"
          aria-label={`Notifications${unreadCount > 0 ? ` (${unreadCount} unread)` : ''}`}
        >
          <Bell className="h-[18px] w-[18px]" />
          {unreadCount > 0 && (
            <span className="absolute top-[5px] right-[5px] min-w-[14px] h-[14px] bg-sv-primary text-white text-[8px] font-bold rounded-full flex items-center justify-center px-0.5 leading-none">
              {unreadCount > 99 ? '99+' : unreadCount}
            </span>
          )}
        </button>

        {/* ── Vertical divider ───────────────────────────────── */}
        <div className="w-px h-5 bg-gray-200 flex-shrink-0" />

        {/* ── User menu ──────────────────────────────────────── */}
        <div className="relative flex-shrink-0" ref={menuRef}>
          <button
            data-testid="user-menu-trigger"
            onClick={() => setUserMenuOpen((v) => !v)}
            className="flex items-center gap-2 pl-1 pr-2 py-1.5 rounded-lg hover:bg-gray-50 transition-colors"
          >
            {/* Avatar */}
            <div className="h-8 w-8 rounded-full bg-sv-primary text-white text-xs font-bold flex items-center justify-center flex-shrink-0 shadow-sm shadow-sv-primary/25">
              {initials}
            </div>

            {/* Name + role chip */}
            <div className="hidden sm:flex flex-col items-start leading-none gap-[3px] max-w-[144px]">
              <span className="text-[13px] font-semibold text-gray-800 truncate w-full leading-tight">
                {displayName}
              </span>
              {user?.role && (
                <span className={`text-[9px] font-bold px-1.5 py-[2px] rounded leading-none ${roleColor}`}>
                  {user.role}
                </span>
              )}
            </div>

            <ChevronDown
              className={`h-3.5 w-3.5 text-gray-400 hidden sm:block transition-transform duration-150 ${
                userMenuOpen ? 'rotate-180' : ''
              }`}
            />
          </button>

          {/* ── Dropdown panel ─────────────────────────────── */}
          {userMenuOpen && (
            <div className="absolute right-0 top-full mt-2 w-60 bg-white rounded-xl border border-gray-200 shadow-xl shadow-gray-900/10 z-50 overflow-hidden">

              {/* User info header */}
              <div className="flex items-center gap-3 px-4 py-3.5 bg-gray-50/70 border-b border-gray-100">
                <div className="h-9 w-9 rounded-full bg-sv-primary text-white text-sm font-bold flex items-center justify-center flex-shrink-0">
                  {initials}
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-[13px] font-semibold text-gray-900 truncate leading-tight">
                    {displayName}
                  </p>
                  <p className="text-[11px] text-gray-400 truncate mt-0.5">
                    {user?.email}
                  </p>
                  {user?.role && (
                    <span className={`inline-flex mt-1.5 text-[9px] font-bold px-1.5 py-[2px] rounded leading-none ${roleColor}`}>
                      {user.role}
                    </span>
                  )}
                </div>
              </div>

              {/* Navigation items */}
              {user?.role === 'ADMIN' && (
                <div className="py-1 border-b border-gray-100">
                  <Link
                    to="/settings"
                    onClick={() => setUserMenuOpen(false)}
                    className="flex items-center gap-2.5 px-4 py-2 text-[13px] text-gray-700 hover:bg-gray-50 transition-colors"
                  >
                    <Settings className="h-3.5 w-3.5 text-gray-400" />
                    Settings
                  </Link>
                </div>
              )}

              {/* Sign out */}
              <div className="py-1">
                <button
                  data-testid="signout-btn"
                  onClick={() => { setUserMenuOpen(false); void logout() }}
                  className="w-full flex items-center gap-2.5 px-4 py-2 text-[13px] text-red-600 hover:bg-red-50 transition-colors"
                >
                  <LogOut className="h-3.5 w-3.5" />
                  Sign out
                </button>
              </div>
            </div>
          )}
        </div>
      </header>

      <NotificationsDrawer open={notifOpen} onClose={() => setNotifOpen(false)} />
    </>
  )
}
