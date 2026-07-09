import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Trash2, ListTree, Plus, Pencil, Check, X, Lock, Layers } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select, SelectTrigger, SelectValue, SelectContent, SelectItem,
} from '@/components/ui/select'
import {
  programKeys,
  useElectiveBaskets,
  useProgramCourses,
  useCreateBasket,
  useUpdateBasket,
  useDeleteBasket,
  useRemoveCourseFromBasket,
  useAddCourse,
  useUpdateCourse,
} from '@/hooks/programs'
import type { Course, ElectiveBasket, Program } from '@/types/program'

interface Props {
  program: Program
}

/** Representative credits a basket contributes to the program: a student takes
 *  exactly ONE course from the basket, so the program counts the basket once,
 *  not once per option. We surface the largest member credit as that single
 *  representative value. */
function representativeCredits(basket: ElectiveBasket): number {
  if (basket.courses.length === 0) return 0
  return Math.max(...basket.courses.map((c) => c.credits))
}

/** Full Dean management of every Elective Basket in this program. A basket
 *  belongs to one semester and holds multiple selectable elective courses;
 *  the program only ever counts ONE representative elective per basket toward
 *  total credits. Create/rename/delete baskets and add/create/remove courses
 *  while the program is still Draft or Pending Approval; once Approved or
 *  Published the section is read-only and the Dean creates a new version to
 *  make changes. */
export function ElectiveBasketsSection({ program }: Props) {
  const isEditable = program.status === 'DRAFT' || program.status === 'PENDING_APPROVAL'
  const qc = useQueryClient()

  const { data: baskets = [], isLoading } = useElectiveBaskets(program.id)
  const { data: courses = [] } = useProgramCourses(program.id)

  const createBasket = useCreateBasket(program.id)
  const deleteBasket = useDeleteBasket(program.id)

  const maxSem = Math.max(program.duration_years * 2, ...baskets.map((b) => b.semester), 1)
  const semesterOptions = Array.from({ length: maxSem }, (_, i) => i + 1)

  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState('')
  const [newSemester, setNewSemester] = useState('1')
  const [createError, setCreateError] = useState<string | null>(null)

  const invalidateBaskets = () =>
    qc.invalidateQueries({ queryKey: programKeys.baskets(program.id) })

  async function handleCreate() {
    if (!newName.trim()) return
    setCreateError(null)
    try {
      await createBasket.mutateAsync({ semester: Number(newSemester), name: newName.trim() })
      setNewName('')
      setCreating(false)
    } catch (e) {
      setCreateError(e instanceof Error ? e.message : 'Could not create the basket.')
    }
  }

  if (isLoading) {
    return <div className="h-32 rounded-xl bg-gray-50 animate-pulse" />
  }

  const bySemester = new Map<number, ElectiveBasket[]>()
  for (const b of baskets) {
    bySemester.set(b.semester, [...(bySemester.get(b.semester) ?? []), b])
  }

  return (
    <div className="space-y-5">
      {/* Header + create control */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <p className="text-sm text-gray-600">
            Each basket belongs to a semester and holds several elective courses a student
            picks ONE from. The program counts a single representative elective per basket
            toward total credits.
          </p>
        </div>
        {isEditable ? (
          <Button size="sm" onClick={() => { setCreating((v) => !v); setCreateError(null) }}>
            <Plus className="h-4 w-4 mr-1" />
            New Basket
          </Button>
        ) : (
          <div className="flex items-center gap-1.5 text-xs text-gray-500 rounded-md border border-gray-200 bg-gray-50 px-2.5 py-1.5">
            <Lock className="h-3.5 w-3.5" />
            {program.status === 'PUBLISHED' ? 'Published' : 'Approved'} — create a new version to modify baskets.
          </div>
        )}
      </div>

      {creating && isEditable && (
        <div className="rounded-xl border border-gray-200 bg-white p-4 space-y-3">
          <h3 className="text-sm font-semibold text-gray-900">Create Elective Basket</h3>
          <div className="grid grid-cols-1 sm:grid-cols-[8rem_1fr] gap-3">
            <Select value={newSemester} onValueChange={setNewSemester}>
              <SelectTrigger><SelectValue placeholder="Semester" /></SelectTrigger>
              <SelectContent>
                {semesterOptions.map((s) => (
                  <SelectItem key={s} value={String(s)}>Semester {s}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Input
              autoFocus
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') handleCreate() }}
              placeholder="e.g. Artificial Intelligence Electives"
            />
          </div>
          {createError && <p className="text-xs text-red-600">{createError}</p>}
          <div className="flex items-center gap-2">
            <Button size="sm" disabled={!newName.trim() || createBasket.isPending} onClick={handleCreate}>
              {createBasket.isPending ? 'Creating…' : 'Create Basket'}
            </Button>
            <Button size="sm" variant="outline" onClick={() => { setCreating(false); setNewName('') }}>
              Cancel
            </Button>
          </div>
        </div>
      )}

      {baskets.length === 0 ? (
        <div className="text-center py-12 rounded-xl border border-dashed border-gray-200">
          <ListTree className="h-8 w-8 mx-auto mb-2 text-gray-300" />
          <p className="text-sm text-gray-500">
            No elective baskets yet.{isEditable ? ' Use “New Basket” to create one.' : ''}
          </p>
        </div>
      ) : (
        <div className="space-y-6">
          {[...bySemester.entries()].sort(([a], [b]) => a - b).map(([semester, semBaskets]) => (
            <div key={semester}>
              <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-2">
                Semester {semester}
              </h3>
              <div className="space-y-3">
                {semBaskets.map((basket) => (
                  <BasketCard
                    key={basket.id}
                    program={program}
                    basket={basket}
                    courses={courses}
                    isEditable={isEditable}
                    onDeleteBasket={() => deleteBasket.mutate(basket.id)}
                    invalidateBaskets={invalidateBaskets}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Single basket card — rename, delete, credits/count, and course management
// ---------------------------------------------------------------------------

interface BasketCardProps {
  program: Program
  basket: ElectiveBasket
  courses: Course[]
  isEditable: boolean
  onDeleteBasket: () => void
  invalidateBaskets: () => void
}

function BasketCard({
  program, basket, courses, isEditable, onDeleteBasket, invalidateBaskets,
}: BasketCardProps) {
  const updateBasket = useUpdateBasket(program.id)
  const removeCourse = useRemoveCourseFromBasket(program.id)
  const addCourse = useAddCourse(program.id)
  const updateCourse = useUpdateCourse(program.id)

  const [renaming, setRenaming] = useState(false)
  const [nameDraft, setNameDraft] = useState(basket.name)

  const [assigning, setAssigning] = useState('')
  const [showNew, setShowNew] = useState(false)
  const [nc, setNc] = useState({ code: '', title: '', credits: '3' })
  const [error, setError] = useState<string | null>(null)

  const repCredits = representativeCredits(basket)

  // Existing same-semester courses not already grouped into a basket.
  const assignable = courses.filter(
    (c) => c.semester === basket.semester && !c.elective_basket_id && !c.id.startsWith('optimistic-'),
  )

  async function handleRename() {
    const name = nameDraft.trim()
    if (!name || name === basket.name) { setRenaming(false); return }
    try {
      await updateBasket.mutateAsync({ basketId: basket.id, payload: { name } })
      setRenaming(false)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not rename the basket.')
    }
  }

  async function handleAssignExisting(courseId: string) {
    setError(null)
    setAssigning('')
    try {
      await updateCourse.mutateAsync({ courseId, payload: { elective_basket_id: basket.id, is_elective: true } })
      invalidateBaskets()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not add the course.')
    }
  }

  async function handleCreateNew() {
    if (!nc.code.trim() || !nc.title.trim()) return
    setError(null)
    try {
      await addCourse.mutateAsync({
        code: nc.code.trim(),
        title: nc.title.trim(),
        credits: Number(nc.credits) || 3,
        semester: basket.semester,
        is_elective: true,
        elective_basket_id: basket.id,
      })
      invalidateBaskets()
      setNc({ code: '', title: '', credits: '3' })
      setShowNew(false)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not create the course.')
    }
  }

  async function handleRemove(courseId: string) {
    setError(null)
    try {
      await removeCourse.mutateAsync(courseId)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not remove the course.')
    }
  }

  return (
    <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between gap-4 px-4 py-3 bg-gray-50 border-b border-gray-100">
        <div className="min-w-0 flex-1">
          {renaming ? (
            <div className="flex items-center gap-2">
              <Input
                autoFocus
                value={nameDraft}
                onChange={(e) => setNameDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleRename()
                  if (e.key === 'Escape') { setRenaming(false); setNameDraft(basket.name) }
                }}
                className="h-8"
              />
              <button type="button" onClick={handleRename} className="text-emerald-600 hover:text-emerald-700" title="Save">
                <Check className="h-4 w-4" />
              </button>
              <button
                type="button"
                onClick={() => { setRenaming(false); setNameDraft(basket.name) }}
                className="text-gray-400 hover:text-gray-600"
                title="Cancel"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-2 min-w-0">
              <p className="text-sm font-semibold text-gray-900 truncate">{basket.name}</p>
              {isEditable && (
                <button
                  type="button"
                  onClick={() => { setNameDraft(basket.name); setRenaming(true) }}
                  className="text-gray-400 hover:text-gray-700 shrink-0"
                  title="Rename basket"
                >
                  <Pencil className="h-3.5 w-3.5" />
                </button>
              )}
            </div>
          )}
          <div className="flex items-center gap-2 mt-1 flex-wrap">
            <span className="inline-flex items-center gap-1 text-[11px] font-medium text-indigo-700 bg-indigo-50 border border-indigo-100 rounded px-1.5 py-0.5">
              <Layers className="h-3 w-3" />
              {basket.courses.length} elective{basket.courses.length === 1 ? '' : 's'}
            </span>
            <span className="text-[11px] font-medium text-emerald-700 bg-emerald-50 border border-emerald-100 rounded px-1.5 py-0.5">
              {repCredits} cr counted
            </span>
          </div>
        </div>
        {isEditable && !renaming && (
          <button
            type="button"
            onClick={onDeleteBasket}
            className="text-gray-400 hover:text-red-500 transition-colors shrink-0"
            title="Delete basket (member courses become unlinked, not deleted)"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        )}
      </div>

      {/* Courses */}
      {basket.courses.length === 0 ? (
        <p className="text-xs text-gray-500 px-4 py-3">No courses in this basket yet.</p>
      ) : (
        <div className="divide-y divide-gray-100">
          {basket.courses.map((c) => (
            <div key={c.id} className="flex items-center justify-between gap-4 px-4 py-2.5">
              <div className="min-w-0">
                <span className="text-sm font-medium text-gray-900">{c.title}</span>
                <span className="text-xs text-gray-500 ml-2">{c.code} · {c.credits} cr</span>
              </div>
              {isEditable && (
                <button
                  type="button"
                  onClick={() => handleRemove(c.id)}
                  className="text-xs text-gray-500 hover:text-red-600 transition-colors shrink-0"
                >
                  Remove
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Add-course controls */}
      {isEditable && (
        <div className="border-t border-gray-100 px-4 py-3 space-y-3 bg-gray-50/60">
          <div className="flex flex-col sm:flex-row gap-2">
            <div className="flex-1">
              <Select
                value={assigning}
                onValueChange={handleAssignExisting}
                disabled={assignable.length === 0}
              >
                <SelectTrigger className="h-9">
                  <SelectValue placeholder={
                    assignable.length === 0
                      ? 'No unassigned Sem-' + basket.semester + ' courses'
                      : 'Add existing course…'
                  } />
                </SelectTrigger>
                <SelectContent>
                  {assignable.map((c) => (
                    <SelectItem key={c.id} value={c.id}>
                      {c.title} ({c.code} · {c.credits} cr)
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <Button
              size="sm"
              variant="outline"
              className="shrink-0"
              onClick={() => { setShowNew((v) => !v); setError(null) }}
            >
              <Plus className="h-4 w-4 mr-1" />
              Create New Elective
            </Button>
          </div>

          {showNew && (
            <div className="rounded-lg border border-gray-200 bg-white p-3 space-y-2">
              <div className="grid grid-cols-1 sm:grid-cols-[7rem_1fr_5rem] gap-2">
                <Input
                  value={nc.code}
                  onChange={(e) => setNc((p) => ({ ...p, code: e.target.value }))}
                  placeholder="Code"
                />
                <Input
                  value={nc.title}
                  onChange={(e) => setNc((p) => ({ ...p, title: e.target.value }))}
                  placeholder="Course title"
                />
                <Input
                  type="number"
                  min={1}
                  max={6}
                  value={nc.credits}
                  onChange={(e) => setNc((p) => ({ ...p, credits: e.target.value }))}
                  placeholder="Cr"
                />
              </div>
              <div className="flex items-center gap-2">
                <Button
                  size="sm"
                  disabled={!nc.code.trim() || !nc.title.trim() || addCourse.isPending}
                  onClick={handleCreateNew}
                >
                  {addCourse.isPending ? 'Adding…' : 'Add to Basket'}
                </Button>
                <Button size="sm" variant="outline" onClick={() => { setShowNew(false); setNc({ code: '', title: '', credits: '3' }) }}>
                  Cancel
                </Button>
                <span className="text-xs text-gray-500">Semester {basket.semester}</span>
              </div>
            </div>
          )}

          {error && <p className="text-xs text-red-600">{error}</p>}
        </div>
      )}
    </div>
  )
}
