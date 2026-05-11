import { useState } from 'react'
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
import { useCreateSyllabus } from '@/hooks/syllabuses'

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  courseId: string
}

export function CreateSyllabusDialog({ open, onOpenChange, courseId }: Props) {
  const [instructions, setInstructions] = useState('')
  const create = useCreateSyllabus()

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    await create.mutateAsync({
      course_id: courseId,
      custom_instructions: instructions || undefined,
    })
    setInstructions('')
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Create Syllabus</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Course ID</label>
            <Input value={courseId} disabled />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Custom Instructions (optional)
            </label>
            <Textarea
              rows={3}
              value={instructions}
              onChange={(e) => setInstructions(e.target.value)}
              placeholder="e.g. Focus on practical labs and industry case studies"
            />
          </div>
          <DialogFooter className="pt-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={create.isPending}>
              {create.isPending ? 'Creating…' : 'Create'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
