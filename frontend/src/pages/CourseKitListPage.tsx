import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Plus, Package, ChevronLeft, ChevronRight, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog'
import { CourseKitStatusBadge } from '@/components/courseKit/CourseKitStatusBadge'
import { CreateCourseKitDialog } from '@/components/courseKit/CreateCourseKitDialog'
import { useCourseKits, useDeleteKit } from '@/hooks/courseKit'
import { addToast } from '@/hooks/useToast'
import { getErrorMessage } from '@/lib/api'
import type { CourseKitStatus } from '@/types/courseKit'

const WRITE_ROLES = ['ADMIN', 'FACULTY']

const STATUS_OPTIONS: Array<{ value: CourseKitStatus | ''; label: string }> = [
  { value: '',              label: 'All' },
  { value: 'DRAFT',         label: 'Draft' },
  { value: 'AI_GENERATING', label: 'Generating' },
  { value: 'PUBLISHED',     label: 'Published' },
  { value: 'ARCHIVED',      label: 'Archived' },
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

export default function CourseKitListPage() {
  const navigate   = useNavigate()
  const [params]   = useSearchParams()
  const syllabusId = params.get('syllabus_id') ?? ''
  const role       = localStorage.getItem('vidya_role') ?? 'FACULTY'
  const canCreate  = WRITE_ROLES.includes(role)
  const canDelete  = WRITE_ROLES.includes(role)

  const [statusFilter, setStatusFilter] = useState<CourseKitStatus | ''>('')
  const [createOpen,   setCreateOpen]   = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null)

  const { data, isLoading, isError } = useCourseKits({
    syllabus_id: syllabusId || undefined,
    status:      statusFilter || undefined,
  })
  const kits = data?.items ?? []

  const deleteKit = useDeleteKit()

  function handleDeleteConfirm() {
    if (!deleteTarget) return
    deleteKit.mutate(deleteTarget, {
      onSuccess: () => {
        addToast('Draft kit deleted.', 'success')
        setDeleteTarget(null)
      },
      onError: (err) => {
        addToast(getErrorMessage(err), 'error')
        setDeleteTarget(null)
      },
    })
  }

  return (
    <div className="max-w-5xl mx-auto px-4 py-8 space-y-6">

      {/* ── Back ── */}
      {syllabusId && (
        <Button
          variant="ghost"
          size="sm"
          className="-mt-2 -ml-1"
          onClick={() => navigate(-1)}
        >
          <ChevronLeft className="h-4 w-4 mr-1" />
          Back
        </Button>
      )}

      {/* ── Header ── */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Course Kits</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            {syllabusId
              ? <>Syllabus: <span className="font-mono text-gray-700">{syllabusId}</span></>
              : 'All course kits in this tenant'}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium bg-gray-100 text-gray-600 px-2 py-1 rounded-full">
            {role}
          </span>
          {canCreate && syllabusId && (
            <Button onClick={() => setCreateOpen(true)}>
              <Plus className="h-4 w-4 mr-1" />
              New Kit
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
            onClick={() => setStatusFilter(opt.value as CourseKitStatus | '')}
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

      {/* ── Error ── */}
      {isError && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
          Failed to load course kits. Please refresh the page.
        </div>
      )}

      {/* ── List ── */}
      {isLoading ? (
        <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white">
          {[1, 2, 3].map((n) => <SkeletonRow key={n} />)}
        </div>
      ) : kits.length === 0 ? (
        <div className="text-center py-16 rounded-xl border border-dashed border-gray-200">
          <Package className="h-10 w-10 mx-auto mb-3 text-gray-200" />
          <p className="text-sm text-gray-400">
            {statusFilter ? `No kits with status "${statusFilter}".` : 'No course kits yet.'}
          </p>
          {canCreate && syllabusId && !statusFilter && (
            <Button variant="outline" className="mt-4" onClick={() => setCreateOpen(true)}>
              Create the first kit
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
          {kits.map((kit) => (
            <div key={kit.id} className="flex items-center group">
              <button
                type="button"
                className="flex-1 text-left px-5 py-4 hover:bg-gray-50 transition-colors"
                onClick={() => navigate(`/course-kits/${kit.id}`)}
              >
                <div className="flex items-center justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-0.5">
                      <span className="text-sm font-semibold text-gray-800">
                        Unit {kit.unit_number} — v{kit.version}
                      </span>
                      <CourseKitStatusBadge status={kit.status} />
                      <span className="text-xs text-gray-400 bg-gray-100 px-1.5 py-0.5 rounded">
                        {kit.complexity_level}
                      </span>
                    </div>
                    {!syllabusId && (
                      <p className="text-[11px] font-mono text-gray-400 truncate">
                        Syllabus: {kit.syllabus_id}
                      </p>
                    )}
                    <p className="text-xs text-gray-400">
                      Created {new Date(kit.created_at).toLocaleDateString()}
                      {kit.published_at && ` · Published ${new Date(kit.published_at).toLocaleDateString()}`}
                    </p>
                  </div>
                  <ChevronRight className="h-4 w-4 text-gray-300 group-hover:text-gray-500 shrink-0" />
                </div>
              </button>

              {/* Delete button — DRAFT only, FACULTY/ADMIN only */}
              {canDelete && kit.status === 'DRAFT' && (
                <button
                  type="button"
                  title="Delete draft"
                  className="px-3 py-4 text-gray-300 hover:text-red-500 transition-colors shrink-0"
                  onClick={(e) => {
                    e.stopPropagation()
                    setDeleteTarget(kit.id)
                  }}
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {/* ── Pagination hint ── */}
      {data && data.total > kits.length && (
        <p className="text-xs text-gray-400 text-center">
          Showing {kits.length} of {data.total} kits
        </p>
      )}

      {syllabusId && (
        <CreateCourseKitDialog
          open={createOpen}
          onOpenChange={setCreateOpen}
          syllabusId={syllabusId}
        />
      )}

      {/* ── Delete confirmation dialog ── */}
      <Dialog open={!!deleteTarget} onOpenChange={(open) => { if (!open) setDeleteTarget(null) }}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Delete Draft Kit?</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-gray-600 pt-1">
            This draft course kit will be permanently deleted. This cannot be undone.
            Only DRAFT kits can be deleted.
          </p>
          <DialogFooter className="gap-2 pt-2">
            <Button
              variant="outline"
              onClick={() => setDeleteTarget(null)}
              disabled={deleteKit.isPending}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleDeleteConfirm}
              disabled={deleteKit.isPending}
            >
              {deleteKit.isPending ? 'Deleting…' : 'Delete'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
