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
import type { BloomLevel, KitSlide, KitSlideCreate, KitSlideUpdate } from '@/types/courseKit'

const BLOOM_LEVELS: BloomLevel[] = ['REMEMBER', 'UNDERSTAND', 'APPLY', 'ANALYSE', 'EVALUATE', 'CREATE']

interface Props {
  open:         boolean
  onOpenChange: (open: boolean) => void
  mode:         'add' | 'edit'
  initial?:     KitSlide | null
  nextNumber?:  number
  onAdd:        (payload: KitSlideCreate) => void
  onEdit:       (slideId: string, payload: KitSlideUpdate) => void
  isPending?:   boolean
  showSpeakerNotes: boolean
}

export function SlideDialog({
  open, onOpenChange, mode, initial, nextNumber = 1,
  onAdd, onEdit, isPending, showSpeakerNotes,
}: Props) {
  const [title,        setTitle]        = useState('')
  const [bullets,      setBullets]      = useState('')
  const [keyConcepts,  setKeyConcepts]  = useState('')
  const [speakerNotes, setSpeakerNotes] = useState('')
  const [bloomLevel,   setBloomLevel]   = useState<BloomLevel | ''>('')
  const [coRef,        setCoRef]        = useState('')

  useEffect(() => {
    if (open && mode === 'edit' && initial) {
      setTitle(initial.title)
      const content = initial.content as Record<string, unknown>
      setBullets(Array.isArray(content.bullets) ? (content.bullets as string[]).join('\n') : '')
      setKeyConcepts(Array.isArray(content.key_concepts) ? (content.key_concepts as string[]).join('\n') : '')
      setSpeakerNotes(initial.speaker_notes ?? '')
      setBloomLevel(initial.bloom_level ?? '')
      setCoRef(initial.co_reference ?? '')
    } else if (open && mode === 'add') {
      setTitle('')
      setBullets('')
      setKeyConcepts('')
      setSpeakerNotes('')
      setBloomLevel('')
      setCoRef('')
    }
  }, [open, mode, initial])

  function buildContent() {
    return {
      bullets:      bullets.split('\n').map((s) => s.trim()).filter(Boolean),
      key_concepts: keyConcepts.split('\n').map((s) => s.trim()).filter(Boolean),
      image_hint:   null,
      code_snippet: null,
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
        speaker_notes: showSpeakerNotes && speakerNotes ? speakerNotes : undefined,
        bloom_level:   bloomLevel || undefined,
        co_reference:  coRef || undefined,
      })
    } else if (initial) {
      onEdit(initial.id, {
        title:         title.trim(),
        content:       buildContent(),
        speaker_notes: showSpeakerNotes && speakerNotes ? speakerNotes : undefined,
        bloom_level:   bloomLevel || undefined,
        co_reference:  coRef || undefined,
      })
    }
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{mode === 'add' ? 'Add Slide' : 'Edit Slide'}</DialogTitle>
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
              placeholder="Slide title"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Bullet Points (one per line)
            </label>
            <Textarea
              rows={3}
              value={bullets}
              onChange={(e) => setBullets(e.target.value)}
              placeholder="Key point 1&#10;Key point 2"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Key Concepts (one per line)
            </label>
            <Textarea
              rows={2}
              value={keyConcepts}
              onChange={(e) => setKeyConcepts(e.target.value)}
              placeholder="Concept A&#10;Concept B"
            />
          </div>
          {showSpeakerNotes && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Speaker Notes
              </label>
              <Textarea
                rows={3}
                value={speakerNotes}
                onChange={(e) => setSpeakerNotes(e.target.value)}
                placeholder="Notes for the presenter…"
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
