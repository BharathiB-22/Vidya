// M08 Exam Setter — TypeScript types

export type ExamType =
  | 'MID_SEM'
  | 'END_SEM'
  | 'QUIZ'
  | 'INTERNAL'
  | 'CUSTOM'

export type ExamPaperStatus =
  | 'DRAFT'
  | 'GENERATING'
  | 'GENERATED'
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
  total_marks:          number
  duration_mins:        number
  units_included:       number[]
  question_format:      QuestionFormatConfig
  requested_dist:       BloomsDistribution
  actual_dist:          BloomsDistribution | null
  special_instructions: string | null
  ai_model:             string | null
  generation_job_id:    string | null
  status:               ExamPaperStatus
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
  total_marks:          number
  duration_mins:        number
  units_included:       number[]
  question_format:      QuestionFormatConfig
  requested_dist:       BloomsDistribution
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
