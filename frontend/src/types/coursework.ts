// Coursework Assignments (theory/essay/PDF/case-study submissions) — TypeScript types.
// Distinct from Labs (m06_labs_evaluator, practical/code work — untouched) and from
// course-teaching assignments (lib/api/assignments.ts, faculty-to-course allocation —
// unrelated concept that already owns the "Assignment" export name, hence "Coursework" here).
// No AI evaluation — coursework is graded manually by faculty.

export type CourseworkType = 'ESSAY' | 'CASE_STUDY' | 'REPORT' | 'HOMEWORK' | 'OTHER'
export type CourseworkStatus = 'DRAFT' | 'PUBLISHED' | 'CLOSED' | 'ARCHIVED'
export type CourseworkSubmissionStatus = 'SUBMITTED' | 'GRADED' | 'RETURNED'

export interface CourseworkAssignment {
  id: string
  syllabus_id: string | null
  title: string
  description: string | null
  instructions: string | null
  assignment_type: CourseworkType
  max_marks: number
  weightage_percent: number | null
  due_date: string
  allow_late: boolean
  late_penalty_percent: number | null
  max_attempts: number
  allowed_file_types: string[] | null
  status: CourseworkStatus
  created_by_user_id: string
  published_at: string | null
  closed_at: string | null
  created_at: string
  updated_at: string
  course_title?: string | null
  course_code?: string | null
}

export interface CourseworkAssignmentListResponse {
  items: CourseworkAssignment[]
  total: number
  offset: number
  limit: number
}

export interface CourseworkAssignmentCreate {
  syllabus_id?: string
  title: string
  description?: string
  instructions?: string
  assignment_type: CourseworkType
  max_marks: number
  weightage_percent?: number
  due_date: string
  allow_late?: boolean
  late_penalty_percent?: number
  max_attempts?: number
  allowed_file_types?: string[]
}

export interface CourseworkAssignmentUpdate {
  title?: string
  description?: string
  instructions?: string
  assignment_type?: CourseworkType
  max_marks?: number
  weightage_percent?: number
  due_date?: string
  allow_late?: boolean
  late_penalty_percent?: number
  max_attempts?: number
  allowed_file_types?: string[]
}

export interface CourseworkSubmission {
  id: string
  assignment_id: string
  student_user_id: string
  attempt_number: number
  content_url: string | null
  content_text: string | null
  submitted_at: string
  is_late: boolean
  status: CourseworkSubmissionStatus
  marks_obtained: number | null
  feedback: string | null
  graded_by_user_id: string | null
  graded_at: string | null
  returned_at: string | null
  // Optional server-side enrichment for faculty grading views
  student_name?: string | null
  student_usn?: string | null
}

export interface CourseworkSubmissionListResponse {
  items: CourseworkSubmission[]
  total: number
  offset: number
  limit: number
}

export interface CourseworkSubmitPayload {
  content_text?: string
  content_url?: string
}

export interface CourseworkGradePayload {
  marks_obtained: number
  feedback?: string
}

export interface CourseworkStatistics {
  total_students: number
  submitted_count: number
  graded_count: number
  average_marks: number | null
  late_count: number
}
