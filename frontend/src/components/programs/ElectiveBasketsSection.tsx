import { useState } from 'react'
import { Trash2, ListTree, Plus, Pencil, Check, X, Lock, Layers } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select, SelectTrigger, SelectValue, SelectContent, SelectItem,
} from '@/components/ui/select'
import {
  useElectiveBaskets,
  useProgramCourses,
  useCreateBasket,
  useUpdateBasket,
  useDeleteBasket,
  useAddElectiveChoice,
  useRemoveElectiveChoice,
  usePublishElectiveSlot,
  useOpenElectiveRegistration,
  useCloseElectiveRegistration,
} from '@/hooks/programs'
import type { Course, ElectiveBasket, ElectiveSlotStatus, Program } from '@/types/program'

interface Props {
  program: Program
}

/** Human explanation of each paper state, shown next to the lifecycle buttons. */
const STATUS_HINT: Record<ElectiveSlotStatus, string> = {
  DRAFT:     'Choices can be added and removed. Nobody else can see this paper — it counts for no dashboard, ownership or faculty assignment yet.',
  PUBLISHED: 'Choices are locked. The paper is now a curriculum subject; students can see it but cannot choose yet.',
  OPEN:      'Students are choosing. They may switch until you close registration.',
  CLOSED:    'The roster is final. Faculty are teaching and marking these students.',
}

const STATUS_STYLE: Record<ElectiveSlotStatus, string> = {
  DRAFT:     'text-gray-600 bg-gray-50 border-gray-200',
  PUBLISHED: 'text-indigo-700 bg-indigo-50 border-indigo-100',
  OPEN:      'text-emerald-700 bg-emerald-50 border-emerald-100',
  CLOSED:    'text-amber-700 bg-amber-50 border-amber-100',
}

/** Dean management of every elective paper in this program.
 *
 *  A semester holds SEVERAL independent elective papers. Elective 1, Elective 2
 *  and Elective 3 are three curriculum courses, not one: the student takes all
 *  three and chooses exactly one subject inside each, so at 3 credits apiece
 *  they contribute 9 credits to the semester. Each paper is rendered as its own
 *  card with its own choices, lifecycle and validation.
 *
 *  Two lifecycles meet here and they are deliberately separate.
 *
 *  A paper's *definition* (name, credits, semester) is curriculum: it feeds
 *  compliance and the program credit total, so it freezes when the program
 *  leaves Draft/Pending Approval.
 *
 *  A paper's *contents* — which subjects it offers — follow the paper's own
 *  status (Draft → Published → Open → Closed). That is what lets a Dean fill in
 *  what Elective 1 offers this year on a curriculum published long ago. A draft
 *  paper's subjects exist as courses but count for nothing: not the ownership
 *  dashboard, not vacancies, not faculty assignment.
 *
 *  Course codes are generated (MCA306, MCA307, ...). The Dean never types one.
 *  Faculty are assigned per running term in Academic Ownership, where elective
 *  choices appear as the ordinary subjects they are. */
export function ElectiveBasketsSection({ program }: Props) {
  const isProgramEditable = program.status === 'DRAFT' || program.status === 'PENDING_APPROVAL'

  const { data: baskets = [], isLoading } = useElectiveBaskets(program.id)
  const { data: courses = [] } = useProgramCourses(program.id)

  const createBasket = useCreateBasket(program.id)
  const deleteBasket = useDeleteBasket(program.id)

  const maxSem = Math.max(program.duration_years * 2, ...baskets.map((b) => b.semester), 1)
  const semesterOptions = Array.from({ length: maxSem }, (_, i) => i + 1)

  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState('')
  const [newSemester, setNewSemester] = useState('1')
  const [newCredits, setNewCredits] = useState('3')
  const [createError, setCreateError] = useState<string | null>(null)

  async function handleCreate() {
    if (!newName.trim()) return
    setCreateError(null)
    try {
      await createBasket.mutateAsync({
        semester: Number(newSemester),
        name: newName.trim(),
        credits: Number(newCredits) || 3,
      })
      setNewName('')
      setNewCredits('3')
      setCreating(false)
    } catch (e) {
      setCreateError(e instanceof Error ? e.message : 'Could not create the paper.')
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
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <p className="text-sm text-gray-600">
            Each elective paper is ONE curriculum course worth its own credits, and a semester
            may hold several. A student takes every paper, choosing exactly one subject inside
            each — so Elective 1, 2 and 3 at 3 credits contribute 9 credits to the semester,
            and each paper counts once no matter how many choices it offers. Subject codes are
            generated for you.
          </p>
        </div>
        {isProgramEditable ? (
          <Button size="sm" onClick={() => { setCreating((v) => !v); setCreateError(null) }}>
            <Plus className="h-4 w-4 mr-1" />
            New Elective Paper
          </Button>
        ) : (
          <div className="flex items-center gap-1.5 text-xs text-gray-500 rounded-md border border-gray-200 bg-gray-50 px-2.5 py-1.5">
            <Lock className="h-3.5 w-3.5" />
            Curriculum locked — papers cannot be added or renamed. Choices still can.
          </div>
        )}
      </div>

      {creating && isProgramEditable && (
        <div className="rounded-xl border border-gray-200 bg-white p-4 space-y-3">
          <h3 className="text-sm font-semibold text-gray-900">Create Elective Paper</h3>
          <div className="grid grid-cols-1 sm:grid-cols-[8rem_1fr_6rem] gap-3">
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
              placeholder="e.g. Elective 1"
            />
            <Input
              type="number"
              min={1}
              max={6}
              value={newCredits}
              onChange={(e) => setNewCredits(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') handleCreate() }}
              placeholder="Credits"
              aria-label="Paper credits"
            />
          </div>
          {createError && <p className="text-xs text-red-600">{createError}</p>}
          <div className="flex items-center gap-2">
            <Button size="sm" disabled={!newName.trim() || createBasket.isPending} onClick={handleCreate}>
              {createBasket.isPending ? 'Creating…' : 'Create Paper'}
            </Button>
            <Button size="sm" variant="outline" onClick={() => { setCreating(false); setNewName('') }}>
              Cancel
            </Button>
          </div>
        </div>
      )}

      {baskets.length === 0 ? (
        <div className="text-center py-12 rounded-xl border border-dashed border-gray-200">
          <ListTree className="h-8 w-8 mx-auto mb-2 text-gray-500" />
          <p className="text-sm text-gray-500">
            No elective papers yet.{isProgramEditable ? ' Use “New Elective Paper” to create one.' : ''}
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
                    isProgramEditable={isProgramEditable}
                    onDeleteBasket={() => deleteBasket.mutate(basket.id)}
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
// One slot — rename/delete (curriculum), choices + lifecycle (slot's own)
// ---------------------------------------------------------------------------

interface BasketCardProps {
  program: Program
  basket: ElectiveBasket
  courses: Course[]
  isProgramEditable: boolean
  onDeleteBasket: () => void
}

function BasketCard({
  program, basket, courses, isProgramEditable, onDeleteBasket,
}: BasketCardProps) {
  const updateBasket = useUpdateBasket(program.id)
  const addChoice = useAddElectiveChoice(program.id)
  const removeChoice = useRemoveElectiveChoice(program.id)
  const publishSlot = usePublishElectiveSlot(program.id)
  const openReg = useOpenElectiveRegistration(program.id)
  const closeReg = useCloseElectiveRegistration(program.id)

  const [renaming, setRenaming] = useState(false)
  const [nameDraft, setNameDraft] = useState(basket.name)
  const [creditsDraft, setCreditsDraft] = useState(String(basket.credits))

  const [showNew, setShowNew] = useState(false)
  const [nc, setNc] = useState({
    title: '',
    credits: String(basket.credits),
    course_type: 'THEORY' as 'THEORY' | 'LAB',
  })
  const [error, setError] = useState<string | null>(null)

  // Choices live in the program's course list, linked back to this slot.
  const choices = courses
    .filter((c) => c.elective_basket_id === basket.id)
    .sort((a, b) => a.code.localeCompare(b.code))

  // Choices are editable while the SLOT is a draft — not while the program is.
  const canEditChoices = basket.status === 'DRAFT'

  function cancelEdit() {
    setRenaming(false)
    setNameDraft(basket.name)
    setCreditsDraft(String(basket.credits))
  }

  async function handleRename() {
    const name = nameDraft.trim()
    const credits = Number(creditsDraft)
    if (!name || !Number.isFinite(credits) || credits < 1) { cancelEdit(); return }
    if (name === basket.name && credits === basket.credits) { setRenaming(false); return }
    setError(null)
    try {
      await updateBasket.mutateAsync({ basketId: basket.id, payload: { name, credits } })
      setRenaming(false)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not update the paper.')
    }
  }

  async function handleAddChoice() {
    if (!nc.title.trim()) return
    setError(null)
    try {
      await addChoice.mutateAsync({
        basketId: basket.id,
        payload: {
          title: nc.title.trim(),
          credits: Number(nc.credits) || basket.credits,
          course_type: nc.course_type,
        },
      })
      setNc({ title: '', credits: String(basket.credits), course_type: 'THEORY' })
      setShowNew(false)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not add the choice.')
    }
  }

  async function handleRemoveChoice(courseId: string) {
    setError(null)
    try {
      await removeChoice.mutateAsync({ basketId: basket.id, courseId })
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not remove the choice.')
    }
  }

  async function runTransition(fn: () => Promise<unknown>, fallback: string) {
    setError(null)
    try {
      await fn()
    } catch (e) {
      setError(e instanceof Error ? e.message : fallback)
    }
  }

  const transitionPending = publishSlot.isPending || openReg.isPending || closeReg.isPending

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
                  if (e.key === 'Escape') cancelEdit()
                }}
                className="h-8"
              />
              <Input
                type="number"
                min={1}
                max={6}
                value={creditsDraft}
                onChange={(e) => setCreditsDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleRename()
                  if (e.key === 'Escape') cancelEdit()
                }}
                className="h-8 w-20"
                aria-label="Paper credits"
              />
              <button type="button" onClick={handleRename} className="text-emerald-600 hover:text-emerald-700" title="Save">
                <Check className="h-4 w-4" />
              </button>
              <button type="button" onClick={cancelEdit} className="text-gray-600 hover:text-gray-600" title="Cancel">
                <X className="h-4 w-4" />
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-2 min-w-0">
              <p className="text-sm font-semibold text-gray-900 truncate">
                {basket.name} <span className="font-normal text-gray-500">({basket.credits} credits)</span>
              </p>
              {isProgramEditable && (
                <button
                  type="button"
                  onClick={() => { setNameDraft(basket.name); setCreditsDraft(String(basket.credits)); setRenaming(true) }}
                  className="text-gray-600 hover:text-gray-700 shrink-0"
                  title="Rename paper / change credits"
                >
                  <Pencil className="h-3.5 w-3.5" />
                </button>
              )}
            </div>
          )}
          <div className="flex items-center gap-2 mt-1 flex-wrap">
            <span className={`text-[11px] font-semibold rounded px-1.5 py-0.5 border ${STATUS_STYLE[basket.status]}`}>
              {basket.status}
            </span>
            <span className="inline-flex items-center gap-1 text-[11px] font-medium text-indigo-700 bg-indigo-50 border border-indigo-100 rounded px-1.5 py-0.5">
              <Layers className="h-3 w-3" />
              {choices.length} choice{choices.length === 1 ? '' : 's'}
            </span>
            <span className="text-[11px] font-medium text-emerald-700 bg-emerald-50 border border-emerald-100 rounded px-1.5 py-0.5">
              {basket.credits} cr counted once
            </span>
          </div>
          <p className="text-[11px] text-gray-500 mt-1">{STATUS_HINT[basket.status]}</p>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {basket.status === 'DRAFT' && (
            <Button
              size="sm"
              disabled={choices.length === 0 || transitionPending}
              title={choices.length === 0 ? 'Add at least one choice before publishing' : undefined}
              onClick={() => runTransition(() => publishSlot.mutateAsync(basket.id), 'Could not publish the paper.')}
            >
              {publishSlot.isPending ? 'Publishing…' : 'Publish'}
            </Button>
          )}
          {basket.status === 'PUBLISHED' && (
            <Button
              size="sm"
              disabled={transitionPending}
              onClick={() => runTransition(() => openReg.mutateAsync(basket.id), 'Could not open registration.')}
            >
              {openReg.isPending ? 'Opening…' : 'Open Registration'}
            </Button>
          )}
          {basket.status === 'OPEN' && (
            <Button
              size="sm"
              variant="outline"
              disabled={transitionPending}
              onClick={() => runTransition(() => closeReg.mutateAsync(basket.id), 'Could not close registration.')}
            >
              {closeReg.isPending ? 'Closing…' : 'Close Registration'}
            </Button>
          )}
          {isProgramEditable && basket.status === 'DRAFT' && (
            <button
              type="button"
              onClick={onDeleteBasket}
              className="text-gray-600 hover:text-red-600"
              title="Delete paper"
            >
              <Trash2 className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>

      {/* Choices */}
      <div className="p-4 space-y-3">
        {error && <p className="text-xs text-red-600">{error}</p>}

        {choices.length === 0 ? (
          <p className="text-sm text-gray-500">
            No choices yet. This paper must offer at least one subject before it can be published.
          </p>
        ) : (
          <>
            <p className="text-xs font-medium text-gray-500">
              Student chooses one of the following:
            </p>
            {/* Rendered as an inert radio group: the Dean is defining the choice
                a student will later make, not making it. The circles are what
                communicate "exactly one of these". */}
            <ul className="divide-y divide-gray-100 border border-gray-100 rounded-lg overflow-hidden">
              {choices.map((c) => (
                <li key={c.id} className="flex items-center gap-3 px-3 py-2">
                  <span
                    aria-hidden
                    className="h-3.5 w-3.5 shrink-0 rounded-full border-2 border-gray-300"
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-medium text-gray-900">{c.title}</span>
                      {/* Generated, never typed. */}
                      <span className="text-xs font-mono text-gray-500">{c.code}</span>
                      <span className="text-xs text-gray-500">{c.credits} cr</span>
                      {c.course_type && (
                        <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded border border-gray-200 text-gray-500">
                          {c.course_type}
                        </span>
                      )}
                    </div>
                  </div>
                  {canEditChoices && (
                    <button
                      type="button"
                      onClick={() => handleRemoveChoice(c.id)}
                      disabled={removeChoice.isPending}
                      className="text-gray-600 hover:text-red-600 shrink-0"
                      title="Remove choice"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  )}
                </li>
              ))}
            </ul>
          </>
        )}

        {canEditChoices ? (
          <>
            <Button size="sm" variant="outline" onClick={() => { setShowNew((v) => !v); setError(null) }}>
              <Plus className="h-4 w-4 mr-1" />
              Add Elective Choice
            </Button>

            {showNew && (
              <div className="rounded-lg border border-gray-200 bg-white p-3 space-y-2">
                <div className="grid grid-cols-1 sm:grid-cols-[1fr_7rem_5rem] gap-2">
                  <Input
                    autoFocus
                    value={nc.title}
                    onChange={(e) => setNc((p) => ({ ...p, title: e.target.value }))}
                    onKeyDown={(e) => { if (e.key === 'Enter') handleAddChoice() }}
                    placeholder="e.g. Artificial Intelligence"
                  />
                  <Select
                    value={nc.course_type}
                    onValueChange={(v) => setNc((p) => ({ ...p, course_type: v as 'THEORY' | 'LAB' }))}
                  >
                    <SelectTrigger aria-label="Subject type"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="THEORY">Theory</SelectItem>
                      <SelectItem value="LAB">Lab</SelectItem>
                    </SelectContent>
                  </Select>
                  <Input
                    type="number"
                    min={1}
                    max={6}
                    value={nc.credits}
                    onChange={(e) => setNc((p) => ({ ...p, credits: e.target.value }))}
                    placeholder="Cr"
                    aria-label="Choice credits"
                  />
                </div>
                <p className="text-[11px] text-gray-500">
                  The subject code is generated automatically from the programme and semester.
                </p>
                <div className="flex items-center gap-2">
                  <Button
                    size="sm"
                    disabled={!nc.title.trim() || addChoice.isPending}
                    onClick={handleAddChoice}
                  >
                    {addChoice.isPending ? 'Adding…' : 'Add Choice'}
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => { setShowNew(false); setNc({ title: '', credits: String(basket.credits), course_type: 'THEORY' }) }}
                  >
                    Cancel
                  </Button>
                </div>
              </div>
            )}
          </>
        ) : (
          <div className="flex items-center gap-1.5 text-xs text-gray-500">
            <Lock className="h-3.5 w-3.5" />
            Choices are locked. Assign faculty for each subject in Academic Ownership.
          </div>
        )}
      </div>
    </div>
  )
}
