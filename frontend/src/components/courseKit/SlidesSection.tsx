import { useState } from 'react'
import { Plus, Pencil, Trash2, Lock, Loader2, ChevronDown, ChevronUp } from 'lucide-react'
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
  isLoading?:       boolean
}

function SkeletonSlide() {
  return (
    <div className="rounded-lg border border-gray-200 px-4 py-3 animate-pulse">
      <div className="flex items-start gap-3">
        <div className="h-4 w-6 rounded bg-gray-200 shrink-0" />
        <div className="flex-1 space-y-2">
          <div className="h-4 w-48 rounded bg-gray-200" />
          <div className="h-3 w-full rounded bg-gray-100" />
          <div className="h-3 w-3/4 rounded bg-gray-100" />
        </div>
      </div>
    </div>
  )
}

export function SlidesSection({ kitId, slides, isEditable, showSpeakerNotes, isLoading }: Props) {
  const [dialogOpen,      setDialogOpen]      = useState(false)
  const [editTarget,      setEditTarget]      = useState<KitSlide | null>(null)
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null)
  const [expandedIds,     setExpandedIds]     = useState<Set<string>>(new Set())

  function toggleExpand(id: string) {
    setExpandedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

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

  function handleDeleteClick(slideId: string) {
    if (pendingDeleteId === slideId) {
      deleteSlide.mutate(slideId)
      setPendingDeleteId(null)
    } else {
      setPendingDeleteId(slideId)
    }
  }

  const mutationError = addSlide.isError || updateSlide.isError || deleteSlide.isError

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-700">
          Slides ({isLoading ? '…' : slides.length})
        </h3>
        {isEditable && (
          <Button size="sm" variant="outline" onClick={openAdd} disabled={addSlide.isPending}>
            <Plus className="h-4 w-4 mr-1" />
            Add Slide
          </Button>
        )}
      </div>

      {mutationError && (
        <p className="text-xs text-red-600 bg-red-50 border border-red-200 rounded px-3 py-1.5">
          Action failed — please try again.
        </p>
      )}

      {isLoading ? (
        <div className="space-y-2">
          {[1, 2, 3].map((n) => <SkeletonSlide key={n} />)}
        </div>
      ) : sorted.length === 0 ? (
        <p className="text-sm text-gray-400 py-4 text-center">
          No slides yet.{isEditable ? ' Click "Add Slide" to begin.' : ''}
        </p>
      ) : (
        <div className="space-y-2">
          {sorted.map((slide) => {
            const content = slide.content as Record<string, unknown>
            const bullets      = Array.isArray(content.bullets)       ? content.bullets      as string[] : []
            const keyConcepts  = Array.isArray(content.key_concepts)  ? content.key_concepts as string[] : []
            const codeSnippet  = typeof content.code_snippet === 'string' ? content.code_snippet  : null
            const imageHint    = typeof content.image_hint   === 'string' ? content.image_hint    : null
            const isConfirmDelete = pendingDeleteId === slide.id
            const isExpanded      = expandedIds.has(slide.id)
            const PREVIEW = 3

            return (
              <div
                key={slide.id}
                className={`rounded-lg border px-4 py-3 ${
                  isConfirmDelete ? 'border-red-300 bg-red-50' : 'border-gray-200 hover:bg-gray-50'
                }`}
              >
                <div className="flex items-start gap-3">
                  <span className="min-w-[2rem] text-sm font-bold text-gray-400 shrink-0">
                    #{slide.slide_number}
                  </span>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold text-gray-800">{slide.title}</p>

                    {/* Bullets — preview or full */}
                    {bullets.length > 0 && (
                      <ul className="mt-1 space-y-0.5">
                        {(isExpanded ? bullets : bullets.slice(0, PREVIEW)).map((b, i) => (
                          <li key={i} className="text-xs text-gray-500 pl-3 border-l-2 border-gray-200">
                            {b}
                          </li>
                        ))}
                      </ul>
                    )}

                    {/* Expand / collapse toggle */}
                    {bullets.length > PREVIEW && (
                      <button
                        type="button"
                        onClick={() => toggleExpand(slide.id)}
                        className="flex items-center gap-0.5 mt-1 text-[11px] text-blue-600 hover:underline"
                      >
                        {isExpanded
                          ? <><ChevronUp className="h-3 w-3" /> Show less</>
                          : <><ChevronDown className="h-3 w-3" /> +{bullets.length - PREVIEW} more</>
                        }
                      </button>
                    )}

                    {/* Extra content when expanded */}
                    {isExpanded && (
                      <div className="mt-2 space-y-2">
                        {keyConcepts.length > 0 && (
                          <div>
                            <p className="text-[10px] font-semibold text-gray-500 uppercase tracking-wide mb-1">Key Concepts</p>
                            <div className="flex flex-wrap gap-1">
                              {keyConcepts.map((kc, i) => (
                                <span key={i} className="text-[10px] bg-blue-50 text-blue-700 border border-blue-100 px-1.5 py-0.5 rounded">
                                  {kc}
                                </span>
                              ))}
                            </div>
                          </div>
                        )}
                        {codeSnippet && (
                          <pre className="text-xs bg-gray-900 text-green-300 rounded p-2 overflow-x-auto whitespace-pre-wrap">
                            {codeSnippet}
                          </pre>
                        )}
                        {showSpeakerNotes && slide.speaker_notes && (
                          <div className="text-xs bg-amber-50 border border-amber-100 rounded px-3 py-2">
                            <p className="font-semibold text-amber-700 mb-0.5">Speaker Notes</p>
                            <p className="text-gray-600 whitespace-pre-wrap">{slide.speaker_notes}</p>
                          </div>
                        )}
                        {imageHint && (
                          <p className="text-[10px] text-gray-400 italic">Image hint: {imageHint}</p>
                        )}
                      </div>
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
                    {isConfirmDelete && (
                      <p className="text-xs text-red-600 mt-1">Click delete again to confirm.</p>
                    )}
                  </div>
                  {isEditable && (
                    <div className="flex gap-1 shrink-0">
                      <Button
                        size="icon"
                        variant="ghost"
                        className="h-7 w-7"
                        onClick={() => openEdit(slide)}
                        aria-label={`Edit slide ${slide.slide_number}`}
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </Button>
                      <Button
                        size="icon"
                        variant="ghost"
                        className={`h-7 w-7 ${isConfirmDelete ? 'text-red-700' : 'text-red-500 hover:text-red-700'}`}
                        onClick={() => handleDeleteClick(slide.id)}
                        disabled={deleteSlide.isPending}
                        aria-label={isConfirmDelete ? `Confirm delete slide ${slide.slide_number}` : `Delete slide ${slide.slide_number}`}
                      >
                        {deleteSlide.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
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
