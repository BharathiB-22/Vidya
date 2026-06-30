import { useNavigate } from 'react-router-dom'
import {
  BookOpen, Layers, FlaskConical, Microscope, FileText,
  GraduationCap, Package, ChevronRight,
} from 'lucide-react'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { MyCoursesBanner } from '@/components/assignments/MyCoursesBanner'
import { useFacultySummary } from '@/hooks/useOwnership'

type IconComponent = React.FC<{ className?: string }>

interface WorkspaceCard {
  title: string
  description: string
  to: string
  icon: IconComponent
  badge: string
  bar: string
}

const TEACH_CARDS: WorkspaceCard[] = [
  {
    title: 'Academic Programs',
    description: 'Design degree programs, add courses, and manage learning outcomes.',
    to: '/programs',
    icon: BookOpen,
    badge: 'bg-blue-50 text-blue-600 border-blue-100',
    bar: 'bg-blue-500',
  },
  {
    title: 'Syllabuses',
    description: 'Generate AI-assisted syllabuses with CO-PO matrices and compliance checks.',
    to: '/syllabuses',
    icon: GraduationCap,
    badge: 'bg-violet-50 text-violet-600 border-violet-100',
    bar: 'bg-violet-500',
  },
  {
    title: 'Course Kits',
    description: 'Generate lecture slides, quizlets, and assignments for your courses.',
    to: '/course-kits',
    icon: Layers,
    badge: 'bg-indigo-50 text-indigo-600 border-indigo-100',
    bar: 'bg-indigo-500',
  },
  {
    title: 'Learning Materials',
    description: 'Build and curate multimedia learning packages for your students.',
    to: '/learning-packages',
    icon: Package,
    badge: 'bg-pink-50 text-pink-600 border-pink-100',
    bar: 'bg-pink-500',
  },
]

const ASSESS_CARDS: WorkspaceCard[] = [
  {
    title: 'Lab Assignments',
    description: 'Create, publish, and evaluate written and code lab submissions.',
    to: '/labs',
    icon: FlaskConical,
    badge: 'bg-emerald-50 text-emerald-600 border-emerald-100',
    bar: 'bg-emerald-500',
  },
  {
    title: 'Research Supervision',
    description: 'Review student proposals, supervise documents, and ratify viva reports.',
    to: '/research/problems',
    icon: Microscope,
    badge: 'bg-purple-50 text-purple-600 border-purple-100',
    bar: 'bg-purple-500',
  },
  {
    title: 'Exam Papers',
    description: 'Set AI-assisted exam papers, submit for board review, and seal for release.',
    to: '/exams',
    icon: FileText,
    badge: 'bg-amber-50 text-amber-600 border-amber-100',
    bar: 'bg-amber-500',
  },
]

function WorkspaceCard({ card, onClick }: { card: WorkspaceCard; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="text-left w-full rounded-xl border border-gray-200 bg-white hover:border-sv-primary/30 hover:shadow-lg hover:shadow-sv-primary/5 transition-all duration-200 group relative overflow-hidden"
    >
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

function AcademicSummaryBanner() {
  const { data } = useFacultySummary()
  if (!data || (data.course_count === 0 && data.program_count === 0)) return null
  return (
    <div className="rounded-xl border border-sv-primary/20 bg-sv-primary/5 px-4 py-3 text-sm text-gray-700">
      You are responsible for{' '}
      <span className="font-semibold text-sv-primary">{data.course_count} course{data.course_count !== 1 ? 's' : ''}</span>
      {' '}across{' '}
      <span className="font-semibold text-sv-primary">{data.program_count} program{data.program_count !== 1 ? 's' : ''}</span>
      {data.department_count > 0 && (
        <> in{' '}
          <span className="font-semibold text-sv-primary">
            {data.department_count} department{data.department_count !== 1 ? 's' : ''}
          </span>
        </>
      )}
      .
    </div>
  )
}

export default function FacultyWorkspacePage() {
  const navigate = useNavigate()

  return (
    <PageShell>
      <PageHeader
        title="Faculty Workspace"
        subtitle="Access teaching tools, course materials, labs, and research supervision."
        icon={BookOpen}
      />

      {/* Academic responsibility summary */}
      <AcademicSummaryBanner />

      {/* My Courses banner — same as Faculty dashboard */}
      <MyCoursesBanner />

      {/* Teach & Prepare */}
      <div>
        <div className="flex items-center gap-3 mb-4">
          <h2 className="text-xs font-bold text-gray-400 uppercase tracking-widest whitespace-nowrap">
            Teach &amp; Prepare
          </h2>
          <div className="flex-1 h-px bg-gray-100" />
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {TEACH_CARDS.map((card) => (
            <WorkspaceCard key={card.to} card={card} onClick={() => navigate(card.to)} />
          ))}
        </div>
      </div>

      {/* Assess & Research */}
      <div>
        <div className="flex items-center gap-3 mb-4">
          <h2 className="text-xs font-bold text-gray-400 uppercase tracking-widest whitespace-nowrap">
            Assess &amp; Research
          </h2>
          <div className="flex-1 h-px bg-gray-100" />
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {ASSESS_CARDS.map((card) => (
            <WorkspaceCard key={card.to} card={card} onClick={() => navigate(card.to)} />
          ))}
        </div>
      </div>
    </PageShell>
  )
}
