import { useNavigate, Link } from 'react-router-dom'
import {
  BookOpen, Layers, FlaskConical, Microscope,
  FileText, ClipboardList, BarChart2, ChevronRight, CheckCircle, Circle,
} from 'lucide-react'
import { useCurrentUser } from '@/hooks/useCurrentUser'
import { useAuth } from '@/lib/auth'

type IconComponent = React.FC<{ className?: string }>

interface ModuleCard {
  title: string
  description: string
  to: string
  icon: IconComponent
  roles: string[]
  accent: string
}

const CARDS: ModuleCard[] = [
  {
    title: 'Programs',
    description: 'Design academic programs, add courses, and manage outcomes.',
    to: '/programs',
    icon: BookOpen,
    roles: ['FACULTY', 'DEAN', 'ADMIN'],
    accent: 'bg-blue-50 text-blue-600 border-blue-100',
  },
  {
    title: 'Course Kits',
    description: 'Generate slides, quizlets, and assignments for your courses.',
    to: '/course-kits',
    icon: Layers,
    roles: ['FACULTY', 'DEAN', 'ADMIN'],
    accent: 'bg-indigo-50 text-indigo-600 border-indigo-100',
  },
  {
    title: 'Lab Assignments',
    description: 'Create, publish, and evaluate written and code lab submissions.',
    to: '/labs',
    icon: FlaskConical,
    roles: ['FACULTY', 'ADMIN'],
    accent: 'bg-emerald-50 text-emerald-600 border-emerald-100',
  },
  {
    title: 'Research Supervision',
    description: 'Review student research proposals, supervise documents, and ratify viva reports.',
    to: '/research/problems',
    icon: Microscope,
    roles: ['FACULTY', 'ADMIN', 'GUIDE'],
    accent: 'bg-purple-50 text-purple-600 border-purple-100',
  },
  {
    title: 'Exam Papers',
    description: 'Set AI-assisted exam papers, submit for board review, and seal for release.',
    to: '/exams',
    icon: FileText,
    roles: ['FACULTY', 'ADMIN', 'BOARD'],
    accent: 'bg-amber-50 text-amber-600 border-amber-100',
  },
  {
    title: 'Scanned Scripts',
    description: 'Upload, evaluate, and finalise student answer scripts with identity masking.',
    to: '/scripts',
    icon: ClipboardList,
    roles: ['ADMIN', 'BOARD'],
    accent: 'bg-orange-50 text-orange-600 border-orange-100',
  },
  {
    title: 'Bell Curve',
    description: 'Analyse score distributions and advise on normalisation. Advisory only.',
    to: '/bell-curve',
    icon: BarChart2,
    roles: ['DEAN', 'ADMIN', 'BOARD'],
    accent: 'bg-teal-50 text-teal-600 border-teal-100',
  },
  {
    title: 'My Labs',
    description: 'View your published lab assignments and submit solutions.',
    to: '/student/labs',
    icon: FlaskConical,
    roles: ['STUDENT'],
    accent: 'bg-emerald-50 text-emerald-600 border-emerald-100',
  },
  {
    title: 'My Research',
    description: 'Submit your research proposal and prepare for your viva voce.',
    to: '/student/research',
    icon: Microscope,
    roles: ['STUDENT'],
    accent: 'bg-purple-50 text-purple-600 border-purple-100',
  },
]

const ROLE_SUBTITLE: Record<string, string> = {
  ADMIN:   'Manage programs, users, and platform settings for your institution.',
  DEAN:    'Review academic programs and analytics across your institution.',
  FACULTY: 'Build courses, set exams, evaluate labs, and supervise research.',
  BOARD:   'Review exam papers, evaluate scripts, and advise on grade distributions.',
  GUIDE:   'Review research proposals assigned to you and supervise student projects.',
  STUDENT: 'Access your lab assignments and research project below.',
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
  const visitedUsers = localStorage.getItem('vidya_onboarding_users') === '1'

  const items: OnboardingItem[] = [
    { label: 'Sign in to Vidya',            done: true,            href: '/dashboard' },
    { label: 'Set your permanent password',  done: passwordChanged, href: '/settings'  },
    { label: 'Add faculty and students',     done: visitedUsers,    href: '/users'     },
    { label: 'Review institution settings',  done: passwordChanged, href: '/settings'  },
  ]
  const completed = items.filter((i) => i.done).length

  if (completed === items.length) {
    return (
      <div data-testid="onboarding-checklist" className="flex items-center gap-3 rounded-xl border border-green-200 bg-green-50 px-5 py-4">
        <CheckCircle className="h-5 w-5 text-green-600 flex-shrink-0" />
        <div className="min-w-0">
          <p className="text-sm font-semibold text-green-800">Setup complete</p>
          <p className="text-xs text-green-700 mt-0.5">
            Your institution is ready. Add more users from{' '}
            <Link to="/users" className="font-medium underline underline-offset-2 hover:text-green-900">
              Users
            </Link>{' '}
            whenever needed.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div data-testid="onboarding-checklist" className="bg-amber-50 border border-amber-200 rounded-xl p-5">
      <div className="flex items-center justify-between mb-3">
        <p className="text-sm font-semibold text-amber-900">Getting started</p>
        <p className="text-xs text-amber-600">{completed}/{items.length} done</p>
      </div>
      <ul className="space-y-2">
        {items.map((item) => (
          <li key={item.label} className="flex items-center gap-2.5">
            {item.done
              ? <CheckCircle className="h-4 w-4 text-amber-600 flex-shrink-0" />
              : <Circle      className="h-4 w-4 text-amber-300 flex-shrink-0" />
            }
            {item.done ? (
              <span className="text-sm text-amber-700 line-through">{item.label}</span>
            ) : (
              <Link to={item.href} className="text-sm text-amber-800 hover:underline font-medium">
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

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function DashboardPage() {
  const navigate = useNavigate()
  const user = useCurrentUser()
  const { user: authUser } = useAuth()
  const role = user?.role ?? ''

  const visibleCards = CARDS.filter((c) => c.roles.includes(role))
  const firstName    = user?.fullName ? user.fullName.split(' ')[0] : null
  const subtitle     = ROLE_SUBTITLE[role] ?? 'Select a module below to get started.'
  const roleContext  = ROLE_CONTEXT[role]

  return (
    <div className="max-w-5xl mx-auto px-4 py-8 space-y-8">

      {/* Welcome */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">
          {getGreeting()}{firstName ? `, ${firstName}` : ''}
        </h1>
        <p className="text-sm text-gray-500 mt-1">{subtitle}</p>
      </div>

      {/* Admin onboarding checklist */}
      {role === 'ADMIN' && authUser && (
        <AdminOnboarding passwordChanged={!authUser.firstLogin} />
      )}

      {/* Module cards */}
      {visibleCards.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {visibleCards.map((card) => (
            <button
              key={card.to}
              onClick={() => navigate(card.to)}
              className="text-left rounded-xl border border-gray-200 bg-white p-5 hover:border-indigo-300 hover:shadow-sm transition-all group"
            >
              <div className="flex items-start justify-between gap-3 mb-3">
                <div className={`p-2 rounded-lg border ${card.accent}`}>
                  <card.icon className="h-5 w-5" />
                </div>
                <ChevronRight className="h-4 w-4 text-gray-300 group-hover:text-indigo-400 mt-1 transition-colors" />
              </div>
              <p className="text-sm font-semibold text-gray-900">{card.title}</p>
              <p className="text-xs text-gray-500 mt-1 leading-relaxed">{card.description}</p>
            </button>
          ))}
        </div>
      )}

      {/* Contextual guidance for sparse roles (GUIDE, STUDENT) */}
      {roleContext && (
        <div className="rounded-xl border border-gray-100 bg-gray-50 px-5 py-4 text-sm space-y-1">
          <p className="font-medium text-gray-700">{roleContext.heading}</p>
          <p className="text-gray-500 leading-relaxed">{roleContext.body}</p>
        </div>
      )}

      {/* Fallback for roles with no visible modules */}
      {visibleCards.length === 0 && (
        <div className="text-center py-16 rounded-xl border border-dashed border-gray-200">
          <p className="text-sm text-gray-400">
            No modules are currently available for your role. Contact your administrator.
          </p>
        </div>
      )}

    </div>
  )
}
