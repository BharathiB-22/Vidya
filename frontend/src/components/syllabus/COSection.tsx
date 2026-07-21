import { useState } from 'react'
import { Plus, Pencil, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { CODialog } from './CODialog'
import {
  useAddCourseOutcome,
  useUpdateCourseOutcome,
  useDeleteCourseOutcome,
} from '@/hooks/syllabuses'
import type { CourseOutcome, CourseOutcomeCreate, CourseOutcomeUpdate } from '@/types/syllabus'

const BLOOM_COLOR: Record<string, string> = {
  REMEMBER:   'bg-gray-100 text-gray-700',
  UNDERSTAND: 'bg-blue-100 text-blue-700',
  APPLY:      'bg-green-100 text-green-700',
  ANALYSE:    'bg-yellow-100 text-yellow-700',
  EVALUATE:   'bg-orange-100 text-orange-700',
  CREATE:     'bg-purple-100 text-purple-700',
}

interface Props {
  syllabusId: string
  outcomes:   CourseOutcome[]
  isEditable: boolean
}

export function COSection({ syllabusId, outcomes, isEditable }: Props) {
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editTarget, setEditTarget] = useState<CourseOutcome | null>(null)

  const addCO    = useAddCourseOutcome(syllabusId)
  const updateCO = useUpdateCourseOutcome(syllabusId)
  const deleteCO = useDeleteCourseOutcome(syllabusId)

  function openAdd() {
    setEditTarget(null)
    setDialogOpen(true)
  }

  function openEdit(co: CourseOutcome) {
    setEditTarget(co)
    setDialogOpen(true)
  }

  function handleAdd(payload: CourseOutcomeCreate) {
    addCO.mutate(payload)
  }

  function handleEdit(coId: string, payload: CourseOutcomeUpdate) {
    updateCO.mutate({ coId, payload })
  }

  const sorted = [...outcomes].sort((a, b) => a.display_order - b.display_order)

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-700">
          Course Outcomes ({outcomes.length})
        </h3>
        {isEditable && (
          <Button size="sm" variant="outline" onClick={openAdd}>
            <Plus className="h-4 w-4 mr-1" />
            Add CO
          </Button>
        )}
      </div>

      {sorted.length === 0 ? (
        <p className="text-sm text-gray-600 py-4 text-center">
          No course outcomes yet.{isEditable ? ' Click "Add CO" to get started.' : ''}
        </p>
      ) : (
        <div className="divide-y divide-gray-100 rounded-lg border border-gray-200">
          {sorted.map((co) => (
            <div key={co.id} className="flex items-start gap-3 px-4 py-3 hover:bg-gray-50">
              <span className="min-w-[3rem] text-sm font-semibold text-gray-800">{co.code}</span>
              <p className="flex-1 text-sm text-gray-700">{co.description}</p>
              <span
                className={`text-xs font-medium px-2 py-0.5 rounded-full whitespace-nowrap ${BLOOM_COLOR[co.bloom_level] ?? 'bg-gray-100 text-gray-600'}`}
              >
                {co.bloom_level[0] + co.bloom_level.slice(1).toLowerCase()}
              </span>
              {isEditable && (
                <div className="flex gap-1 ml-2 shrink-0">
                  <Button
                    size="icon"
                    variant="ghost"
                    className="h-7 w-7"
                    onClick={() => openEdit(co)}
                  >
                    <Pencil className="h-3.5 w-3.5" />
                  </Button>
                  <Button
                    size="icon"
                    variant="ghost"
                    className="h-7 w-7 text-red-500 hover:text-red-700"
                    onClick={() => deleteCO.mutate(co.id)}
                    disabled={deleteCO.isPending}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      <CODialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        mode={editTarget ? 'edit' : 'add'}
        initial={editTarget}
        onAdd={handleAdd}
        onEdit={handleEdit}
        isPending={addCO.isPending || updateCO.isPending}
      />
    </div>
  )
}
