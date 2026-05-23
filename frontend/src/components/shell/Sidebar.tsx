import { Link, useLocation } from 'react-router-dom'
import {
  LayoutDashboard, BookOpen, Layers, FlaskConical, Microscope,
  FileText, ClipboardList, BarChart2, X, Users, Settings, AlertTriangle,
  GraduationCap, Package,
} from 'lucide-react'
import { useCurrentUser } from '@/hooks/useCurrentUser'
import { useAuth } from '@/lib/auth'

type LucideIconType = typeof LayoutDashboard

interface NavItem {
  label: string
  to: string
  icon: LucideIconType
  roles: string[]
}

interface NavSection {
  heading: string
  items: NavItem[]
}

const ALL_ROLES = ['ADMIN', 'DEAN', 'FACULTY', 'STUDENT', 'BOARD', 'GUIDE']

const NAV_SECTIONS: NavSection[] = [
  {
    heading: '',
    items: [
      { label: 'Dashboard', to: '/dashboard', icon: LayoutDashboard, roles: ALL_ROLES },
    ],
  },
  {
    heading: 'Teach & Prepare',
    items: [
      { label: 'Programs',          to: '/programs',          icon: BookOpen,       roles: ['FACULTY', 'DEAN', 'ADMIN'] },
      { label: 'Syllabuses',        to: '/syllabuses',        icon: GraduationCap,  roles: ['FACULTY', 'DEAN', 'ADMIN'] },
      { label: 'Course Kits',       to: '/course-kits',       icon: Layers,         roles: ['FACULTY', 'DEAN', 'ADMIN'] },
      { label: 'Learning Packages', to: '/learning-packages', icon: Package,        roles: ['FACULTY', 'DEAN', 'ADMIN'] },
    ],
  },
  {
    heading: 'Assess & Research',
    items: [
      { label: 'Lab Assignments', to: '/labs',               icon: FlaskConical,  roles: ['FACULTY', 'ADMIN'] },
      { label: 'Research',        to: '/research/problems',  icon: Microscope,    roles: ['FACULTY', 'ADMIN', 'GUIDE'] },
      { label: 'Exam Papers',     to: '/exams',              icon: FileText,      roles: ['FACULTY', 'ADMIN', 'BOARD'] },
      { label: 'Scripts',         to: '/scripts',            icon: ClipboardList, roles: ['ADMIN', 'BOARD'] },
    ],
  },
  {
    heading: 'Analytics',
    items: [
      { label: 'Bell Curve', to: '/bell-curve', icon: BarChart2, roles: ['DEAN', 'ADMIN', 'BOARD'] },
    ],
  },
  {
    heading: 'Student',
    items: [
      { label: 'My Labs',     to: '/student/labs',      icon: FlaskConical, roles: ['STUDENT'] },
      { label: 'My Research', to: '/student/research',  icon: Microscope,   roles: ['STUDENT'] },
    ],
  },
  {
    heading: 'Administration',
    items: [
      { label: 'Users',    to: '/users',    icon: Users,    roles: ['ADMIN'] },
      { label: 'Settings', to: '/settings', icon: Settings, roles: ['ADMIN'] },
    ],
  },
]

function prettifySlug(slug: string): string {
  if (!slug) return 'Vidya'
  return slug
    .split('-')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')
}

interface SidebarProps {
  onClose: () => void
}

export function Sidebar({ onClose }: SidebarProps) {
  const location = useLocation()
  const user = useCurrentUser()
  const { user: authUser } = useAuth()
  const role = user?.role ?? ''
  const institution = prettifySlug(user?.tenantSlug ?? '')
  const setupIncomplete = role === 'ADMIN' && authUser?.firstLogin === true

  function isActive(to: string): boolean {
    if (to === '/dashboard') return location.pathname === '/dashboard'
    return location.pathname.startsWith(to)
  }

  return (
    <div className="flex flex-col h-full">
      {/* Brand / institution */}
      <div className="px-4 py-4 border-b border-gray-100 flex items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="text-base font-bold text-indigo-700 leading-tight">Vidya</p>
          <p className="text-xs text-gray-500 truncate mt-0.5" title={institution}>
            {institution}
          </p>
        </div>
        {/* Mobile close */}
        <button
          onClick={onClose}
          className="p-1 rounded text-gray-400 hover:text-gray-600 hover:bg-gray-100 lg:hidden flex-shrink-0"
          aria-label="Close sidebar"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto py-3 px-2">
        {NAV_SECTIONS.map((section) => {
          const visibleItems = section.items.filter((item) => item.roles.includes(role))
          if (visibleItems.length === 0) return null

          return (
            <div key={section.heading || '__root'} className="mb-4">
              {section.heading && (
                <p className="px-2 mb-1 text-[10px] font-semibold text-gray-400 uppercase tracking-wider">
                  {section.heading}
                </p>
              )}
              <ul className="space-y-0.5">
                {visibleItems.map((item) => {
                  const active = isActive(item.to)
                  return (
                    <li key={item.to}>
                      <Link
                        to={item.to}
                        onClick={onClose}
                        className={`flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-sm font-medium transition-colors ${
                          active
                            ? 'bg-indigo-100 text-indigo-700'
                            : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
                        }`}
                      >
                        <item.icon
                          className={`h-4 w-4 flex-shrink-0 ${active ? 'text-indigo-600' : 'text-gray-400'}`}
                        />
                        {item.label}
                      </Link>
                    </li>
                  )
                })}
              </ul>
            </div>
          )
        })}
      </nav>

      {/* Setup incomplete banner */}
      {setupIncomplete && (
        <Link
          to="/first-login"
          onClick={onClose}
          className="mx-2 mb-2 flex items-center gap-2 rounded-lg bg-amber-50 border border-amber-200 px-3 py-2 text-xs text-amber-800 hover:bg-amber-100"
        >
          <AlertTriangle className="h-3.5 w-3.5 text-amber-600 flex-shrink-0" />
          Set your permanent password
        </Link>
      )}

      {/* Footer: role chip */}
      <div className="px-4 py-3 border-t border-gray-100">
        <p className="text-xs text-gray-400 truncate">
          Signed in as{' '}
          <span className="font-medium text-gray-600">{role || '—'}</span>
        </p>
      </div>
    </div>
  )
}
