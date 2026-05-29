import { useNavigate, Link } from 'react-router-dom'
import {
  BookOpen, Layers, FlaskConical, Microscope, FileText, ClipboardList,
  BarChart2, ChevronRight, CheckCircle, Circle, GraduationCap, Package,
  ClipboardCheck, Cpu, ShieldCheck, Building2,
} from 'lucide-react'
import { PageShell } from '@/components/shell/PageShell'
import { PageEmpty } from '@/components/shared/PageEmpty'
import { useCurrentUser } from '@/hooks/useCurrentUser'
import { useAuth } from '@/lib/auth'
import { MyCoursesBanner } from '@/components/assignments/MyCoursesBanner'

type IconComponent = React.FC<{ className?: string }>

interface ModuleCard {
  title: string
  description: string
  to: string
  icon: IconComponent
  roles: string[]
  badge: string   // icon badge colors (bg/text/border)
  bar: string     // top accent bar bg color
  section: string // grouping key
}

const CARDS: ModuleCard[] = [
  // ── Teach & Prepare ──────────────────────────────────────────────────────
  {
    title: 'Programs',
    description: 'Design academic programs, add courses, and manage learning outcomes.',
    to: '/programs',
    icon: BookOpen,
    roles: ['FACULTY', 'DEAN', 'ADMIN'],
    badge: 'bg-blue-50 text-blue-600 border-blue-100',
    bar:   'bg-blue-500',
    section: 'teach',
  },
  {
    title: 'Syllabuses',
    description: 'Generate AI-assisted syllabuses with CO-PO matrices and compliance checks.',
    to: '/syllabuses',
    icon: GraduationCap,
    roles: ['FACULTY', 'DEAN', 'ADMIN'],
    badge: 'bg-violet-50 text-violet-600 border-violet-100',
    bar:   'bg-violet-500',
    section: 'teach',
  },
  {
    title: 'Course Kits',
    description: 'Generate lecture slides, quizlets, and assignments for your courses.',
    to: '/course-kits',
    icon: Layers,
    roles: ['FACULTY', 'DEAN', 'ADMIN'],
    badge: 'bg-indigo-50 text-indigo-600 border-indigo-100',
    bar:   'bg-indigo-500',
    section: 'teach',
  },
  {
    title: 'Learning Packages',
    description: 'Build and curate multimedia learning packages for your students.',
    to: '/learning-packages',
    icon: Package,
    roles: ['FACULTY', 'DEAN', 'ADMIN'],
    badge: 'bg-pink-50 text-pink-600 border-pink-100',
    bar:   'bg-pink-500',
    section: 'teach',
  },

  // ── Assess & Research ─────────────────────────────────────────────────────
  {
    title: 'Lab Assignments',
    description: 'Create, publish, and evaluate written and code lab submissions.',
    to: '/labs',
    icon: FlaskConical,
    roles: ['FACULTY', 'ADMIN'],
    badge: 'bg-emerald-50 text-emerald-600 border-emerald-100',
    bar:   'bg-emerald-500',
    section: 'assess',
  },
  {
    title: 'Research Supervision',
    description: 'Review student proposals, supervise documents, and ratify viva reports.',
    to: '/research/problems',
    icon: Microscope,
    roles: ['FACULTY', 'ADMIN', 'GUIDE'],
    badge: 'bg-purple-50 text-purple-600 border-purple-100',
    bar:   'bg-purple-500',
    section: 'assess',
  },
  {
    title: 'Exam Papers',
    description: 'Set AI-assisted exam papers, submit for board review, and seal for release.',
    to: '/exams',
    icon: FileText,
    roles: ['FACULTY', 'ADMIN', 'BOARD'],
    badge: 'bg-amber-50 text-amber-600 border-amber-100',
    bar:   'bg-amber-500',
    section: 'assess',
  },
  {
    title: 'Scanned Scripts',
    description: 'Upload, evaluate, and finalise student answer scripts with identity masking.',
    to: '/scripts',
    icon: ClipboardList,
    roles: ['ADMIN', 'BOARD'],
    badge: 'bg-orange-50 text-orange-600 border-orange-100',
    bar:   'bg-orange-500',
    section: 'assess',
  },

  // ── Analytics ─────────────────────────────────────────────────────────────
  {
    title: 'Bell Curve',
    description: 'Analyse score distributions and advise on normalisation. Advisory only.',
    to: '/bell-curve',
    icon: BarChart2,
    roles: ['DEAN', 'ADMIN', 'BOARD'],
    badge: 'bg-teal-50 text-teal-600 border-teal-100',
    bar:   'bg-teal-500',
    section: 'analytics',
  },

  // ── Student ───────────────────────────────────────────────────────────────
  {
    title: 'My Labs',
    description: 'View your published lab assignments and submit solutions.',
    to: '/student/labs',
    icon: FlaskConical,
    roles: ['STUDENT'],
    badge: 'bg-emerald-50 text-emerald-600 border-emerald-100',
    bar:   'bg-emerald-500',
    section: 'student',
  },
  {
    title: 'My Research',
    description: 'Submit your research proposal and prepare for your viva voce.',
    to: '/student/research',
    icon: Microscope,
    roles: ['STUDENT'],
    badge: 'bg-purple-50 text-purple-600 border-purple-100',
    bar:   'bg-purple-500',
    section: 'student',
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

// Module sections define the grouping order and labels
const MODULE_SECTIONS = [
  { key: 'teach',    label: 'Teach & Prepare' },
  { key: 'assess',   label: 'Assess & Research' },
  { key: 'analytics',label: 'Analytics' },
  { key: 'student',  label: 'Student Portal' },
  { key: 'evaluate', label: 'Evaluation' },
]

const ROLE_SUBTITLE: Record<string, string> = {
  ADMIN:     'Manage programs, users, and platform settings for your institution.',
  DEAN:      'Review academic programs and analytics across your institution.',
  FACULTY:   'Build courses, set exams, evaluate labs, and supervise research.',
  BOARD:     'Review exam papers, evaluate scripts, and advise on grade distributions.',
  GUIDE:     'Review research proposals assigned to you and supervise student projects.',
  STUDENT:   'Access your lab assignments and research project below.',
  EVALUATOR: 'Review and score student submissions assigned to you.',
}

const ROLE_CONTEXT: Partial<Record<string, { heading: string; body: string }>> = {
  GUIDE: {
    heading: 'How supervision works',
    body: 'Students submit proposals → you receive a notification → review via Research Supervision to accept, request revision, or reject. Viva sessions are scheduled by the admin.',
  },
  STUDENT: {
    heading: 'What to expect',
    body: 'Lab assignments appear in My Labs when your faculty publishes them. Use My Research to register your thesis topic and track progress with your assigned guide.',
  },
  BOARD: {
    heading: 'Board responsibilities',
    body: 'Review submitted exam papers and approve or return with feedback. Once evaluators finalise scripts, review and ratify marks. Bell curve analysis is advisory — raw scores are never altered.',
  },
}

// ---------------------------------------------------------------------------
// Stat card
// ---------------------------------------------------------------------------

interface StatCardProps {
  label: string
  value: string
  icon: IconComponent
  accent?: boolean
}

function StatCard({ label, value, icon: Icon, accent }: StatCardProps) {
  return (
    <div className={`rounded-xl border px-4 py-3.5 flex items-start gap-3 ${
      accent
        ? 'bg-sv-light border-sv-primary/20'
        : 'bg-white border-gray-200'
    }`}>
      <div className={`p-1.5 rounded-lg mt-0.5 ${accent ? 'bg-sv-primary/10' : 'bg-gray-100'}`}>
        <Icon className={`h-3.5 w-3.5 ${accent ? 'text-sv-primary' : 'text-gray-400'}`} />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wide">{label}</p>
        <p className={`text-sm font-bold mt-0.5 truncate ${accent ? 'text-sv-primary' : 'text-gray-900'}`}>
          {value}
        </p>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Module card
// ---------------------------------------------------------------------------

function ModuleCardItem({ card, onClick }: { card: ModuleCard; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="text-left w-full rounded-xl border border-gray-200 bg-white hover:border-sv-primary/30 hover:shadow-lg hover:shadow-sv-primary/5 transition-all duration-200 group relative overflow-hidden"
    >
      {/* Top accent bar */}
      <div className={`absolute inset-x-0 top-0 h-[3px] ${card.bar}`} />

      <div className="p-5 pt-6">
        <div className="flex items-start justify-between gap-3 mb-3">
          <div className={`p-2 rounded-lg border ${card.badge}`}>
            <card.icon className="h-4 w-4" />
          </div>
          <ChevronRight className="h-4 w-4 text-gray-300 group-hover:text-sv-primary mt-0.5 transition-colors duration-200" />
        </div>
        <p className="text-sm font-semibold text-gray-900 leading-snug">{card.title}</p>
        <p className="text-xs text-gray-500 mt-1 leading-relaxed">{card.description}</p>
      </div>
    </button>
  )
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
// Greeting
// ---------------------------------------------------------------------------

function getGreeting(): string {
  const hour = new Date().getHours()
  if (hour < 12) return 'Good morning'
  if (hour < 17) return 'Good afternoon'
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
  return slug.split('-').map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function DashboardPage() {
  const navigate = useNavigate()
  const user     = useCurrentUser()
  const { user: authUser } = useAuth()
  const role = user?.role ?? ''

  const visibleCards = CARDS.filter((c) => c.roles.includes(role))
  const displayFirstName = user?.fullName ? getDisplayFirstName(user.fullName) : null
  const subtitle     = ROLE_SUBTITLE[role] ?? 'Select a module below to get started.'
  const roleContext  = ROLE_CONTEXT[role]
  const institution  = prettifySlug(user?.tenantSlug ?? '')

  return (
    <PageShell>

      {/* ── Welcome header ─────────────────────────────────────── */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-[10px] font-bold text-sv-primary uppercase tracking-[0.18em] mb-1.5">
            VIDYA AI · Academic Workspace
          </p>
          <h1 className="text-2xl font-bold text-gray-900 leading-tight">
            {getGreeting()}{displayFirstName ? `, ${displayFirstName}` : ''}
          </h1>
          <p className="text-sm text-gray-500 mt-1">{subtitle}</p>
        </div>
        <div className="hidden sm:flex items-center gap-1.5 bg-sv-light border border-sv-primary/20 text-sv-primary text-[11px] font-bold px-3 py-1.5 rounded-full whitespace-nowrap flex-shrink-0">
          <span className="w-1.5 h-1.5 rounded-full bg-sv-accent animate-pulse" />
          AI Platform Active
        </div>
      </div>

      {/* ── Stats strip — hidden for narrow single-purpose roles ── */}
      {!['STUDENT', 'GUIDE'].includes(role) && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <StatCard
            label="Modules available"
            value={String(visibleCards.length)}
            icon={Cpu}
            accent
          />
          <StatCard
            label="Access level"
            value={role || '—'}
            icon={ShieldCheck}
          />
          <StatCard
            label="Workspace"
            value={institution}
            icon={Building2}
          />
        </div>
      )}

      {/* ── Admin onboarding ───────────────────────────────────── */}
      {role === 'ADMIN' && authUser && (
        <AdminOnboarding passwordChanged={!authUser.firstLogin} />
      )}

      {/* ── My Courses — FACULTY only (H-31) ──────────────────── */}
      {role === 'FACULTY' && <MyCoursesBanner />}

      {/* ── Module sections ────────────────────────────────────── */}
      {visibleCards.length > 0 && (
        <div className="space-y-8">
          {MODULE_SECTIONS.map((section) => {
            const sectionCards = visibleCards.filter((c) => c.section === section.key)
            if (sectionCards.length === 0) return null

            return (
              <div key={section.key}>
                <div className="flex items-center gap-3 mb-4">
                  <h2 className="text-xs font-bold text-gray-400 uppercase tracking-widest whitespace-nowrap">
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

      {/* ── Contextual guidance (GUIDE, STUDENT) ──────────────── */}
      {roleContext && (
        <div className="rounded-xl border border-sv-primary/10 bg-sv-light px-5 py-4 space-y-1.5">
          <p className="text-sm font-semibold text-sv-dark">{roleContext.heading}</p>
          <p className="text-sm text-gray-500 leading-relaxed">{roleContext.body}</p>
        </div>
      )}

      {/* ── Empty state ────────────────────────────────────────── */}
      {visibleCards.length === 0 && (
        <PageEmpty message="No modules are available for your role. Contact your administrator." />
      )}

    </PageShell>
  )
}
