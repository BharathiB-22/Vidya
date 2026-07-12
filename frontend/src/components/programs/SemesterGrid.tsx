import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus, Pencil, Trash2, BookOpen } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { CourseDialog } from './CourseDialog'
import { useAddCourse, useUpdateCourse, useDeleteCourse, useElectiveBaskets } from '@/hooks/programs'
import type { Course, CourseType, ElectiveBasket, Program } from '@/types/program'

const COURSE_TYPE_COLORS: Record<CourseType, string> = {
  THEORY:        'bg-blue-50 text-blue-700 border-blue-100',
  LAB:           'bg-purple-50 text-purple-700 border-purple-100',
  MINI_PROJECT:  'bg-green-50 text-green-700 border-green-100',
  MAJOR_PROJECT: 'bg-emerald-50 text-emerald-700 border-emerald-100',
  INTERNSHIP:    'bg-orange-50 text-orange-700 border-orange-100',
  SEMINAR:       'bg-yellow-50 text-yellow-700 border-yellow-100',
}

/**
 * Courses saved before course_type was captured (or added without picking one) have
 * course_type: null. Infer a sensible type from the title so the badge is never
 * blank, rather than leaving it unset.
 *
 * The type is not cosmetic — it decides which document the Board generates — so
 * "mini" is checked before the general project case, exactly as migration 0086ten
 * splits the old PROJECT rows. A major project is the safer fallback of the two:
 * its document is the superset, and a Board correcting one down to a mini project
 * loses nothing, while the reverse would silently drop the proposal and the viva.
 */
function resolveCourseType(course: Course): CourseType {
  if (course.course_type) return course.course_type
  const title = course.title.toLowerCase()
  if (title.includes('internship')) return 'INTERNSHIP'
  if (title.includes('mini') && title.includes('project')) return 'MINI_PROJECT'
  if (title.includes('project')) return 'MAJOR_PROJECT'
  if (title.includes('lab') || title.includes('laboratory')) return 'LAB'
  if (title.includes('seminar')) return 'SEMINAR'
  return 'THEORY'
}

/** One elective slot in the structure, e.g. "Elective 1 (3 cr)".
 *
 *  Rendered exactly like a curriculum course, because that is what it is: one
 *  curriculum position worth its own credits. Its choices are deliberately NOT
 *  listed here — the structure answers "where do electives sit in this
 *  programme", and Elective Basket answers "which subjects does this slot
 *  offer". Showing the choices here would read as though the student takes all
 *  of them, and would duplicate the Basket.
 *
 *  `optionCount` is shown only so an empty slot is visibly unfinished. */
function ElectiveSlotCard({ slot, optionCount }: { slot: ElectiveBasket; optionCount: number }) {
  return (
    <div className="rounded-md border border-gray-200 bg-white p-2 shadow-sm">
      <div className="flex items-start justify-between gap-1">
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-gray-800 leading-tight">{slot.name}</p>
          <div className="flex items-center gap-1 mt-1 flex-wrap">
            <span className="text-xs text-gray-500">{slot.credits} cr</span>
            <Badge variant="info" className="text-[10px] py-0 px-1.5">
              Choose one
            </Badge>
            {/* A draft slot is not curriculum yet: it is invisible to Academic
                Ownership, faculty assignment and students. Say so plainly rather
                than letting it look like a live subject. */}
            <span className="text-[9px] font-semibold px-1.5 py-0.5 rounded border border-gray-200 text-gray-500">
              {slot.status}
            </span>
          </div>
          <p className="mt-1 text-[10px] text-gray-500">
            {optionCount === 0
              ? 'No choices yet — add them in Elective Basket.'
              : `${optionCount} choice${optionCount === 1 ? '' : 's'} in Elective Basket`}
          </p>
        </div>
      </div>
    </div>
  )
}

/** Credits the curriculum actually carries: each elective slot contributes its
 *  own `credits` exactly once (the student takes one option from it), never the
 *  sum of its options. Non-option courses (core + standalone electives) each
 *  count fully. `baskets` must be the slots belonging to the same scope as
 *  `list` — the whole program, or one semester.
 *
 *  An option whose slot is absent from `baskets` still counts individually,
 *  so a not-yet-loaded basket query understates rather than drops credits. */
function effectiveCredits(list: Course[], baskets: ElectiveBasket[]): number {
  const slotIds = new Set(baskets.map((b) => b.id))
  let total = baskets.reduce((sum, b) => sum + b.credits, 0)
  for (const c of list) {
    if (c.elective_basket_id && slotIds.has(c.elective_basket_id)) continue
    total += c.credits
  }
  return total
}

interface Props {
  program: Program
  courses: Course[]
}

export function SemesterGrid({ program, courses }: Props) {
  const navigate = useNavigate()
  const isEditable = program.status === 'DRAFT' || program.status === 'PENDING_APPROVAL'
  const maxSem = Math.max(program.duration_years * 2, ...courses.map((c) => c.semester), 0)
  const semesters = Array.from({ length: maxSem }, (_, i) => i + 1)

  const add = useAddCourse(program.id)
  const update = useUpdateCourse(program.id)
  const del = useDeleteCourse(program.id)
  const basketsQ = useElectiveBaskets(program.id)
  const baskets = basketsQ.data ?? []
  const basketNameById = new Map(baskets.map((b) => [b.id, b.name]))

  const [addSem, setAddSem] = useState<number | null>(null)
  const [editCourse, setEditCourse] = useState<Course | null>(null)

  const computedTotal = effectiveCredits(courses, baskets)
  // Slots carry the credits, so the total is only meaningful once they load.
  const matches = basketsQ.isLoading || computedTotal === program.total_credits

  return (
    <div className="space-y-3">
      <div
        className={`flex items-center justify-between rounded-lg border px-4 py-2.5 text-sm ${
          matches
            ? 'border-emerald-200 bg-emerald-50 text-emerald-800'
            : 'border-amber-200 bg-amber-50 text-amber-800'
        }`}
      >
        <span className="font-semibold">Total Credits</span>
        <span>
          <span className="font-bold">{computedTotal}</span>
          <span className="text-current/60"> / {program.total_credits} configured</span>
          {!matches && (
            <span className="ml-2 text-xs font-medium">
              — regenerate the structure to rebalance to exactly {program.total_credits}
            </span>
          )}
        </span>
      </div>

      <div className="overflow-x-auto">
      <div className="flex gap-4 min-w-max pb-4">
        {semesters.map((sem) => {
          const semCourses = courses.filter((c) => c.semester === sem)
          const semBaskets = baskets.filter((b) => b.semester === sem)
          const semCredits = effectiveCredits(semCourses, semBaskets)

          // Options are shown inside their slot's card, never as loose courses.
          // A course whose slot hasn't loaded yet stays a loose card rather
          // than vanishing.
          const slotIds = new Set(semBaskets.map((b) => b.id))
          const optionsBySlot = new Map<string, Course[]>(semBaskets.map((b) => [b.id, []]))
          const looseCourses: Course[] = []
          for (const c of semCourses) {
            if (c.elective_basket_id && slotIds.has(c.elective_basket_id)) {
              optionsBySlot.get(c.elective_basket_id)!.push(c)
            } else {
              looseCourses.push(c)
            }
          }

          return (
            <div key={sem} className="w-56 flex-shrink-0">
              <div className="flex items-center justify-between mb-2 px-1">
                <span className="text-sm font-semibold text-gray-700">Semester {sem}</span>
                <span className="text-xs text-gray-500">{semCredits} cr</span>
              </div>
              <div className="space-y-2 min-h-[4rem]">
                {looseCourses.map((course) => {
                  const courseType = resolveCourseType(course)
                  return (
                  <div
                    key={course.id}
                    className="rounded-md border border-gray-200 bg-white p-2 shadow-sm"
                  >
                    <div className="flex items-start justify-between gap-1">
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-mono text-gray-600 truncate">{course.code}</p>
                        <p className="text-sm font-medium text-gray-800 leading-tight">
                          {course.title}
                        </p>
                        <div className="flex items-center gap-1 mt-1 flex-wrap">
                          <span className="text-xs text-gray-500">{course.credits} cr</span>
                          <span className={`text-[9px] font-semibold px-1.5 py-0.5 rounded border ${COURSE_TYPE_COLORS[courseType]}`}>
                            {courseType}
                          </span>
                          {course.is_elective && (
                            <Badge variant="info" className="text-[10px] py-0 px-1.5">
                              {course.elective_basket_id
                                ? (basketNameById.get(course.elective_basket_id) ?? 'Elective')
                                : 'Elective (no basket)'}
                            </Badge>
                          )}
                          {course.is_ai_generated && (
                            <Badge variant="warning" className="text-[10px] py-0 px-1.5">
                              AI
                            </Badge>
                          )}
                        </div>
                        <button
                          type="button"
                          className="mt-1.5 flex items-center gap-1 text-[10px] font-medium text-blue-600 hover:text-blue-800 hover:underline transition-colors"
                          onClick={(e) => {
                            e.stopPropagation()
                            navigate(`/syllabuses?course_id=${course.id}&program_id=${program.id}`)
                          }}
                        >
                          <BookOpen className="h-3 w-3" />
                          Syllabus
                        </button>
                      </div>
                      {isEditable && (
                        <div className="flex gap-0.5 shrink-0">
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-6 w-6"
                            onClick={() => setEditCourse(course)}
                          >
                            <Pencil className="h-3 w-3" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-6 w-6 text-red-500 hover:text-red-700 hover:bg-red-50"
                            onClick={() => del.mutate(course.id)}
                          >
                            <Trash2 className="h-3 w-3" />
                          </Button>
                        </div>
                      )}
                    </div>
                  </div>
                  )
                })}

                {semBaskets.map((slot) => (
                  <ElectiveSlotCard
                    key={slot.id}
                    slot={slot}
                    optionCount={(optionsBySlot.get(slot.id) ?? []).length}
                  />
                ))}

                {isEditable && (
                  <Button
                    variant="outline"
                    size="sm"
                    className="w-full text-xs"
                    onClick={() => setAddSem(sem)}
                  >
                    <Plus className="h-3 w-3 mr-1" />
                    Add Course
                  </Button>
                )}
              </div>
            </div>
          )
        })}

        {semesters.length === 0 && (
          <p className="text-sm text-gray-400 py-8 px-4">
            No semesters configured. Set duration_years to generate the grid.
          </p>
        )}
      </div>

      <CourseDialog
        open={addSem !== null}
        onOpenChange={(o) => {
          if (!o) setAddSem(null)
        }}
        mode="add"
        semester={addSem ?? 1}
        programId={program.id}
        onAdd={(payload) => add.mutate(payload)}
        isPending={add.isPending}
      />

      <CourseDialog
        open={editCourse !== null}
        onOpenChange={(o) => {
          if (!o) setEditCourse(null)
        }}
        mode="edit"
        initial={editCourse}
        semester={editCourse?.semester ?? 1}
        programId={program.id}
        onEdit={(courseId, payload) => update.mutate({ courseId, payload })}
        isPending={update.isPending}
      />
      </div>
    </div>
  )
}
