import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  AlertTriangle, ArrowLeft, ArrowRight, BookLock, CheckCircle2, CircleDashed,
  FileText, Landmark, Loader2, Lock, Sparkles, SquarePen,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { PageLoading } from '@/components/shared/PageLoading'
import { PageError } from '@/components/shared/PageError'
import { useApproveCurriculum, useGenerateSyllabi, useReadiness } from '@/hooks/governance'
import { useProgram } from '@/hooks/programs'
import { useGovernance } from '@/lib/governance'
import type { ReadinessItem, ReadinessSummary } from '@/types/governance'
import { COURSE_TYPE_DOCUMENT } from '@/types/program'
import { ApproveCurriculumDialog, GenerateSyllabiDialog } from '@/components/governance/GovernanceDialogs'
import { GovernanceTrail } from '@/components/governance/GovernanceTrail'

/**
 * The Board's working surface for one curriculum.
 *
 * The Board's real job is not "approve a curriculum" — it is "produce a complete
 * official syllabus for every subject in it, then approve". That is N pieces of
 * work, not one, so this page is a worksheet rather than a decision screen.
 *
 * The flow it lays out, left to right, is the whole of the Board's phase:
 *
 *     Review Program → Edit Structure → Generate Syllabus → Review/Edit → Approve
 *
 * There is deliberately no "finalize structure" step. The Board may keep editing
 * the structure right up to approval; editing a subject whose syllabus is already
 * approved simply returns that syllabus to Draft, which this page shows, and the
 * approve gate then blocks until the Board has re-read it.
 */
export default function CurriculumWorkbenchPage() {
  const { programId = '' } = useParams()
  const navigate = useNavigate()
  const { bodyLabel } = useGovernance()

  const { data: program, isLoading: loadingProgram } = useProgram(programId)
  const { data: readiness, isLoading: loadingReadiness, isError } = useReadiness(programId)

  const generate = useGenerateSyllabi()
  const approve = useApproveCurriculum()

  const [generateOpen, setGenerateOpen] = useState(false)
  const [approveOpen, setApproveOpen] = useState(false)

  if (loadingProgram || loadingReadiness) {
    return <div className="p-6"><PageLoading message="Loading the curriculum…" /></div>
  }
  if (isError || !readiness || !program) {
    return (
      <div className="p-6">
        <PageError message={`Could not load this curriculum. You may not be a member of the ${bodyLabel}.`} />
      </div>
    )
  }

  const locked = program.status === 'APPROVED' || program.status === 'PUBLISHED'
  const generating = readiness.items.some((i) => i.syllabus_status === 'AI_GENERATING')
  const missing = readiness.missing_count

  return (
    <div className="max-w-7xl mx-auto px-4 py-6">
      <button
        onClick={() => navigate('/governance/curriculum')}
        className="mb-4 inline-flex items-center gap-1 text-sm font-medium text-gray-600 hover:text-black"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to Curriculum Review
      </button>

      <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-start gap-2.5 min-w-0">
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-black text-white">
            <Landmark className="h-5 w-5" />
          </span>
          <div className="min-w-0">
            <h1 className="text-2xl font-bold tracking-tight text-black">{program.title}</h1>
            <p className="text-sm text-gray-600">
              {program.department} · {program.degree_type} · Version {program.version}
              {program.academic_year ? ` · ${program.academic_year}` : ''}
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => navigate(`/programs/${programId}`)}>
            <SquarePen className="h-4 w-4 mr-1" />
            Edit Program Structure
          </Button>

          {!locked && (
            <>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setGenerateOpen(true)}
                disabled={generating || generate.isPending}
              >
                {generating || generate.isPending
                  ? <Loader2 className="h-4 w-4 mr-1 animate-spin" />
                  : <Sparkles className="h-4 w-4 mr-1" />}
                {missing > 0 ? `Generate ${missing} Missing Syllabi` : 'Regenerate Syllabi'}
              </Button>

              <Button
                size="sm"
                onClick={() => setApproveOpen(true)}
                disabled={!readiness.can_approve || approve.isPending}
                title={
                  readiness.can_approve
                    ? undefined
                    : 'Every subject needs an approved official syllabus first.'
                }
              >
                <Lock className="h-4 w-4 mr-1" />
                Approve Curriculum
              </Button>
            </>
          )}
        </div>
      </header>

      {locked ? <LockedBanner /> : <ApproveGate readiness={readiness} />}

      <ReadinessTiles readiness={readiness} />

      <SubjectTable items={readiness.items} locked={locked} />

      {/* The Board has no separation of duties — one member may enhance, write the
          syllabus, approve and lock this curriculum alone. The trail is what makes
          that accountable, so it belongs on the working screen, not hidden away in
          an admin audit page. */}
      <div className="mt-6">
        <GovernanceTrail programId={programId} />
      </div>

      <GenerateSyllabiDialog
        open={generateOpen}
        onOpenChange={setGenerateOpen}
        missingCount={missing}
        totalCount={readiness.total_subjects}
        isPending={generate.isPending}
        onConfirm={(regenerateAll) =>
          generate.mutate(
            { id: programId, payload: { regenerate_all: regenerateAll } },
            { onSuccess: () => setGenerateOpen(false) },
          )
        }
      />

      <ApproveCurriculumDialog
        open={approveOpen}
        onOpenChange={setApproveOpen}
        subjectCount={readiness.total_subjects}
        isPending={approve.isPending}
        onConfirm={(comment) =>
          approve.mutate(
            { id: programId, payload: { comment } },
            { onSuccess: () => setApproveOpen(false) },
          )
        }
      />
    </div>
  )
}

/**
 * Why the Approve button is disabled, in words. A greyed-out button with no
 * explanation is the most common way a governance screen wastes someone's
 * afternoon.
 */
function ApproveGate({ readiness }: { readiness: ReadinessSummary }) {
  if (readiness.can_approve) {
    return (
      <div className="mb-5 flex items-start gap-3 rounded-xl border border-emerald-200 bg-emerald-50 p-4">
        <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-emerald-600" />
        <div>
          <p className="font-semibold text-emerald-900">
            Every subject has an approved official syllabus.
          </p>
          <p className="mt-0.5 text-sm text-emerald-800">
            This curriculum is ready to approve. Approving locks the structure and every
            syllabus permanently — nobody will be able to edit them again.
          </p>
        </div>
      </div>
    )
  }

  const outstanding: string[] = []
  if (readiness.missing_count > 0) {
    outstanding.push(`${readiness.missing_count} with no syllabus at all`)
  }
  if (readiness.draft_count > 0) {
    outstanding.push(`${readiness.draft_count} with a syllabus still in draft`)
  }

  return (
    <div className="mb-5 flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4">
      <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-600" />
      <div>
        <p className="font-semibold text-amber-900">
          This curriculum cannot be approved yet.
        </p>
        <p className="mt-0.5 text-sm text-amber-800">
          Every subject must have an approved official syllabus first — {outstanding.join(', ')}.
          Approval is permanent, so a subject locked without a syllabus could never be given
          one.
        </p>
      </div>
    </div>
  )
}

function LockedBanner() {
  return (
    <div className="mb-5 flex items-start gap-3 rounded-xl border border-gray-300 bg-gray-50 p-4">
      <BookLock className="mt-0.5 h-5 w-5 shrink-0 text-gray-600" />
      <div>
        <p className="font-semibold text-black">This curriculum is approved and locked.</p>
        <p className="mt-0.5 text-sm text-gray-700">
          The structure and every official syllabus are frozen permanently — for the Dean, for
          the Board, for everyone. Academic changes are made by creating a new curriculum
          version.
        </p>
      </div>
    </div>
  )
}

function ReadinessTiles({ readiness }: { readiness: ReadinessSummary }) {
  const tiles = [
    { label: 'Subjects', value: readiness.total_subjects, icon: FileText },
    { label: 'Syllabus approved', value: readiness.approved_count, icon: CheckCircle2 },
    { label: 'Still in draft', value: readiness.draft_count, icon: SquarePen },
    { label: 'No syllabus yet', value: readiness.missing_count, icon: CircleDashed },
  ]
  return (
    <div className="mb-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      {tiles.map(({ label, value, icon: Icon }) => (
        <div key={label} className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
          <div className="flex items-center justify-between">
            <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">{label}</p>
            <Icon className="h-4 w-4 text-gray-400" />
          </div>
          <p className="mt-1 text-3xl font-bold text-black">{value}</p>
        </div>
      ))}
    </div>
  )
}

function SubjectTable({
  items, locked,
}: {
  items: ReadinessItem[]
  locked: boolean
}) {
  const navigate = useNavigate()

  if (items.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-gray-300 bg-gray-50 p-10 text-center">
        <p className="text-sm text-gray-600">This curriculum has no subjects.</p>
      </div>
    )
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white shadow-sm">
      <table className="w-full min-w-[720px] text-sm">
        <thead className="border-b border-gray-200 bg-gray-50">
          <tr className="text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
            <th className="px-4 py-3">Sem</th>
            <th className="px-4 py-3">Subject</th>
            <th className="px-4 py-3">Category</th>
            <th className="px-4 py-3">Official document</th>
            <th className="px-4 py-3 text-right">Action</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {items.map((item) => (
            <tr key={item.course_id} className="align-top hover:bg-gray-50">
              <td className="px-4 py-3 font-medium text-gray-700">{item.semester}</td>
              <td className="px-4 py-3">
                <p className="font-semibold text-black">{item.course_title}</p>
                <p className="text-xs text-gray-500">
                  {item.course_code}
                  {' · '}
                  {/*
                    WHICH document this subject carries. Saying "Syllabus" for an
                    internship would be a lie in the one place the Board is checking
                    whether the right thing exists.
                  */}
                  <span className="text-gray-600">
                    {COURSE_TYPE_DOCUMENT[item.course_type] ?? 'Syllabus'}
                  </span>
                </p>
              </td>
              <td className="px-4 py-3">
                {item.is_elective ? (
                  <span className="inline-flex items-center rounded-md border border-violet-200 bg-violet-50 px-2 py-0.5 text-xs font-medium text-violet-800">
                    {item.basket_name ?? 'Elective'}
                  </span>
                ) : (
                  <span className="text-xs text-gray-500">Core</span>
                )}
              </td>
              <td className="px-4 py-3">
                <SyllabusBadge status={item.syllabus_status} />
                {/*
                  What is still WRONG with a document that already exists.

                  This is the line that earns the dashboard its keep. The subject
                  with NO syllabus is obvious and nobody misses it. The dangerous one
                  is the document that exists, looks finished, and has three topics
                  in Unit IV — because no Board member re-opens an approved-looking
                  document to count them.
                */}
                {item.gaps.length > 0 && (
                  <ul className="mt-1.5 space-y-0.5">
                    {item.gaps.map((gap) => (
                      <li key={gap} className="flex items-start gap-1 text-xs text-amber-700">
                        <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
                        <span>{gap}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </td>
              <td className="px-4 py-3 text-right">
                {item.syllabus_id ? (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => navigate(`/syllabuses/${item.syllabus_id}`)}
                  >
                    {locked || item.syllabus_status === 'LOCKED' ? 'View' : 'Review & edit'}
                    <ArrowRight className="ml-1 h-3.5 w-3.5" />
                  </Button>
                ) : (
                  <span className="text-xs text-gray-400">Not generated</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function SyllabusBadge({ status }: { status: ReadinessItem['syllabus_status'] }) {
  const styles: Record<string, { text: string; className: string; icon: typeof Lock }> = {
    LOCKED: {
      text: 'Locked',
      className: 'border-gray-300 bg-gray-100 text-gray-700',
      icon: Lock,
    },
    APPROVED: {
      text: 'Approved',
      className: 'border-emerald-200 bg-emerald-50 text-emerald-800',
      icon: CheckCircle2,
    },
    AI_GENERATING: {
      text: 'Generating…',
      className: 'border-blue-200 bg-blue-50 text-blue-800',
      icon: Loader2,
    },
    DRAFT: {
      text: 'Draft — needs review',
      className: 'border-amber-200 bg-amber-50 text-amber-800',
      icon: SquarePen,
    },
  }

  if (!status) {
    return (
      <span className="inline-flex items-center gap-1 rounded-md border border-red-200 bg-red-50 px-2 py-0.5 text-xs font-medium text-red-800">
        <CircleDashed className="h-3.5 w-3.5" />
        None
      </span>
    )
  }

  const { text, className, icon: Icon } = styles[status]
  return (
    <span className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-medium ${className}`}>
      <Icon className={`h-3.5 w-3.5 ${status === 'AI_GENERATING' ? 'animate-spin' : ''}`} />
      {text}
    </span>
  )
}
