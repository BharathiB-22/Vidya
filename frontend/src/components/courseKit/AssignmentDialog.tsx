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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type {
  AssignmentType,
  BloomLevel,
  ComplexityLevel,
  KitAssignment,
  KitAssignmentCreate,
  KitAssignmentUpdate,
} from '@/types/courseKit'

const BLOOM_LEVELS: BloomLevel[] = ['REMEMBER', 'UNDERSTAND', 'APPLY', 'ANALYSE', 'EVALUATE', 'CREATE']

interface Props {
  open:          boolean
  onOpenChange:  (open: boolean) => void
  mode:          'add' | 'edit'
  initial?:      KitAssignment | null
  nextNumber?:   number
  onAdd:         (payload: KitAssignmentCreate) => void
  onEdit:        (assignmentId: string, payload: KitAssignmentUpdate) => void
  isPending?:    boolean
  showModelAnswer: boolean
}

export function AssignmentDialog({
  open, onOpenChange, mode, initial, nextNumber = 1,
  onAdd, onEdit, isPending, showModelAnswer,
}: Props) {
  const [title,          setTitle]          = useState('')
  const [assignmentType, setAssignmentType] = useState<AssignmentType>('CLASSWORK')
  const [questionText,   setQuestionText]   = useState('')
  const [complexity,     setComplexity]     = useState<ComplexityLevel>('UG')
  const [currentEvents,  setCurrentEvents]  = useState(false)
  const [modelAnswer,    setModelAnswer]    = useState('')
  const [bloomLevel,     setBloomLevel]     = useState<BloomLevel | ''>('')
  const [coRef,          setCoRef]          = useState('')

  useEffect(() => {
    if (open && mode === 'edit' && initial) {
      setTitle(initial.title)
      setAssignmentType(initial.assignment_type)
      setQuestionText(initial.question_text)
      setComplexity(initial.complexity_level)
      setCurrentEvents(initial.current_events_toggle)
      setModelAnswer(initial.model_answer ?? '')
      setBloomLevel(initial.bloom_level ?? '')
      setCoRef(initial.co_reference ?? '')
    } else if (open && mode === 'add') {
      setTitle('')
      setAssignmentType('CLASSWORK')
      setQuestionText('')
      setComplexity('UG')
      setCurrentEvents(false)
      setModelAnswer('')
      setBloomLevel('')
      setCoRef('')
    }
  }, [open, mode, initial])

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!title.trim() || !questionText.trim()) return
    if (mode === 'add') {
      onAdd({
        assignment_number:      nextNumber,
        title:                  title.trim(),
        assignment_type:        assignmentType,
        question_text:          questionText.trim(),
        complexity_level:       complexity,
        current_events_toggle:  currentEvents,
        model_answer:           showModelAnswer && modelAnswer ? modelAnswer : undefined,
        bloom_level:            bloomLevel || undefined,
        co_reference:           coRef || undefined,
      })
    } else if (initial) {
      onEdit(initial.id, {
        title:                  title.trim(),
        assignment_type:        assignmentType,
        question_text:          questionText.trim(),
        complexity_level:       complexity,
        current_events_toggle:  currentEvents,
        model_answer:           showModelAnswer && modelAnswer ? modelAnswer : undefined,
        bloom_level:            bloomLevel || undefined,
        co_reference:           coRef || undefined,
      })
    }
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{mode === 'add' ? 'Add Assignment' : 'Edit Assignment'}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Title <span className="text-red-500">*</span>
            </label>
            <Input
              required
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Assignment title"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Type</label>
              <Select value={assignmentType} onValueChange={(v) => setAssignmentType(v as AssignmentType)}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="CLASSWORK">Classwork</SelectItem>
                  <SelectItem value="HOMEWORK">Homework</SelectItem>
                  <SelectItem value="CASE_STUDY">Case Study</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Complexity</label>
              <Select value={complexity} onValueChange={(v) => setComplexity(v as ComplexityLevel)}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="UG">UG</SelectItem>
                  <SelectItem value="PG">PG</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Question <span className="text-red-500">*</span>
            </label>
            <Textarea
              rows={4}
              required
              value={questionText}
              onChange={(e) => setQuestionText(e.target.value)}
              placeholder="Describe the assignment or question…"
            />
          </div>
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="current_events"
              checked={currentEvents}
              onChange={(e) => setCurrentEvents(e.target.checked)}
              className="h-4 w-4 rounded border-gray-300"
            />
            <label htmlFor="current_events" className="text-sm text-gray-700">
              Link to current events
            </label>
          </div>
          {showModelAnswer && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Model Answer</label>
              <Textarea
                rows={3}
                value={modelAnswer}
                onChange={(e) => setModelAnswer(e.target.value)}
                placeholder="Expected model answer…"
              />
            </div>
          )}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Bloom Level</label>
              <Select value={bloomLevel} onValueChange={(v) => setBloomLevel(v as BloomLevel)}>
                <SelectTrigger><SelectValue placeholder="None" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="">None</SelectItem>
                  {BLOOM_LEVELS.map((b) => (
                    <SelectItem key={b} value={b}>{b}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">CO Reference</label>
              <Input
                value={coRef}
                onChange={(e) => setCoRef(e.target.value)}
                placeholder="e.g. CO3"
              />
            </div>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="submit" disabled={isPending || !title.trim() || !questionText.trim()}>
              {isPending ? 'Saving…' : mode === 'add' ? 'Add Assignment' : 'Save'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
