import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Plus, BookOpen, ChevronLeft, ChevronRight, RotateCcw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { SyllabusStatusBadge } from '@/components/syllabus/SyllabusStatusBadge'
import { CreateSyllabusDialog } from '@/components/syllabus/CreateSyllabusDialog'
import { useSyllabuses } from '@/hooks/syllabuses'
import type { SyllabusStatus } from '@/types/syllabus'
import { useWorkspace } from '@/lib/workspace'

const WRITE_ROLES = ['ADMIN', 'FACULTY']

const STATUS_OPTIONS: Array<{ value: SyllabusStatus | ''; label: string }> = [
  { value: '',               label: 'All' },
  { value: 'DRAFT',          label: 'Draft' },
  { value: 'AI_GENERATING',  label: 'Generating' },
  { value: 'PENDING_REVIEW', label: 'Pending Review' },
  { value: 'REJECTED',       label: 'Rejected' },
  { value: 'DEAN_APPROVED',  label: 'Dean Approved' },
  { value: 'DEAN_LOCKED',    label: 'Locked' },
]

function semesterLabel(n: number | undefined): string {
  if (!n) return ''
  const suffixes: Record<number, string> = { 1: 'st', 2: 'nd', 3: 'rd' }
  const suffix = suffixes[n] ?? 'th'
  return `${n}${suffix} Semester`
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-IN', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  })
}

function SkeletonCard() {
  return (
    <div className="px-6 py-5 animate-pulse">
      <div className="h-5 w-64 rounded bg-gray-200 mb-2" />
      <div className="h-3.5 w-40 rounded bg-gray-100 mb-1" />
      <div className="h-3 w-28 rounded bg-gray-100 mb-4" />
      <div className="flex items-center gap-2">
        <div className="h-5 w-20 rounded-full bg-gray-200" />
        <div className="h-5 w-16 rounded-full bg-gray-100" />
        <div className="h-3 w-32 rounded bg-gray-100 ml-auto" />
      </div>
    </div>
  )
}

export default function SyllabusListPage() {
  const navigate   = useNavigate()
  const [params]   = useSearchParams()
  const courseId   = params.get('course_id') ?? ''
  const programId  = params.get('program_id') ?? ''
  const { activeWorkspace: role } = useWorkspace()
  const canCreate  = WRITE_ROLES.includes(role)

  const [statusFilter, setStatusFilter] = useState<SyllabusStatus | ''>('')
  const [createOpen, setCreateOpen]     = useState(false)

  const { data, isLoading } = useSyllabuses({
    course_id: courseId || undefined,
    status:    statusFilter || undefined,
  })
  const syllabuses = data?.items ?? []

  return (
    <div className="max-w-4xl mx-auto px-4 py-8 space-y-6">

      {/* ── Back to Program ── */}
      {programId && (
        <Button
          variant="ghost"
          size="sm"
          className="-mt-2 -ml-1"
          onClick={() => navigate(`/programs/${programId}`)}
        >
          <ChevronLeft className="h-4 w-4 mr-1" />
          Back to Program
        </Button>
      )}

      {/* ── Header ── */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900 tracking-tight">Syllabus Registry</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            {courseId ? 'Showing all versions for this course' : 'All syllabuses in this institution'}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium bg-gray-100 text-gray-500 px-2.5 py-1 rounded-full border border-gray-200">
            {role}
          </span>
          {canCreate && courseId && (
            <Button onClick={() => setCreateOpen(true)}>
              <Plus className="h-4 w-4 mr-1" />
              New Syllabus
            </Button>
          )}
        </div>
      </div>

      {/* ── Status filter pills ── */}
      <div className="flex gap-2 flex-wrap">
        {STATUS_OPTIONS.map((opt) => (
          <button
            key={opt.value}
            type="button"
            onClick={() => setStatusFilter(opt.value as SyllabusStatus | '')}
            className={`px-3 py-1 rounded-full text-sm border transition-colors ${
              statusFilter === opt.value
                ? 'bg-gray-900 text-white border-gray-900'
                : 'bg-white text-gray-600 border-gray-200 hover:bg-gray-50'
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {/* ── List ── */}
      {isLoading ? (
        <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white shadow-sm">
          {[1, 2, 3].map((n) => <SkeletonCard key={n} />)}
        </div>
      ) : syllabuses.length === 0 ? (
        <div className="text-center py-16 rounded-xl border border-dashed border-gray-200">
          <BookOpen className="h-10 w-10 mx-auto mb-3 text-gray-200" />
          <p className="text-sm text-gray-400">
            {statusFilter ? `No syllabuses with status "${statusFilter}".` : 'No syllabuses found.'}
          </p>
          {canCreate && courseId && !statusFilter && (
            <Button variant="outline" className="mt-4" onClick={() => setCreateOpen(true)}>
              Create the first syllabus
            </Button>
          )}
          {statusFilter && (
            <button
              type="button"
              onClick={() => setStatusFilter('')}
              className="mt-3 text-xs text-blue-600 underline underline-offset-2"
            >
              Clear filter
            </button>
          )}
        </div>
      ) : (
        <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white shadow-sm overflow-hidden">
          {syllabuses.map((s) => {
            const isRejected  = s.status === 'REJECTED'
            const deanComment = isRejected && s.dean_comment
              ? s.dean_comment.replace(/^\[REVISION REQUESTED\]\s*/, '')
              : null
            const isRevision  = isRejected && s.dean_comment?.startsWith('[REVISION REQUESTED]')

            return (
              <button
                key={s.id}
                type="button"
                className="w-full text-left px-6 py-5 hover:bg-gray-50 transition-colors group"
                onClick={() => navigate(`/syllabuses/${s.id}`)}
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">

                    {/* Course name — primary heading */}
                    <h2 className="text-[15px] font-semibold text-gray-900 leading-snug truncate">
                      {s.course_title ?? 'Untitled Course'}
                    </h2>

                    {/* Program · Semester */}
                    {(s.program_name || s.semester) && (
                      <p className="text-sm text-gray-500 mt-0.5 truncate">
                        {[s.program_name, semesterLabel(s.semester)].filter(Boolean).join(' · ')}
                      </p>
                    )}

                    {/* Course code */}
                    {s.course_code && s.course_code !== '—' && (
                      <p className="text-xs text-gray-400 mt-0.5">
                        Course Code: <span className="font-medium text-gray-600">{s.course_code}</span>
                      </p>
                    )}

                    {/* Dean feedback for rejected syllabi */}
                    {deanComment && (
                      <p className="mt-1.5 text-xs text-red-600 truncate">
                        {isRevision ? 'Revision: ' : 'Rejected: '}{deanComment}
                      </p>
                    )}

                    {/* Footer row: status · version · date */}
                    <div className="mt-3 flex items-center gap-2 flex-wrap">
                      <SyllabusStatusBadge status={s.status} />

                      {isRejected && (
                        <span className="inline-flex items-center gap-1 text-[10px] font-semibold px-1.5 py-0.5 rounded-full bg-red-100 text-red-700 border border-red-200">
                          <RotateCcw className="h-2.5 w-2.5" />
                          {isRevision ? 'Revision Requested' : 'Needs Revision'}
                        </span>
                      )}

                      <span className="text-[11px] text-gray-400 font-medium">
                        Version {s.version}
                      </span>

                      <span className="text-gray-200 text-xs select-none">·</span>

                      <span className="text-[11px] text-gray-400">
                        Created {formatDate(s.created_at)}
                      </span>
                    </div>
                  </div>

                  <ChevronRight className="h-4 w-4 text-gray-300 group-hover:text-gray-500 shrink-0 mt-1" />
                </div>
              </button>
            )
          })}
        </div>
      )}

      {/* ── Pagination hint ── */}
      {data && data.total > syllabuses.length && (
        <p className="text-xs text-gray-400 text-center">
          Showing {syllabuses.length} of {data.total} syllabuses
        </p>
      )}

      {courseId && (
        <CreateSyllabusDialog
          open={createOpen}
          onOpenChange={setCreateOpen}
          courseId={courseId}
        />
      )}
    </div>
  )
}
