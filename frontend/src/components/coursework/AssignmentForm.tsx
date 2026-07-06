import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { useAssignment, useCreateAssignment, useUpdateAssignment } from '@/hooks/coursework'
import { addToast } from '@/hooks/useToast'
import { getErrorMessage } from '@/lib/api'
import type { CourseworkAssignment, CourseworkType } from '@/types/coursework'

const TYPE_OPTIONS: Array<{ value: CourseworkType; label: string }> = [
  { value: 'ESSAY', label: 'Essay' },
  { value: 'CASE_STUDY', label: 'Case Study' },
  { value: 'REPORT', label: 'Report' },
  { value: 'HOMEWORK', label: 'Homework' },
  { value: 'OTHER', label: 'Other' },
]

const FILE_TYPE_OPTIONS = ['pdf', 'doc', 'docx', 'ppt', 'pptx', 'zip', 'txt']

function toLocalInputValue(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

export interface AssignmentFormProps {
  /** Omit to create a new assignment; pass an id to edit an existing one. */
  assignmentId?: string
  /** Only used when creating. */
  syllabusId?: string
  onCreated?: (assignment: CourseworkAssignment) => void
  onUpdated?: (assignment: CourseworkAssignment) => void
}

export function AssignmentForm({ assignmentId, syllabusId, onCreated, onUpdated }: AssignmentFormProps) {
  const isEdit = Boolean(assignmentId)

  const { data: existing } = useAssignment(assignmentId ?? '')
  const create = useCreateAssignment()
  const update = useUpdateAssignment(assignmentId ?? '')

  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [instructions, setInstructions] = useState('')
  const [assignmentType, setAssignmentType] = useState<CourseworkType>('ESSAY')
  const [maxMarks, setMaxMarks] = useState(100)
  const [weightagePercent, setWeightagePercent] = useState<string>('')
  const [dueDate, setDueDate] = useState('')
  const [allowLate, setAllowLate] = useState(true)
  const [latePenaltyPercent, setLatePenaltyPercent] = useState<string>('')
  const [maxAttempts, setMaxAttempts] = useState(1)
  const [allowedFileTypes, setAllowedFileTypes] = useState<string[]>(['pdf', 'docx'])

  useEffect(() => {
    if (existing) {
      setTitle(existing.title)
      setDescription(existing.description ?? '')
      setInstructions(existing.instructions ?? '')
      setAssignmentType(existing.assignment_type)
      setMaxMarks(existing.max_marks)
      setWeightagePercent(existing.weightage_percent != null ? String(existing.weightage_percent) : '')
      setDueDate(toLocalInputValue(existing.due_date))
      setAllowLate(existing.allow_late)
      setLatePenaltyPercent(existing.late_penalty_percent != null ? String(existing.late_penalty_percent) : '')
      setMaxAttempts(existing.max_attempts)
      setAllowedFileTypes(existing.allowed_file_types ?? ['pdf', 'docx'])
    }
  }, [existing])

  function toggleFileType(ext: string) {
    setAllowedFileTypes((prev) => (prev.includes(ext) ? prev.filter((e) => e !== ext) : [...prev, ext]))
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const payload = {
      title,
      description: description || undefined,
      instructions: instructions || undefined,
      assignment_type: assignmentType,
      max_marks: maxMarks,
      weightage_percent: weightagePercent ? Number(weightagePercent) : undefined,
      due_date: dueDate ? new Date(dueDate).toISOString() : undefined,
      allow_late: allowLate,
      late_penalty_percent: latePenaltyPercent ? Number(latePenaltyPercent) : undefined,
      max_attempts: maxAttempts,
      allowed_file_types: allowedFileTypes,
    }

    try {
      if (isEdit) {
        const updated = await update.mutateAsync(payload)
        addToast('Assignment updated.', 'success')
        onUpdated?.(updated)
      } else {
        const created = await create.mutateAsync({ ...payload, due_date: payload.due_date!, syllabus_id: syllabusId })
        addToast('Assignment created as draft.', 'success')
        onCreated?.(created)
      }
    } catch (err) {
      addToast(getErrorMessage(err), 'error')
    }
  }

  const saving = create.isPending || update.isPending

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">{isEdit ? 'Edit Assignment' : 'New Assignment'}</h1>
        {isEdit && existing?.status !== 'DRAFT' && (
          <p className="text-sm text-orange-600 mt-1">Only draft assignments can be edited.</p>
        )}
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="text-sm font-medium text-gray-700">Title</label>
          <input
            className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-400"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
          />
        </div>

        <div>
          <label className="text-sm font-medium text-gray-700">Description</label>
          <textarea
            className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-400"
            rows={4}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </div>

        <div>
          <label className="text-sm font-medium text-gray-700">Submission Instructions</label>
          <textarea
            className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-400"
            rows={3}
            value={instructions}
            onChange={(e) => setInstructions(e.target.value)}
          />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="text-sm font-medium text-gray-700">Type</label>
            <select
              className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-400"
              value={assignmentType}
              onChange={(e) => setAssignmentType(e.target.value as CourseworkType)}
            >
              {TYPE_OPTIONS.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
            </select>
          </div>
          <div>
            <label className="text-sm font-medium text-gray-700">Max Marks</label>
            <input
              type="number"
              min={1}
              className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-400"
              value={maxMarks}
              onChange={(e) => setMaxMarks(Number(e.target.value))}
              required
            />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="text-sm font-medium text-gray-700">Weightage % (Internal Assessment)</label>
            <input
              type="number"
              min={0}
              max={100}
              className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-400"
              value={weightagePercent}
              onChange={(e) => setWeightagePercent(e.target.value)}
              placeholder="Optional"
            />
          </div>
          <div>
            <label className="text-sm font-medium text-gray-700">Due Date</label>
            <input
              type="datetime-local"
              className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-400"
              value={dueDate}
              onChange={(e) => setDueDate(e.target.value)}
              required
            />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4 items-end">
          <div className="flex items-center gap-2">
            <input
              id="allow-late"
              type="checkbox"
              checked={allowLate}
              onChange={(e) => setAllowLate(e.target.checked)}
            />
            <label htmlFor="allow-late" className="text-sm font-medium text-gray-700">Allow late submissions</label>
          </div>
          {allowLate && (
            <div>
              <label className="text-sm font-medium text-gray-700">Late Penalty %</label>
              <input
                type="number"
                min={0}
                max={100}
                className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-400"
                value={latePenaltyPercent}
                onChange={(e) => setLatePenaltyPercent(e.target.value)}
                placeholder="Optional"
              />
            </div>
          )}
        </div>

        <div>
          <label className="text-sm font-medium text-gray-700">Maximum Attempts</label>
          <input
            type="number"
            min={1}
            className="mt-1 w-32 rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-400"
            value={maxAttempts}
            onChange={(e) => setMaxAttempts(Number(e.target.value))}
          />
        </div>

        <div>
          <label className="text-sm font-medium text-gray-700">Allowed File Types</label>
          <div className="mt-2 flex gap-2 flex-wrap">
            {FILE_TYPE_OPTIONS.map((ext) => (
              <button
                key={ext}
                type="button"
                onClick={() => toggleFileType(ext)}
                className={`text-xs px-3 py-1.5 rounded-lg font-medium border transition-colors ${
                  allowedFileTypes.includes(ext)
                    ? 'bg-gray-900 text-white border-gray-900'
                    : 'bg-white text-gray-600 border-gray-200 hover:bg-gray-50'
                }`}
              >
                .{ext}
              </button>
            ))}
          </div>
        </div>

        <div className="flex justify-end pt-2">
          <Button type="submit" disabled={saving}>
            {saving ? 'Saving…' : isEdit ? 'Save Changes' : 'Create Draft'}
          </Button>
        </div>
      </form>
    </div>
  )
}
