// M06 Labs & Assignment Evaluator — TypeScript types

export type SubmissionType = 'WRITTEN' | 'CODE'
export type AssignmentStatus = 'DRAFT' | 'PUBLISHED' | 'CLOSED' | 'ARCHIVED'
export type SubmissionStatus = 'SUBMITTED' | 'EVALUATING' | 'EVALUATED' | 'REVIEWED' | 'RATIFIED'
export type AIScanStatus = 'PENDING' | 'CLEAN' | 'FLAGGED'
export type ConfidenceLevel = 'HIGH' | 'MEDIUM' | 'LOW'

export interface RubricCriterion {
  criterion_id: string
  name: string
  description: string
  max_marks: number
  weight: number
}

export interface TestCase {
  id: string
  name: string
  stdin: string
  expected_stdout: string
  is_hidden: boolean
  points: number
}

export interface LabAssignment {
  id: string
  title: string
  description: string | null
  instructions: string | null
  submission_type: SubmissionType
  language: string | null
  rubric: RubricCriterion[]
  test_cases: TestCase[]
  max_marks: number | null
  deadline: string | null
  ai_not_permitted: boolean
  allow_late: boolean
  plagiarism_threshold: number
  status: AssignmentStatus
  syllabus_id: string | null
  kit_assignment_id: string | null
  created_by_user_id: string
  published_at: string | null
  closed_at: string | null
  created_at: string
  updated_at: string | null
  // Enriched on detail endpoints from syllabi → courses join
  course_title: string | null
  course_code: string | null
}

export interface LabAssignmentListResponse {
  items: LabAssignment[]
  total: number
  offset: number
  limit: number
}

export interface AssignmentCreate {
  title: string
  description?: string
  instructions?: string
  submission_type: SubmissionType
  language?: string
  rubric: RubricCriterion[]
  test_cases?: TestCase[]
  syllabus_id?: string
  deadline?: string
  ai_not_permitted?: boolean
  allow_late?: boolean
  plagiarism_threshold?: number
}

export interface AssignmentUpdate {
  title?: string
  description?: string
  instructions?: string
  rubric?: RubricCriterion[]
  test_cases?: TestCase[]
  deadline?: string
  ai_not_permitted?: boolean
  allow_late?: boolean
  language?: string
}

// ── Submission ──────────────────────────────────────────────────────────────

export interface LabSubmission {
  id: string
  assignment_id: string
  student_user_id: string
  submission_type: SubmissionType
  content_url: string | null
  submitted_at: string
  is_late: boolean
  eval_job_id: string | null
  ai_scan_status: AIScanStatus
  status: SubmissionStatus
  // Populated for RATIFIED submissions
  final_score: number | null
  graded_max_marks: number | null
}

export interface LabSubmissionDetail extends LabSubmission {
  content_text: string | null
  ai_scan_result: {
    probability: number
    confidence: number
    highlights: Array<{ start: number; end: number; score: number }>
  } | null
  evaluation: LabEvaluation | null
}

export interface SubmissionListResponse {
  items: LabSubmission[]
  total: number
  offset: number
  limit: number
}

export interface SubmitPayload {
  content_text?: string
  content_url?: string
}

// ── Evaluation ──────────────────────────────────────────────────────────────

export interface CriterionScore {
  criterion_id: string
  ai_score: number
  ai_justification: string
  human_score: number | null
  human_note: string | null
}

export interface TestResult {
  id: string
  name: string
  passed: boolean
  actual_stdout: string
  error: string | null
  points_awarded: number
  timed_out: boolean
}

export interface StaticAnalysis {
  complexity_score: number
  complexity_label: string
  issues: Array<{ line: number; message: string; code: string }>
  parse_error: string | null
}

export interface PlagiarismMatch {
  submission_id: string
  similarity: number
  student_user_id?: string
}

export interface LabEvaluation {
  id: string
  submission_id: string
  rubric_scores: CriterionScore[]
  overall_ai_score: number | null
  overall_human_score: number | null
  confidence_level: ConfidenceLevel | null
  test_results: TestResult[] | null
  static_analysis: StaticAnalysis | null
  plagiarism_score: number | null
  plagiarism_matches: PlagiarismMatch[] | null
  ai_model: string | null
  created_at: string
  updated_at: string | null
}

// ── Review panel ─────────────────────────────────────────────────────────────

export interface ReviewPanel {
  submission: LabSubmissionDetail
  assignment: LabAssignment
  grade_entry: GradeLedgerEntry | null
}

// ── Grade ledger ─────────────────────────────────────────────────────────────

export interface GradeLedgerEntry {
  id: string
  submission_id: string
  assignment_id: string
  student_user_id: string
  ratified_by_user_id: string
  final_score: number
  max_marks: number
  ratification_note: string | null
  ratified_at: string
}

// ── Score update ─────────────────────────────────────────────────────────────

export interface ScoreUpdate {
  criterion_id: string
  human_score: number
  human_note?: string
}

export interface ScoresUpdateRequest {
  scores: ScoreUpdate[]
}

export interface RatifyRequest {
  ratification_note?: string
}

// ── Job status ───────────────────────────────────────────────────────────────

export interface JobStatus {
  job_id: string
  status: string
  result: Record<string, unknown> | null
  error: string | null
  created_at: string | null
  completed_at: string | null
}
