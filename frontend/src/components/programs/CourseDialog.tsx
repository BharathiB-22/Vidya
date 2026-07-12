import { useState, useEffect } from 'react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import {
  Select, SelectTrigger, SelectValue, SelectContent, SelectItem,
} from '@/components/ui/select'
import { useElectiveBaskets, useCreateBasket } from '@/hooks/programs'
import type { Course, CourseCreate, CourseType, CourseUpdate } from '@/types/program'

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  mode: 'add' | 'edit'
  initial?: Course | null
  semester: number
  programId: string
  onAdd?: (payload: CourseCreate) => void
  onEdit?: (courseId: string, payload: CourseUpdate) => void
  isPending?: boolean
}

const NEW_BASKET_VALUE = '__new_basket__'

/**
 * The course's type is NOT a label. It decides which official document the Board of
 * Studies produces for this course — a syllabus, a lab manual, a set of internship
 * guidelines, a project handbook — so the hint says what each one yields. Picking
 * the wrong one here does not mis-tag the course; it generates the wrong document
 * for it.
 */
const COURSE_TYPES: { value: CourseType; label: string; hint: string }[] = [
  { value: 'THEORY',        label: 'Theory',        hint: 'Full syllabus — Unit I–V, objectives, outcomes, books' },
  { value: 'LAB',           label: 'Laboratory',    hint: 'Lab manual and experiment list — no theory units' },
  { value: 'INTERNSHIP',    label: 'Internship',    hint: 'Guidelines, rubric, weekly activities, viva — no syllabus' },
  { value: 'MINI_PROJECT',  label: 'Mini Project',  hint: 'Milestones, deliverables, reviews, rubrics — no syllabus' },
  { value: 'MAJOR_PROJECT', label: 'Major Project', hint: 'Handbook: proposal, timeline, demo, viva — no syllabus' },
  { value: 'SEMINAR',       label: 'Seminar',       hint: 'Seminar guidelines — no syllabus' },
]

/** The types that carry no syllabus, and therefore no L-T-P worth speaking of. */
const PROJECT_LIKE: CourseType[] = [
  'INTERNSHIP',
  'MINI_PROJECT',
  'MAJOR_PROJECT',
]

const EMPTY = {
  code: '',
  title: '',
  credits: 3,
  course_type: '' as CourseType | '',
  is_elective: false,
  elective_basket_id: '',
  new_basket_name: '',
  hours_lecture: '',
  hours_tutorial: '',
  hours_practical: '',
  description: '',
}

/** Must mirror `compliance._check_course_credit_range` on the backend.
 *
 *  Projects and internships span 2–20: a Semester 3 mini-project is routinely
 *  worth 2 credits, while a final-year dissertation runs to 20. Everything else
 *  stays in the ordinary 1–6 band. */
function creditBounds(courseType: CourseType | ''): { min: number; max: number; hint: string } {
  if (courseType && PROJECT_LIKE.includes(courseType)) {
    return { min: 2, max: 20, hint: '2–20 (project/internship)' }
  }
  return { min: 1, max: 6, hint: '1–6' }
}

export function CourseDialog({
  open,
  onOpenChange,
  mode,
  initial,
  semester,
  programId,
  onAdd,
  onEdit,
  isPending,
}: Props) {
  const [f, setF] = useState(EMPTY)
  const [creatingNewBasket, setCreatingNewBasket] = useState(false)
  const [basketError, setBasketError] = useState<string | null>(null)

  const basketsQ = useElectiveBaskets(programId)
  const createBasket = useCreateBasket(programId)
  const basketsForSemester = (basketsQ.data ?? []).filter((b) => b.semester === semester)

  useEffect(() => {
    if (!open) return
    setCreatingNewBasket(false)
    setBasketError(null)
    if (mode === 'edit' && initial) {
      setF({
        code: initial.code,
        title: initial.title,
        credits: initial.credits,
        course_type: (initial.course_type ?? '') as CourseType | '',
        is_elective: initial.is_elective,
        elective_basket_id: initial.elective_basket_id ?? '',
        new_basket_name: '',
        hours_lecture: initial.hours_lecture?.toString() ?? '',
        hours_tutorial: initial.hours_tutorial?.toString() ?? '',
        hours_practical: initial.hours_practical?.toString() ?? '',
        description: initial.description ?? '',
      })
    } else {
      setF(EMPTY)
    }
  }, [open, mode, initial])

  const bounds = creditBounds(f.course_type)
  const selectedType = COURSE_TYPES.find((ct) => ct.value === f.course_type)

  async function resolveBasketId(): Promise<string | undefined> {
    if (!f.is_elective) return undefined
    if (creatingNewBasket) {
      if (!f.new_basket_name.trim()) return undefined
      const basket = await createBasket.mutateAsync({ semester, name: f.new_basket_name.trim() })
      return basket.id
    }
    return f.elective_basket_id || undefined
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setBasketError(null)
    let elective_basket_id: string | undefined
    try {
      elective_basket_id = await resolveBasketId()
    } catch (err) {
      setBasketError(err instanceof Error ? err.message : 'Could not create the basket.')
      return
    }
    const hours_lecture = f.hours_lecture ? Number(f.hours_lecture) : undefined
    const hours_tutorial = f.hours_tutorial ? Number(f.hours_tutorial) : undefined
    const hours_practical = f.hours_practical ? Number(f.hours_practical) : undefined
    const description = f.description || undefined
    const course_type = f.course_type || undefined

    if (mode === 'add') {
      onAdd?.({
        code: f.code,
        title: f.title,
        credits: Number(f.credits),
        semester,
        course_type,
        is_elective: f.is_elective,
        elective_basket_id,
        hours_lecture,
        hours_tutorial,
        hours_practical,
        description,
      })
    } else if (mode === 'edit' && initial) {
      onEdit?.(initial.id, {
        code: f.code || undefined,
        title: f.title,
        credits: Number(f.credits),
        semester: initial.semester,
        course_type,
        is_elective: f.is_elective,
        elective_basket_id,
        hours_lecture,
        hours_tutorial,
        hours_practical,
        description,
      })
    }
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>
            {mode === 'add' ? `Add Course — Semester ${semester}` : 'Edit Course'}
          </DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Course Code</label>
            <Input
              required
              value={f.code}
              onChange={(e) => setF((p) => ({ ...p, code: e.target.value }))}
              placeholder="CS101"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Title</label>
            <Input
              required
              value={f.title}
              onChange={(e) => setF((p) => ({ ...p, title: e.target.value }))}
              placeholder="Introduction to Programming"
            />
          </div>

          {/* Course Type */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Course Type
            </label>
            <select
              className="w-full rounded-md border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-400 bg-white"
              value={f.course_type}
              onChange={(e) => {
                const ct = e.target.value as CourseType | ''
                setF((p) => {
                  const newBounds = creditBounds(ct)
                  // Clamp existing credits into new range
                  const credits = Math.min(Math.max(p.credits, newBounds.min), newBounds.max)
                  return { ...p, course_type: ct, credits }
                })
              }}
            >
              <option value="">— Not specified —</option>
              {COURSE_TYPES.map((ct) => (
                <option key={ct.value} value={ct.value}>{ct.label}</option>
              ))}
            </select>
            {/*
              The type decides WHICH DOCUMENT the Board generates for this course —
              not merely how it is tagged. An internship marked THEORY gets five
              units of lectures for a student who is not on campus to attend them,
              and that is a document the Board must throw away. So the consequence
              is stated at the point the choice is made.
            */}
            <p className="mt-1 text-xs text-gray-500">
              {selectedType
                ? selectedType.hint
                : 'Decides what the Board generates: a syllabus, a lab manual, or guidelines. ' +
                  'Leave unset and this course is treated as Theory.'}
            </p>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Credits
                <span className="ml-1 text-xs font-normal text-gray-400">({bounds.hint})</span>
              </label>
              <Input
                type="number"
                min={bounds.min}
                max={bounds.max}
                required
                value={f.credits}
                onChange={(e) => setF((p) => ({ ...p, credits: Number(e.target.value) }))}
              />
            </div>
            <div className="flex items-end pb-1">
              <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
                <input
                  type="checkbox"
                  checked={f.is_elective}
                  onChange={(e) => setF((p) => ({ ...p, is_elective: e.target.checked }))}
                  className="rounded"
                />
                Elective
              </label>
            </div>
          </div>

          {f.is_elective && (
            <div className="rounded-md border border-gray-200 p-3 space-y-2 bg-gray-50">
              <label className="block text-sm font-medium text-gray-700">
                Elective Basket
                <span className="text-gray-500 font-normal ml-1">
                  (a group students pick ONE course from — never a standalone elective)
                </span>
              </label>
              {creatingNewBasket ? (
                <div className="flex gap-2">
                  <Input
                    autoFocus
                    value={f.new_basket_name}
                    onChange={(e) => setF((p) => ({ ...p, new_basket_name: e.target.value }))}
                    placeholder="e.g. Artificial Intelligence Electives"
                  />
                  <Button type="button" variant="outline" size="sm" onClick={() => setCreatingNewBasket(false)}>
                    Cancel
                  </Button>
                </div>
              ) : (
                <Select
                  value={f.elective_basket_id}
                  onValueChange={(v) => {
                    if (v === NEW_BASKET_VALUE) { setCreatingNewBasket(true); return }
                    setF((p) => ({ ...p, elective_basket_id: v }))
                  }}
                >
                  <SelectTrigger><SelectValue placeholder="Select a basket" /></SelectTrigger>
                  <SelectContent>
                    {basketsForSemester.map((b) => (
                      <SelectItem key={b.id} value={b.id}>{b.name}</SelectItem>
                    ))}
                    <SelectItem value={NEW_BASKET_VALUE}>+ Create new basket…</SelectItem>
                  </SelectContent>
                </Select>
              )}
              {basketError && <p className="text-xs text-red-600">{basketError}</p>}
            </div>
          )}

          <div className="grid grid-cols-3 gap-2">
            {(
              ['hours_lecture', 'hours_tutorial', 'hours_practical'] as Array<
                'hours_lecture' | 'hours_tutorial' | 'hours_practical'
              >
            ).map((field) => (
              <div key={field}>
                <label className="block text-xs font-medium text-gray-600 mb-1 capitalize">
                  {field.replace('hours_', '')}
                </label>
                <Input
                  type="number"
                  min={0}
                  value={f[field]}
                  onChange={(e) => setF((p) => ({ ...p, [field]: e.target.value }))}
                  placeholder="0"
                />
              </div>
            ))}
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
            <Textarea
              rows={2}
              value={f.description}
              onChange={(e) => setF((p) => ({ ...p, description: e.target.value }))}
              placeholder="Optional"
            />
          </div>
          <DialogFooter className="pt-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={isPending}>
              {isPending ? 'Saving…' : 'Save'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
