import { useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import {
  LayoutDashboard, BookOpen, FlaskConical, Microscope,
  FileText, ClipboardList, BarChart2, X, Users, Settings, AlertTriangle,
  GraduationCap, UserPlus, ClipboardCheck, Palette,
  Building2, Calendar, CalendarRange, LayoutList, UserCheck, BookMarked,
  BookLock, School2, UsersRound, UserCircle2, RefreshCw, CalendarCheck,
  Award, Ticket, MapPin, CalendarDays, History, Gauge, ShieldAlert, Monitor,
  Activity, Scale, ShieldCheck, ScanSearch, Crown, ListChecks,
  Bell, Presentation, Library, PartyPopper, CalendarClock, TrendingUp,
} from 'lucide-react'
import { useCurrentUser } from '@/hooks/useCurrentUser'
import { useAuth, effectiveRoles } from '@/lib/auth'
import { useBranding } from '@/lib/branding'
import { useWorkspace } from '@/lib/workspace'
import { WorkspaceSwitcher } from './WorkspaceSwitcher'

type LucideIconType = typeof LayoutDashboard

interface NavItem {
  label: string
  to: string
  icon: LucideIconType
  // Base-workspace item (the default): visible only when the user's
  // currently active workspace (see WorkspaceSwitcher — user-selectable,
  // not simply user.role) is one of these. This is what keeps a DEAN who
  // also holds a FACULTY grant inside one workspace's navigation at a time
  // instead of the union of every held role.
  roles: string[]
  // Grant-overlay item: attaches to whichever primary workspace holds the
  // grant (e.g. a FACULTY user who also holds an EVALUATOR grant). Ignores
  // primary-role gating and checks the full effective role set instead.
  grantOverlay?: boolean
  allRoles?: string[]     // AND (grant-overlay only): effective role set must also contain all of these
  excludeRoles?: string[] // NOT: hidden if the effective role set contains any of these
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

  // ── FACULTY / DEAN: Account (single shared location — do not duplicate per role) ──
  {
    heading: 'Account',
    items: [
      { label: 'My Profile', to: '/sis/me/profile', icon: UserCircle2, roles: ['FACULTY', 'DEAN'] },
    ],
  },

  // ── FACULTY: My Teaching ───────────────────────────────────────────────────
  {
    heading: 'My Teaching',
    items: [
      { label: 'My Courses',          to: '/my-courses',                   icon: BookOpen,      roles: ['FACULTY'] },
      { label: 'My Responsibilities', to: '/faculty/my-responsibilities',  icon: UsersRound,    roles: ['FACULTY'] },
      { label: 'Syllabuses',          to: '/syllabuses',                   icon: GraduationCap, roles: ['FACULTY'] },
      { label: 'Course Kits',         to: '/course-kits',                  icon: Presentation,  roles: ['FACULTY'] },
      { label: 'Learning Materials',  to: '/learning-packages',            icon: Library,       roles: ['FACULTY'] },
      { label: 'Labs',                to: '/labs',                         icon: FlaskConical,  roles: ['FACULTY'] },
      { label: 'Assignments',         to: '/faculty/assignments',          icon: FileText,      roles: ['FACULTY'] },
      { label: 'Attendance',          to: '/sis/attendance/mark',          icon: CalendarCheck, roles: ['FACULTY'] },
      { label: 'Internal Marks',      to: '/sis/marks/setup',              icon: BookMarked,    roles: ['FACULTY'] },
      { label: 'My Timetable',        to: '/faculty/timetable',            icon: CalendarClock, roles: ['FACULTY'] },
      { label: 'Propose Elective',    to: '/elective-offerings',           icon: ListChecks,    roles: ['FACULTY'] },
    ],
  },

  // ── FACULTY: Research Supervision ─────────────────────────────────────────
  {
    heading: 'Research Supervision',
    items: [
      { label: 'Research Supervision', to: '/research/problems', icon: Microscope, roles: ['FACULTY'] },
    ],
  },

  // ── FACULTY: Assessment ───────────────────────────────────────────────────
  {
    heading: 'Assessment',
    items: [
      { label: 'My Evaluations', to: '/scripts/evaluator', icon: ClipboardList, roles: ['FACULTY'] },
    ],
  },

  // ── FACULTY: Analytics ────────────────────────────────────────────────────
  {
    heading: 'Analytics',
    items: [
      { label: 'Performance Analytics', to: '/sis/attendance/shortage', icon: BarChart2, roles: ['FACULTY'] },
    ],
  },

  // ── DEAN: My Department ───────────────────────────────────────────────────
  {
    heading: 'My Department',
    items: [
      { label: 'My Faculty',         to: '/dean/my-faculty',    icon: UserCheck,      roles: ['DEAN'] },
      { label: 'My Students',        to: '/dean/my-students',   icon: UsersRound,     roles: ['DEAN'] },
    ],
  },

  // ── DEAN: Academic Governance ──────────────────────────────────────────────
  {
    heading: 'Academic Governance',
    items: [
      { label: 'Academic Ownership', to: '/dean/academic-ownership',        icon: LayoutList,    roles: ['DEAN'] },
      { label: 'Programs',            to: '/programs',                       icon: BookMarked,    roles: ['DEAN'] },
      { label: 'Syllabus Review',     to: '/dean-review',                    icon: ClipboardCheck, roles: ['DEAN'] },
      { label: 'Syllabuses',          to: '/syllabuses',                     icon: GraduationCap, roles: ['DEAN'] },
      { label: 'Course Kit Compliance', to: '/dean/course-kit-compliance',  icon: ShieldCheck,   roles: ['DEAN'] },
      { label: 'Timetable Builder',   to: '/timetable/builder',              icon: CalendarClock, roles: ['DEAN'] },
      { label: 'Timetable Review',    to: '/dean/timetable-review',          icon: CalendarClock, roles: ['DEAN'] },
      { label: 'Elective Offerings',  to: '/elective-offerings',             icon: ListChecks,    roles: ['DEAN'] },
    ],
  },

  // ── DEAN: Academic Operations ──────────────────────────────────────────────
  {
    heading: 'Academic Operations',
    items: [
      { label: 'Attendance Analytics',  to: '/sis/attendance/analytics', icon: CalendarCheck, roles: ['DEAN'] },
      { label: 'Internal Marks Report', to: '/sis/marks/report',         icon: BookMarked,    roles: ['DEAN'] },
    ],
  },

  // ── DEAN: Examinations ────────────────────────────────────────────────────
  // Dean is the academic owner of all examination operations. Digital sessions,
  // monitoring, OCR and physical logistics all sit here; Admin retains
  // read-only access to results and analytics.
  {
    heading: 'Examinations',
    items: [
      { label: 'Digital Sessions', to: '/exams/digital',            icon: Monitor,       roles: ['DEAN'] },
      { label: 'Exam Monitoring',  to: '/exams/digital/monitoring', icon: Activity,      roles: ['DEAN'] },
      { label: 'OCR Review Queue', to: '/ocr-review',               icon: ScanSearch,    roles: ['DEAN'] },
      { label: 'Hall Tickets',     to: '/sis/hall-tickets',         icon: Ticket,        roles: ['DEAN'] },
      { label: 'Exam Sessions',    to: '/sis/exam/sessions',        icon: CalendarDays,  roles: ['DEAN'] },
      { label: 'Exam Centers',     to: '/sis/exam/centers',         icon: MapPin,        roles: ['DEAN'] },
      { label: 'Results',          to: '/sis/results',              icon: ClipboardList, roles: ['DEAN'] },
    ],
  },

  // ── DEAN: Analytics ───────────────────────────────────────────────────────
  {
    heading: 'Analytics',
    items: [
      { label: 'Grade Analytics',       to: '/bell-curve',          icon: BarChart2, roles: ['DEAN'] },
      { label: 'Examination Analytics', to: '/dean/exam-analytics', icon: BarChart2, roles: ['DEAN'] },
    ],
  },

  // ── DEAN: My Responsibilities ─────────────────────────────────────────────
  // This section appears only when the Dean holds an active GUIDE or EVALUATOR
  // responsibility grant. Items use allRoles to require DEAN ∩ grant so that
  // plain GUIDE/EVALUATOR users (e.g. Faculty) never see Dean-scoped routes.
  {
    heading: 'My Responsibilities',
    items: [
      {
        label: 'Guide Assignments',
        to: '/research/problems',
        icon: Microscope,
        roles: ['DEAN'],
        allRoles: ['GUIDE'],
      },
      {
        label: 'Evaluation Assignments',
        to: '/dean/evaluation-assignments',
        icon: ClipboardCheck,
        roles: ['DEAN'],
        allRoles: ['EVALUATOR'],
      },
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
      { label: 'Student Directory',    to: '/sis/directory/students', icon: GraduationCap, roles: ['ADMIN'] },
      { label: 'Faculty Directory',    to: '/sis/directory/faculty',  icon: UserCheck,     roles: ['ADMIN'] },
      { label: 'Governance Directory', to: '/sis/governance',          icon: Crown,         roles: ['ADMIN'] },
      { label: 'Enrollment Roster', to: '/sis/roster',              icon: UsersRound,    roles: ['ADMIN'] },
      { label: 'Import Users',      to: '/users/bulk-onboarding',   icon: UserPlus,      roles: ['ADMIN'] },
      { label: 'Import History',    to: '/sis/imports',             icon: History,       roles: ['ADMIN'] },
      { label: 'Section Capacity',  to: '/sis/capacity',            icon: Gauge,         roles: ['ADMIN'] },
      { label: 'Semester Rollover', to: '/sis/rollover',            icon: RefreshCw,     roles: ['ADMIN'] },
    ],
  },

  // ── ADMIN: Examination Reports ─────────────────────────────────────────────
  // Dean owns examination operations. Admin retains read-only access to
  // results, analytics, and compliance; cannot create sessions or approve results.
  {
    heading: 'Examination Reports',
    items: [
      { label: 'Results',               to: '/sis/results',          icon: ClipboardList, roles: ['ADMIN'] },
      { label: 'Examination Analytics', to: '/admin/exam-analytics', icon: BarChart2,     roles: ['ADMIN'] },
      { label: 'Compliance & Audit',    to: '/admin/compliance',     icon: ShieldCheck,   roles: ['ADMIN'] },
    ],
  },

  // ── ADMIN: Administration ─────────────────────────────────────────────────
  {
    heading: 'Administration',
    items: [
      { label: 'Branding',        to: '/settings/branding', icon: Palette,     roles: ['ADMIN'] },
      { label: 'Settings',        to: '/settings',          icon: Settings,    roles: ['ADMIN'] },
      { label: 'Data Validation', to: '/sis/validation',    icon: ShieldAlert, roles: ['ADMIN'] },
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
  // BOARD can be a base role (its own login) OR a grant layered onto a
  // FACULTY account (faculty_role_grants.role_code = 'BOARD'), same as
  // GUIDE/EVALUATOR — hence grantOverlay so a FACULTY-primary user who also
  // holds a BOARD grant keeps this section. excludeRoles: DEAN so a Dean
  // holding a BOARD grant isn't handed the full raw Board workspace (no
  // dean-scoped Board view exists yet, matching the GUIDE/EVALUATOR pattern).
  {
    heading: 'Examination',
    items: [
      { label: 'Exam Paper Review', to: '/exams/board/pending',        icon: ClipboardCheck, roles: ['BOARD'], grantOverlay: true, excludeRoles: ['DEAN'] },
      { label: 'Answer Scripts',    to: '/scripts',                     icon: ClipboardList,  roles: ['BOARD'], grantOverlay: true, excludeRoles: ['DEAN'] },
      { label: 'Script Evaluation', to: '/scripts/board',               icon: FileText,       roles: ['BOARD'], grantOverlay: true, excludeRoles: ['DEAN'] },
      { label: 'Mark Sheet',        to: '/scripts/ledger',              icon: BookLock,       roles: ['BOARD'], grantOverlay: true, excludeRoles: ['DEAN'] },
      { label: 'Grade Analytics',   to: '/bell-curve',                  icon: BarChart2,      roles: ['BOARD'], grantOverlay: true, excludeRoles: ['DEAN'] },
      { label: 'Digital Sessions',  to: '/exams/digital',               icon: Monitor,        roles: ['BOARD'], grantOverlay: true, excludeRoles: ['DEAN'] },
      { label: 'Exam Monitoring',   to: '/exams/digital/monitoring',    icon: Activity,       roles: ['BOARD'], grantOverlay: true, excludeRoles: ['DEAN'] },
      { label: 'Exam Analytics',    to: '/exams/digital/analytics',     icon: BarChart2,      roles: ['BOARD'], grantOverlay: true, excludeRoles: ['DEAN'] },
      { label: 'Board Analytics',   to: '/board/exam-analytics',        icon: Scale,          roles: ['BOARD'], grantOverlay: true, excludeRoles: ['DEAN'] },
      { label: 'Compliance & Audit', to: '/board/compliance',           icon: ShieldCheck,    roles: ['BOARD'], grantOverlay: true, excludeRoles: ['DEAN'] },
    ],
  },

  // ── STUDENT: Academics ────────────────────────────────────────────────────
  {
    heading: 'Academics',
    items: [
      { label: 'My Subjects',         to: '/student/subjects',           icon: BookOpen,      roles: ['STUDENT'] },
      { label: 'Assignments',         to: '/student/assignments',        icon: ListChecks,    roles: ['STUDENT'] },
      { label: 'Labs',                to: '/student/labs',               icon: FlaskConical,  roles: ['STUDENT'] },
      { label: 'Course Kits',         to: '/student/course-kits',        icon: Presentation,  roles: ['STUDENT'] },
      { label: 'Learning Materials',  to: '/student/learning-materials', icon: Library,       roles: ['STUDENT'] },
      { label: 'Research',           to: '/student/research',            icon: Microscope,    roles: ['STUDENT'] },
      { label: 'Electives',          to: '/student/electives',           icon: LayoutList,    roles: ['STUDENT'] },
    ],
  },

  // ── STUDENT: Assessments ──────────────────────────────────────────────────
  {
    heading: 'Assessments',
    items: [
      { label: 'Digital Exams',    to: '/student/exams/digital',   icon: Monitor,       roles: ['STUDENT'] },
      { label: 'Attendance',       to: '/sis/attendance/me',       icon: CalendarCheck, roles: ['STUDENT'] },
      { label: 'Internal Marks',   to: '/sis/marks/me',            icon: BookMarked,    roles: ['STUDENT'] },
      { label: 'Semester Results', to: '/student/semester-results', icon: BarChart2,     roles: ['STUDENT'] },
      { label: 'Hall Ticket',      to: '/sis/hall-tickets/me',     icon: Ticket,        roles: ['STUDENT'] },
      { label: 'Exam Timetable',   to: '/sis/exam/my-timetable',   icon: CalendarDays,  roles: ['STUDENT'] },
      { label: 'Transcript',       to: '/sis/my-transcript',       icon: Award,         roles: ['STUDENT'] },
      { label: 'Timetable',        to: '/student/timetable',       icon: CalendarClock, roles: ['STUDENT'] },
      { label: 'Academic Progress', to: '/student/academic-progress', icon: TrendingUp, roles: ['STUDENT'] },
    ],
  },

  // ── STUDENT: Services ─────────────────────────────────────────────────────
  {
    heading: 'Services',
    items: [
      { label: 'Calendar',      to: '/student/calendar',   icon: CalendarRange, roles: ['STUDENT'] },
      { label: 'Events',        to: '/student/events',     icon: PartyPopper,   roles: ['STUDENT'] },
      { label: 'Notifications', to: '/notifications',      icon: Bell,          roles: ['STUDENT'] },
      { label: 'My Profile',    to: '/sis/me/profile',     icon: UserCircle2,   roles: ['STUDENT'] },
    ],
  },

  // ── EVALUATOR: Evaluate ───────────────────────────────────────────────────
  // excludeRoles: DEAN because a Dean with EVALUATOR grant uses the dean-scoped
  // /dean/evaluation-assignments view surfaced under My Responsibilities instead.
  {
    heading: 'Evaluate',
    items: [
      { label: 'My Evaluations', to: '/evaluator', icon: ClipboardCheck, roles: ['EVALUATOR'], grantOverlay: true, excludeRoles: ['DEAN'] },
    ],
  },

  // ── GUIDE: Research ───────────────────────────────────────────────────────
  // excludeRoles: DEAN because a Dean with GUIDE grant uses /research/problems
  // surfaced under My Responsibilities with dean-level context instead.
  {
    heading: 'Research',
    items: [
      { label: 'Research Supervision', to: '/research/problems', icon: Microscope, roles: ['GUIDE'], grantOverlay: true, excludeRoles: ['DEAN'] },
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

/** Sample a logo's average luminance so we can keep it visible on the dark
 *  sidebar.  Returns 'dark' (needs a light chip behind it), 'light' (fine on the
 *  dark sidebar), or null while loading.  On any read failure (e.g. a
 *  CORS-tainted canvas) we assume 'dark' — the safe choice that guarantees the
 *  logo never blends into the background. */
function useLogoLuminance(url: string | null | undefined): 'dark' | 'light' | null {
  const [tone, setTone] = useState<'dark' | 'light' | null>(null)
  useEffect(() => {
    if (!url) { setTone(null); return }
    let cancelled = false
    const img = new Image()
    img.crossOrigin = 'anonymous'
    img.onload = () => {
      try {
        const canvas = document.createElement('canvas')
        const w = (canvas.width = 32)
        const h = (canvas.height = 32)
        const ctx = canvas.getContext('2d')
        if (!ctx) return
        ctx.drawImage(img, 0, 0, w, h)
        const { data } = ctx.getImageData(0, 0, w, h)
        let sum = 0, count = 0
        for (let i = 0; i < data.length; i += 4) {
          const a = data[i + 3]
          if (a < 16) continue // ignore (near-)transparent pixels
          sum += (0.2126 * data[i] + 0.7152 * data[i + 1] + 0.0722 * data[i + 2]) * (a / 255)
          count++
        }
        if (cancelled) return
        // All-transparent (e.g. a glyph-only mark) → treat as dark to be safe.
        setTone(count === 0 ? 'dark' : (sum / count) < 110 ? 'dark' : 'light')
      } catch {
        if (!cancelled) setTone('dark')
      }
    }
    img.onerror = () => { if (!cancelled) setTone('dark') }
    img.src = url
    return () => { cancelled = true }
  }, [url])
  return tone
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
  // The active workspace — user-selectable (see WorkspaceSwitcher), defaults
  // to the base login role, persisted per-user in localStorage. Base-workspace
  // nav items are gated to this alone so a DEAN who also holds a FACULTY
  // grant stays inside one workspace's navigation at a time instead of seeing
  // the union of every held role, and can explicitly switch to the other.
  const { activeWorkspace } = useWorkspace()
  // Full effective role set (base role + active responsibility grants) —
  // used only for grant-overlay items (roles held ON TOP of the active
  // workspace, e.g. a FACULTY user who also evaluates) and for allRoles/
  // excludeRoles intersection checks, never for base-workspace visibility.
  const roleSet = effectiveRoles(user)

  // Use the registered institution name from branding; fall back to slug-derived label
  const institution = branding.name || prettifySlug(user?.tenantSlug ?? '')

  const setupIncomplete = role === 'ADMIN' && authUser?.firstLogin === true
  const displayName = user?.fullName || user?.email || ''
  const initials = displayName ? getInitials(displayName) : role?.slice(0, 2) || '??'

  const savedLogo    = branding.logoUrl
  const primaryColor = branding.primaryColor
  // Logo-aware: a dark logo gets a light chip so it never blends into the sidebar.
  const logoTone     = useLogoLuminance(savedLogo)

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
            <div
              className={`relative h-9 w-9 flex-shrink-0 rounded-xl backdrop-blur-sm transition-colors ${
                logoTone === 'dark'
                  ? 'bg-white border border-black/5 shadow-sm'
                  : 'bg-white/5 border border-white/10'
              }`}
            >
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

      {/* ── Workspace switcher — hidden when the user has only one workspace ── */}
      <WorkspaceSwitcher />

      {/* ── Nav ──────────────────────────────────────────────────── */}
      <nav className="flex-1 overflow-y-auto py-4 px-2 space-y-0">
        {NAV_SECTIONS.map((section) => {
          const visibleItems = section.items.filter((item) => {
            if (item.grantOverlay) {
              if (!item.roles.some((r) => roleSet.has(r))) return false
            } else if (!item.roles.includes(activeWorkspace)) {
              return false
            }
            if (item.allRoles && !item.allRoles.every((r) => roleSet.has(r))) return false
            if (item.excludeRoles && item.excludeRoles.some((r) => roleSet.has(r))) return false
            return true
          })
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
              {activeWorkspace}
            </p>
          </div>
        </div>
      </div>

    </div>
  )
}
