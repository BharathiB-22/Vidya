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
import type { Course, CourseCreate, CourseType, CourseUpdate } from '@/types/program'

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  mode: 'add' | 'edit'
  initial?: Course | null
  semester: number
  onAdd?: (payload: CourseCreate) => void
  onEdit?: (courseId: string, payload: CourseUpdate) => void
  isPending?: boolean
}

const COURSE_TYPES: { value: CourseType; label: string }[] = [
  { value: 'THEORY',     label: 'Theory' },
  { value: 'LAB',        label: 'Lab' },
  { value: 'PROJECT',    label: 'Project' },
  { value: 'INTERNSHIP', label: 'Internship' },
  { value: 'SEMINAR',    label: 'Seminar' },
]

const EMPTY = {
  code: '',
  title: '',
  credits: 3,
  course_type: '' as CourseType | '',
  is_elective: false,
  hours_lecture: '',
  hours_tutorial: '',
  hours_practical: '',
  description: '',
}

function creditBounds(courseType: CourseType | ''): { min: number; max: number; hint: string } {
  if (courseType === 'PROJECT' || courseType === 'INTERNSHIP') {
    return { min: 6, max: 20, hint: '6–20 (project/internship)' }
  }
  return { min: 1, max: 6, hint: '1–6' }
}

export function CourseDialog({
  open,
  onOpenChange,
  mode,
  initial,
  semester,
  onAdd,
  onEdit,
  isPending,
}: Props) {
  const [f, setF] = useState(EMPTY)

  useEffect(() => {
    if (!open) return
    if (mode === 'edit' && initial) {
      setF({
        code: initial.code,
        title: initial.title,
        credits: initial.credits,
        course_type: (initial.course_type ?? '') as CourseType | '',
        is_elective: initial.is_elective,
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

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
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
              <span className="text-gray-400 font-normal ml-1">(optional)</span>
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
