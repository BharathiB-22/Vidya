// M08 Exam Setter — TypeScript types

export type ExamType =
  | 'MID_SEM'
  | 'END_SEM'
  | 'QUIZ'
  | 'INTERNAL'
  | 'CUSTOM'

export type ExamWorkflow = 'INTERNAL' | 'BOARD_EXAM'

export interface SectionConfig {
  label:        string        // 'A', 'B', 'C'
  instruction?: string | null
  total_q:      number
  answer_q:     number
  marks_each:   number
  order:        number
  mcq_only:     boolean
}

export interface CoCoverageEntry {
  co_id:          string
  co_code:        string
  covered:        boolean
  question_count: number
}

export interface UnitCoverageEntry {
  unit_no:        number
  covered:        boolean
  question_count: number
}

export type ExamPaperStatus =
  | 'DRAFT'
  | 'GENERATING'
  | 'GENERATED'
  | 'FAILED'
  | 'SUBMITTED'
  | 'BOARD_APPROVED'
  | 'BOARD_RETURNED'
  | 'SEALED'
  | 'RELEASED'

export type QuestionType =
  | 'MCQ'
  | 'SHORT_ANSWER'
  | 'LONG_ANSWER'
  | 'PROBLEM_SOLVING'

export type BloomLevel =
  | 'REMEMBER'
  | 'UNDERSTAND'
  | 'APPLY'
  | 'ANALYSE'
  | 'EVALUATE'
  | 'CREATE'

export interface QuestionFormatConfig {
  mcq_count:     number
  short_count:   number
  long_count:    number
  problem_count: number
}

export interface BloomsDistribution {
  remember:   number
  understand: number
  apply:      number
  analyse:    number
  evaluate:   number
  create:     number
}

export interface ExamPaper {
  id:                   string
  course_id:            string
  created_by:           string
  title:                string
  exam_type:            ExamType
  exam_workflow:        ExamWorkflow
  total_marks:          number
  duration_mins:        number
  units_included:       number[]
  question_format:      QuestionFormatConfig
  requested_dist:       BloomsDistribution
  actual_dist:          BloomsDistribution | null
  section_config:       SectionConfig[] | null
  co_coverage_report:   CoCoverageEntry[] | null
  unit_coverage_report: UnitCoverageEntry[] | null
  special_instructions: string | null
  ai_model:             string | null
  generation_job_id:    string | null
  status:               ExamPaperStatus
  failure_reason:       string | null
  submitted_at:         string | null
  approved_by:          string | null
  approved_at:          string | null
  board_comment:        string | null
  sealed_at:            string | null
  release_at:           string | null
  released_at:          string | null
  created_at:           string
  updated_at:           string | null
}

export interface ExamPaperListResponse {
  items:  ExamPaper[]
  total:  number
  offset: number
  limit:  number
}

export interface MCQOption {
  label: string
  text:  string
}

export interface ExamQuestion {
  id:             string
  exam_paper_id:  string
  unit_number:    number
  co_code:        string | null
  bloom_level:    BloomLevel
  question_type:  QuestionType
  question_text:  string
  options:        MCQOption[] | null
  marks:          number
  section_label:  string | null
  co_ids:         string[] | null
  choice_group:   number | null
  set_membership: string[]
  ai_generated:   boolean
  is_edited:      boolean
  created_at:     string
  updated_at:     string | null
  // model_answer and correct_option only in answers export
  model_answer?:   string | null
  correct_option?: string | null
}

export interface BloomsViolation {
  level:         BloomLevel
  requested_pct: number
  actual_pct:    number
  delta_pct:     number
}

export interface BloomsComplianceReport {
  id:             string
  exam_paper_id:  string
  requested_dist: BloomsDistribution
  actual_dist:    BloomsDistribution
  compliance_ok:  boolean
  violations:     BloomsViolation[]
  generated_at:   string
}

// Request bodies
export interface ExamPaperCreatePayload {
  course_id:            string
  title:                string
  exam_type:            ExamType
  exam_workflow?:       ExamWorkflow
  total_marks:          number
  duration_mins:        number
  units_included:       number[]
  question_format:      QuestionFormatConfig
  requested_dist:       BloomsDistribution
  section_config?:      SectionConfig[]
  special_instructions?: string
}

export interface BoardDecisionPayload {
  approved:       boolean
  board_comment?: string
}

export interface SealPayload {
  release_at: string  // ISO 8601 UTC datetime
}

export interface ExamQuestionUpdatePayload {
  question_text?:  string
  marks?:          number
  model_answer?:   string
  bloom_level?:    BloomLevel
  set_membership?: string[]
}

export interface JobStatus {
  job_id: string
  status: string
  result: Record<string, unknown> | null
}

// ---- H-35: Internal marks types ----

export type InternalMarksStatus = 'PENDING' | 'FACULTY_SUBMITTED' | 'DEAN_LOCKED'

export interface InternalMarks {
  id:               string
  student_id:       string
  course_id:        string
  semester:         number
  academic_year:    string
  internal1_marks:  number | null
  internal2_marks:  number | null
  assignment_marks: number | null
  attendance_marks: number | null
  total_internal:   number | null
  max_internal:     number
  status:           InternalMarksStatus
  submitted_by:     string | null
  submitted_at:     string | null
  locked_by:        string | null
  locked_at:        string | null
  created_at:       string
  updated_at:       string | null
}

export interface InternalMarksListResponse {
  items:  InternalMarks[]
  total:  number
  offset: number
  limit:  number
}
