// Examination Setup — navigation consolidation only.
//
// Hosts the THREE existing Dean examination pages as a guided stepper, reusing
// them verbatim. Each tab renders its original page component (with its own
// PageShell, header, data fetching, Create actions, validation and permissions)
// completely unchanged — this file adds no business logic and calls no API.
//
//   1. Sessions      → ExamSessionsPage        (create exam sessions)
//   2. Centers       → ExamCentersPage         (configure exam centers)
//   3. Hall Tickets  → HallTicketDashboardPage (generate hall tickets)
//
// Active tab lives in the URL (?tab=…) so it is deep-linkable and the old list
// routes can redirect straight to the right step.
import { useSearchParams } from 'react-router-dom'
import { CalendarDays, MapPin, Ticket, ChevronRight } from 'lucide-react'
import ExamSessionsPage from './ExamSessionsPage'
import ExamCentersPage from './ExamCentersPage'
import HallTicketDashboardPage from './HallTicketDashboardPage'

const STEPS = [
  { key: 'sessions',     step: 1, label: 'Sessions',     hint: 'Create exam sessions',   icon: CalendarDays, Comp: ExamSessionsPage },
  { key: 'centers',      step: 2, label: 'Centers',      hint: 'Configure exam centers', icon: MapPin,       Comp: ExamCentersPage },
  { key: 'hall-tickets', step: 3, label: 'Hall Tickets', hint: 'Generate hall tickets',  icon: Ticket,       Comp: HallTicketDashboardPage },
] as const

export default function ExaminationSetupPage() {
  const [params, setParams] = useSearchParams()
  const active = STEPS.find(s => s.key === params.get('tab')) ?? STEPS[0]
  const ActivePage = active.Comp

  return (
    <div>
      {/* Stepper header — aligned to the pages' own max-w-5xl PageShell width */}
      <div className="max-w-5xl mx-auto px-6 pt-6">
        <h1 className="text-xl font-bold text-gray-900">Examination Setup</h1>
        <p className="text-sm text-gray-600 mt-0.5">
          Set up exam sessions, configure centers, then generate hall tickets.
        </p>

        <div className="mt-4 flex items-center gap-1 border-b border-gray-200">
          {STEPS.map((s, i) => {
            const isActive = s.key === active.key
            const Icon = s.icon
            return (
              <div key={s.key} className="flex items-center">
                <button
                  type="button"
                  onClick={() => setParams({ tab: s.key })}
                  title={s.hint}
                  className={`flex items-center gap-2 px-4 py-2.5 -mb-px border-b-2 text-sm font-medium transition-colors ${
                    isActive
                      ? 'border-indigo-600 text-indigo-700'
                      : 'border-transparent text-gray-600 hover:text-gray-900'
                  }`}
                >
                  <span
                    className={`flex h-5 w-5 items-center justify-center rounded-full text-xs font-bold ${
                      isActive ? 'bg-indigo-600 text-white' : 'bg-gray-200 text-gray-700'
                    }`}
                  >
                    {s.step}
                  </span>
                  <Icon className="h-4 w-4" />
                  {s.label}
                </button>
                {i < STEPS.length - 1 && (
                  <ChevronRight className="h-4 w-4 text-gray-400 mx-1 shrink-0" />
                )}
              </div>
            )
          })}
        </div>
      </div>

      {/* The existing page, rendered unchanged (brings its own PageShell/header) */}
      <ActivePage />
    </div>
  )
}
