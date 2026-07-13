import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  AlertTriangle, ArrowRight, BookLock, Briefcase, CheckCircle2, CircleDashed, Loader2,
  Plus, Send, SquarePen, type LucideIcon,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { PageLoading } from '@/components/shared/PageLoading'
import { PageError } from '@/components/shared/PageError'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { usePrograms, useProgram, useProgramCourses, usePublishProgram } from '@/hooks/programs'
import { usePublishReadiness } from '@/hooks/governance'
import { useCreateSyllabus, useSyllabuses } from '@/hooks/syllabuses'
import { COURSE_TYPE_DOCUMENT, isExecutionDocument } from '@/types/program'
import type { Course } from '@/types/program'

/**
 * The Dean's execution documents.
 *
 * An internship, a mini project, a major project and a seminar are in the curriculum,
 * but they are not TAUGHT. What each one contains — which company hosts the student
 * and what it requires of them, which supervisor is free, when the reviews fall, how
 * the viva is run — depends on how this institution executes the programme. A Board of
 * Studies cannot know any of it, and the workflow that asked it to produced its own
 * absurdity: a curriculum that could not be approved until a Board had signed off the
 * evaluation rubric of an internship nobody had arranged yet.
 *
 * So they are the Dean's, from end to end. He creates each document, drafts it with AI
 * if he wants one, edits it, approves it, and publishes it. The Board decides only THAT
 * the curriculum contains an internship.
 *
 * The document itself is edited on the ordinary syllabus page — it is the same kind of
 * record, with the same versions, the same audit trail and the same approval. This page
 * is the way in: it is the list of the documents that are the Dean's, and what each one
 * still needs.
 */
export default function ExecutionDocumentsPage() {
  const { data: programs, isLoading, isError } = usePrograms()
  const [programId, setProgramId] = useState<string>('')

  if (isLoading) {
    return <div className="p-6"><PageLoading message="Loading your curricula…" /></div>
  }
  if (isError || !programs) {
    return <div className="p-6"><PageError message="Could not load your curricula." /></div>
  }

  const all = programs.items

  // The Dean's half of the workflow, in the three states it can actually be in.
  //
  // A curriculum the Board has not finished with is not his problem yet, and does not
  // appear: he cannot write an internship for a curriculum whose subjects may still
  // change. What he sees is what is his — waiting on him, ready to release, or released.
  const waiting   = all.filter((p) => p.status === 'APPROVED')
  const published = all.filter((p) => p.status === 'PUBLISHED')

  const selected = programId || waiting[0]?.id || all[0]?.id || ''

  return (
    <div className="mx-auto max-w-5xl px-4 py-6">
      <header className="mb-6 flex items-start gap-2.5">
        <span className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-black text-white">
          <Briefcase className="h-5 w-5" />
        </span>
        <div className="min-w-0">
          <h1 className="text-2xl font-bold tracking-tight text-black">
            Execution Documents &amp; Publishing
          </h1>
          <p className="text-sm text-gray-600">
            Internships, projects and seminars. These are yours: what they contain depends on
            the host company, the supervisor and the review calendar — things the Board cannot
            settle. You prepare them, you approve them, and then you publish the curriculum.
          </p>
        </div>
      </header>

      {/* Where every curriculum of yours stands. Board-approved curricula are the ones
          waiting on YOU; published ones are done. */}
      <div className="mb-6 grid gap-3 sm:grid-cols-3">
        <StateTile label="Waiting on you" value={waiting.length} tone="amber" />
        <StateTile label="Published" value={published.length} tone="gray" />
        <StateTile label="All curricula" value={all.length} tone="gray" />
      </div>

      {all.length === 0 ? (
        <div className="rounded-xl border border-dashed border-gray-300 bg-gray-50 p-10 text-center">
          <p className="text-sm text-gray-600">You have no curricula yet.</p>
        </div>
      ) : (
        <>
          <div className="mb-4 max-w-md">
            <label className="mb-1 block text-sm font-medium text-gray-700">Curriculum</label>
            <Select value={selected} onValueChange={setProgramId}>
              <SelectTrigger><SelectValue placeholder="Choose a curriculum" /></SelectTrigger>
              <SelectContent>
                {all.map((p) => (
                  <SelectItem key={p.id} value={p.id}>
                    {p.title} — v{p.version} ({p.status.toLowerCase()})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {selected && <PublishPanel programId={selected} />}
          {selected && <DocumentList programId={selected} />}
        </>
      )}
    </div>
  )
}

function StateTile({
  label, value, tone,
}: {
  label: string
  value: number
  tone: 'amber' | 'gray'
}) {
  return (
    <div
      className={`rounded-xl border p-4 shadow-sm ${
        tone === 'amber' ? 'border-amber-200 bg-amber-50' : 'border-gray-200 bg-white'
      }`}
    >
      <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">{label}</p>
      <p className="mt-1 text-3xl font-bold text-black">{value}</p>
    </div>
  )
}

/**
 * The second gate — and it is the Dean's.
 *
 * The Board approves the taught curriculum, and that publishes nothing. Publishing is a
 * separate act by a different authority, and it becomes possible only when every
 * execution document is approved as well. A curriculum released with an internship
 * nobody has written promises students a component that does not exist, and they find
 * out in their final year.
 *
 * Publishing changes no content. It moves a state, and it freezes the Dean's documents
 * so that what students were shown stays what students were shown.
 */
function PublishPanel({ programId }: { programId: string }) {
  const { data: program } = useProgram(programId)
  const { data: gate } = usePublishReadiness(programId)
  const publish = usePublishProgram()

  if (!program || !gate) return null

  if (program.status === 'PUBLISHED') {
    return (
      <div className="mb-4 flex items-start gap-2 rounded-xl border border-gray-300 bg-gray-50 p-4">
        <BookLock className="mt-0.5 h-5 w-5 shrink-0 text-gray-600" />
        <div>
          <p className="font-semibold text-black">This curriculum is published.</p>
          <p className="mt-0.5 text-sm text-gray-700">
            Everything in it is immutable — the syllabi, and your execution documents.
            Students are taught and assessed against exactly this. A change is a new
            version, never an edit to what was published.
          </p>
        </div>
      </div>
    )
  }

  if (program.status !== 'APPROVED') {
    return (
      <div className="mb-4 flex items-start gap-2 rounded-xl border border-gray-200 bg-white p-4">
        <Loader2 className="mt-0.5 h-5 w-5 shrink-0 animate-spin text-gray-400" />
        <div>
          <p className="font-semibold text-black">Still with the board.</p>
          <p className="mt-0.5 text-sm text-gray-600">
            The board is approving the teaching subjects. Your execution documents can be
            prepared once it has finished.
          </p>
        </div>
      </div>
    )
  }

  const outstanding = gate.total_documents - gate.approved_documents

  return (
    <div
      className={`mb-4 flex flex-wrap items-start gap-3 rounded-xl border p-4 ${
        gate.can_publish
          ? 'border-emerald-200 bg-emerald-50'
          : 'border-amber-200 bg-amber-50'
      }`}
    >
      {gate.can_publish ? (
        <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-emerald-600" />
      ) : (
        <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-600" />
      )}

      <div className="min-w-0 flex-1">
        {gate.can_publish ? (
          <>
            <p className="font-semibold text-emerald-900">Ready to publish.</p>
            <p className="mt-0.5 text-sm text-emerald-800">
              The board has approved every teaching subject, and every
              execution document is approved. Publishing releases the curriculum to faculty and
              students — it changes nothing in it, and freezes your documents as they stand.
            </p>
          </>
        ) : (
          <>
            <p className="font-semibold text-amber-900">
              {outstanding} execution document{outstanding === 1 ? '' : 's'} still to approve.
            </p>
            <p className="mt-0.5 text-sm text-amber-800">
              The board has finished its half. The curriculum can be published once every
              internship, project and seminar document below is prepared and approved by you.
            </p>
          </>
        )}
      </div>

      <Button
        disabled={!gate.can_publish || publish.isPending}
        onClick={() => publish.mutate({ id: programId, payload: {} })}
      >
        <Send className="mr-1 h-4 w-4" />
        {publish.isPending ? 'Publishing…' : 'Publish Curriculum'}
      </Button>
    </div>
  )
}

function DocumentList({ programId }: { programId: string }) {
  const { data: courses = [], isLoading } = useProgramCourses(programId)

  if (isLoading) return <PageLoading message="Loading the curriculum…" />

  const execution = courses
    .filter((c) => isExecutionDocument(c.course_type))
    .sort((a, b) => a.semester - b.semester || a.code.localeCompare(b.code))

  if (execution.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-gray-300 bg-gray-50 p-10 text-center">
        <p className="text-sm text-gray-600">
          This curriculum has no internship, project or seminar.
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-2">
      {execution.map((course) => (
        <DocumentRow key={course.id} course={course} />
      ))}
    </div>
  )
}

/**
 * One document, and the one thing to do with it next.
 *
 * The syllabus list is queried per course rather than per programme, because there are
 * only ever two or three of these in a curriculum — an internship, a mini project, a
 * major project — and a handful of small queries beats inventing an endpoint.
 */
function DocumentRow({ course }: { course: Course }) {
  const navigate = useNavigate()
  const create = useCreateSyllabus()
  const { data, isLoading } = useSyllabuses({ course_id: course.id, page_size: 50 })

  // The latest version is the live one; older versions are history.
  const latest = [...(data?.items ?? [])].sort((a, b) => b.version - a.version)[0]
  const label = COURSE_TYPE_DOCUMENT[course.course_type ?? 'THEORY'] ?? 'Document'

  function createAndOpen() {
    create.mutate(
      { course_id: course.id },
      { onSuccess: (syllabus) => navigate(`/syllabuses/${syllabus.id}`) },
    )
  }

  return (
    <div className="flex flex-wrap items-center gap-3 rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
      <div className="min-w-0 flex-1">
        <p className="font-semibold text-black">{course.title}</p>
        <p className="text-xs text-gray-500">
          {course.code} · Semester {course.semester} · {label}
        </p>
      </div>

      {isLoading ? (
        <Loader2 className="h-4 w-4 animate-spin text-gray-400" />
      ) : latest ? (
        <>
          <DocumentStatus status={latest.status} />
          <Button
            variant="outline"
            size="sm"
            onClick={() => navigate(`/syllabuses/${latest.id}`)}
          >
            {latest.status === 'LOCKED' ? 'View' : 'Prepare & approve'}
            <ArrowRight className="ml-1 h-3.5 w-3.5" />
          </Button>
        </>
      ) : (
        <>
          <span className="inline-flex items-center gap-1 rounded-md border border-red-200 bg-red-50 px-2 py-0.5 text-xs font-medium text-red-800">
            <CircleDashed className="h-3.5 w-3.5" />
            Not created
          </span>
          <Button size="sm" onClick={createAndOpen} disabled={create.isPending}>
            <Plus className="mr-1 h-4 w-4" />
            {create.isPending ? 'Creating…' : `Create ${label}`}
          </Button>
        </>
      )}
    </div>
  )
}

function DocumentStatus({ status }: { status: string }) {
  const styles: Record<string, { text: string; className: string; icon: LucideIcon }> = {
    LOCKED: {
      text: 'Published',
      className: 'border-gray-300 bg-gray-100 text-gray-700',
      icon: CheckCircle2,
    },
    APPROVED: {
      text: 'Approved by you',
      className: 'border-emerald-200 bg-emerald-50 text-emerald-800',
      icon: CheckCircle2,
    },
    AI_GENERATING: {
      text: 'Drafting…',
      className: 'border-blue-200 bg-blue-50 text-blue-800',
      icon: Loader2,
    },
    DRAFT: {
      text: 'Draft — needs your approval',
      className: 'border-amber-200 bg-amber-50 text-amber-800',
      icon: SquarePen,
    },
  }

  const style = styles[status] ?? styles.DRAFT
  const Icon = style.icon
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-medium ${style.className}`}
    >
      <Icon className={`h-3.5 w-3.5 ${status === 'AI_GENERATING' ? 'animate-spin' : ''}`} />
      {style.text}
    </span>
  )
}
