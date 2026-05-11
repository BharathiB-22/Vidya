import { useState } from 'react'
import { Plus, Pencil, Trash2, Clock } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { UnitDialog } from './UnitDialog'
import {
  useAddUnit,
  useUpdateUnit,
  useDeleteUnit,
} from '@/hooks/syllabuses'
import type { SyllabusUnit, SyllabusUnitCreate, SyllabusUnitUpdate } from '@/types/syllabus'

interface Props {
  syllabusId: string
  units:      SyllabusUnit[]
  isEditable: boolean
}

export function UnitsSection({ syllabusId, units, isEditable }: Props) {
  const [dialogOpen, setDialogOpen]   = useState(false)
  const [editTarget, setEditTarget]   = useState<SyllabusUnit | null>(null)

  const addUnit    = useAddUnit(syllabusId)
  const updateUnit = useUpdateUnit(syllabusId)
  const deleteUnit = useDeleteUnit(syllabusId)

  function openAdd() {
    setEditTarget(null)
    setDialogOpen(true)
  }

  function openEdit(unit: SyllabusUnit) {
    setEditTarget(unit)
    setDialogOpen(true)
  }

  function handleAdd(payload: SyllabusUnitCreate) {
    addUnit.mutate(payload)
  }

  function handleEdit(unitId: string, payload: SyllabusUnitUpdate) {
    updateUnit.mutate({ unitId, payload })
  }

  const sorted = [...units].sort((a, b) => a.unit_number - b.unit_number)
  const totalHours = units.reduce((s, u) => s + u.total_hours, 0)

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-semibold text-gray-700">
            Units ({units.length})
          </h3>
          {units.length > 0 && (
            <span className="flex items-center gap-1 text-xs text-gray-500">
              <Clock className="h-3.5 w-3.5" />
              {totalHours}h total
            </span>
          )}
        </div>
        {isEditable && (
          <Button size="sm" variant="outline" onClick={openAdd}>
            <Plus className="h-4 w-4 mr-1" />
            Add Unit
          </Button>
        )}
      </div>

      {sorted.length === 0 ? (
        <p className="text-sm text-gray-400 py-4 text-center">
          No units yet.{isEditable ? ' Click "Add Unit" to begin.' : ''}
        </p>
      ) : (
        <div className="space-y-2">
          {sorted.map((unit) => (
            <div
              key={unit.id}
              className="rounded-lg border border-gray-200 px-4 py-3 hover:bg-gray-50"
            >
              <div className="flex items-start gap-3">
                <span className="min-w-[2.5rem] text-sm font-bold text-gray-500">
                  U{unit.unit_number}
                </span>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-gray-800">{unit.title}</p>
                  {unit.pedagogy && (
                    <p className="text-xs text-gray-500 mt-0.5">{unit.pedagogy}</p>
                  )}
                  {unit.topics.length > 0 && (
                    <ul className="mt-1 space-y-0.5">
                      {unit.topics.map((t, i) => (
                        <li key={i} className="text-xs text-gray-600 pl-3 border-l-2 border-gray-200">
                          {t.title}
                          {t.hours_estimate ? ` (${t.hours_estimate}h)` : ''}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <span className="flex items-center gap-1 text-xs text-gray-500">
                    <Clock className="h-3.5 w-3.5" />
                    {unit.total_hours}h
                  </span>
                  {isEditable && (
                    <div className="flex gap-1">
                      <Button
                        size="icon"
                        variant="ghost"
                        className="h-7 w-7"
                        onClick={() => openEdit(unit)}
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </Button>
                      <Button
                        size="icon"
                        variant="ghost"
                        className="h-7 w-7 text-red-500 hover:text-red-700"
                        onClick={() => deleteUnit.mutate(unit.id)}
                        disabled={deleteUnit.isPending}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      <UnitDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        mode={editTarget ? 'edit' : 'add'}
        initial={editTarget}
        onAdd={handleAdd}
        onEdit={handleEdit}
        isPending={addUnit.isPending || updateUnit.isPending}
      />
    </div>
  )
}
