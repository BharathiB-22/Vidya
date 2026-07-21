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
  /** Marks ratified by a human (Dean). Not yet visible to students. */
  | 'FINALIZED'
  /** Ratified marks released to students; results now visible. */
  | 'RELEASED'
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
  /** Display name of the faculty who created it (detail endpoint only). */
  created_by_name?: string | null
  /** Display names of the nominated evaluators (detail endpoint only). */
  evaluator_names?: string[]
  /** Live evaluation progress, derived server-side on the list + detail
   *  endpoints. Undefined where it was not computed (e.g. the student list). */
  progress?: CourseworkProgress
}

/** How far one assignment has travelled. Every number is derived on read from
 *  submissions, AI evaluations and the M09.6 ledger — nothing is stored, so it
 *  cannot drift. AI counts are advisory state, never marks. */
export interface CourseworkProgress {
  total_students: number
  submitted_count: number
  graded_count: number
  late_count: number
  ai_completed_count: number
  ai_failed_count: number
  ai_pending_count: number
  evaluator_assigned_count: number
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
  /** Advisory AI evaluation state for this submission; null/undefined when the
   *  worker has not produced a row yet. Status only — the suggestions come from
   *  the per-submission AI endpoint. */
  ai_status?: AiEvalStatus | null
  /** What the EVALUATOR recommended, preserved permanently. Visible to the
   *  assignment's owner so they can compare it with their own decision; never
   *  sent to students. Null when the owner graded it themselves. */
  evaluator_marks_obtained?: number | null
  evaluator_feedback?: string | null
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
/** One ASSIGNMENT the evaluator is assigned to (shown from publish, before any
 *  submission exists) with per-evaluator progress counts. */
export interface MyCourseworkEvaluation {
  assignment_id: string
  assignment_title: string
  assignment_status: CourseworkStatus
  course_title: string | null
  course_code: string | null
  semester: number | null
  sections: string | null
  faculty_name: string | null
  evaluator_names: string | null
  due_date: string | null
  max_marks: number
  question_count: number
  total_submissions: number
  // Assignment-level progress (whole class) for the home card.
  total_students: number
  submitted_students: number
  reviewed_students: number
  pending_submission: number
  pending_review: number
  // Evaluator's own slice.
  allocated_to_me: number
  graded_by_me: number
  pending_for_me: number
}

/** One course the faculty teaches, with its resolved approved syllabus. Scopes
 *  the create form's course picker to the faculty's own load. */
export interface MyTeachingCourse {
  course_id: string
  course_code: string
  course_title: string
  semester: number | null
  section_id: string | null
  section_name: string | null
  syllabus_id: string | null
  has_approved_syllabus: boolean
}

// ── Evaluation Center — one assignment's full class roster + live progress ──
export type EvaluationCenterStatus = 'NOT_SUBMITTED' | 'SUBMITTED' | 'UNDER_REVIEW' | 'REVIEWED'

export interface EvaluationCenterStudent {
  student_user_id: string
  student_name: string | null
  student_usn?: string | null
  submission_status: EvaluationCenterStatus
  submission_id: string | null
  is_late: boolean
  submitted_at: string | null
  marks_obtained: number | null
  graded_at?: string | null
  evaluator_user_id: string | null
  evaluator_name: string | null
  ai_status?: AiEvalStatus | null
}

export interface EvaluationCenterProgress {
  total_students: number
  submitted: number
  pending_submission: number
  reviewed: number
  pending_review: number
  ai_completed?: number
  ai_failed?: number
}

export interface EvaluationCenterResponse {
  assignment: CourseworkAssignment
  semester: number | null
  progress: EvaluationCenterProgress
  students: EvaluationCenterStudent[]
}

// ── AI evaluation (advisory) ───────────────────────────────────────────────
export type AiEvalStatus = 'PENDING' | 'EXTRACTING' | 'EVALUATING' | 'COMPLETED' | 'FAILED'

export interface AiSuggestedMark {
  question_number: number
  suggested: number
  max: number
  reason: string
}

export interface AiEvaluation {
  submission_id: string
  status: AiEvalStatus
  extracted_text: string | null
  word_count: number | null
  file_type: string | null
  suggested_marks: AiSuggestedMark[] | null
  overall_suggested_marks: number | null
  percentage: number | null
  confidence_level: 'HIGH' | 'MEDIUM' | 'LOW' | string | null
  feedback: {
    strengths?: string[]
    weaknesses?: string[]
    missing_concepts?: string[]
    writing_quality?: string
    technical_correctness?: string
    suggestions?: string[]
  } | null
  rubric_scores: { criterion: string; score: number; max: number; comment?: string }[] | null
  bloom_analysis: { expected_level?: string; detected_level?: string; alignment_percent?: number; notes?: string } | null
  co_analysis: { covered?: string[]; weak?: string[]; missing?: string[]; notes?: string } | null
  similarity_score: number | null
  similarity_matches: { submission_id: string; similarity: number }[] | null
  plagiarism_status: string
  ai_model: string | null
  provider_used: string | null
  fallback_chain: string | null
  processing_ms: number | null
  error_log: string | null
  retry_count: number
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
  ai_completed_count?: number
  ai_failed_count?: number
  ai_pending_count?: number
  evaluator_assigned_count?: number
}
