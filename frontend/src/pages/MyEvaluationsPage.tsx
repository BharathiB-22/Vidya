// My Evaluations — one desk for every kind of evaluation work.
//
// Evaluation work reaches a person from three places, and it used to be shown in
// two different menu items with the same name (and coursework in neither):
//
//     Exam scripts   m09 — anonymous, keyed by script code
//     Coursework     m04 — via the M09.6 ledger, NOT anonymous
//     Lab work       m06 — its own assignment model
//
// Whether a person holds EVALUATOR outright or as a grant on their FACULTY
// account changes nothing about the work itself, so it does not change this page
// either: one nav item, one list, whatever the source. Each section simply hides
// when that source has nothing in it.
//
// This page owns no evaluation logic. It reads each source's existing endpoint
// and links to that source's existing evaluation screen.
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ClipboardCheck, ClipboardList, FlaskConical, FileText, Clock } from 'lucide-react'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { PageEmpty } from '@/components/shared/PageEmpty'
import { listMyScripts } from '@/lib/api/scripts'
import { listMyCourseworkEvaluations } from '@/lib/api/coursework'
import { useEvaluatorAssignments } from '@/hooks/labs'

const SCRIPT_STATUS_COLOR: Record<string, string> = {
  SCORED:                   'bg-indigo-100 text-indigo-700',
  REVIEW_REQUIRED:          'bg-orange-100 text-orange-700',
  WAITING_SECOND_EVALUATOR: 'bg-purple-100 text-purple-700',
  SECONDARY_EVALUATED:      'bg-violet-100 text-violet-700',
  MARKS_SUBMITTED:          'bg-yellow-100 text-yellow-700',
  BOARD_FINALISED:          'bg-emerald-100 text-emerald-700',
}

function Pill({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return (
    <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${className || 'bg-gray-100 text-gray-600'}`}>
      {children}
    </span>
  )
}

function Section({
  icon: Icon, title, count, children,
}: {
  icon: typeof ClipboardCheck; title: string; count: number; children: React.ReactNode
}) {
  return (
    <section className="space-y-3">
      <div className="flex items-center gap-2">
        <Icon className="w-4 h-4 text-gray-600" />
        <h2 className="text-sm font-semibold text-gray-700">{title}</h2>
        <span className="text-xs text-gray-600">({count})</span>
      </div>
      <div className="rounded-xl border border-gray-200 bg-white divide-y divide-gray-100 overflow-hidden">
        {children}
      </div>
    </section>
  )
}

function Row({
  onClick, title, meta, right,
}: {
  onClick: () => void; title: React.ReactNode; meta: React.ReactNode; right: React.ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full px-5 py-4 flex items-center justify-between gap-4 hover:bg-gray-50 transition-colors text-left"
    >
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">{title}</div>
        <p className="text-xs text-gray-600 mt-0.5">{meta}</p>
      </div>
      <span className="text-xs text-indigo-600 font-medium shrink-0">{right}</span>
    </button>
  )
}

export default function MyEvaluationsPage() {
  const navigate = useNavigate()

  // Each source is independent: one being empty or unavailable must not hide the
  // others, so nothing here waits on a combined load.
  const { data: scriptsData, isLoading: scriptsLoading } = useQuery({
    queryKey: ['my-evaluations', 'scripts'],
    queryFn:  () => listMyScripts({ limit: 100 }),
  })
  const { data: coursework = [], isLoading: courseworkLoading } = useQuery({
    queryKey: ['my-evaluations', 'coursework'],
    queryFn:  listMyCourseworkEvaluations,
  })
  const { data: labsData, isLoading: labsLoading } = useEvaluatorAssignments()

  const scripts = scriptsData?.items ?? []
  const labs = labsData?.items ?? []

  const loading = scriptsLoading || courseworkLoading || labsLoading
  const total = scripts.length + coursework.length + labs.length

  return (
    <PageShell>
      <PageHeader
        icon={ClipboardCheck}
        title="My Evaluations"
        subtitle="Everything assigned to you for evaluation — scripts, coursework and lab work"
      />

      {!loading && total === 0 && (
        <PageEmpty
          icon={ClipboardCheck}
          message="Nothing is assigned to you for evaluation right now."
        />
      )}

      <div className="space-y-6">
        {/* Coursework — assignment-centric: shown from publish, before any student
            submits, so the evaluator can open and prepare. */}
        {coursework.length > 0 && (
          <Section icon={FileText} title="Coursework" count={coursework.length}>
            {coursework.map(cw => (
              <Row
                key={cw.assignment_id}
                onClick={() => navigate(`/faculty/assignments/${cw.assignment_id}/submissions`)}
                title={
                  <>
                    <p className="text-sm font-medium text-gray-900 truncate">{cw.assignment_title}</p>
                    {cw.total_submissions === 0 && (
                      <Pill className="bg-gray-100 text-gray-600">No submissions yet</Pill>
                    )}
                    {cw.allocated_to_me > 0 && cw.pending_for_me === 0 && (
                      <Pill className="bg-emerald-50 text-emerald-700">All evaluated</Pill>
                    )}
                    {cw.pending_for_me > 0 && (
                      <Pill className="bg-orange-50 text-orange-700">{cw.pending_for_me} to evaluate</Pill>
                    )}
                  </>
                }
                meta={
                  <>
                    {[cw.course_code, cw.faculty_name, cw.sections && `Sec ${cw.sections}`,
                      cw.semester != null && `Sem ${cw.semester}`]
                      .filter(Boolean).join(' · ')}
                    {' · '}{cw.question_count} question{cw.question_count === 1 ? '' : 's'} · {cw.max_marks} marks
                    {cw.due_date && <> · Due {new Date(cw.due_date).toLocaleDateString()}</>}
                    {cw.allocated_to_me > 0 && <> · {cw.graded_by_me}/{cw.allocated_to_me} done</>}
                  </>
                }
                right={cw.total_submissions === 0 ? 'Open →' : (cw.pending_for_me > 0 ? 'Evaluate →' : 'Review →')}
              />
            ))}
          </Section>
        )}

        {/* Exam scripts — anonymous, keyed by script code and nothing else. */}
        {scripts.length > 0 && (
          <Section icon={ClipboardList} title="Exam Scripts" count={scripts.length}>
            {scripts.map(script => (
              <Row
                key={script.id}
                onClick={() => navigate(`/scripts/${script.id}/evaluate`)}
                title={
                  <>
                    <p className="text-sm font-medium text-gray-900 truncate">
                      {script.masked_id}
                    </p>
                    <Pill className={SCRIPT_STATUS_COLOR[script.status] ?? ''}>
                      {script.status.replace(/_/g, ' ')}
                    </Pill>
                  </>
                }
                meta={
                  <>
                    {/* Identity stays hidden until BOARD_FINALISED — a script is a
                        masked id and nothing else here. */}
                    Anonymous script
                    {script.page_count ? ` · ${script.page_count} pages` : ''}
                  </>
                }
                right="Evaluate →"
              />
            ))}
          </Section>
        )}

        {/* Lab work — m06's own model, reached through its own screens. */}
        {labs.length > 0 && (
          <Section icon={FlaskConical} title="Lab Assignments" count={labs.length}>
            {labs.map(lab => (
              <Row
                key={lab.id}
                onClick={() => navigate(`/evaluator/${lab.id}/submissions`)}
                title={
                  <>
                    <p className="text-sm font-medium text-gray-900 truncate">{lab.title}</p>
                    <Pill className={
                      lab.submission_type === 'CODE'
                        ? 'bg-blue-50 text-blue-700'
                        : 'bg-purple-50 text-purple-700'
                    }>
                      {lab.submission_type}
                    </Pill>
                  </>
                }
                meta={
                  <>
                    {lab.rubric.reduce((s, c) => s + c.max_marks, 0)} marks
                    {lab.deadline && (
                      <> · <Clock className="w-3 h-3 inline -mt-0.5" /> Due {new Date(lab.deadline).toLocaleDateString()}</>
                    )}
                  </>
                }
                right="View submissions →"
              />
            ))}
          </Section>
        )}
      </div>
    </PageShell>
  )
}
