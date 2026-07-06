import type { Assignment } from '@/lib/api/assignments'
import type { SyllabusStatus } from '@/types/syllabus'

/** Resolved once by the workspace page and handed to every tab — avoids re-deriving
 * the syllabus lookup, department, and faculty-name lookups per tab. syllabusId/
 * syllabusStatus are null when the course has no syllabus yet; departmentName and
 * facultyName are null when not resolvable from existing endpoints. */
export interface FacultySubjectContext {
  assignment: Assignment
  syllabusId: string | null
  syllabusStatus: SyllabusStatus | null
  departmentName: string | null
  facultyName: string | null
  /** All section names this faculty teaches for this same course (usually one). */
  sectionsHandled: string[]
}

export interface FacultySubjectTabProps {
  ctx: FacultySubjectContext
  onNavigateTab: (key: string) => void
}
