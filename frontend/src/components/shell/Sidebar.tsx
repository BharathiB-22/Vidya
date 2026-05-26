import { Link, useLocation } from 'react-router-dom'
import {
  LayoutDashboard, BookOpen, Layers, FlaskConical, Microscope,
  FileText, ClipboardList, BarChart2, X, Users, Settings, AlertTriangle,
  GraduationCap, Package, UserPlus, ClipboardCheck, Palette,
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

const ALL_ROLES = ['ADMIN', 'DEAN', 'FACULTY', 'STUDENT', 'BOARD', 'GUIDE', 'EVALUATOR']

const NAV_SECTIONS: NavSection[] = [
  {
    heading: '',
    items: [
      { label: 'Dashboard', to: '/dashboard', icon: LayoutDashboard, roles: ALL_ROLES },
    ],
  },
  {
    heading: 'Academics',
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
      { label: 'Lab Assignments', to: '/labs',                icon: FlaskConical,   roles: ['FACULTY', 'ADMIN'] },
      { label: 'Research',        to: '/research/problems',   icon: Microscope,     roles: ['FACULTY', 'ADMIN', 'GUIDE'] },
      { label: 'Exam Papers',     to: '/exams',               icon: FileText,       roles: ['FACULTY', 'ADMIN', 'BOARD'] },
      { label: 'Pending Review',  to: '/exams/board/pending', icon: ClipboardCheck, roles: ['BOARD', 'ADMIN'] },
      { label: 'Scripts',         to: '/scripts',             icon: ClipboardList,  roles: ['ADMIN', 'BOARD'] },
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
      { label: 'My Labs',     to: '/student/labs',     icon: FlaskConical, roles: ['STUDENT'] },
      { label: 'My Research', to: '/student/research', icon: Microscope,   roles: ['STUDENT'] },
    ],
  },
  {
    heading: 'Evaluate',
    items: [
      { label: 'My Evaluations', to: '/evaluator', icon: ClipboardCheck, roles: ['EVALUATOR'] },
    ],
  },
  {
    heading: 'Administration',
    items: [
      { label: 'Users',                to: '/users',                 icon: Users,    roles: ['ADMIN'] },
      { label: 'Bulk Onboarding',      to: '/users/bulk-onboarding', icon: UserPlus, roles: ['ADMIN'] },
      { label: 'Institution Branding', to: '/settings/branding',     icon: Palette,  roles: ['ADMIN'] },
      { label: 'Settings',             to: '/settings',              icon: Settings, roles: ['ADMIN'] },
    ],
  },
]

function prettifySlug(slug: string): string {
  if (!slug) return 'Institution'
  return slug
    .split('-')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')
}

function getInitials(name: string): string {
  const parts = name.trim().split(/\s+/)
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
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
  const displayName = user?.fullName || user?.email || ''
  const initials = displayName ? getInitials(displayName) : role?.slice(0, 2) || '??'

  // Read institution logo from localStorage branding settings
  const savedLogo = typeof window !== 'undefined'
    ? localStorage.getItem('vidya_institution_logo') ?? ''
    : ''

  function isActive(to: string): boolean {
    if (to === '/dashboard') return location.pathname === '/dashboard'
    return location.pathname.startsWith(to)
  }

  return (
    <div className="flex flex-col h-full bg-sv-dark">

      {/* ── Brand header ─────────────────────────────────────────── */}
      <div className="relative px-4 py-4 border-b border-white/10 flex items-center justify-between gap-2 overflow-hidden">
        {/* Subtle gradient glow behind logo */}
        <div className="absolute top-0 left-0 w-24 h-full bg-sv-primary/10 blur-2xl pointer-events-none" />

        <div className="relative flex items-center gap-2.5 min-w-0">
          {savedLogo ? (
            <img
              src={savedLogo}
              alt="Institution logo"
              className="w-8 h-8 rounded-lg object-contain bg-white p-0.5 flex-shrink-0"
            />
          ) : (
            <img
              src="/branding/sherpavector-logo.png"
              alt="VIDYA AI"
              className="w-8 h-8 rounded-full object-contain flex-shrink-0"
              style={{ filter: 'drop-shadow(0 0 4px rgba(37,99,235,0.4))' }}
            />
          )}
          <div className="min-w-0">
            <p className="text-[13px] font-bold text-white leading-none tracking-wide">VIDYA AI</p>
            <p className="text-[10px] text-slate-500 truncate mt-0.5" title={institution}>
              {institution}
            </p>
          </div>
        </div>

        <button
          onClick={onClose}
          className="relative p-1 rounded text-slate-500 hover:text-slate-300 hover:bg-white/10 lg:hidden flex-shrink-0"
          aria-label="Close sidebar"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* ── Nav ──────────────────────────────────────────────────── */}
      <nav className="flex-1 overflow-y-auto py-3 px-2 space-y-0">
        {NAV_SECTIONS.map((section) => {
          const visibleItems = section.items.filter((item) => item.roles.includes(role))
          if (visibleItems.length === 0) return null

          return (
            <div key={section.heading || '__root'} className="mb-4">
              {section.heading && (
                <div className="flex items-center gap-2 px-2 mb-1.5">
                  <span className="text-[9px] font-bold text-slate-600 uppercase tracking-[0.14em] whitespace-nowrap">
                    {section.heading}
                  </span>
                  <div className="flex-1 h-px bg-white/[0.04]" />
                </div>
              )}
              <ul className="space-y-0.5">
                {visibleItems.map((item) => {
                  const active = isActive(item.to)
                  return (
                    <li key={item.to} className="relative">
                      {active && (
                        <div className="absolute -left-2 top-1.5 bottom-1.5 w-[3px] bg-sv-accent rounded-r-full" />
                      )}
                      <Link
                        to={item.to}
                        onClick={onClose}
                        className={`flex items-center gap-2.5 px-2.5 py-[7px] rounded-lg text-sm font-medium transition-all duration-150 ${
                          active
                            ? 'bg-sv-primary text-white shadow-sm shadow-sv-primary/30'
                            : 'text-slate-400 hover:bg-white/[0.06] hover:text-slate-100'
                        }`}
                      >
                        <item.icon
                          className={`h-[15px] w-[15px] flex-shrink-0 transition-colors ${
                            active ? 'text-white' : 'text-slate-500 group-hover:text-slate-300'
                          }`}
                        />
                        <span className="truncate">{item.label}</span>
                      </Link>
                    </li>
                  )
                })}
              </ul>
            </div>
          )
        })}
      </nav>

      {/* ── Setup incomplete banner ──────────────────────────────── */}
      {setupIncomplete && (
        <Link
          to="/first-login"
          onClick={onClose}
          className="mx-2 mb-2 flex items-center gap-2 rounded-lg bg-amber-950/60 border border-amber-700/30 px-3 py-2 text-xs text-amber-400 hover:bg-amber-900/40 transition-colors"
        >
          <AlertTriangle className="h-3.5 w-3.5 text-amber-500 flex-shrink-0" />
          Set your permanent password
        </Link>
      )}

      {/* ── Footer ──────────────────────────────────────────────── */}
      <div className="px-3 py-3 border-t border-white/10">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-full bg-sv-primary/30 border border-sv-primary/40 flex items-center justify-center flex-shrink-0">
            <span className="text-[10px] font-bold text-sv-muted uppercase">{initials}</span>
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-[11px] font-semibold text-slate-300 truncate leading-tight">
              {displayName || role}
            </p>
            <p className="text-[9px] text-slate-600 leading-tight mt-0.5 uppercase tracking-wide font-medium">
              {role}
            </p>
          </div>
        </div>
        <p className="text-[8px] text-slate-700 mt-2.5 font-bold tracking-[0.18em] uppercase">
          SherpaVector · VIDYA AI
        </p>
      </div>

    </div>
  )
}
