import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { BookOpen, Lock, Eye, Info, ChevronDown, ChevronUp, BookMarked } from 'lucide-react'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { Badge } from '@/components/ui/badge'
import { sisApi, StudentCourseMarks, StudentComponentView } from '@/lib/api/sis'

const STATUS_COLORS: Record<string, string> = {
  PUBLISHED: 'bg-green-100  text-green-800  border-green-200',
  LOCKED:    'bg-gray-100   text-gray-700   border-gray-300',
}
const TYPE_LABELS: Record<string, string> = {
  CIE: 'CIE', ASSIGNMENT: 'Assignment', LAB: 'Lab Assessment', OTHER: 'Other',
}

function ScoreBar({ obtained, max }: { obtained: number | null; max: number }) {
  if (obtained === null) return <span className="text-muted-foreground">—</span>
  const pct = Math.min(100, (obtained / max) * 100)
  return (
    <div className="flex items-center gap-2">
      <span className="font-semibold w-10 text-right text-sm">{Number(obtained).toFixed(1)}</span>
      <div className="flex-1 h-1.5 rounded bg-muted overflow-hidden">
        <div className={`h-full rounded ${pct >= 50 ? 'bg-green-500' : 'bg-amber-500'}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-muted-foreground w-10">/{max}</span>
    </div>
  )
}

function CourseCard({ course }: { course: StudentCourseMarks }) {
  const [open, setOpen] = useState(true)

  return (
    <div className="rounded-md border overflow-hidden">
      {/* Course header row */}
      <button
        className="w-full flex items-center justify-between px-4 py-3 bg-muted/20 hover:bg-muted/30 text-left"
        onClick={() => setOpen(o => !o)}
      >
        <div className="flex items-center gap-2">
          <BookOpen className="h-4 w-4 text-muted-foreground" />
          <span className="font-semibold">{course.course_code}</span>
          <span className="text-muted-foreground text-sm">{course.course_title}</span>
          <Badge variant="outline" className="text-xs">{course.section_name}</Badge>
        </div>
        <div className="flex items-center gap-3">
          {course.total_marks_obtained !== null && course.total_max_marks !== null ? (
            <span className="text-sm font-semibold">
              {Number(course.total_marks_obtained).toFixed(1)}
              <span className="text-muted-foreground font-normal"> / {Number(course.total_max_marks).toFixed(1)}</span>
            </span>
          ) : (
            <span className="text-muted-foreground text-xs">Pending</span>
          )}
          {open ? <ChevronUp className="h-4 w-4 text-muted-foreground" /> : <ChevronDown className="h-4 w-4 text-muted-foreground" />}
        </div>
      </button>

      {open && (
        <div className="border-t">
          <table className="w-full text-sm">
            <thead className="bg-muted/20 text-xs uppercase text-muted-foreground">
              <tr>
                <th className="px-4 py-2 text-left">Component</th>
                <th className="px-4 py-2 text-left">Type</th>
                <th className="px-4 py-2 text-left w-52">Score</th>
                <th className="px-4 py-2 text-center">Status</th>
                <th className="px-4 py-2 text-left">Remarks</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {course.components.map((c: StudentComponentView) => (
                <tr key={c.component_id} className="hover:bg-muted/10">
                  <td className="px-4 py-2 font-medium">{c.name}</td>
                  <td className="px-4 py-2 text-muted-foreground">{TYPE_LABELS[c.component_type] ?? c.component_type}</td>
                  <td className="px-4 py-2">
                    <ScoreBar obtained={c.marks_obtained} max={c.max_marks} />
                  </td>
                  <td className="px-4 py-2 text-center">
                    <Badge variant="outline" className={`text-xs ${STATUS_COLORS[c.status]}`}>
                      {c.status === 'LOCKED'
                        ? <><Lock className="h-3 w-3 inline mr-1" />Locked</>
                        : <><Eye className="h-3 w-3 inline mr-1" />Published</>
                      }
                    </Badge>
                  </td>
                  <td className="px-4 py-2 text-xs text-muted-foreground">{c.remarks ?? '—'}</td>
                </tr>
              ))}
              {course.components.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-4 text-center text-muted-foreground text-xs">
                    No published marks yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>

          {/* Course total footer */}
          {course.total_marks_obtained !== null && course.total_max_marks !== null && (
            <div className="px-4 py-2 bg-muted/20 border-t flex justify-between items-center text-sm font-medium">
              <span>Course Internal Total</span>
              <span>
                {Number(course.total_marks_obtained).toFixed(1)}
                <span className="text-muted-foreground font-normal"> / {Number(course.total_max_marks).toFixed(1)}</span>
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function MyMarksPage() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['my-marks'],
    queryFn:  sisApi.getMyMarks,
  })

  if (isLoading) return <div className="p-6 text-muted-foreground">Loading your marks…</div>
  if (isError)   return <div className="p-6 text-red-600">Failed to load marks. Try again.</div>
  if (!data)     return null

  return (
    <PageShell>
      <PageHeader
        icon={BookMarked}
        title="My Internal Marks"
        subtitle={`${data.student_name}${data.usn ? ` · USN: ${data.usn}` : ''}`}
      />

      <div className="flex gap-2 items-start rounded-md border border-blue-200 bg-blue-50 p-3 text-sm text-blue-800 mb-4">
        <Info className="h-4 w-4 mt-0.5 shrink-0" />
        Only published and locked marks are shown. DRAFT components are not visible until faculty publishes them.
      </div>

      {data.courses.length === 0 ? (
        <div className="text-center py-16 text-muted-foreground">
          No marks have been published yet. Check back after your faculty publishes the assessment results.
        </div>
      ) : (
        <div className="space-y-3">
          {data.courses.map((course: StudentCourseMarks) => (
            <CourseCard key={course.course_id} course={course} />
          ))}
        </div>
      )}
    </PageShell>
  )
}
