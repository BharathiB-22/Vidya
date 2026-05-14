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
import type { BloomLevel, KitQuizlet, KitQuizletCreate, KitQuizletUpdate, QuizletType } from '@/types/courseKit'

const BLOOM_LEVELS: BloomLevel[] = ['REMEMBER', 'UNDERSTAND', 'APPLY', 'ANALYSE', 'EVALUATE', 'CREATE']

interface Props {
  open:         boolean
  onOpenChange: (open: boolean) => void
  mode:         'add' | 'edit'
  initial?:     KitQuizlet | null
  nextNumber?:  number
  onAdd:        (payload: KitQuizletCreate) => void
  onEdit:       (quizletId: string, payload: KitQuizletUpdate) => void
  isPending?:   boolean
  showAnswerKey: boolean
}

export function QuizletDialog({
  open, onOpenChange, mode, initial, nextNumber = 1,
  onAdd, onEdit, isPending, showAnswerKey,
}: Props) {
  const [questionText,  setQuestionText]  = useState('')
  const [questionType,  setQuestionType]  = useState<QuizletType>('MCQ')
  const [answerText,    setAnswerText]    = useState('')
  const [explanation,   setExplanation]   = useState('')
  const [bloomLevel,    setBloomLevel]    = useState<BloomLevel | ''>('')
  const [coRef,         setCoRef]         = useState('')

  useEffect(() => {
    if (open && mode === 'edit' && initial) {
      setQuestionText(initial.question_text)
      setQuestionType(initial.question_type)
      const ak = initial.answer_key as Record<string, unknown> | null
      setAnswerText(ak ? (ak.correct_answer as string ?? JSON.stringify(ak)) : '')
      setExplanation(initial.answer_explanation ?? '')
      setBloomLevel(initial.bloom_level ?? '')
      setCoRef(initial.co_reference ?? '')
    } else if (open && mode === 'add') {
      setQuestionText('')
      setQuestionType('MCQ')
      setAnswerText('')
      setExplanation('')
      setBloomLevel('')
      setCoRef('')
    }
  }, [open, mode, initial])

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!questionText.trim()) return
    const answerKey = showAnswerKey && answerText
      ? { correct_answer: answerText }
      : undefined
    if (mode === 'add') {
      onAdd({
        question_number:     nextNumber,
        question_text:       questionText.trim(),
        question_type:       questionType,
        answer_key:          answerKey,
        answer_explanation:  explanation || undefined,
        bloom_level:         bloomLevel || undefined,
        co_reference:        coRef || undefined,
      })
    } else if (initial) {
      onEdit(initial.id, {
        question_text:       questionText.trim(),
        question_type:       questionType,
        answer_key:          answerKey,
        answer_explanation:  explanation || undefined,
        bloom_level:         bloomLevel || undefined,
        co_reference:        coRef || undefined,
      })
    }
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{mode === 'add' ? 'Add Quizlet' : 'Edit Quizlet'}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Question Type</label>
            <Select value={questionType} onValueChange={(v) => setQuestionType(v as QuizletType)}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="MCQ">Multiple Choice (MCQ)</SelectItem>
                <SelectItem value="SHORT_ANSWER">Short Answer</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Question <span className="text-red-500">*</span>
            </label>
            <Textarea
              rows={3}
              required
              value={questionText}
              onChange={(e) => setQuestionText(e.target.value)}
              placeholder="Enter the question…"
            />
          </div>
          {showAnswerKey && (
            <>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Answer Key</label>
                <Input
                  value={answerText}
                  onChange={(e) => setAnswerText(e.target.value)}
                  placeholder={questionType === 'MCQ' ? 'e.g. A' : 'Correct answer…'}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Explanation</label>
                <Textarea
                  rows={2}
                  value={explanation}
                  onChange={(e) => setExplanation(e.target.value)}
                  placeholder="Explain the answer…"
                />
              </div>
            </>
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
                placeholder="e.g. CO2"
              />
            </div>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="submit" disabled={isPending || !questionText.trim()}>
              {isPending ? 'Saving…' : mode === 'add' ? 'Add Quizlet' : 'Save'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
