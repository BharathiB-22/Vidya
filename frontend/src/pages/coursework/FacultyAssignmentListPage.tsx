import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Plus, ClipboardList, Send, Lock as LockIcon, Pencil, Trash2, Archive, RotateCcw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useAssignments } from '@/hooks/coursework'
import {
  usePublishAssignment, useCloseAssignment, useDeleteAssignment,
  useArchiveAssignment, useRestoreAssignment,
} from '@/hooks/coursework'
import { addToast } from '@/hooks/useToast'
import { getErrorMessage } from '@/lib/api'
import type { CourseworkProgress, CourseworkStatus } from '@/types/coursework'

const STATUS_OPTIONS: Array<{ value: CourseworkStatus | ''; label: string }> = [
  { value: '', label: 'All' },
  { value: 'DRAFT', label: 'Draft' },
  { value: 'PUBLISHED', label: 'Published' },
  { value: 'CLOSED', label: 'Closed' },
  { value: 'SUBMITTED', label: 'Under Evaluation' },
  { value: 'FINALIZED', label: 'Finalized' },
  { value: 'RELEASED', label: 'Released' },
  { value: 'ARCHIVED', label: 'Archived' },
]

const STATUS_STYLE: Record<string, string> = {
  DRAFT: 'bg-gray-100 text-gray-600',
  PUBLISHED: 'bg-green-50 text-green-700',
  CLOSED: 'bg-orange-50 text-orange-700',
  SUBMITTED: 'bg-blue-50 text-blue-700',
  FINALIZED: 'bg-indigo-50 text-indigo-700',
  RELEASED: 'bg-emerald-50 text-emerald-700',
  ARCHIVED: 'bg-gray-100 text-gray-500',
}

/** One line of live evaluation progress for the assignment's owner.
 *
 *  The faculty who set the coursework used to lose sight of it the moment it went
 *  out for evaluation. Every figure here is derived server-side from the existing
 *  submission / AI-evaluation / allocation records — read-only, and advisory where
 *  the AI is concerned. Renders nothing before the first submission arrives, so a
 *  draft row looks exactly as it did. */
function ProgressLine({ progress }: { progress?: CourseworkProgress }) {
  if (!progress || progress.submitted_count === 0) return null
  const {
    submitted_count, total_students, graded_count,
    ai_completed_count, ai_failed_count, ai_pending_count, evaluator_assigned_count,
  } = progress

  return (
    <p className="text-xs text-gray-500 mt-1 flex items-center gap-x-3 gap-y-1 flex-wrap">
      <span>
        <span className="font-medium text-gray-700">{submitted_count}</span>
        {total_students > 0 && `/${total_students}`} submitted
      </span>
      {evaluator_assigned_count > 0 && <span>{evaluator_assigned_count} allocated</span>}
      <span>
        <span className={graded_count > 0 ? 'font-medium text-green-700' : ''}>{graded_count}</span> graded
      </span>
      {ai_completed_count > 0 && <span className="text-indigo-600">AI: {ai_completed_count} done</span>}
      {ai_pending_count > 0 && <span className="text-indigo-400">AI: {ai_pending_count} running</span>}
      {ai_failed_count > 0 && <span className="text-orange-600">AI: {ai_failed_count} failed</span>}
    </p>
  )
}

function SkeletonRow() {
  return (
    <div className="px-5 py-4 animate-pulse">
      <div className="h-4 w-48 rounded bg-gray-200" />
      <div className="mt-1.5 h-3 w-28 rounded bg-gray-100" />
    </div>
  )
}

export default function FacultyAssignmentListPage() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const syllabusId = params.get('syllabus_id') ?? ''
  const [statusFilter, setStatusFilter] = useState<CourseworkStatus | ''>('')

  const { data, isLoading, isError } = useAssignments({
    syllabus_id: syllabusId || undefined,
    status: statusFilter || undefined,
  })
  const assignments = data?.items ?? []

  const publish = usePublishAssignment()
  const close = useCloseAssignment()
  const del = useDeleteAssignment()
  const archive = useArchiveAssignment()
  const restore = useRestoreAssignment()

  function handleArchive(id: string, e: React.MouseEvent) {
    e.stopPropagation()
    archive.mutate(id, {
      onSuccess: () => addToast('Assignment archived.', 'success'),
      onError: (err) => addToast(getErrorMessage(err), 'error'),
    })
  }

  function handleRestore(id: string, e: React.MouseEvent) {
    e.stopPropagation()
    restore.mutate(id, {
      onSuccess: () => addToast('Assignment restored.', 'success'),
      onError: (err) => addToast(getErrorMessage(err), 'error'),
    })
  }

  function handlePublish(id: string, e: React.MouseEvent) {
    e.stopPropagation()
    publish.mutate(id, {
      onSuccess: () => addToast('Assignment published — students have been notified.', 'success'),
      onError: (err) => addToast(getErrorMessage(err), 'error'),
    })
  }

  function handleEdit(id: string, e: React.MouseEvent) {
    e.stopPropagation()
    navigate(`/faculty/assignments/${id}/edit`)
  }

  function handleDelete(id: string, title: string, e: React.MouseEvent) {
    e.stopPropagation()
    if (!window.confirm(`Delete draft assignment "${title}"? This cannot be undone.`)) return
    del.mutate(id, {
      onSuccess: () => addToast('Draft assignment deleted.', 'success'),
      onError: (err) => addToast(getErrorMessage(err), 'error'),
    })
  }

  function handleClose(id: string, e: React.MouseEvent) {
    e.stopPropagation()
    close.mutate(id, {
      onSuccess: () => addToast('Assignment closed.', 'success'),
      onError: (err) => addToast(getErrorMessage(err), 'error'),
    })
  }

  return (
    <div className="max-w-5xl mx-auto px-4 py-8 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Assignments</h1>
          <p className="text-sm text-gray-400 mt-0.5">Create and grade theory coursework.</p>
        </div>
        <Button onClick={() => navigate('/faculty/assignments/new')}>
          <Plus className="h-4 w-4 mr-1.5" />
          New Assignment
        </Button>
      </div>

      <div className="flex gap-1.5 flex-wrap">
        {STATUS_OPTIONS.map((opt) => (
          <button
            key={opt.value}
            type="button"
            onClick={() => setStatusFilter(opt.value)}
            className={`text-xs px-3 py-1.5 rounded-lg font-medium border transition-colors ${
              statusFilter === opt.value
                ? 'bg-gray-900 text-white border-gray-900'
                : 'bg-white text-gray-600 border-gray-200 hover:bg-gray-50'
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {isError && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
          Failed to load assignments. Please refresh.
        </div>
      )}

      {isLoading ? (
        <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white">
          {[1, 2, 3].map((n) => <SkeletonRow key={n} />)}
        </div>
      ) : assignments.length === 0 ? (
        <div className="text-center py-16 rounded-xl border border-dashed border-gray-200">
          <ClipboardList className="h-10 w-10 mx-auto mb-3 text-gray-200" />
          <p className="text-sm text-gray-400">No assignments yet.</p>
        </div>
      ) : (
        <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white overflow-hidden">
          {assignments.map((a) => (
            <button
              key={a.id}
              type="button"
              onClick={() => navigate(`/faculty/assignments/${a.id}/submissions`)}
              className="w-full text-left px-5 py-4 hover:bg-gray-50 transition-colors flex items-center justify-between gap-4"
            >
              <div className="min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-sm font-semibold text-gray-800">{a.title}</span>
                  <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${STATUS_STYLE[a.status]}`}>
                    {a.status}
                  </span>
                  {a.weightage_percent != null && (
                    <span className="text-xs text-gray-400">{a.weightage_percent}% weightage</span>
                  )}
                </div>
                <p className="text-xs text-gray-400 mt-1">
                  Due {new Date(a.due_date).toLocaleString()} · {a.max_marks} marks
                </p>
                <ProgressLine progress={a.progress} />
              </div>
              <div className="flex items-center gap-2 shrink-0">
                {a.status === 'DRAFT' && (
                  <>
                    <Button size="sm" variant="outline" onClick={(e) => handleEdit(a.id, e)}>
                      <Pencil className="h-3.5 w-3.5 mr-1" />
                      Edit
                    </Button>
                    <Button size="sm" variant="outline" onClick={(e) => handlePublish(a.id, e)}>
                      <Send className="h-3.5 w-3.5 mr-1" />
                      Publish
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      className="text-red-600 hover:text-red-700"
                      onClick={(e) => handleDelete(a.id, a.title, e)}
                      disabled={del.isPending}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </>
                )}
                {a.status === 'PUBLISHED' && (
                  <Button size="sm" variant="outline" onClick={(e) => handleClose(a.id, e)}>
                    <LockIcon className="h-3.5 w-3.5 mr-1" />
                    Close
                  </Button>
                )}
                {(a.status === 'FINALIZED' || a.status === 'RELEASED') && (
                  <Button size="sm" variant="outline" onClick={(e) => handleArchive(a.id, e)} disabled={archive.isPending}>
                    <Archive className="h-3.5 w-3.5 mr-1" />
                    Archive
                  </Button>
                )}
                {a.status === 'ARCHIVED' && (
                  <Button size="sm" variant="outline" onClick={(e) => handleRestore(a.id, e)} disabled={restore.isPending}>
                    <RotateCcw className="h-3.5 w-3.5 mr-1" />
                    Restore
                  </Button>
                )}
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
