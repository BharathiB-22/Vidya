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
import type { BloomLevel, KitSlide, KitSlideCreate, KitSlideUpdate, SlideType } from '@/types/courseKit'

const BLOOM_LEVELS: BloomLevel[] = ['REMEMBER', 'UNDERSTAND', 'APPLY', 'ANALYSE', 'EVALUATE', 'CREATE']

const SLIDE_TYPES: Array<{ value: SlideType; label: string }> = [
  { value: 'TITLE',      label: 'Title / Overview' },
  { value: 'CONCEPT',    label: 'Concept' },
  { value: 'DEFINITION', label: 'Definition' },
  { value: 'EXAMPLE',    label: 'Example' },
  { value: 'CODE',       label: 'Code' },
  { value: 'DIAGRAM',    label: 'Diagram' },
  { value: 'ACTIVITY',   label: 'Activity' },
  { value: 'SUMMARY',    label: 'Summary' },
  { value: 'QUIZ',       label: 'Quiz' },
]

interface Props {
  open:             boolean
  onOpenChange:     (open: boolean) => void
  mode:             'add' | 'edit'
  initial?:         KitSlide | null
  nextNumber?:      number
  onAdd:            (payload: KitSlideCreate) => void
  onEdit:           (slideId: string, payload: KitSlideUpdate) => void
  isPending?:       boolean
  showSpeakerNotes: boolean
}

export function SlideDialog({
  open, onOpenChange, mode, initial, nextNumber = 1,
  onAdd, onEdit, isPending, showSpeakerNotes,
}: Props) {
  const [title,             setTitle]             = useState('')
  const [slideType,         setSlideType]         = useState<SlideType | 'NONE'>('NONE')
  const [bullets,           setBullets]           = useState('')
  const [keyConcepts,       setKeyConcepts]       = useState('')
  const [definitions,       setDefinitions]       = useState('')
  const [examples,          setExamples]          = useState('')
  const [codeSnippet,       setCodeSnippet]       = useState('')
  const [diagramPrompt,     setDiagramPrompt]     = useState('')
  const [classroomActivity, setClassroomActivity] = useState('')
  const [studentSummary,    setStudentSummary]    = useState('')
  const [teachingNotes,     setTeachingNotes]     = useState('')
  const [speakerNotes,      setSpeakerNotes]      = useState('')
  const [bloomLevel,        setBloomLevel]        = useState<BloomLevel | 'NONE'>('NONE')
  const [coRef,             setCoRef]             = useState('')

  useEffect(() => {
    if (open && mode === 'edit' && initial) {
      const c = initial.content as Record<string, unknown>
      setTitle(initial.title)
      setSlideType((c.slide_type as SlideType | undefined) ?? 'NONE')
      setBullets(Array.isArray(c.bullets)      ? (c.bullets      as string[]).join('\n') : '')
      setKeyConcepts(Array.isArray(c.key_concepts)  ? (c.key_concepts  as string[]).join('\n') : '')
      setDefinitions(Array.isArray(c.definitions)   ? (c.definitions   as string[]).join('\n') : '')
      setExamples(Array.isArray(c.examples)         ? (c.examples      as string[]).join('\n') : '')
      setCodeSnippet(typeof c.code_snippet       === 'string' ? c.code_snippet       : '')
      setDiagramPrompt(typeof c.diagram_prompt   === 'string' ? c.diagram_prompt     : (typeof c.image_hint === 'string' ? c.image_hint : ''))
      setClassroomActivity(typeof c.classroom_activity === 'string' ? c.classroom_activity : '')
      setStudentSummary(typeof c.student_summary === 'string' ? c.student_summary : '')
      setTeachingNotes(typeof c.teaching_notes   === 'string' ? c.teaching_notes   : '')
      setSpeakerNotes(initial.speaker_notes ?? '')
      setBloomLevel(initial.bloom_level ?? 'NONE')
      setCoRef(initial.co_reference ?? '')
    } else if (open && mode === 'add') {
      setTitle('')
      setSlideType('NONE')
      setBullets('')
      setKeyConcepts('')
      setDefinitions('')
      setExamples('')
      setCodeSnippet('')
      setDiagramPrompt('')
      setClassroomActivity('')
      setStudentSummary('')
      setTeachingNotes('')
      setSpeakerNotes('')
      setBloomLevel('NONE')
      setCoRef('')
    }
  }, [open, mode, initial])

  function splitLines(s: string) {
    return s.split('\n').map((x) => x.trim()).filter(Boolean)
  }

  function buildContent() {
    return {
      ...(slideType !== 'NONE' ? { slide_type: slideType } : {}),
      bullets:             splitLines(bullets),
      key_concepts:        splitLines(keyConcepts),
      definitions:         splitLines(definitions),
      examples:            splitLines(examples),
      code_snippet:        codeSnippet.trim() || null,
      diagram_prompt:      diagramPrompt.trim() || null,
      image_hint:          null,
      classroom_activity:  classroomActivity.trim() || null,
      student_summary:     studentSummary.trim() || null,
      teaching_notes:      showSpeakerNotes && teachingNotes.trim() ? teachingNotes.trim() : null,
    }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!title.trim()) return
    if (mode === 'add') {
      onAdd({
        slide_number:  nextNumber,
        title:         title.trim(),
        content:       buildContent(),
        speaker_notes: showSpeakerNotes && speakerNotes.trim() ? speakerNotes.trim() : undefined,
        bloom_level:   bloomLevel !== 'NONE' ? bloomLevel : undefined,
        co_reference:  coRef.trim() || undefined,
      })
    } else if (initial) {
      onEdit(initial.id, {
        title:         title.trim(),
        content:       buildContent(),
        speaker_notes: showSpeakerNotes && speakerNotes.trim() ? speakerNotes.trim() : undefined,
        bloom_level:   bloomLevel !== 'NONE' ? bloomLevel : undefined,
        co_reference:  coRef.trim() || undefined,
      })
    }
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{mode === 'add' ? 'Add Slide' : 'Edit Slide'}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">

          {/* Title + Slide Type */}
          <div className="grid grid-cols-2 gap-3">
            <div className="col-span-2 md:col-span-1">
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Title <span className="text-red-500">*</span>
              </label>
              <Input
                required
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Slide title"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Slide Type</label>
              <Select value={slideType} onValueChange={(v) => setSlideType(v as SlideType | 'NONE')}>
                <SelectTrigger><SelectValue placeholder="Select type" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="NONE">Unspecified</SelectItem>
                  {SLIDE_TYPES.map((st) => (
                    <SelectItem key={st.value} value={st.value}>{st.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Bullets */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Bullet Points <span className="text-xs text-gray-600">(one per line)</span>
            </label>
            <Textarea
              rows={4}
              value={bullets}
              onChange={(e) => setBullets(e.target.value)}
              placeholder="Key point 1&#10;Key point 2&#10;Key point 3"
            />
          </div>

          {/* Key Concepts */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Key Concepts <span className="text-xs text-gray-600">(one per line)</span>
            </label>
            <Textarea
              rows={2}
              value={keyConcepts}
              onChange={(e) => setKeyConcepts(e.target.value)}
              placeholder="Concept A&#10;Concept B"
            />
          </div>

          {/* Definitions */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Definitions <span className="text-xs text-gray-600">(one per line)</span>
            </label>
            <Textarea
              rows={3}
              value={definitions}
              onChange={(e) => setDefinitions(e.target.value)}
              placeholder="Term A: formal definition&#10;Term B: formal definition"
            />
          </div>

          {/* Examples */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Examples <span className="text-xs text-gray-600">(one per line)</span>
            </label>
            <Textarea
              rows={3}
              value={examples}
              onChange={(e) => setExamples(e.target.value)}
              placeholder="Real-world example 1&#10;Applied scenario 2"
            />
          </div>

          {/* Code Snippet */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Code Snippet</label>
            <Textarea
              rows={4}
              value={codeSnippet}
              onChange={(e) => setCodeSnippet(e.target.value)}
              placeholder="# paste relevant code here"
              className="font-mono text-xs"
            />
          </div>

          {/* Diagram Prompt */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Diagram / Visual Prompt</label>
            <Input
              value={diagramPrompt}
              onChange={(e) => setDiagramPrompt(e.target.value)}
              placeholder="e.g. Flowchart showing A → B → C"
            />
          </div>

          {/* Classroom Activity */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Classroom Activity</label>
            <Textarea
              rows={2}
              value={classroomActivity}
              onChange={(e) => setClassroomActivity(e.target.value)}
              placeholder="In pairs, discuss X for 5 minutes…"
            />
          </div>

          {/* Student Takeaway */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Student Takeaway</label>
            <Textarea
              rows={2}
              value={studentSummary}
              onChange={(e) => setStudentSummary(e.target.value)}
              placeholder="Brief student-friendly summary of this slide…"
            />
          </div>

          {/* Faculty-only fields */}
          {showSpeakerNotes && (
            <>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Teaching Notes <span className="text-xs text-orange-500">(faculty only)</span>
                </label>
                <Textarea
                  rows={3}
                  value={teachingNotes}
                  onChange={(e) => setTeachingNotes(e.target.value)}
                  placeholder="How to present this slide, common misconceptions, discussion prompts…"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Speaker Notes <span className="text-xs text-orange-500">(faculty only)</span>
                </label>
                <Textarea
                  rows={3}
                  value={speakerNotes}
                  onChange={(e) => setSpeakerNotes(e.target.value)}
                  placeholder="Presenter notes…"
                />
              </div>
            </>
          )}

          {/* Bloom Level + CO Reference */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Bloom Level</label>
              <Select value={bloomLevel} onValueChange={(v) => setBloomLevel(v as BloomLevel | 'NONE')}>
                <SelectTrigger><SelectValue placeholder="None" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="NONE">None</SelectItem>
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
                placeholder="e.g. CO1"
              />
            </div>
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="submit" disabled={isPending || !title.trim()}>
              {isPending ? 'Saving…' : mode === 'add' ? 'Add Slide' : 'Save'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
