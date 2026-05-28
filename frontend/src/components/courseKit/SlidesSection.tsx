import { useState } from 'react'
import { Plus, Pencil, Trash2, Lock, Loader2, ChevronDown, ChevronUp, BookOpen, Lightbulb, Users, GraduationCap } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { SlideDialog } from './SlideDialog'
import {
  useAddSlide,
  useUpdateSlide,
  useDeleteSlide,
} from '@/hooks/courseKit'
import type { KitSlide, KitSlideCreate, KitSlideUpdate, SlideType } from '@/types/courseKit'

interface Props {
  kitId:            string
  slides:           KitSlide[]
  isEditable:       boolean
  showSpeakerNotes: boolean
  isLoading?:       boolean
}

// Slide type badge colours
const SLIDE_TYPE_STYLES: Record<SlideType, string> = {
  TITLE:      'bg-indigo-100 text-indigo-700 border-indigo-200',
  CONCEPT:    'bg-blue-50 text-blue-700 border-blue-200',
  DEFINITION: 'bg-purple-50 text-purple-700 border-purple-200',
  EXAMPLE:    'bg-emerald-50 text-emerald-700 border-emerald-200',
  CODE:       'bg-gray-900 text-green-300 border-gray-700',
  DIAGRAM:    'bg-cyan-50 text-cyan-700 border-cyan-200',
  ACTIVITY:   'bg-amber-50 text-amber-700 border-amber-200',
  SUMMARY:    'bg-green-50 text-green-700 border-green-200',
  QUIZ:       'bg-red-50 text-red-700 border-red-200',
}

function SlideTypeBadge({ type }: { type: SlideType }) {
  return (
    <span className={`inline-flex items-center text-[10px] font-bold px-1.5 py-0.5 rounded border ${SLIDE_TYPE_STYLES[type] ?? 'bg-gray-100 text-gray-600 border-gray-200'}`}>
      {type}
    </span>
  )
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
            const c = slide.content as Record<string, unknown>
            const slideType        = c.slide_type    as SlideType | undefined
            const bullets          = Array.isArray(c.bullets)            ? c.bullets            as string[] : []
            const keyConcepts      = Array.isArray(c.key_concepts)       ? c.key_concepts       as string[] : []
            const definitions      = Array.isArray(c.definitions)        ? c.definitions        as string[] : []
            const examples         = Array.isArray(c.examples)           ? c.examples           as string[] : []
            const codeSnippet      = typeof c.code_snippet      === 'string' ? c.code_snippet      : null
            const diagramPrompt    = typeof c.diagram_prompt    === 'string' ? c.diagram_prompt    : (typeof c.image_hint === 'string' ? c.image_hint : null)
            const classroomActivity= typeof c.classroom_activity=== 'string' ? c.classroom_activity: null
            const studentSummary   = typeof c.student_summary   === 'string' ? c.student_summary   : null
            const teachingNotes    = typeof c.teaching_notes    === 'string' ? c.teaching_notes    : null

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
                    {/* Title row with slide type badge */}
                    <div className="flex items-center gap-2 flex-wrap">
                      <p className="text-sm font-semibold text-gray-800">{slide.title}</p>
                      {slideType && <SlideTypeBadge type={slideType} />}
                    </div>

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

                    {/* Student summary preview when no bullets */}
                    {bullets.length === 0 && studentSummary && !isExpanded && (
                      <p className="mt-1 text-xs text-gray-500 italic">{studentSummary}</p>
                    )}

                    {/* Expand / collapse toggle */}
                    {(bullets.length > PREVIEW || definitions.length > 0 || examples.length > 0 || codeSnippet || classroomActivity || studentSummary || (showSpeakerNotes && (teachingNotes || slide.speaker_notes))) && (
                      <button
                        type="button"
                        onClick={() => toggleExpand(slide.id)}
                        className="flex items-center gap-0.5 mt-1 text-[11px] text-blue-600 hover:underline"
                      >
                        {isExpanded
                          ? <><ChevronUp className="h-3 w-3" /> Show less</>
                          : <><ChevronDown className="h-3 w-3" /> Show full slide content</>
                        }
                      </button>
                    )}

                    {/* Expanded rich content */}
                    {isExpanded && (
                      <div className="mt-3 space-y-3">

                        {/* Remaining bullets (if more than PREVIEW) */}
                        {bullets.length > PREVIEW && (
                          <ul className="space-y-0.5">
                            {bullets.slice(PREVIEW).map((b, i) => (
                              <li key={i} className="text-xs text-gray-500 pl-3 border-l-2 border-gray-200">
                                {b}
                              </li>
                            ))}
                          </ul>
                        )}

                        {/* Key Concepts */}
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

                        {/* Definitions */}
                        {definitions.length > 0 && (
                          <div className="rounded-md bg-purple-50 border border-purple-100 px-3 py-2">
                            <div className="flex items-center gap-1.5 mb-1">
                              <BookOpen className="h-3 w-3 text-purple-500" />
                              <p className="text-[10px] font-semibold text-purple-700 uppercase tracking-wide">Definitions</p>
                            </div>
                            <ul className="space-y-0.5">
                              {definitions.map((d, i) => (
                                <li key={i} className="text-xs text-purple-800">{d}</li>
                              ))}
                            </ul>
                          </div>
                        )}

                        {/* Examples */}
                        {examples.length > 0 && (
                          <div className="rounded-md bg-emerald-50 border border-emerald-100 px-3 py-2">
                            <div className="flex items-center gap-1.5 mb-1">
                              <Lightbulb className="h-3 w-3 text-emerald-600" />
                              <p className="text-[10px] font-semibold text-emerald-700 uppercase tracking-wide">Examples</p>
                            </div>
                            <ul className="space-y-0.5">
                              {examples.map((ex, i) => (
                                <li key={i} className="text-xs text-emerald-800">{ex}</li>
                              ))}
                            </ul>
                          </div>
                        )}

                        {/* Code snippet */}
                        {codeSnippet && (
                          <pre className="text-xs bg-gray-900 text-green-300 rounded p-2 overflow-x-auto whitespace-pre-wrap">
                            {codeSnippet}
                          </pre>
                        )}

                        {/* Diagram prompt */}
                        {diagramPrompt && (
                          <p className="text-[10px] text-cyan-600 italic bg-cyan-50 border border-cyan-100 rounded px-2 py-1">
                            Diagram: {diagramPrompt}
                          </p>
                        )}

                        {/* Classroom Activity — visible to all */}
                        {classroomActivity && (
                          <div className="rounded-md bg-amber-50 border border-amber-100 px-3 py-2">
                            <div className="flex items-center gap-1.5 mb-1">
                              <Users className="h-3 w-3 text-amber-600" />
                              <p className="text-[10px] font-semibold text-amber-700 uppercase tracking-wide">Classroom Activity</p>
                            </div>
                            <p className="text-xs text-amber-800">{classroomActivity}</p>
                          </div>
                        )}

                        {/* Student Summary — visible to all */}
                        {studentSummary && (
                          <div className="rounded-md bg-green-50 border border-green-100 px-3 py-2">
                            <div className="flex items-center gap-1.5 mb-1">
                              <GraduationCap className="h-3 w-3 text-green-600" />
                              <p className="text-[10px] font-semibold text-green-700 uppercase tracking-wide">Student Takeaway</p>
                            </div>
                            <p className="text-xs text-green-800">{studentSummary}</p>
                          </div>
                        )}

                        {/* Teaching Notes — faculty only */}
                        {showSpeakerNotes && teachingNotes && (
                          <div className="text-xs bg-orange-50 border border-orange-100 rounded px-3 py-2">
                            <p className="font-semibold text-orange-700 mb-0.5">Teaching Notes (Faculty)</p>
                            <p className="text-gray-700 whitespace-pre-wrap">{teachingNotes}</p>
                          </div>
                        )}

                        {/* Speaker Notes — faculty only */}
                        {showSpeakerNotes && slide.speaker_notes && (
                          <div className="text-xs bg-amber-50 border border-amber-100 rounded px-3 py-2">
                            <p className="font-semibold text-amber-700 mb-0.5">Speaker Notes</p>
                            <p className="text-gray-600 whitespace-pre-wrap">{slide.speaker_notes}</p>
                          </div>
                        )}
                      </div>
                    )}

                    {/* Tag row */}
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
                      {!showSpeakerNotes && (slide.speaker_notes !== null && slide.speaker_notes !== undefined) && (
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
