import { useState } from 'react'
import { Plus, Pencil, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { CourseDialog } from './CourseDialog'
import { useAddCourse, useUpdateCourse, useDeleteCourse } from '@/hooks/programs'
import type { Course, Program } from '@/types/program'

interface Props {
  program: Program
  courses: Course[]
}

export function SemesterGrid({ program, courses }: Props) {
  const isDraft = program.status === 'DRAFT'
  const maxSem = Math.max(program.duration_years * 2, ...courses.map((c) => c.semester), 0)
  const semesters = Array.from({ length: maxSem }, (_, i) => i + 1)

  const add = useAddCourse(program.id)
  const update = useUpdateCourse(program.id)
  const del = useDeleteCourse(program.id)

  const [addSem, setAddSem] = useState<number | null>(null)
  const [editCourse, setEditCourse] = useState<Course | null>(null)

  return (
    <div className="overflow-x-auto">
      <div className="flex gap-4 min-w-max pb-4">
        {semesters.map((sem) => {
          const semCourses = courses.filter((c) => c.semester === sem)
          const semCredits = semCourses.reduce((sum, c) => sum + c.credits, 0)

          return (
            <div key={sem} className="w-56 flex-shrink-0">
              <div className="flex items-center justify-between mb-2 px-1">
                <span className="text-sm font-semibold text-gray-700">Semester {sem}</span>
                <span className="text-xs text-gray-400">{semCredits} cr</span>
              </div>
              <div className="space-y-2 min-h-[4rem]">
                {semCourses.map((course) => (
                  <div
                    key={course.id}
                    className="rounded-md border border-gray-200 bg-white p-2 shadow-sm"
                  >
                    <div className="flex items-start justify-between gap-1">
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-mono text-gray-400 truncate">{course.code}</p>
                        <p className="text-sm font-medium text-gray-800 leading-tight">
                          {course.title}
                        </p>
                        <div className="flex items-center gap-1 mt-1 flex-wrap">
                          <span className="text-xs text-gray-500">{course.credits} cr</span>
                          {course.is_elective && (
                            <Badge variant="info" className="text-[10px] py-0 px-1.5">
                              Elective
                            </Badge>
                          )}
                          {course.is_ai_generated && (
                            <Badge variant="warning" className="text-[10px] py-0 px-1.5">
                              AI
                            </Badge>
                          )}
                        </div>
                      </div>
                      {isDraft && (
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
                ))}
                {isDraft && (
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
        onEdit={(courseId, payload) => update.mutate({ courseId, payload })}
        isPending={update.isPending}
      />
    </div>
  )
}
