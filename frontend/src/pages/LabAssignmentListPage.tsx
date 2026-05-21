import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Plus, ClipboardList, ChevronRight, ChevronLeft, Download } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { LabStatusBadge } from '@/components/labs/LabStatusBadge'
import { useLabAssignments } from '@/hooks/labs'
import { useCreateAssignment, usePublishAssignment, useCloseAssignment } from '@/hooks/labs'
import { getModerationReportUrl } from '@/lib/api/labs'
import { addToast } from '@/hooks/useToast'
import type { AssignmentStatus, AssignmentCreate } from '@/types/labs'

const WRITE_ROLES = ['ADMIN', 'FACULTY']

const STATUS_OPTIONS: Array<{ value: AssignmentStatus | ''; label: string }> = [
  { value: '',          label: 'All' },
  { value: 'DRAFT',     label: 'Draft' },
  { value: 'PUBLISHED', label: 'Published' },
  { value: 'CLOSED',    label: 'Closed' },
  { value: 'ARCHIVED',  label: 'Archived' },
]

function SkeletonRow() {
  return (
    <div className="px-5 py-4 animate-pulse">
      <div className="flex items-center gap-3">
        <div className="h-4 w-40 rounded bg-gray-200" />
        <div className="h-5 w-20 rounded-full bg-gray-200" />
      </div>
      <div className="mt-1.5 h-3 w-32 rounded bg-gray-100" />
    </div>
  )
}

function CreateDialog({
  onClose,
  onCreated,
}: {
  onClose: () => void
  onCreated: (id: string) => void
}) {
  const [title, setTitle]   = useState('')
  const [type, setType]     = useState<'WRITTEN' | 'CODE'>('WRITTEN')
  const [lang, setLang]     = useState('python')
  const [rubricName, setRubricName] = useState('Content Quality')
  const { mutateAsync, isPending } = useCreateAssignment()

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const payload: AssignmentCreate = {
      title,
      submission_type: type,
      language: type === 'CODE' ? lang : undefined,
      rubric: [{
        criterion_id: 'c1',
        name: rubricName,
        description: 'Evaluates the overall quality of the submission.',
        max_marks: 100,
        weight: 1.0,
      }],
    }
    const assignment = await mutateAsync(payload)
    onCreated(assignment.id)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm">
      <form
        onSubmit={handleSubmit}
        className="bg-white rounded-2xl shadow-xl w-full max-w-md p-6 space-y-4"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-semibold text-gray-900">New Assignment</h2>

        <div className="space-y-1">
          <label className="text-sm font-medium text-gray-700">Title</label>
          <input
            className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-400"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
            placeholder="Assignment title"
          />
        </div>

        <div className="space-y-1">
          <label className="text-sm font-medium text-gray-700">Type</label>
          <select
            className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none"
            value={type}
            onChange={(e) => setType(e.target.value as 'WRITTEN' | 'CODE')}
          >
            <option value="WRITTEN">Written</option>
            <option value="CODE">Code</option>
          </select>
        </div>

        {type === 'CODE' && (
          <div className="space-y-1">
            <label className="text-sm font-medium text-gray-700">Language</label>
            <select
              className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
              value={lang}
              onChange={(e) => setLang(e.target.value)}
            >
              <option value="python">Python</option>
            </select>
          </div>
        )}

        <div className="space-y-1">
          <label className="text-sm font-medium text-gray-700">First rubric criterion</label>
          <input
            className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
            value={rubricName}
            onChange={(e) => setRubricName(e.target.value)}
            placeholder="e.g. Correctness"
          />
          <p className="text-xs text-gray-400">You can add more criteria after creation.</p>
        </div>

        <div className="flex gap-2 pt-2 justify-end">
          <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
          <Button type="submit" disabled={isPending || !title.trim()}>
            {isPending ? 'Creating…' : 'Create Draft'}
          </Button>
        </div>
      </form>
    </div>
  )
}

export default function LabAssignmentListPage() {
  const navigate          = useNavigate()
  const [params]          = useSearchParams()
  const syllabusId        = params.get('syllabus_id') ?? ''
  const role              = localStorage.getItem('vidya_role') ?? 'FACULTY'
  const canWrite          = WRITE_ROLES.includes(role)

  const [statusFilter, setStatusFilter] = useState<AssignmentStatus | ''>('')
  const [createOpen,   setCreateOpen]   = useState(false)

  const { data, isLoading, isError } = useLabAssignments({
    syllabus_id: syllabusId || undefined,
    status: statusFilter || undefined,
  })
  const assignments = data?.items ?? []

  const { mutate: publish, isPending: publishing } = usePublishAssignment()
  const { mutate: close,   isPending: closing }    = useCloseAssignment()

  return (
    <div className="max-w-5xl mx-auto px-4 py-8 space-y-6">
      <Button variant="ghost" size="sm" className="-mt-2 -ml-1" onClick={() => navigate(-1)}>
        <ChevronLeft className="h-4 w-4 mr-1" />
        Back
      </Button>

      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Lab Assignments</h1>
          {syllabusId && (
            <p className="text-sm text-gray-500 mt-0.5">
              Syllabus: <span className="font-mono text-gray-700">{syllabusId}</span>
            </p>
          )}
        </div>
        {canWrite && (
          <Button onClick={() => setCreateOpen(true)}>
            <Plus className="h-4 w-4 mr-1" />
            New Assignment
          </Button>
        )}
      </div>

      {/* Status filter */}
      <div className="flex gap-2 flex-wrap">
        {STATUS_OPTIONS.map((opt) => (
          <button
            key={opt.value}
            type="button"
            onClick={() => setStatusFilter(opt.value as AssignmentStatus | '')}
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
            <div key={a.id} className="px-5 py-4 hover:bg-gray-50 transition-colors">
              <div className="flex items-center justify-between gap-4">
                <button
                  type="button"
                  className="flex-1 text-left"
                  onClick={() => navigate(`/labs/${a.id}`)}
                >
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-semibold text-gray-800">{a.title}</span>
                    <LabStatusBadge status={a.status} />
                    <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${
                      a.submission_type === 'CODE'
                        ? 'bg-blue-50 text-blue-700'
                        : 'bg-purple-50 text-purple-700'
                    }`}>
                      {a.submission_type}
                    </span>
                    {a.max_marks != null && (
                      <span className="text-xs text-gray-400">{a.max_marks} marks</span>
                    )}
                  </div>
                  <p className="text-xs text-gray-400 mt-0.5">
                    Created {new Date(a.created_at).toLocaleDateString()}
                    {a.deadline && ` · Due ${new Date(a.deadline).toLocaleDateString()}`}
                  </p>
                </button>

                <div className="flex items-center gap-2">
                  {/* Quick actions for faculty */}
                  {canWrite && a.status === 'DRAFT' && (
                    <Button
                      size="sm"
                      variant="ghost"
                      className="text-green-700 hover:text-green-800 hover:bg-green-50"
                      onClick={(e) => {
                        e.stopPropagation()
                        publish(a.id, {
                          onSuccess: () => addToast('Assignment published.', 'success'),
                          onError:   () => addToast('Failed to publish assignment.', 'error'),
                        })
                      }}
                      disabled={publishing}
                    >
                      Publish
                    </Button>
                  )}
                  {canWrite && a.status === 'PUBLISHED' && (
                    <>
                      <Button
                        size="sm"
                        variant="ghost"
                        className="text-orange-700 hover:bg-orange-50"
                        onClick={(e) => {
                          e.stopPropagation()
                          close(a.id, {
                            onSuccess: () => addToast('Assignment closed.', 'success'),
                            onError:   () => addToast('Failed to close assignment.', 'error'),
                          })
                        }}
                        disabled={closing}
                      >
                        Close
                      </Button>
                      <a
                        href={getModerationReportUrl(a.id)}
                        download
                        className="p-1 rounded hover:bg-gray-100 text-gray-400 hover:text-gray-600"
                        title="Download moderation report"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <Download className="h-4 w-4" />
                      </a>
                    </>
                  )}
                  <button
                    type="button"
                    onClick={() => navigate(`/labs/${a.id}`)}
                    className="p-1 rounded hover:bg-gray-100"
                  >
                    <ChevronRight className="h-4 w-4 text-gray-300" />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {createOpen && (
        <CreateDialog
          onClose={() => setCreateOpen(false)}
          onCreated={(id) => { setCreateOpen(false); navigate(`/labs/${id}`) }}
        />
      )}
    </div>
  )
}
