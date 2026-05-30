// M09 Paper Administration & Scanning — TypeScript types

export type ScriptStatus =
  | 'PENDING'
  | 'PROCESSING'
  | 'SCORED'
  | 'FAILED'
  | 'REVIEW_REQUIRED'
  | 'MARKS_SUBMITTED'
  | 'BOARD_FINALISED'
  // H-36 pipeline statuses
  | 'QUALITY_CHECKING'
  | 'QUALITY_FAILED'
  | 'OCR_PROCESSING'

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

  // H-36 enrichment fields — visible to evaluator in review panel
  keyword_hits:        KeywordHit[] | null
  rubric_mapping:      RubricItem[] | null
  ai_confidence:       number | null
  page_range:          { start: number; end: number } | null

  // Human marks (written only by evaluator endpoints)
  evaluator_marks:     number | null
  evaluator_note:      string | null

  // Final marks (set at Board finalisation only)
  final_marks:         number | null

  created_at:          string
  updated_at:          string | null
}

export interface KeywordHit {
  keyword:    string
  found:      boolean
  context?:   string
}

export interface RubricItem {
  criterion:  string
  matched:    boolean
  note?:      string
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

// ---------------------------------------------------------------------------
// Evaluator review panel (H-36 STEP-05 backend / STEP-06 frontend)
// ---------------------------------------------------------------------------

export interface EvaluatorReviewResponse {
  script_id:            string
  masked_id:            string
  exam_paper_id:        string
  status:               ScriptStatus
  ocr_text:             string | null
  ocr_status:           string | null
  page_count:           number | null
  page_image_keys:      { page: number; key: string }[] | null
  objective_auto_score: number | null
  evaluations:          ScriptEvaluation[]
}

export interface AcceptSuggestionsPayload {
  question_ids?:  string[]
  evaluator_note?: string
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

// ---------------------------------------------------------------------------
// Paper pipeline stats (H-36 STEP-10)
// ---------------------------------------------------------------------------

export interface PaperPipelineStats {
  paper_id:         string
  total:            number
  pending:          number
  quality_checking: number
  quality_failed:   number
  ocr_processing:   number
  processing:       number
  scored:           number
  failed:           number
  review_required:  number
  marks_submitted:  number
  board_finalised:  number
  completion_pct:   number
}
