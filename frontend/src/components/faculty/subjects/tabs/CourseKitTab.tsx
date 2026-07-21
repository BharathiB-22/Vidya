import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Package, ExternalLink, Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { CourseKitStatusBadge } from '@/components/courseKit/CourseKitStatusBadge'
import { CreateCourseKitDialog } from '@/components/courseKit/CreateCourseKitDialog'
import { CourseKitPanel } from '@/components/courseKit/CourseKitPanel'
import { useCourseKits } from '@/hooks/courseKit'
import type { FacultySubjectTabProps } from './types'

export function CourseKitTab({ ctx }: FacultySubjectTabProps) {
  const navigate = useNavigate()
  const { syllabusId } = ctx
  const [showCreate, setShowCreate] = useState(false)
  const [openKitId, setOpenKitId] = useState<string | null>(null)

  const { data, isLoading, isError } = useCourseKits({ syllabus_id: syllabusId ?? undefined })
  const items = data?.items ?? []

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <p className="text-xs font-semibold text-gray-600 uppercase tracking-wide">
          {data ? `${data.total} unit kit${data.total !== 1 ? 's' : ''}` : 'Course Kits'}
        </p>
        <div className="flex gap-2">
          <Button size="sm" onClick={() => setShowCreate(true)} disabled={!syllabusId}>
            <Plus className="h-3.5 w-3.5 mr-1.5" />
            Create Kit
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => navigate(`/course-kits${syllabusId ? `?syllabus_id=${syllabusId}` : ''}`)}
          >
            <ExternalLink className="h-3.5 w-3.5 mr-1.5" />
            Open Full Page
          </Button>
        </div>
      </div>

      {isLoading ? (
        <div className="text-sm text-gray-600 py-8 text-center">Loading course kits…</div>
      ) : isError ? (
        <div className="text-sm text-gray-600 py-8 text-center">Failed to load course kits.</div>
      ) : items.length === 0 ? (
        <div className="text-center py-12 rounded-xl border border-dashed border-gray-200">
          <Package className="h-8 w-8 mx-auto mb-2 text-gray-200" />
          <p className="text-sm text-gray-600">No course kits created yet for this subject.</p>
        </div>
      ) : (
        <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white overflow-hidden">
          {items.map((k) => (
            <button
              key={k.id}
              type="button"
              onClick={() => setOpenKitId(k.id)}
              className="w-full text-left flex items-center justify-between gap-3 px-4 py-3 hover:bg-gray-50 transition-colors"
            >
              <div className="min-w-0">
                <p className="text-sm font-medium text-gray-800 truncate">Unit {k.unit_number}</p>
                <p className="text-xs text-gray-600">Version {k.version} · {k.complexity_level}</p>
              </div>
              <CourseKitStatusBadge status={k.status} />
            </button>
          ))}
        </div>
      )}

      <CreateCourseKitDialog
        open={showCreate}
        onOpenChange={setShowCreate}
        syllabusId={syllabusId ?? ''}
      />

      <Dialog open={!!openKitId} onOpenChange={(open) => !open && setOpenKitId(null)}>
        <DialogContent className="max-w-4xl max-h-[85vh] overflow-y-auto">
          {openKitId && <CourseKitPanel kitId={openKitId} />}
        </DialogContent>
      </Dialog>
    </div>
  )
}
