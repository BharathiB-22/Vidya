// Coursework Assignments (theory/essay/PDF/case-study submissions) — TypeScript types.
// Distinct from Labs (m06_labs_evaluator, practical/code work — untouched) and from
// course-teaching assignments (lib/api/assignments.ts, faculty-to-course allocation —
// unrelated concept that already owns the "Assignment" export name, hence "Coursework" here).
// No AI evaluation — coursework is graded manually by a human evaluator.
//
// Evaluation hand-off:
//   Faculty creates (nominating evaluator(s)) -> students submit, and each
//   submission raises its own evaluator work item -> Faculty submits ->
//   Evaluator evaluates -> a human finalizes the marks.
// Evaluator allocation reuses the M09.6 assignment engine and the existing
// EVALUATOR role. The faculty's nomination is a nomination, not an allocation:
// the department can still allocate or override by hand.

export type CourseworkType = 'ESSAY' | 'CASE_STUDY' | 'REPORT' | 'HOMEWORK' | 'OTHER'
export type CourseworkStatus =
  | 'DRAFT'
  | 'PUBLISHED'
  | 'CLOSED'
  /** Handed to the department; evaluators can now be allocated. */
  | 'SUBMITTED'
  /** Marks ratified by a human. Terminal for grading. */
  | 'FINALIZED'
  | 'ARCHIVED'
export type CourseworkSubmissionStatus = 'SUBMITTED' | 'GRADED' | 'RETURNED'

/** One question in the assignment's question builder. `marks` is per-question;
 *  across the assignment they sum to max_marks. */
export interface CourseworkQuestion {
  question_number: number
  question_text: string
  marks: number
  notes?: string | null
}

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
  /** The evaluator(s) the faculty nominated. Each student submission becomes one
   *  work item against these, round-robin. Empty = the department allocates. */
  evaluator_user_ids: string[]
  /** The questions the faculty set, in order. Empty = none (a question paper may
   *  be attached instead, or this is an older metadata-only assignment). */
  questions: CourseworkQuestion[]
  /** S3 object key of an uploaded question paper (.pdf/.docx); null when none.
   *  The fallback used when no structured questions are entered. */
  question_paper_url: string | null
  status: CourseworkStatus
  created_by_user_id: string
  published_at: string | null
  closed_at: string | null
  submitted_at: string | null
  submitted_by_user_id: string | null
  finalized_at: string | null
  finalized_by_user_id: string | null
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
  evaluator_user_ids?: string[]
  questions?: CourseworkQuestion[]
  question_paper_url?: string | null
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
  evaluator_user_ids?: string[]
  questions?: CourseworkQuestion[]
  question_paper_url?: string | null
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
  /** Who the M09.6 engine currently has evaluating this submission; null until
   *  the department allocates one. */
  evaluator_user_id?: string | null
  evaluator_name?: string | null
}

/** A user who may be allocated coursework to evaluate — the existing EVALUATOR
 *  responsibility, held as a role or as a FACULTY grant. */
export interface EligibleEvaluator {
  id: string
  full_name: string | null
  email: string | null
  role: string
}

/** One coursework submission on the calling evaluator's desk — the M09.6 ledger
 *  resolved back to the coursework it points at, so "My Evaluations" can list
 *  coursework beside scripts and labs. */
export interface MyCourseworkEvaluation {
  submission_id: string
  assignment_id: string
  assignment_title: string
  course_title: string | null
  course_code: string | null
  student_name: string | null
  attempt_number: number
  submitted_at: string
  is_late: boolean
  submission_status: CourseworkSubmissionStatus
  assignment_status: CourseworkStatus
  max_marks: number
  marks_obtained: number | null
  due_at: string | null
  allocation_status: string
}

export interface AssignEvaluatorPayload {
  evaluator_user_id: string
  due_at?: string | null
  notes?: string | null
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
