import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Plus, BookOpen, ChevronLeft, ChevronRight, RotateCcw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { SyllabusStatusBadge } from '@/components/syllabus/SyllabusStatusBadge'
import { CreateSyllabusDialog } from '@/components/syllabus/CreateSyllabusDialog'
import { useSyllabuses } from '@/hooks/syllabuses'
import type { SyllabusStatus } from '@/types/syllabus'

const WRITE_ROLES = ['ADMIN', 'FACULTY']

const STATUS_OPTIONS: Array<{ value: SyllabusStatus | ''; label: string }> = [
  { value: '',               label: 'All' },
  { value: 'DRAFT',          label: 'Draft' },
  { value: 'AI_GENERATING',  label: 'Generating' },
  { value: 'PENDING_REVIEW', label: 'Pending Review' },
  { value: 'DEAN_APPROVED',  label: 'Dean Approved' },
  { value: 'DEAN_LOCKED',    label: 'Locked' },
]

function SkeletonRow() {
  return (
    <div className="px-5 py-4 animate-pulse">
      <div className="flex items-center gap-3">
        <div className="h-4 w-16 rounded bg-gray-200" />
        <div className="h-5 w-28 rounded-full bg-gray-200" />
      </div>
      <div className="mt-1.5 h-3 w-48 rounded bg-gray-100" />
    </div>
  )
}

export default function SyllabusListPage() {
  const navigate   = useNavigate()
  const [params]   = useSearchParams()
  const courseId   = params.get('course_id') ?? ''
  const programId  = params.get('program_id') ?? ''
  const role       = localStorage.getItem('vidya_role') ?? 'FACULTY'
  const canCreate  = WRITE_ROLES.includes(role)

  const [statusFilter, setStatusFilter] = useState<SyllabusStatus | ''>('')
  const [createOpen, setCreateOpen]     = useState(false)

  const { data, isLoading } = useSyllabuses({
    course_id: courseId || undefined,
    status:    statusFilter || undefined,
  })
  const syllabuses = data?.items ?? []

  return (
    <div className="max-w-5xl mx-auto px-4 py-8 space-y-6">

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
          <h1 className="text-2xl font-bold text-gray-900">Syllabuses</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            {courseId
              ? <>Course: <span className="font-mono text-gray-700">{courseId}</span></>
              : 'All syllabuses in this tenant'}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium bg-gray-100 text-gray-600 px-2 py-1 rounded-full">
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
        <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white">
          {[1, 2, 3].map((n) => <SkeletonRow key={n} />)}
        </div>
      ) : syllabuses.length === 0 ? (
        <div className="text-center py-16 rounded-xl border border-dashed border-gray-200">
          <BookOpen className="h-10 w-10 mx-auto mb-3 text-gray-200" />
          <p className="text-sm text-gray-400">
            {statusFilter ? `No syllabuses with status "${statusFilter}".` : 'No syllabuses yet.'}
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
        <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white overflow-hidden">
          {syllabuses.map((s) => (
            <button
              key={s.id}
              type="button"
              className="w-full text-left px-5 py-4 hover:bg-gray-50 transition-colors group"
              onClick={() => navigate(`/syllabuses/${s.id}`)}
            >
              <div className="flex items-center justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-0.5">
                    <span className="text-sm font-semibold text-gray-800">
                      Version {s.version}
                    </span>
                    <SyllabusStatusBadge status={s.status} />
                    {s.status === 'DRAFT' && s.change_note?.startsWith('Rejected by Dean:') && (
                      <span className="inline-flex items-center gap-1 text-[10px] font-semibold px-1.5 py-0.5 rounded-full bg-orange-100 text-orange-700 border border-orange-200">
                        <RotateCcw className="h-2.5 w-2.5" />
                        Sent Back
                      </span>
                    )}
                  </div>
                  {!courseId && (
                    <p className="text-[11px] font-mono text-gray-400 truncate">
                      Course: {s.course_id}
                    </p>
                  )}
                  {s.change_note?.startsWith('Rejected by Dean:') ? (
                    <p className="text-xs text-orange-600 truncate">
                      {s.change_note.replace(/^Rejected by Dean:\s*/, '')}
                    </p>
                  ) : s.change_note ? (
                    <p className="text-xs text-gray-500 truncate">{s.change_note}</p>
                  ) : (
                    <p className="text-xs text-gray-400">
                      Created {new Date(s.created_at).toLocaleDateString()}
                    </p>
                  )}
                </div>
                <ChevronRight className="h-4 w-4 text-gray-300 group-hover:text-gray-500 shrink-0" />
              </div>
            </button>
          ))}
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
