import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Plus, BookOpen } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { SyllabusStatusBadge } from '@/components/syllabus/SyllabusStatusBadge'
import { CreateSyllabusDialog } from '@/components/syllabus/CreateSyllabusDialog'
import { useSyllabuses } from '@/hooks/syllabuses'
import type { SyllabusStatus } from '@/types/syllabus'

const WRITE_ROLES = ['ADMIN', 'FACULTY']

const STATUS_OPTIONS: Array<{ value: SyllabusStatus | ''; label: string }> = [
  { value: '',                 label: 'All' },
  { value: 'DRAFT',            label: 'Draft' },
  { value: 'AI_GENERATING',    label: 'Generating' },
  { value: 'FACULTY_APPROVED', label: 'Faculty Approved' },
  { value: 'ADMIN_LOCKED',     label: 'Locked' },
]

export default function SyllabusListPage() {
  const navigate     = useNavigate()
  const [params]     = useSearchParams()
  const courseId     = params.get('course_id') ?? ''
  const role         = localStorage.getItem('vidya_role') ?? 'FACULTY'
  const canCreate    = WRITE_ROLES.includes(role)

  const [statusFilter, setStatusFilter] = useState<SyllabusStatus | ''>('')
  const [createOpen, setCreateOpen]     = useState(false)

  const { data, isLoading } = useSyllabuses({
    course_id: courseId,
    status:    statusFilter || undefined,
  })
  const syllabuses = data?.items ?? []

  if (!courseId) {
    return (
      <div className="p-8 text-center text-gray-500">
        <BookOpen className="h-10 w-10 mx-auto mb-3 text-gray-300" />
        <p className="text-sm">Please provide a <code>?course_id=</code> query parameter.</p>
      </div>
    )
  }

  return (
    <div className="max-w-5xl mx-auto px-4 py-8 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Syllabuses</h1>
          <p className="text-sm text-gray-500 mt-0.5">Course: <span className="font-mono">{courseId}</span></p>
        </div>
        {canCreate && (
          <Button onClick={() => setCreateOpen(true)}>
            <Plus className="h-4 w-4 mr-1" />
            New Syllabus
          </Button>
        )}
      </div>

      {/* Filters */}
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

      {/* List */}
      {isLoading ? (
        <p className="text-sm text-gray-400 text-center py-12">Loading syllabuses…</p>
      ) : syllabuses.length === 0 ? (
        <div className="text-center py-16 text-gray-400">
          <BookOpen className="h-10 w-10 mx-auto mb-3 text-gray-200" />
          <p className="text-sm">No syllabuses found.</p>
          {canCreate && (
            <Button variant="outline" className="mt-3" onClick={() => setCreateOpen(true)}>
              Create the first syllabus
            </Button>
          )}
        </div>
      ) : (
        <div className="divide-y divide-gray-100 rounded-xl border border-gray-200 bg-white">
          {syllabuses.map((s) => (
            <button
              key={s.id}
              type="button"
              className="w-full text-left px-5 py-4 hover:bg-gray-50 transition-colors"
              onClick={() => navigate(`/syllabuses/${s.id}`)}
            >
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-sm font-semibold text-gray-800">
                      Version {s.version}
                    </span>
                    <SyllabusStatusBadge status={s.status} />
                  </div>
                  {s.change_note && (
                    <p className="text-xs text-gray-500 truncate">{s.change_note}</p>
                  )}
                </div>
                <p className="text-xs text-gray-400 shrink-0 mt-0.5">
                  {new Date(s.created_at).toLocaleDateString()}
                </p>
              </div>
            </button>
          ))}
        </div>
      )}

      {/* Pagination hint */}
      {data && data.total > (data.page_size ?? 20) && (
        <p className="text-xs text-gray-400 text-center">
          Showing {syllabuses.length} of {data.total}
        </p>
      )}

      <CreateSyllabusDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        courseId={courseId}
      />
    </div>
  )
}
