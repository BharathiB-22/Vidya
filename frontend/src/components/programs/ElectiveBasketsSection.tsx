import { Trash2, ListTree } from 'lucide-react'
import { useElectiveBaskets, useDeleteBasket, useRemoveCourseFromBasket } from '@/hooks/programs'
import type { Program } from '@/types/program'

interface Props {
  program: Program
}

/** Read-only-once-locked view of every Elective Basket in this program —
 * baskets themselves are created inline from the course dialog (Structure
 * tab); this section is for reviewing/removing them. An elective is never a
 * single standalone course — it always belongs to one of these baskets. */
export function ElectiveBasketsSection({ program }: Props) {
  const isEditable = program.status === 'DRAFT' || program.status === 'PENDING_APPROVAL'
  const { data: baskets = [], isLoading } = useElectiveBaskets(program.id)
  const deleteBasket = useDeleteBasket(program.id)
  const removeCourse = useRemoveCourseFromBasket(program.id)

  if (isLoading) {
    return <div className="h-32 rounded-xl bg-gray-50 animate-pulse" />
  }

  if (baskets.length === 0) {
    return (
      <div className="text-center py-12 rounded-xl border border-dashed border-gray-200">
        <ListTree className="h-8 w-8 mx-auto mb-2 text-gray-300" />
        <p className="text-sm text-gray-500">
          No elective baskets yet. Add one from the Structure tab when creating or editing an elective course.
        </p>
      </div>
    )
  }

  const bySemester = new Map<number, typeof baskets>()
  for (const b of baskets) {
    bySemester.set(b.semester, [...(bySemester.get(b.semester) ?? []), b])
  }

  return (
    <div className="space-y-6">
      {[...bySemester.entries()].sort(([a], [b]) => a - b).map(([semester, semBaskets]) => (
        <div key={semester}>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-2">
            Semester {semester}
          </h3>
          <div className="space-y-3">
            {semBaskets.map((basket) => (
              <div key={basket.id} className="rounded-xl border border-gray-200 bg-white overflow-hidden">
                <div className="flex items-center justify-between gap-4 px-4 py-3 bg-gray-50 border-b border-gray-100">
                  <div>
                    <p className="text-sm font-semibold text-gray-900">{basket.name}</p>
                    {basket.description && (
                      <p className="text-xs text-gray-600 mt-0.5">{basket.description}</p>
                    )}
                  </div>
                  {isEditable && (
                    <button
                      type="button"
                      onClick={() => deleteBasket.mutate(basket.id)}
                      className="text-gray-400 hover:text-red-500 transition-colors shrink-0"
                      title="Delete basket (courses become unlinked, not deleted)"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  )}
                </div>
                {basket.courses.length === 0 ? (
                  <p className="text-xs text-gray-500 px-4 py-3">No courses in this basket yet.</p>
                ) : (
                  <div className="divide-y divide-gray-100">
                    {basket.courses.map((c) => (
                      <div key={c.id} className="flex items-center justify-between gap-4 px-4 py-2.5">
                        <div>
                          <span className="text-sm font-medium text-gray-900">{c.title}</span>
                          <span className="text-xs text-gray-500 ml-2">{c.code} · {c.credits} cr</span>
                        </div>
                        {isEditable && (
                          <button
                            type="button"
                            onClick={() => removeCourse.mutate(c.id)}
                            className="text-xs text-gray-500 hover:text-red-600 transition-colors shrink-0"
                          >
                            Remove from basket
                          </button>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}
