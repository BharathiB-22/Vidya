import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { useCreateAssignment } from '@/hooks/labs'
import type { AssignmentCreate } from '@/types/labs'

export function CreateLabDialog({
  onClose,
  onCreated,
}: {
  onClose: () => void
  onCreated: (id: string) => void
}) {
  const [title, setTitle]           = useState('')
  const [description, setDescription] = useState('')
  const [instructions, setInstructions] = useState('')
  const [type, setType]             = useState<'WRITTEN' | 'CODE'>('WRITTEN')
  const [lang, setLang]             = useState('python')
  const [deadline, setDeadline]     = useState('')
  const [allowLate, setAllowLate]   = useState(false)
  const [rubricName, setRubricName] = useState('Content Quality')
  const [labGroup, setLabGroup]     = useState('')
  const [programNumber, setProgramNumber] = useState('')
  const { mutateAsync, isPending }  = useCreateAssignment()

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const payload: AssignmentCreate = {
      title,
      description: description.trim() || undefined,
      instructions: instructions.trim() || undefined,
      submission_type: type,
      language: type === 'CODE' ? lang : undefined,
      deadline: deadline || undefined,
      allow_late: allowLate,
      lab_group: labGroup.trim() || undefined,
      program_number: programNumber ? Number(programNumber) : undefined,
      rubric: [{
        criterion_id: 'c1',
        name: rubricName,
        description: 'Evaluates the overall quality of the submission.',
        max_marks: 100,
        weight: 1.0,
      }],
    }
    const assignment = await mutateAsync(payload)
    onCreated(assignment.id)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm p-4">
      <form
        onSubmit={handleSubmit}
        className="bg-white rounded-2xl shadow-xl w-full max-w-lg p-6 space-y-4 max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-semibold text-gray-900">New Assignment</h2>

        <div className="space-y-1">
          <label className="text-sm font-medium text-gray-700">Title <span className="text-red-500">*</span></label>
          <input
            className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-400"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
            placeholder="Assignment title"
          />
        </div>

        <div className="space-y-1">
          <label className="text-sm font-medium text-gray-700">Type</label>
          <select
            className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none"
            value={type}
            onChange={(e) => setType(e.target.value as 'WRITTEN' | 'CODE')}
          >
            <option value="WRITTEN">Written</option>
            <option value="CODE">Code</option>
          </select>
        </div>

        {type === 'CODE' && (
          <div className="space-y-1">
            <label className="text-sm font-medium text-gray-700">Language</label>
            <select
              className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
              value={lang}
              onChange={(e) => setLang(e.target.value)}
            >
              <option value="python">Python</option>
            </select>
          </div>
        )}

        <div className="space-y-1">
          <label className="text-sm font-medium text-gray-700">
            Problem Statement
            <span className="ml-1 text-xs text-gray-600">(required to publish)</span>
          </label>
          <textarea
            className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-400 resize-y"
            rows={3}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Describe the task students must complete…"
          />
        </div>

        <div className="space-y-1">
          <label className="text-sm font-medium text-gray-700">
            Student Instructions
            <span className="ml-1 text-xs text-gray-600">(optional)</span>
          </label>
          <textarea
            className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-400 resize-y"
            rows={2}
            value={instructions}
            onChange={(e) => setInstructions(e.target.value)}
            placeholder="e.g. Write 500 words. Cite sources in APA format."
          />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1">
            <label className="text-sm font-medium text-gray-700">
              Lab Group <span className="text-xs font-normal text-gray-600">(optional)</span>
            </label>
            <input
              className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-400"
              value={labGroup}
              onChange={(e) => setLabGroup(e.target.value)}
              placeholder="e.g. Python Lab"
            />
          </div>
          <div className="space-y-1">
            <label className="text-sm font-medium text-gray-700">
              Program # <span className="text-xs font-normal text-gray-600">(optional)</span>
            </label>
            <input
              type="number"
              min={1}
              className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-400"
              value={programNumber}
              onChange={(e) => setProgramNumber(e.target.value)}
              placeholder="e.g. 1"
            />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1">
            <label className="text-sm font-medium text-gray-700">Due Date</label>
            <input
              type="datetime-local"
              className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-400"
              value={deadline}
              onChange={(e) => setDeadline(e.target.value)}
            />
          </div>
          <div className="space-y-1">
            <label className="text-sm font-medium text-gray-700">Late Submissions</label>
            <label className="flex items-center gap-2 mt-2 cursor-pointer">
              <input
                type="checkbox"
                className="rounded border-gray-300"
                checked={allowLate}
                onChange={(e) => setAllowLate(e.target.checked)}
              />
              <span className="text-sm text-gray-700">Allow late</span>
            </label>
          </div>
        </div>

        <div className="space-y-1">
          <label className="text-sm font-medium text-gray-700">First rubric criterion</label>
          <input
            className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
            value={rubricName}
            onChange={(e) => setRubricName(e.target.value)}
            placeholder="e.g. Correctness"
          />
          <p className="text-xs text-gray-600">You can add more criteria after creation.</p>
        </div>

        <div className="flex gap-2 pt-2 justify-end">
          <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
          <Button type="submit" disabled={isPending || !title.trim()}>
            {isPending ? 'Creating…' : 'Create Draft'}
          </Button>
        </div>
      </form>
    </div>
  )
}
