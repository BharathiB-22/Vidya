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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useCreateKit } from '@/hooks/courseKit'
import type { ComplexityLevel } from '@/types/courseKit'

interface Props {
  open:           boolean
  onOpenChange:   (open: boolean) => void
  syllabusId:     string
}

export function CreateCourseKitDialog({ open, onOpenChange, syllabusId }: Props) {
  const [unitNumber,    setUnitNumber]    = useState('')
  const [complexity,    setComplexity]    = useState<ComplexityLevel>('UG')
  const [tone,          setTone]          = useState('')
  const [instructions,  setInstructions]  = useState('')

  const create = useCreateKit()

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const unit = parseInt(unitNumber, 10)
    if (!unit || unit < 1) return
    try {
      await create.mutateAsync({
        syllabus_id:         syllabusId,
        unit_number:         unit,
        complexity_level:    complexity,
        tone:                tone || undefined,
        custom_instructions: instructions || undefined,
      })
      setUnitNumber('')
      setComplexity('UG')
      setTone('')
      setInstructions('')
      onOpenChange(false)
    } catch {
      // error visible via create.isError — dialog stays open
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Create Course Kit</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Syllabus ID</label>
            <Input value={syllabusId} disabled />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Unit Number <span className="text-red-500">*</span>
            </label>
            <Input
              type="number"
              min={1}
              required
              value={unitNumber}
              onChange={(e) => setUnitNumber(e.target.value)}
              placeholder="e.g. 1"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Complexity Level</label>
            <Select value={complexity} onValueChange={(v) => setComplexity(v as ComplexityLevel)}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="UG">UG (Undergraduate)</SelectItem>
                <SelectItem value="PG">PG (Postgraduate)</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Tone (optional)
            </label>
            <Input
              value={tone}
              onChange={(e) => setTone(e.target.value)}
              placeholder="e.g. formal, engaging, concise"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Custom Instructions (optional)
            </label>
            <Textarea
              rows={3}
              value={instructions}
              onChange={(e) => setInstructions(e.target.value)}
              placeholder="e.g. Emphasise hands-on labs and industry tools"
            />
          </div>
          {create.isError && (
            <p className="text-xs text-red-600 bg-red-50 border border-red-200 rounded px-3 py-1.5">
              Failed to create kit. Ensure the syllabus is Dean-Approved or Locked first.
            </p>
          )}
          <DialogFooter className="pt-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={create.isPending || !unitNumber}>
              {create.isPending ? 'Creating…' : 'Create'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
