import { Link, useLocation } from 'react-router-dom'
import {
  LayoutDashboard, BookOpen, Layers, FlaskConical, Microscope,
  FileText, ClipboardList, BarChart2, X, Users, Settings, AlertTriangle,
  GraduationCap, Package, UserPlus, ClipboardCheck, Palette,
  Building2, Calendar, CalendarRange, LayoutList, UserCheck, BookMarked,
  BookLock, School2, UsersRound, UserCircle2, RefreshCw, CalendarCheck,
  Award, Ticket, MapPin, CalendarDays, History,
} from 'lucide-react'
import { useCurrentUser } from '@/hooks/useCurrentUser'
import { useAuth } from '@/lib/auth'
import { useBranding } from '@/lib/branding'

type LucideIconType = typeof LayoutDashboard

interface NavItem {
  label: string
  to: string
  icon: LucideIconType
  roles: string[]
  exact?: boolean
}

interface NavSection {
  heading: string
  items: NavItem[]
}

const ALL_ROLES = ['ADMIN', 'DEAN', 'FACULTY', 'STUDENT', 'BOARD', 'GUIDE', 'EVALUATOR']

const NAV_SECTIONS: NavSection[] = [

  // ── Root — every role ──────────────────────────────────────────────────────
  {
    heading: '',
    items: [
      { label: 'Dashboard', to: '/dashboard', icon: LayoutDashboard, roles: ALL_ROLES, exact: true },
    ],
  },

  // ── FACULTY: My Teaching ───────────────────────────────────────────────────
  {
    heading: 'My Teaching',
    items: [
      { label: 'My Courses',         to: '/my-courses',              icon: BookOpen,      roles: ['FACULTY'] },
      { label: 'Mark Attendance',    to: '/sis/attendance/mark',     icon: CalendarCheck, roles: ['FACULTY'] },
      { label: 'Shortage Report',    to: '/sis/attendance/shortage', icon: AlertTriangle, roles: ['FACULTY'] },
      { label: 'Syllabuses',         to: '/syllabuses',              icon: GraduationCap, roles: ['FACULTY'] },
      { label: 'Course Kits',        to: '/course-kits',             icon: Layers,        roles: ['FACULTY'] },
      { label: 'Learning Materials', to: '/learning-packages',       icon: Package,       roles: ['FACULTY'] },
    ],
  },

  // ── FACULTY: Assess & Research ─────────────────────────────────────────────
  {
    heading: 'Assess & Research',
    items: [
      { label: 'Lab Assignments',      to: '/labs',                 icon: FlaskConical,  roles: ['FACULTY'] },
      { label: 'Research Supervision', to: '/research/problems',    icon: Microscope,    roles: ['FACULTY'] },
      { label: 'Exam Papers',          to: '/exams',                icon: FileText,      roles: ['FACULTY'] },
      { label: 'Internal Marks',       to: '/sis/marks/setup',      icon: BookMarked,    roles: ['FACULTY'] },
      { label: 'My Evaluations',       to: '/scripts/evaluator',    icon: ClipboardList, roles: ['FACULTY'] },
    ],
  },

  // ── FACULTY: My Account ───────────────────────────────────────────────────
  {
    heading: 'My Account',
    items: [
      { label: 'My Profile', to: '/sis/me/profile', icon: UserCircle2, roles: ['FACULTY'] },
      { label: 'Faculty Directory', to: '/sis/directory/faculty', icon: UserCheck, roles: ['FACULTY'] },
    ],
  },

  // ── DEAN: Academic Operations ──────────────────────────────────────────────
  {
    heading: 'Academic Operations',
    items: [
      { label: 'Attendance Analytics', to: '/sis/attendance/analytics', icon: CalendarCheck, roles: ['DEAN'] },
      { label: 'Internal Marks',       to: '/sis/marks/report',         icon: BookMarked,    roles: ['DEAN'] },
    ],
  },

  // ── DEAN: Examinations ────────────────────────────────────────────────────
  {
    heading: 'Examinations',
    items: [
      { label: 'Hall Tickets',  to: '/sis/hall-tickets',   icon: Ticket,      roles: ['DEAN'] },
      { label: 'Exam Sessions', to: '/sis/exam/sessions',  icon: CalendarDays, roles: ['DEAN'] },
      { label: 'Exam Centers',  to: '/sis/exam/centers',   icon: MapPin,       roles: ['DEAN'] },
      { label: 'Results',       to: '/sis/results',        icon: ClipboardList, roles: ['DEAN'] },
    ],
  },

  // ── DEAN: Analytics ───────────────────────────────────────────────────────
  {
    heading: 'Analytics',
    items: [
      { label: 'Grade Analytics', to: '/bell-curve', icon: BarChart2, roles: ['DEAN'] },
    ],
  },

  // ── DEAN: Faculty Oversight ────────────────────────────────────────────────
  {
    heading: 'Faculty Oversight',
    items: [
      { label: 'Faculty Directory',   to: '/sis/directory/faculty', icon: UserCheck,      roles: ['DEAN'] },
      { label: 'Course Assignments',  to: '/course-assignments',    icon: ClipboardCheck, roles: ['DEAN'] },
    ],
  },

  // ── DEAN: Academic View ────────────────────────────────────────────────────
  {
    heading: 'Academic View',
    items: [
      { label: 'Syllabus Review', to: '/dean-review',  icon: ClipboardCheck, roles: ['DEAN'] },
      { label: 'Syllabuses',      to: '/syllabuses',   icon: GraduationCap,  roles: ['DEAN'] },
    ],
  },

  // ── ADMIN: Academic Structure ─────────────────────────────────────────────
  {
    heading: 'Academic Structure',
    items: [
      { label: 'Schools',         to: '/sis/schools',         icon: School2,       roles: ['ADMIN'] },
      { label: 'Departments',     to: '/sis/departments',     icon: Building2,     roles: ['ADMIN'] },
      { label: 'Degree Programs', to: '/academics/programs',  icon: GraduationCap, roles: ['ADMIN'] },
      { label: 'Batches',         to: '/academics/batches',   icon: CalendarRange, roles: ['ADMIN'] },
      { label: 'Semesters',       to: '/academics/semesters', icon: Calendar,      roles: ['ADMIN'] },
      { label: 'Sections',        to: '/academics/sections',  icon: LayoutList,    roles: ['ADMIN'] },
    ],
  },

  // ── ADMIN: People ─────────────────────────────────────────────────────────
  {
    heading: 'People',
    items: [
      { label: 'Users',             to: '/users',                   icon: Users,         roles: ['ADMIN'] },
      { label: 'Student Directory', to: '/sis/directory/students',  icon: GraduationCap, roles: ['ADMIN'] },
      { label: 'Faculty Directory', to: '/sis/directory/faculty',   icon: UserCheck,     roles: ['ADMIN'] },
      { label: 'Enrollment Roster', to: '/sis/roster',              icon: UsersRound,    roles: ['ADMIN'] },
      { label: 'Import Users',      to: '/users/bulk-onboarding',   icon: UserPlus,      roles: ['ADMIN'] },
      { label: 'Import History',    to: '/sis/imports',             icon: History,       roles: ['ADMIN'] },
      { label: 'Semester Rollover', to: '/sis/rollover',            icon: RefreshCw,     roles: ['ADMIN'] },
    ],
  },

  // ── ADMIN: Administration ─────────────────────────────────────────────────
  {
    heading: 'Administration',
    items: [
      { label: 'Branding', to: '/settings/branding', icon: Palette,  roles: ['ADMIN'] },
      { label: 'Settings', to: '/settings',           icon: Settings, roles: ['ADMIN'] },
    ],
  },

  // ── ADMIN: Reports ────────────────────────────────────────────────────────
  {
    heading: 'Reports',
    items: [
      { label: 'Enrollment Overview', to: '/sis', icon: LayoutDashboard, roles: ['ADMIN'], exact: true },
    ],
  },

  // ── BOARD: Examination ────────────────────────────────────────────────────
  {
    heading: 'Examination',
    items: [
      { label: 'Exam Paper Review', to: '/exams/board/pending', icon: ClipboardCheck, roles: ['BOARD'] },
      { label: 'Answer Scripts',    to: '/scripts',              icon: ClipboardList,  roles: ['BOARD'] },
      { label: 'Script Evaluation', to: '/scripts/board',        icon: FileText,       roles: ['BOARD'] },
      { label: 'Mark Sheet',        to: '/scripts/ledger',       icon: BookLock,       roles: ['BOARD'] },
      { label: 'Grade Analytics',   to: '/bell-curve',           icon: BarChart2,      roles: ['BOARD'] },
    ],
  },

  // ── STUDENT: My Work ──────────────────────────────────────────────────────
  {
    heading: 'My Work',
    items: [
      { label: 'My Labs',           to: '/student/labs',          icon: FlaskConical,  roles: ['STUDENT'] },
      { label: 'My Research',       to: '/student/research',      icon: Microscope,    roles: ['STUDENT'] },
      { label: 'My Attendance',     to: '/sis/attendance/me',     icon: CalendarCheck, roles: ['STUDENT'] },
      { label: 'My Marks',          to: '/sis/marks/me',          icon: BookMarked,    roles: ['STUDENT'] },
      { label: 'My Hall Ticket',    to: '/sis/hall-tickets/me',   icon: Ticket,        roles: ['STUDENT'] },
      { label: 'My Exam Timetable', to: '/sis/exam/my-timetable', icon: CalendarDays,  roles: ['STUDENT'] },
      { label: 'My Transcript',     to: '/sis/my-transcript',     icon: Award,         roles: ['STUDENT'] },
      { label: 'My Profile',        to: '/sis/me/profile',        icon: UserCircle2,   roles: ['STUDENT'] },
    ],
  },

  // ── EVALUATOR: Evaluate ───────────────────────────────────────────────────
  {
    heading: 'Evaluate',
    items: [
      { label: 'My Evaluations', to: '/evaluator', icon: ClipboardCheck, roles: ['EVALUATOR'] },
    ],
  },

  // ── GUIDE: Research ───────────────────────────────────────────────────────
  {
    heading: 'Research',
    items: [
      { label: 'Research Supervision', to: '/research/problems', icon: Microscope, roles: ['GUIDE'] },
    ],
  },
]

function getGreeting(): string {
  const h = new Date().getHours()
  if (h < 12) return 'Good morning'
  if (h < 17) return 'Good afternoon'
  return 'Good evening'
}

const HONORIFICS = new Set(['dr.', 'prof.', 'mr.', 'ms.', 'mrs.', 'mx.', 'sir'])

function getDisplayFirstName(fullName: string): string {
  const parts = fullName.trim().split(/\s+/).filter(Boolean)
  if (parts.length <= 1) return parts[0] ?? ''
  if (HONORIFICS.has(parts[0].toLowerCase())) return `${parts[0]} ${parts[1]}`
  return parts[0]
}

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
  const { branding } = useBranding()
  const role = user?.role ?? ''

  // Use the registered institution name from branding; fall back to slug-derived label
  const institution = branding.name || prettifySlug(user?.tenantSlug ?? '')

  const setupIncomplete = role === 'ADMIN' && authUser?.firstLogin === true
  const displayName = user?.fullName || user?.email || ''
  const initials = displayName ? getInitials(displayName) : role?.slice(0, 2) || '??'

  const savedLogo    = branding.logoUrl
  const primaryColor = branding.primaryColor

  function isActive(to: string, exact?: boolean): boolean {
    if (exact) return location.pathname === to
    return location.pathname.startsWith(to)
  }

  return (
    <div className="flex flex-col h-full bg-gradient-to-b from-sv-dark via-[#0b1938] to-[#071026] text-white">

      {/* ── Brand header ─────────────────────────────────────────── */}
      <div className="relative px-4 py-4 border-b border-white/10 flex items-center justify-between gap-2 overflow-hidden bg-white/[0.02] backdrop-blur">
        <div className="absolute top-0 left-0 w-32 h-full bg-sv-primary/15 blur-2xl pointer-events-none" />
        <div className="absolute -top-24 -right-24 w-64 h-64 rounded-full bg-emerald-400/10 blur-3xl pointer-events-none" />

        <div className="relative flex items-center gap-2.5 min-w-0">
          {savedLogo ? (
            <div className="relative h-9 w-9 flex-shrink-0 rounded-xl border border-white/10 bg-white/5 backdrop-blur-sm">
              <img
                src={savedLogo}
                alt="Institution logo"
                className="h-full w-full rounded-xl object-contain p-1"
              />
            </div>
          ) : (
            <div className="relative h-9 w-9 flex-shrink-0 rounded-xl bg-sv-primary/10 border border-sv-primary/30">
              <img
                src="/branding/sherpavector-logo.png"
                alt="VIDYA AI"
                className="h-full w-full rounded-xl object-contain p-1.5"
                style={{ filter: 'drop-shadow(0 0 10px rgba(37,99,235,0.35))' }}
              />
            </div>
          )}
          <div className="min-w-0">
            <p
              className="text-[13px] font-black leading-none tracking-wide truncate"
              title={institution}
            >
              {institution}
            </p>
            <p className="text-[10px] text-slate-500 truncate mt-0.5">
              VIDYA AI Workspace
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
      <nav className="flex-1 overflow-y-auto py-4 px-2 space-y-0">
        {NAV_SECTIONS.map((section) => {
          const visibleItems = section.items.filter((item) => item.roles.includes(role))
          if (visibleItems.length === 0) return null

          return (
            <div key={section.heading || '__root'} className="mb-4">
              {section.heading && (
                <div className="flex items-center gap-2 px-2 mb-1.5">
                  <span className="text-[9px] font-extrabold text-slate-500 uppercase tracking-[0.16em] whitespace-nowrap">
                    {section.heading}
                  </span>
                  <div className="flex-1 h-px bg-white/[0.06]" />
                </div>
              )}
              <ul className="space-y-0.5">
                {visibleItems.map((item) => {
                  const active = isActive(item.to, item.exact)
                  return (
                    <li key={item.to + item.label} className="relative">
                      {active && (
                        <div className="absolute -left-2 top-1.5 bottom-1.5 w-[3px] bg-sv-accent rounded-r-full" />
                      )}
                      <Link
                        to={item.to}
                        onClick={onClose}
                        className={`flex items-center gap-2.5 px-3 py-[9px] rounded-xl text-sm font-semibold transition-all duration-150 border border-transparent ${
                          active
                            ? 'text-white shadow-[0_0_0_1px_rgba(37,99,235,0.18),0_14px_34px_rgba(0,0,0,0.25)]'
                            : 'text-slate-400 hover:bg-white/[0.06] hover:text-slate-100 hover:border-white/[0.08]'
                        }`}
                        style={active ? {
                          backgroundColor: `${primaryColor}55`,
                          borderColor: `${primaryColor}50`,
                        } : {}}
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
          className="mx-2 mb-2 flex items-center gap-2 rounded-xl bg-amber-950/60 border border-amber-700/30 px-3 py-2 text-xs text-amber-300 hover:bg-amber-900/40 transition-colors"
        >
          <AlertTriangle className="h-3.5 w-3.5 text-amber-500 flex-shrink-0" />
          Set your permanent password
        </Link>
      )}

      {/* ── Footer ──────────────────────────────────────────────── */}
      <div className="px-3 py-3 border-t border-white/10 bg-white/[0.02]">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-xl bg-sv-primary/22 border border-sv-primary/35 flex items-center justify-center flex-shrink-0 shadow-[0_10px_22px_rgba(0,0,0,0.25)]">
            <span className="text-[10px] font-extrabold text-white/90 uppercase tracking-wide">{initials}</span>
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-[11px] font-semibold text-slate-300 truncate leading-tight">
              {user?.fullName
                ? `${getGreeting()}, ${getDisplayFirstName(user.fullName)}`
                : getGreeting()}
            </p>
            <p className="text-[9px] text-slate-600 leading-tight mt-0.5 uppercase tracking-wide font-medium">
              {role}
            </p>
          </div>
        </div>
        <p className="text-[8px] text-slate-600 mt-2.5 font-extrabold tracking-[0.2em] uppercase">
          Powered by VIDYA AI
        </p>
      </div>

    </div>
  )
}
