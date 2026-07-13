import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  AlertTriangle, ArrowLeft, ArrowRight, BookLock, Briefcase, CheckCircle2, ChevronDown,
  ChevronRight, Circle, CircleDashed, Landmark, Loader2, Lock, PenLine, Sparkles, SquarePen,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { PageLoading } from '@/components/shared/PageLoading'
import { PageError } from '@/components/shared/PageError'
import { useApproveCurriculum, useReadiness } from '@/hooks/governance'
import { usePrepareSyllabus } from '@/hooks/syllabuses'
import { useProgram } from '@/hooks/programs'
import { useGovernance } from '@/lib/governance'
import type { ChecklistItem, ReadinessItem, ReadinessSummary } from '@/types/governance'
import { COURSE_TYPE_DOCUMENT } from '@/types/program'
import { ApproveCurriculumDialog } from '@/components/governance/GovernanceDialogs'
import { PrepareSyllabusDialog } from '@/components/governance/PrepareSyllabusDialog'
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

  const approve = useApproveCurriculum()

  // Creating a syllabus MANUALLY needs nothing from the Board — an empty page, and the
  // editor. Asking the AI for a draft needs the academic structure first, so that opens
  // the dialog. Two doors; the same room behind both.
  const prepare = usePrepareSyllabus()
  const [draftSubject, setDraftSubject] = useState<ReadinessItem | null>(null)
  const [approveOpen, setApproveOpen] = useState(false)

  async function prepareSubject(subject: ReadinessItem, mode: 'AI' | 'MANUAL') {
    if (mode === 'AI') {
      setDraftSubject(subject)
      return
    }
    const syllabus = await prepare.mutateAsync({ courseId: subject.course_id, mode: 'MANUAL' })
    navigate(`/syllabuses/${syllabus.id}`)
  }

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

  // The curriculum has two kinds of subject in it, and only one of them is the
  // Board's work. The counts and the approve gate already come from the server and
  // count the taught subjects alone; this is the same split, for the eye.
  const taught    = readiness.items.filter((i) => i.owner === 'BOARD')
  const deanOwned = readiness.items.filter((i) => i.owner === 'DEAN')

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
              {/* There is no "generate everything" button, and there must not be.
                  A Board of Studies does not decide to draft forty syllabi at once; it
                  decides, subject by subject, whether THIS one wants an AI draft or is
                  better written by the professor who has taught it for fifteen years.
                  The choice lives on each row of the table below. */}
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

      {/* What the Board owns: the taught curriculum. Each subject without a syllabus
          offers the Board its two choices — an AI draft, or a blank page. */}
      <SubjectTable items={taught} locked={locked} onPrepare={prepareSubject} />

      {/* What it does not. Shown so the curriculum can be seen whole, and shown as
          information — no status to chase, no button to press, no bearing on whether
          the curriculum can be approved. */}
      <DeanDocuments items={deanOwned} />

      {/* The Board has no separation of duties — one member may enhance, write the
          syllabus, approve and lock this curriculum alone. The trail is what makes
          that accountable, so it belongs on the working screen, not hidden away in
          an admin audit page. */}
      <div className="mt-6">
        <GovernanceTrail programId={programId} />
      </div>

      <PrepareSyllabusDialog
        open={draftSubject !== null}
        onOpenChange={(o) => !o && setDraftSubject(null)}
        subject={draftSubject}
        programId={programId}
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

/**
 * Where the curriculum stands — for the two bodies working on it, separately.
 *
 * The Board's progress is the taught curriculum, and it is the only thing its approve
 * gate tests. The Dean's is the execution documents, which gate HIS publish. They do
 * not wait on each other, so they are not added together: a single "78% complete"
 * would tell each of them how much work the other still had to do.
 */
function ReadinessTiles({ readiness }: { readiness: ReadinessSummary }) {
  return (
    <div className="mb-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <ProgressTile
        label="Board Progress"
        percent={readiness.board_progress_percent}
        detail={`${readiness.approved_count} of ${readiness.total_subjects} subjects approved`}
        accent="bg-blue-600"
      />
      <ProgressTile
        label="Dean Documents"
        percent={readiness.dean_progress_percent}
        detail={
          readiness.dean_document_count === 0
            ? 'None in this curriculum'
            : `${readiness.dean_document_count} internship / project document${
                readiness.dean_document_count === 1 ? '' : 's'
              }`
        }
        accent="bg-gray-500"
      />

      {[
        { label: 'Still in draft', value: readiness.draft_count, icon: SquarePen },
        { label: 'No syllabus yet', value: readiness.missing_count, icon: CircleDashed },
      ].map(({ label, value, icon: Icon }) => (
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

function ProgressTile({
  label, percent, detail, accent,
}: {
  label: string
  percent: number
  detail: string
  accent: string
}) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">{label}</p>
      <p className="mt-1 text-3xl font-bold text-black">{percent}%</p>
      <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-gray-100">
        <div
          className={`h-full rounded-full transition-all ${accent}`}
          style={{ width: `${Math.min(100, Math.max(0, percent))}%` }}
        />
      </div>
      <p className="mt-1.5 text-xs text-gray-500">{detail}</p>
    </div>
  )
}

/**
 * The subject worksheet.
 *
 * Electives are GROUPED into their baskets rather than listed one per row. An MCA
 * with four elective slots of six options each is twenty-four rows of a forty-row
 * table — the electives drown the core subjects, and the Board scrolls past the
 * twelve subjects every student actually takes to reach them.
 *
 * A basket is one row that opens. Its state is the state of its options: a basket
 * whose six options are all approved needs no attention, and one with a missing
 * syllabus inside says so on the closed row, so nothing hides.
 *
 * This is a grouping of exactly the rows the API already returns — no filtering, no
 * second request, and no backend change. Every subject is still here.
 */
function SubjectTable({
  items, locked, onPrepare,
}: {
  items: ReadinessItem[]
  locked: boolean
  onPrepare: (subject: ReadinessItem, mode: 'AI' | 'MANUAL') => void
}) {
  if (items.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-gray-300 bg-gray-50 p-10 text-center">
        <p className="text-sm text-gray-600">This curriculum has no subjects.</p>
      </div>
    )
  }

  const rows = groupElectives(items)

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
          {rows.map((row) =>
            row.kind === 'subject' ? (
              <SubjectRow
                key={row.item.course_id}
                item={row.item}
                locked={locked}
                onPrepare={onPrepare}
              />
            ) : (
              <BasketRows key={row.key} basket={row} locked={locked} onPrepare={onPrepare} />
            ),
          )}
        </tbody>
      </table>
    </div>
  )
}

/** One elective slot — "Elective 1" — and the subjects a student may choose in it. */
interface BasketRow {
  kind: 'basket'
  key: string
  name: string
  semester: number
  options: ReadinessItem[]
}

type Row = { kind: 'subject'; item: ReadinessItem } | BasketRow

/**
 * Core subjects stay as they are; electives collapse into their basket.
 *
 * Order is preserved — the API returns the subjects by semester, and a basket takes
 * the position of its first option, so the worksheet still reads in teaching order.
 */
function groupElectives(items: ReadinessItem[]): Row[] {
  const rows: Row[] = []
  const baskets = new Map<string, BasketRow>()

  for (const item of items) {
    if (!item.is_elective) {
      rows.push({ kind: 'subject', item })
      continue
    }

    // An elective with no basket is a data problem, not a basket called "undefined".
    // It is shown on its own row rather than swept into a group that does not exist.
    const name = item.basket_name?.trim()
    if (!name) {
      rows.push({ kind: 'subject', item })
      continue
    }

    const key = `${item.semester}-${name}`
    const existing = baskets.get(key)
    if (existing) {
      existing.options.push(item)
      continue
    }

    const basket: BasketRow = {
      kind: 'basket', key, name, semester: item.semester, options: [item],
    }
    baskets.set(key, basket)
    rows.push(basket)
  }

  return rows
}

function BasketRows({
  basket, locked, onPrepare,
}: {
  basket: BasketRow
  locked: boolean
  onPrepare: (subject: ReadinessItem, mode: 'AI' | 'MANUAL') => void
}) {
  const [open, setOpen] = useState(false)

  // The basket's state is the state of its options. A closed row must never look
  // calmer than what is inside it — that is the whole risk of collapsing rows, and
  // it is why the counts are on the summary line rather than behind the click.
  const missing = basket.options.filter((o) => !o.syllabus_status).length
  const draft = basket.options.filter((o) => o.syllabus_status === 'DRAFT').length
  const approved = basket.options.filter(
    (o) => o.syllabus_status === 'APPROVED' || o.syllabus_status === 'LOCKED',
  ).length
  const flagged = basket.options.reduce((n, o) => n + o.gaps.length, 0)

  return (
    <>
      <tr className="bg-violet-50/40 align-middle hover:bg-violet-50">
        <td className="px-4 py-3 font-medium text-gray-700">{basket.semester}</td>
        <td className="px-4 py-3">
          <button
            type="button"
            onClick={() => setOpen((o) => !o)}
            aria-expanded={open}
            className="flex items-center gap-1.5 text-left"
          >
            {open
              ? <ChevronDown className="h-4 w-4 shrink-0 text-violet-700" />
              : <ChevronRight className="h-4 w-4 shrink-0 text-violet-700" />}
            <span>
              <span className="font-semibold text-black">{basket.name}</span>
              <span className="block text-xs text-gray-500">
                {basket.options.length} subject{basket.options.length === 1 ? '' : 's'} to
                choose from
              </span>
            </span>
          </button>
        </td>
        <td className="px-4 py-3">
          <span className="inline-flex items-center rounded-md border border-violet-200 bg-violet-100 px-2 py-0.5 text-xs font-medium text-violet-800">
            Elective basket
          </span>
        </td>
        <td className="px-4 py-3">
          <div className="flex flex-wrap items-center gap-1.5">
            {approved > 0 && (
              <span className="inline-flex items-center gap-1 rounded-md border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-800">
                <CheckCircle2 className="h-3.5 w-3.5" />
                {approved} approved
              </span>
            )}
            {draft > 0 && (
              <span className="inline-flex items-center gap-1 rounded-md border border-amber-200 bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-800">
                <SquarePen className="h-3.5 w-3.5" />
                {draft} in draft
              </span>
            )}
            {missing > 0 && (
              <span className="inline-flex items-center gap-1 rounded-md border border-red-200 bg-red-50 px-2 py-0.5 text-xs font-medium text-red-800">
                <CircleDashed className="h-3.5 w-3.5" />
                {missing} with no syllabus
              </span>
            )}
          </div>
          {flagged > 0 && (
            <p className="mt-1.5 flex items-center gap-1 text-xs text-amber-700">
              <AlertTriangle className="h-3 w-3 shrink-0" />
              {flagged} thing{flagged === 1 ? '' : 's'} to fix inside
            </p>
          )}
        </td>
        <td className="px-4 py-3 text-right">
          <Button variant="outline" size="sm" onClick={() => setOpen((o) => !o)}>
            {open ? 'Hide' : 'Expand'}
          </Button>
        </td>
      </tr>

      {open && basket.options.map((option) => (
        <SubjectRow
          key={option.course_id}
          item={option}
          locked={locked}
          nested
          onPrepare={onPrepare}
        />
      ))}
    </>
  )
}

function SubjectRow({
  item, locked, nested = false, onPrepare,
}: {
  item: ReadinessItem
  locked: boolean
  nested?: boolean
  /** How this subject's syllabus should BEGIN — with an AI draft, or with a blank page.
   *  Only offered when it has none; once it exists, the choice is over. */
  onPrepare?: (subject: ReadinessItem, mode: 'AI' | 'MANUAL') => void
}) {
  const navigate = useNavigate()

  return (
    <tr className={`align-top hover:bg-gray-50 ${nested ? 'bg-white' : ''}`}>
      <td className="px-4 py-3 font-medium text-gray-700">{nested ? '' : item.semester}</td>
      <td className={`px-4 py-3 ${nested ? 'pl-11' : ''}`}>
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
          <span className="text-xs text-gray-500">Elective option</span>
        ) : (
          <span className="text-xs text-gray-500">Core</span>
        )}
      </td>
      <td className="px-4 py-3">
        <div className="flex items-center gap-2">
          <SyllabusBadge status={item.syllabus_status} />
          <span className="text-xs font-semibold text-gray-600">
            {item.progress_percent}%
          </span>
        </div>

        {/*
          WHERE this syllabus stands, stage by stage.

          This is the line that earns the dashboard its keep. The subject with NO
          syllabus is obvious and nobody misses it. The dangerous one is the document
          that exists, looks finished, and is quietly half-written — because no Board
          member re-opens an approved-looking syllabus to check.

          Every label here is written by the server. The rules behind them — how deep a
          unit must be, what counts as a duplicate, how many times we retried — are ours,
          and the Board never sees one.
        */}
        {item.checklist.length > 0 && (
          <Checklist items={item.checklist} />
        )}
      </td>
      <td className="px-4 py-3 text-right">
        {/*
          A subject with no syllabus has exactly two futures, and the Board picks one.
          Neither happens by itself: nothing generates until somebody asks for it, and
          "Create Manually" asks for no machine at all.

          Once a syllabus exists there is only one action — open it. The choice was
          about how it BEGAN, and it is over.
        */}
        {item.syllabus_id ? (
          <Button
            variant="outline"
            size="sm"
            onClick={() => navigate(`/syllabuses/${item.syllabus_id}`)}
          >
            {locked || item.syllabus_status === 'LOCKED' ? 'View' : 'Review & edit'}
            <ArrowRight className="ml-1 h-3.5 w-3.5" />
          </Button>
        ) : locked || !onPrepare ? (
          <span className="text-xs text-gray-400">No syllabus</span>
        ) : (
          <div className="flex justify-end gap-1.5">
            <Button size="sm" onClick={() => onPrepare(item, 'AI')}>
              <Sparkles className="mr-1 h-3.5 w-3.5" />
              Generate AI Draft
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => onPrepare(item, 'MANUAL')}
            >
              <PenLine className="mr-1 h-3.5 w-3.5" />
              Create Manually
            </Button>
          </div>
        )}
      </td>
    </tr>
  )
}

/**
 * The Dean's documents — internship, mini project, major project, seminar.
 *
 * They are in this curriculum, so the Board must be able to SEE them: a Board that
 * cannot tell whether the programme contains an internship cannot judge the
 * programme. But it does not write them, does not approve them, and is not waiting on
 * them — what an internship document contains depends on the host company, the
 * supervisor and the review calendar, and no Board of Studies can know those.
 *
 * So this is a list, and deliberately nothing more. No status to chase, no button, no
 * bearing on Approve Curriculum. The Dean prepares them in his own workspace.
 */
function DeanDocuments({ items }: { items: ReadinessItem[] }) {
  if (items.length === 0) return null

  return (
    <section className="mt-5 rounded-xl border border-gray-200 bg-gray-50 p-4">
      <div className="flex items-start gap-2">
        <Briefcase className="mt-0.5 h-4 w-4 shrink-0 text-gray-500" />
        <div className="min-w-0">
          <h2 className="text-sm font-semibold text-black">Prepared by the Dean</h2>
          <p className="mt-0.5 text-sm text-gray-600">
            These are part of the curriculum but not of the taught syllabus. What they
            contain — the host company's requirements, the supervisor, the review calendar,
            the viva — depends on how the institution runs the programme, so the Dean
            prepares and approves them. They do not hold up this curriculum's approval.
          </p>

          <ul className="mt-3 grid gap-2 sm:grid-cols-2">
            {items.map((item) => (
              <li
                key={item.course_id}
                className="rounded-lg border border-gray-200 bg-white px-3 py-2"
              >
                <div className="flex items-baseline justify-between gap-3">
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-medium text-black">
                      {item.course_title}
                    </span>
                    <span className="text-xs text-gray-500">
                      {item.course_code} · Semester {item.semester}
                    </span>
                  </span>
                  <span className="shrink-0 text-xs font-medium text-gray-600">
                    {COURSE_TYPE_DOCUMENT[item.course_type] ?? 'Document'}
                  </span>
                </div>
                {/* The Dean's own lifecycle — created, drafted, reviewed, approved.
                    Never Unit I–V: these documents have no units and never had. */}
                <p className="mt-1 text-xs text-gray-500">
                  {item.progress_percent}% ·{' '}
                  {item.checklist.find((s) => !s.optional && s.state !== 'DONE')?.label ??
                    'Complete'}
                </p>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  )
}

/**
 * The academic lifecycle of one document, as the Board reads it.
 *
 *   ✓ Unit III                     written, and deep enough to publish
 *   ⚠ Unit IV — AI Generation Incomplete    the AI did not finish it
 *     Unit V                       not written yet
 *
 * The stages come from the server, labels and all. Nothing here knows what makes a unit
 * complete, and nothing here should: the Board is told WHERE the syllabus stands and
 * WHAT to do, never how our validator reached that conclusion.
 */
function Checklist({ items }: { items: ChecklistItem[] }) {
  const [open, setOpen] = useState(false)

  // An OPTIONAL stage is never chased. It is shown when the Board opens the full
  // lifecycle, and it is never counted as outstanding work — because the approval gate
  // does not test it, and a checklist that nags about something the system will happily
  // approve without is a checklist the Board learns to ignore.
  const required = items.filter((i) => !i.optional)
  const unfinished = required.filter((i) => i.state !== 'DONE')
  const incomplete = required.filter((i) => i.state === 'INCOMPLETE')

  // Closed, the row shows what needs attention: the stages that are not done, and
  // loudly the ones the AI left half-written. Opened, it shows the whole lifecycle.
  const shown = open ? items : unfinished.slice(0, 3)

  if (unfinished.length === 0) {
    return (
      <p className="mt-1.5 flex items-center gap-1 text-xs text-emerald-700">
        <CheckCircle2 className="h-3 w-3 shrink-0" />
        Complete
      </p>
    )
  }

  return (
    <div className="mt-1.5">
      <ul className="space-y-0.5">
        {shown.map((stage) => (
          <li key={stage.key} className="flex items-start gap-1.5 text-xs">
            <StageIcon state={stage.state} />
            <span
              className={
                stage.optional
                  ? 'text-gray-400'
                  : stage.state === 'DONE'
                    ? 'text-gray-600'
                    : stage.state === 'INCOMPLETE'
                      ? 'font-medium text-amber-800'
                      : 'text-gray-500'
              }
            >
              {stage.label}
              {stage.state === 'INCOMPLETE' && ' — AI Generation Incomplete'}
            </span>
          </li>
        ))}
      </ul>

      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="mt-1 text-xs font-medium text-blue-600 hover:underline"
      >
        {open
          ? 'Hide'
          : `Show all ${items.length} stages${
              incomplete.length ? ` · ${incomplete.length} to regenerate` : ''
            }`}
      </button>
    </div>
  )
}

function StageIcon({ state }: { state: ChecklistItem['state'] }) {
  if (state === 'DONE') {
    return <CheckCircle2 className="mt-0.5 h-3 w-3 shrink-0 text-emerald-600" />
  }
  if (state === 'INCOMPLETE') {
    return <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0 text-amber-600" />
  }
  return <Circle className="mt-0.5 h-3 w-3 shrink-0 text-gray-300" />
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
        No syllabus created
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
