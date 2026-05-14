import { useState } from 'react'
import { Plus, Pencil, Trash2, Lock } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { SlideDialog } from './SlideDialog'
import {
  useAddSlide,
  useUpdateSlide,
  useDeleteSlide,
} from '@/hooks/courseKit'
import type { KitSlide, KitSlideCreate, KitSlideUpdate } from '@/types/courseKit'

interface Props {
  kitId:            string
  slides:           KitSlide[]
  isEditable:       boolean
  showSpeakerNotes: boolean
}

export function SlidesSection({ kitId, slides, isEditable, showSpeakerNotes }: Props) {
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editTarget, setEditTarget] = useState<KitSlide | null>(null)

  const addSlide    = useAddSlide(kitId)
  const updateSlide = useUpdateSlide(kitId)
  const deleteSlide = useDeleteSlide(kitId)

  const sorted = [...slides].sort((a, b) => a.slide_number - b.slide_number)

  function openAdd() {
    setEditTarget(null)
    setDialogOpen(true)
  }

  function openEdit(slide: KitSlide) {
    setEditTarget(slide)
    setDialogOpen(true)
  }

  function handleAdd(payload: KitSlideCreate) {
    addSlide.mutate(payload)
  }

  function handleEdit(slideId: string, payload: KitSlideUpdate) {
    updateSlide.mutate({ slideId, payload })
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-700">Slides ({slides.length})</h3>
        {isEditable && (
          <Button size="sm" variant="outline" onClick={openAdd}>
            <Plus className="h-4 w-4 mr-1" />
            Add Slide
          </Button>
        )}
      </div>

      {sorted.length === 0 ? (
        <p className="text-sm text-gray-400 py-4 text-center">
          No slides yet.{isEditable ? ' Click "Add Slide" to begin.' : ''}
        </p>
      ) : (
        <div className="space-y-2">
          {sorted.map((slide) => {
            const content = slide.content as Record<string, unknown>
            const bullets = Array.isArray(content.bullets) ? content.bullets as string[] : []
            return (
              <div
                key={slide.id}
                className="rounded-lg border border-gray-200 px-4 py-3 hover:bg-gray-50"
              >
                <div className="flex items-start gap-3">
                  <span className="min-w-[2rem] text-sm font-bold text-gray-400 shrink-0">
                    #{slide.slide_number}
                  </span>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold text-gray-800">{slide.title}</p>
                    {bullets.length > 0 && (
                      <ul className="mt-1 space-y-0.5">
                        {bullets.slice(0, 3).map((b, i) => (
                          <li key={i} className="text-xs text-gray-500 pl-3 border-l-2 border-gray-200 truncate">
                            {b}
                          </li>
                        ))}
                        {bullets.length > 3 && (
                          <li className="text-xs text-gray-400 pl-3">+{bullets.length - 3} more</li>
                        )}
                      </ul>
                    )}
                    <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                      {slide.bloom_level && (
                        <span className="text-[10px] font-semibold bg-purple-50 text-purple-700 border border-purple-200 px-1.5 py-0.5 rounded">
                          {slide.bloom_level}
                        </span>
                      )}
                      {slide.co_reference && (
                        <span className="text-[10px] font-mono text-gray-500 bg-gray-100 px-1.5 py-0.5 rounded">
                          {slide.co_reference}
                        </span>
                      )}
                      {!showSpeakerNotes && slide.speaker_notes !== undefined && (
                        <span className="flex items-center gap-1 text-[10px] text-gray-400">
                          <Lock className="h-3 w-3" /> notes hidden
                        </span>
                      )}
                    </div>
                  </div>
                  {isEditable && (
                    <div className="flex gap-1 shrink-0">
                      <Button
                        size="icon"
                        variant="ghost"
                        className="h-7 w-7"
                        onClick={() => openEdit(slide)}
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </Button>
                      <Button
                        size="icon"
                        variant="ghost"
                        className="h-7 w-7 text-red-500 hover:text-red-700"
                        onClick={() => deleteSlide.mutate(slide.id)}
                        disabled={deleteSlide.isPending}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}

      <SlideDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        mode={editTarget ? 'edit' : 'add'}
        initial={editTarget}
        nextNumber={slides.length + 1}
        onAdd={handleAdd}
        onEdit={handleEdit}
        isPending={addSlide.isPending || updateSlide.isPending}
        showSpeakerNotes={showSpeakerNotes}
      />
    </div>
  )
}
