// M09 Paper Administration & Scanning — TypeScript types

export type ScriptStatus =
  | 'PENDING'
  | 'PROCESSING'
  | 'SCORED'
  | 'FAILED'
  | 'REVIEW_REQUIRED'
  | 'MARKS_SUBMITTED'
  | 'BOARD_FINALISED'

export type EvaluationRound =
  | 'PRIMARY'
  | 'SECONDARY'
  | 'MODERATION'

// ---------------------------------------------------------------------------
// ScriptEvaluation — AI suggestion + evaluator marks per question
// ---------------------------------------------------------------------------

export interface ScriptEvaluation {
  id:                  string
  script_id:           string
  question_id:         string
  question_type:       string
  max_marks:           number
  evaluation_round:    EvaluationRound

  // AI-suggested (written by Celery task only, never final)
  ai_suggested_marks:  number | null
  ai_justification:    string | null
  ai_model:            string | null

  // Human marks (written only by evaluator endpoints)
  evaluator_marks:     number | null
  evaluator_note:      string | null

  // Final marks (set at Board finalisation only)
  final_marks:         number | null

  created_at:          string
  updated_at:          string | null
}

// ---------------------------------------------------------------------------
// ScannedScript
// Identity masking: student_user_id and student_roll_ref are null until
// status === 'BOARD_FINALISED'.
// ---------------------------------------------------------------------------

export interface ScannedScript {
  id:                   string
  exam_paper_id:        string
  masked_id:            string

  // Identity — null until BOARD_FINALISED
  student_user_id:      string | null
  student_roll_ref:     string | null

  upload_url:           string | null
  page_count:           number | null

  status:               ScriptStatus
  eval_job_id:          string | null
  objective_auto_score: number | null

  evaluator_id:         string | null
  second_evaluator_id:  string | null

  // Gate 1
  submitted_by:         string | null
  submitted_at:         string | null

  // Gate 2
  finalised_by:         string | null
  finalised_at:         string | null

  // OCR placeholder (null until OCR pipeline is implemented)
  ocr_status:           string | null

  created_at:           string
  updated_at:           string | null
}

export interface ScannedScriptListResponse {
  items:  ScannedScript[]
  total:  number
  offset: number
  limit:  number
}

// ---------------------------------------------------------------------------
// ExamScoreLedger — append-only Board-finalised record
// ---------------------------------------------------------------------------

export interface ExamScoreLedger {
  id:                string
  script_id:         string
  exam_paper_id:     string
  student_user_id:   string | null
  student_roll_ref:  string | null
  total_marks:       number
  max_marks:         number
  finalised_by:      string
  finalisation_note: string | null
  finalised_at:      string
}

export interface ExamScoreLedgerListResponse {
  items:  ExamScoreLedger[]
  total:  number
  offset: number
  limit:  number
}

// ---------------------------------------------------------------------------
// Job status (shared with M08)
// ---------------------------------------------------------------------------

export interface JobStatus {
  job_id: string
  status: string
  result: Record<string, unknown> | null
}

// ---------------------------------------------------------------------------
// Request payload types
// ---------------------------------------------------------------------------

export interface ScriptIngestPayload {
  exam_paper_id:    string
  student_user_id?: string
  student_roll_ref?: string
}

export interface ScriptAssignEvaluatorPayload {
  evaluator_id:         string
  second_evaluator_id?: string
}

export interface EvaluatorMarkUpdate {
  evaluator_marks: number
  evaluator_note?: string
}

/** Keyed by question_id (UUID string) */
export type MarksMap = Record<string, EvaluatorMarkUpdate>

export interface BulkMarkUpdatePayload {
  marks: MarksMap
}

export interface ScriptSubmitMarksPayload {
  marks:             MarksMap
  submission_note?:  string
}

export interface ScriptFinalisePayload {
  finalisation_note?: string
}

// ---------------------------------------------------------------------------
// Response types for compound actions
// ---------------------------------------------------------------------------

export interface ScriptIngestResponse {
  script_id: string
  masked_id: string
  job_id:    string
  status:    string
}

export interface BoardFinaliseResponse {
  script: ScannedScript
  ledger: ExamScoreLedger
}
