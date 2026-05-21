import { useNavigate } from 'react-router-dom'
import {
  BookOpen, Layers, FlaskConical, Microscope,
  FileText, ClipboardList, BarChart2, ChevronRight,
} from 'lucide-react'
import { useCurrentUser } from '@/hooks/useCurrentUser'

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

function getGreeting(): string {
  const hour = new Date().getHours()
  if (hour < 12) return 'Good morning'
  if (hour < 17) return 'Good afternoon'
  return 'Good evening'
}

export default function DashboardPage() {
  const navigate = useNavigate()
  const user = useCurrentUser()
  const role = user?.role ?? ''

  const visibleCards = CARDS.filter((c) => c.roles.includes(role))
  const firstName = user?.fullName ? user.fullName.split(' ')[0] : null

  return (
    <div className="max-w-5xl mx-auto px-4 py-8 space-y-8">
      {/* Welcome */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">
          {getGreeting()}{firstName ? `, ${firstName}` : ''}
        </h1>
        <p className="text-sm text-gray-500 mt-1">
          {visibleCards.length > 0
            ? 'Select a module below to get started.'
            : 'No modules are currently available for your role. Contact your administrator.'}
        </p>
      </div>

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
    </div>
  )
}
