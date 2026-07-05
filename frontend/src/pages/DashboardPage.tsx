import { useNavigate, Link } from 'react-router-dom'
import {
  BookOpen, Layers, FlaskConical, Microscope, FileText, ClipboardList,
  BarChart2, CheckCircle, Circle, GraduationCap, Package,
  ClipboardCheck, Cpu, ShieldCheck, Building2, Users,
  School2, CalendarRange, Calendar, LayoutList, UserCheck, UsersRound,
  CalendarCheck, BookMarked, Ticket, CalendarDays, MapPin,
  Palette, Settings,
} from 'lucide-react'
import { PageShell } from '@/components/shell/PageShell'
import { PageEmpty } from '@/components/shared/PageEmpty'
import { useCurrentUser } from '@/hooks/useCurrentUser'
import { useAuth } from '@/lib/auth'
import { useBranding } from '@/lib/branding'
import { useWorkspace } from '@/lib/workspace'
import { MyCoursesBanner } from '@/components/assignments/MyCoursesBanner'
import { StudentDashboard } from '@/pages/student/StudentDashboard'
import {
  StatCard, ModuleCardItem, AdminActionCard, getGreeting, getDisplayFirstName,
  type ModuleCard, type AdminCard,
} from '@/components/dashboard/shared'

const CARDS: ModuleCard[] = [
  // ── Teach & Prepare — Program Builder is governance/ADMIN scope; DEAN only ─
  {
    title: 'Academic Programs',
    description: 'Design degree programs, add courses, and manage learning outcomes.',
    to: '/programs',
    icon: BookOpen,
    roles: ['DEAN'],
    badge: 'bg-blue-50 text-blue-600 border-blue-100',
    bar:   'bg-blue-500',
    section: 'teach',
  },
  {
    title: 'Syllabuses',
    description: 'Generate AI-assisted syllabuses with CO-PO matrices and compliance checks.',
    to: '/syllabuses',
    icon: GraduationCap,
    roles: ['FACULTY', 'DEAN'],
    badge: 'bg-violet-50 text-violet-600 border-violet-100',
    bar:   'bg-violet-500',
    section: 'teach',
  },
  {
    title: 'Course Kits',
    description: 'Generate lecture slides and assignments for your courses.',
    to: '/course-kits',
    icon: Layers,
    roles: ['FACULTY'],
    badge: 'bg-indigo-50 text-indigo-600 border-indigo-100',
    bar:   'bg-indigo-500',
    section: 'teach',
  },
  {
    title: 'Learning Materials',
    description: 'Build and curate multimedia learning packages for your students.',
    to: '/learning-packages',
    icon: Package,
    roles: ['FACULTY'],
    badge: 'bg-pink-50 text-pink-600 border-pink-100',
    bar:   'bg-pink-500',
    section: 'teach',
  },

  // ── Assess & Research — FACULTY and GUIDE ─────────────────────────────────
  {
    title: 'Lab Assignments',
    description: 'Create, publish, and evaluate written and code lab submissions.',
    to: '/labs',
    icon: FlaskConical,
    roles: ['FACULTY'],
    badge: 'bg-emerald-50 text-emerald-600 border-emerald-100',
    bar:   'bg-emerald-500',
    section: 'assess',
  },
  {
    title: 'Research Supervision',
    description: 'Review student proposals, supervise documents, and ratify viva reports.',
    to: '/research/problems',
    icon: Microscope,
    roles: ['FACULTY', 'GUIDE'],
    badge: 'bg-purple-50 text-purple-600 border-purple-100',
    bar:   'bg-purple-500',
    section: 'assess',
  },
  {
    title: 'Exam Papers',
    description: 'Set AI-assisted exam papers, submit for board review, and seal for release.',
    to: '/exams',
    icon: FileText,
    roles: ['FACULTY'],
    badge: 'bg-amber-50 text-amber-600 border-amber-100',
    bar:   'bg-amber-500',
    section: 'assess',
  },

  // ── Board — examination governance ────────────────────────────────────────
  {
    title: 'Exam Paper Review',
    description: 'Review and approve submitted exam papers before they are sealed.',
    to: '/exams/board/pending',
    icon: ClipboardCheck,
    roles: ['BOARD'],
    badge: 'bg-amber-50 text-amber-600 border-amber-100',
    bar:   'bg-amber-500',
    section: 'assess',
  },
  {
    title: 'Answer Scripts',
    description: 'Upload, evaluate, and finalise student answer scripts with identity masking.',
    to: '/scripts',
    icon: ClipboardList,
    roles: ['BOARD'],
    badge: 'bg-orange-50 text-orange-600 border-orange-100',
    bar:   'bg-orange-500',
    section: 'assess',
  },

  // ── Analytics ─────────────────────────────────────────────────────────────
  {
    title: 'Grade Analytics',
    description: 'Analyse score distributions and advise on normalisation. Advisory only.',
    to: '/bell-curve',
    icon: BarChart2,
    roles: ['DEAN', 'BOARD'],
    badge: 'bg-teal-50 text-teal-600 border-teal-100',
    bar:   'bg-teal-500',
    section: 'analytics',
  },

  // ── Evaluate ──────────────────────────────────────────────────────────────
  {
    title: 'My Evaluations',
    description: 'Review and score assigned student submissions.',
    to: '/evaluator',
    icon: ClipboardCheck,
    roles: ['EVALUATOR'],
    badge: 'bg-sky-50 text-sky-600 border-sky-100',
    bar:   'bg-sky-500',
    section: 'evaluate',
  },
]

const MODULE_SECTIONS = [
  { key: 'teach',    label: 'Teach & Prepare' },
  { key: 'assess',   label: 'Assess & Research' },
  { key: 'analytics',label: 'Analytics' },
  { key: 'evaluate', label: 'Evaluation' },
]

// Responsibility-chip colors (GUIDE / EVALUATOR / BOARD)
const DASH_RESP_COLORS: Record<string, string> = {
  GUIDE: '#6366f1', EVALUATOR: '#10b981', BOARD: '#f59e0b',
}

// Entry route for each responsibility's EXISTING workflow (role switching —
// no rebuild). A FACULTY account with these grants switches into the same
// Guide / Evaluator / Board screens a standalone account would use.
const RESP_ROUTES: Record<string, string> = {
  GUIDE:     '/research/problems',
  EVALUATOR: '/evaluator',
  BOARD:     '/exams/board/pending',
}

const ROLE_SUBTITLE: Record<string, string> = {
  ADMIN:     'Manage your institution\'s academic structure, people, and settings.',
  DEAN:      'Oversee academic operations, examinations, results, and institutional analytics.',
  FACULTY:   'Build courses, set exams, evaluate labs, and supervise research.',
  BOARD:     'Review exam papers, evaluate scripts, and advise on grade distributions.',
  GUIDE:     'Review research proposals assigned to you and supervise student projects.',
  STUDENT:   'Your academic workspace — attendance, marks, exams, and research at a glance.',
  EVALUATOR: 'Review and score student submissions assigned to you.',
}

const ROLE_CONTEXT: Partial<Record<string, { heading: string; body: string }>> = {
  GUIDE: {
    heading: 'How supervision works',
    body: 'Students submit proposals → you receive a notification → review via Research Supervision to accept, request revision, or reject. Viva sessions are scheduled by the admin.',
  },
  BOARD: {
    heading: 'Board responsibilities',
    body: 'Review submitted exam papers and approve or return with feedback. Once evaluators finalise scripts, review and ratify marks. Bell curve analysis is advisory — raw scores are never altered.',
  },
}

// ---------------------------------------------------------------------------
// Admin onboarding checklist
// ---------------------------------------------------------------------------

interface OnboardingItem {
  label: string
  done: boolean
  href: string
}

function AdminOnboarding({ passwordChanged }: { passwordChanged: boolean }) {
  const visitedUsers    = localStorage.getItem('vidya_onboarding_users')    === '1'
  const visitedSettings = localStorage.getItem('vidya_onboarding_settings') === '1'

  const items: OnboardingItem[] = [
    { label: 'Sign in to VIDYA AI',            done: true,             href: '/dashboard' },
    { label: 'Set your permanent password',    done: passwordChanged,  href: '/settings'  },
    { label: 'Add faculty and students',       done: visitedUsers,     href: '/users'     },
    { label: 'Review institution settings',    done: visitedSettings,  href: '/settings'  },
  ]
  const completed = items.filter((i) => i.done).length

  if (completed === items.length) {
    return (
      <div data-testid="onboarding-checklist" className="flex items-center gap-3 rounded-xl border border-emerald-200 bg-emerald-50 px-5 py-4">
        <CheckCircle className="h-5 w-5 text-emerald-600 flex-shrink-0" />
        <div className="min-w-0">
          <p className="text-sm font-semibold text-emerald-800">Institution ready</p>
          <p className="text-xs text-emerald-700 mt-0.5">
            Setup complete. Add more users from{' '}
            <Link to="/users" className="font-semibold underline underline-offset-2 hover:text-emerald-900">
              Users
            </Link>{' '}
            whenever needed.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div data-testid="onboarding-checklist" className="rounded-xl border border-sv-primary/20 bg-sv-light p-5">
      <div className="flex items-center justify-between mb-4">
        <div>
          <p className="text-sm font-bold text-sv-dark">Getting started</p>
          <p className="text-xs text-gray-500 mt-0.5">Complete these steps to set up your institution</p>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="h-1.5 w-16 bg-gray-200 rounded-full overflow-hidden">
            <div
              className="h-full bg-sv-primary rounded-full transition-all"
              style={{ width: `${(completed / items.length) * 100}%` }}
            />
          </div>
          <p className="text-xs text-gray-500 font-medium whitespace-nowrap">{completed}/{items.length}</p>
        </div>
      </div>
      <ul className="space-y-2.5">
        {items.map((item) => (
          <li key={item.label} className="flex items-center gap-2.5">
            {item.done
              ? <CheckCircle className="h-4 w-4 text-sv-primary flex-shrink-0" />
              : <Circle      className="h-4 w-4 text-gray-300 flex-shrink-0" />
            }
            {item.done ? (
              <span className="text-sm text-gray-400 line-through">{item.label}</span>
            ) : (
              <Link to={item.href} className="text-sm text-sv-dark font-medium hover:text-sv-primary hover:underline">
                {item.label}
              </Link>
            )}
          </li>
        ))}
      </ul>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Admin workspace sections
// ---------------------------------------------------------------------------

interface AdminSection {
  heading: string
  cards: AdminCard[]
}

const ADMIN_SECTIONS: AdminSection[] = [
  {
    heading: 'Academic Setup',
    cards: [
      {
        title: 'Schools',
        description: 'Manage schools and faculties within the institution.',
        to: '/sis/schools',
        icon: School2,
        bar: 'bg-indigo-500',
        badge: 'bg-indigo-50 text-indigo-600 border-indigo-100',
      },
      {
        title: 'Departments',
        description: 'Configure departments under each school.',
        to: '/sis/departments',
        icon: Building2,
        bar: 'bg-blue-500',
        badge: 'bg-blue-50 text-blue-600 border-blue-100',
      },
      {
        title: 'Programs',
        description: 'Define degree programs, courses, and learning outcomes.',
        to: '/academics/programs',
        icon: GraduationCap,
        bar: 'bg-violet-500',
        badge: 'bg-violet-50 text-violet-600 border-violet-100',
      },
      {
        title: 'Batches',
        description: 'Set up academic batches and manage intake years.',
        to: '/academics/batches',
        icon: CalendarRange,
        bar: 'bg-sky-500',
        badge: 'bg-sky-50 text-sky-600 border-sky-100',
      },
      {
        title: 'Semesters',
        description: 'Configure semesters and manage the academic calendar.',
        to: '/academics/semesters',
        icon: Calendar,
        bar: 'bg-cyan-500',
        badge: 'bg-cyan-50 text-cyan-600 border-cyan-100',
      },
      {
        title: 'Sections',
        description: 'Create and organise class sections for batches.',
        to: '/academics/sections',
        icon: LayoutList,
        bar: 'bg-teal-500',
        badge: 'bg-teal-50 text-teal-600 border-teal-100',
      },
    ],
  },
  {
    heading: 'People',
    cards: [
      {
        title: 'Users',
        description: 'Create and manage user accounts for faculty and students.',
        to: '/users',
        icon: Users,
        bar: 'bg-slate-500',
        badge: 'bg-slate-50 text-slate-600 border-slate-100',
      },
      {
        title: 'Faculty',
        description: 'Browse faculty profiles, assignments, and contact details.',
        to: '/sis/directory/faculty',
        icon: UserCheck,
        bar: 'bg-emerald-500',
        badge: 'bg-emerald-50 text-emerald-600 border-emerald-100',
      },
      {
        title: 'Students',
        description: 'Search the student directory and view profiles and USNs.',
        to: '/sis/directory/students',
        icon: Users,
        bar: 'bg-green-500',
        badge: 'bg-green-50 text-green-600 border-green-100',
      },
      {
        title: 'Enrollment',
        description: 'Manage course enrollments, moves, and withdrawals.',
        to: '/sis/roster',
        icon: UsersRound,
        bar: 'bg-lime-500',
        badge: 'bg-lime-50 text-lime-600 border-lime-100',
      },
    ],
  },
  {
    heading: 'Administration',
    cards: [
      {
        title: 'Branding',
        description: 'Customise institution name, logo, and colour scheme.',
        to: '/settings/branding',
        icon: Palette,
        bar: 'bg-pink-500',
        badge: 'bg-pink-50 text-pink-600 border-pink-100',
      },
      {
        title: 'Settings',
        description: 'Review and update institution account and security settings.',
        to: '/settings',
        icon: Settings,
        bar: 'bg-gray-500',
        badge: 'bg-gray-50 text-gray-600 border-gray-100',
      },
    ],
  },
]

const DEAN_SECTIONS: AdminSection[] = [
  {
    heading: 'Academic Operations',
    cards: [
      {
        title: 'Attendance',
        description: 'Monitor attendance across sections, flag shortages, and view analytics.',
        to: '/sis/attendance/analytics',
        icon: CalendarCheck,
        bar: 'bg-amber-500',
        badge: 'bg-amber-50 text-amber-600 border-amber-100',
      },
      {
        title: 'Internal Marks',
        description: 'Review internal assessment marks submitted by faculty across programs.',
        to: '/sis/marks/report',
        icon: BookMarked,
        bar: 'bg-orange-500',
        badge: 'bg-orange-50 text-orange-600 border-orange-100',
      },
    ],
  },
  {
    heading: 'Examinations',
    cards: [
      {
        title: 'Hall Tickets',
        description: 'Manage eligibility rules and publish hall tickets for examinations.',
        to: '/sis/hall-tickets',
        icon: Ticket,
        bar: 'bg-yellow-500',
        badge: 'bg-yellow-50 text-yellow-600 border-yellow-100',
      },
      {
        title: 'Exam Sessions',
        description: 'Schedule sessions, allocate seating, and manage invigilation.',
        to: '/sis/exam/sessions',
        icon: CalendarDays,
        bar: 'bg-red-500',
        badge: 'bg-red-50 text-red-600 border-red-100',
      },
      {
        title: 'Exam Centers',
        description: 'Configure examination venues and room capacity.',
        to: '/sis/exam/centers',
        icon: MapPin,
        bar: 'bg-rose-500',
        badge: 'bg-rose-50 text-rose-600 border-rose-100',
      },
      {
        title: 'Results',
        description: 'Declare results, issue grade cards, and publish rank lists.',
        to: '/sis/results',
        icon: ClipboardList,
        bar: 'bg-pink-500',
        badge: 'bg-pink-50 text-pink-600 border-pink-100',
      },
    ],
  },
  {
    heading: 'Analytics',
    cards: [
      {
        title: 'Grade Analytics',
        description: 'Analyse score distributions and advise on normalisation. Advisory only.',
        to: '/bell-curve',
        icon: BarChart2,
        bar: 'bg-teal-500',
        badge: 'bg-teal-50 text-teal-600 border-teal-100',
      },
    ],
  },
  {
    heading: 'My Department',
    cards: [
      {
        title: 'My Faculty',
        description: 'Browse faculty in your department — primary assignment or active teaching.',
        to: '/dean/my-faculty',
        icon: UserCheck,
        bar: 'bg-emerald-500',
        badge: 'bg-emerald-50 text-emerald-600 border-emerald-100',
      },
      {
        title: 'My Students',
        description: 'View students enrolled in programs under your department.',
        to: '/dean/my-students',
        icon: UsersRound,
        bar: 'bg-green-500',
        badge: 'bg-green-50 text-green-600 border-green-100',
      },
      {
        title: 'Academic Ownership',
        description: 'Assign faculty to courses, govern programs, and report on teaching coverage.',
        to: '/dean/academic-ownership',
        icon: ClipboardCheck,
        bar: 'bg-teal-500',
        badge: 'bg-teal-50 text-teal-600 border-teal-100',
      },
    ],
  },
]

function prettifySlug(slug: string): string {
  if (!slug) return 'Institution'
  return slug.split('-').map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function DashboardPage() {
  const navigate = useNavigate()
  const user     = useCurrentUser()
  const { user: authUser } = useAuth()
  const { branding } = useBranding()
  // Driven by the active workspace (see WorkspaceSwitcher), not the raw base
  // login role — so a DEAN who switches into the Faculty workspace sees the
  // Faculty dashboard content, and vice versa. Reuses this exact page/logic
  // for every workspace; nothing new is built per workspace.
  const { activeWorkspace } = useWorkspace()
  const role = activeWorkspace

  const visibleCards = CARDS.filter((c) => c.roles.includes(role))
  const displayFirstName = user?.fullName ? getDisplayFirstName(user.fullName) : null
  const subtitle     = ROLE_SUBTITLE[role] ?? 'Select a module below to get started.'
  const roleContext  = ROLE_CONTEXT[role]
  const institution  = branding.name || prettifySlug(user?.tenantSlug ?? '')

  return (
    <PageShell>

      {/* ── Welcome header ─────────────────────────────────────── */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-[10px] font-bold text-sv-primary uppercase tracking-[0.18em] mb-1.5">
            {institution} · VIDYA AI Workspace
          </p>
          {/* STUDENT's greeting lives in the richer WelcomeCard below (photo + program/batch/section) */}
          {role !== 'STUDENT' && (
            <>
              <h1 className="text-2xl font-bold text-gray-900 leading-tight">
                {getGreeting()}{displayFirstName ? `, ${displayFirstName}` : ''}
              </h1>
              <p className="text-sm text-gray-500 mt-1">{subtitle}</p>
            </>
          )}
        </div>
        <div className="hidden sm:flex items-center gap-1.5 bg-sv-light border border-sv-primary/20 text-sv-primary text-[11px] font-bold px-3 py-1.5 rounded-full whitespace-nowrap flex-shrink-0">
          <span className="w-1.5 h-1.5 rounded-full bg-sv-accent animate-pulse" />
          AI Platform Active
        </div>
      </div>

      {/* ── Stats strip — role-aware, hidden for narrow single-purpose roles ── */}
      {!['STUDENT', 'GUIDE'].includes(role) && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          {role === 'ADMIN' ? (
            <>
              <StatCard label="Institution"   value={institution}     icon={Building2}  accent />
              <StatCard label="Access level"  value="Administrator"   icon={ShieldCheck} />
              <StatCard label="Modules"       value={String(visibleCards.length)} icon={Cpu} />
            </>
          ) : role === 'DEAN' ? (
            <>
              <StatCard label="Institution"  value={institution}  icon={Building2}  accent />
              <StatCard label="Role"         value="Dean"         icon={ShieldCheck} />
              <StatCard label="Operations"   value="Active"       icon={CalendarCheck} />
            </>
          ) : (
            <>
              <StatCard label="Modules available" value={String(visibleCards.length)} icon={Cpu} accent />
              <StatCard label="Access level"      value={role || '—'}  icon={ShieldCheck} />
              <StatCard label="Workspace"         value={institution}  icon={Building2} />
            </>
          )}
        </div>
      )}

      {/* ── My Responsibilities — role-switch into existing workflows ── */}
      {role === 'FACULTY' && (authUser?.responsibilities?.length ?? 0) > 0 && (
        <div className="rounded-xl border border-gray-200 bg-white px-4 py-3.5 shadow-sm">
          <div className="flex items-center gap-1.5 mb-2.5">
            <ShieldCheck className="h-3.5 w-3.5 text-sv-primary" />
            <span className="text-xs font-semibold text-gray-600">My Responsibilities</span>
            <span className="text-[11px] text-gray-400">— one login, switch into each workflow.</span>
          </div>
          <div className="flex flex-wrap gap-2">
            {authUser!.responsibilities.map((r) => {
              const c     = DASH_RESP_COLORS[r] ?? '#64748b'
              const route = RESP_ROUTES[r]
              return (
                <button
                  key={r}
                  disabled={!route}
                  onClick={() => route && navigate(route)}
                  className="inline-flex items-center gap-1.5 text-sm font-semibold px-3.5 py-1.5 rounded-lg transition-colors disabled:opacity-60"
                  style={{ background: `${c}14`, color: c, border: `1px solid ${c}40` }}
                >
                  <ShieldCheck className="h-3.5 w-3.5" />
                  {r}
                </button>
              )
            })}
          </div>
        </div>
      )}

      {/* ── Admin onboarding ───────────────────────────────────── */}
      {role === 'ADMIN' && authUser && (
        <AdminOnboarding passwordChanged={!authUser.firstLogin} />
      )}

      {/* ── Admin workspace ─────────────────────────────────────── */}
      {role === 'ADMIN' && (
        <div className="space-y-8">
          {ADMIN_SECTIONS.map((section) => (
            <div key={section.heading}>
              <div className="flex items-center gap-3 mb-4">
                <h2 className="text-xs font-bold text-foreground uppercase tracking-widest whitespace-nowrap">
                  {section.heading}
                </h2>
                <div className="flex-1 h-px bg-gray-100" />
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                {section.cards.map((card) => (
                  <AdminActionCard
                    key={card.title}
                    card={card}
                    onClick={() => card.to && navigate(card.to)}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ── Dean operational workspace ─────────────────────────── */}
      {role === 'DEAN' && (
        <div className="space-y-8">
          {DEAN_SECTIONS.map((section) => (
            <div key={section.heading}>
              <div className="flex items-center gap-3 mb-4">
                <h2 className="text-xs font-bold text-foreground uppercase tracking-widest whitespace-nowrap">
                  {section.heading}
                </h2>
                <div className="flex-1 h-px bg-gray-100" />
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                {section.cards.map((card) => (
                  <AdminActionCard
                    key={card.title}
                    card={card}
                    onClick={() => card.to && navigate(card.to)}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ── My Courses — FACULTY only ──────────────────────────── */}
      {role === 'FACULTY' && <MyCoursesBanner />}

      {/* ── Student workspace — its own composed dashboard, not the generic module grid ── */}
      {role === 'STUDENT' && <StudentDashboard />}

      {/* ── Module sections — Faculty, Board, Guide, Evaluator ── */}
      {!['ADMIN', 'DEAN', 'STUDENT'].includes(role) && visibleCards.length > 0 && (
        <div className="space-y-8">
          {MODULE_SECTIONS.map((section) => {
            const sectionCards = visibleCards.filter((c) => c.section === section.key)
            if (sectionCards.length === 0) return null

            return (
              <div key={section.key}>
                <div className="flex items-center gap-3 mb-4">
                  <h2 className="text-xs font-bold text-foreground uppercase tracking-widest whitespace-nowrap">
                    {section.label}
                  </h2>
                  <div className="flex-1 h-px bg-gray-100" />
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                  {sectionCards.map((card) => (
                    <ModuleCardItem
                      key={card.to}
                      card={card}
                      onClick={() => navigate(card.to)}
                    />
                  ))}
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* ── Contextual guidance (GUIDE, BOARD) ──────────────── */}
      {roleContext && (
        <div className="rounded-xl border border-sv-primary/10 bg-sv-light px-5 py-4 space-y-1.5">
          <p className="text-sm font-semibold text-sv-dark">{roleContext.heading}</p>
          <p className="text-sm text-gray-500 leading-relaxed">{roleContext.body}</p>
        </div>
      )}

      {/* ── Empty state ────────────────────────────────────────── */}
      {!['ADMIN', 'DEAN', 'STUDENT'].includes(role) && visibleCards.length === 0 && (
        <PageEmpty message="No modules are available for your role. Contact your administrator." />
      )}

    </PageShell>
  )
}
