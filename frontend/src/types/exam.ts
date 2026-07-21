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

/** The STORED question vocabulary (exam_questions.question_type). The builder's
 *  richer vocabulary maps onto it — see `storedQuestionType` in lib/paperTemplate.
 *  CASE_STUDY and PROGRAMMING arrived with P1.19; the column is a plain VARCHAR,
 *  so they needed no migration. */
export type QuestionType =
  | 'MCQ'
  | 'SHORT_ANSWER'
  | 'LONG_ANSWER'
  | 'PROBLEM_SOLVING'
  | 'CASE_STUDY'
  | 'PROGRAMMING'

/** Requested per question definition and honoured by the generator. */
export type Difficulty = 'EASY' | 'MEDIUM' | 'HARD'

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

// Per-unit paper blueprint (university exam patterns).
export type ChoicePattern = 'COMPULSORY' | 'ANSWER_ANY' | 'OR_CHOICE'

export interface BlueprintRow {
  category?:       string | null   // optional group label
  count:           number          // questions to GENERATE
  marks:           number          // marks per question
  answer_count:    number          // questions the student must answer
  choice_pattern:  ChoicePattern
  // Identity of the template block this row was compiled from. Generation stamps
  // it onto every question the row produces so the paper reconstructs exactly.
  template_block_id?: string | null
  subpart_index?:     number | null  // sub-part within a FULL_QUESTION block
  block_order?:       number | null  // the block's position in the printed paper
}

export interface UnitBlueprint {
  unit_number: number
  rows:        BlueprintRow[]
}

// Paper Template — the source of truth for structure & PDF layout. The blueprint
// above is the internal generation model compiled from this.

/** The stored template document — a paper's structure, and its source of truth.
 *  Kept loosely typed here so the shape lives in one place (lib/paperTemplate,
 *  which mirrors the backend compiler); read it through `normaliseDefinition`,
 *  which also upgrades documents written before the current version.
 *
 *  v3 is `sections` alone. There are no template "types": every university
 *  pattern is expressed by choosing sections, answer rules and question
 *  definitions. The legacy fields below are still READ off stored documents so
 *  sealed papers keep printing what they printed — nothing writes them. */
export interface PaperTemplateDefinition {
  version?:  number
  sections?: unknown[]        // PaperSection[] — see lib/paperTemplate
  // ── legacy, read-only (v1/v2) — upgraded in memory by normaliseDefinition ──
  type?:     string | null
  blocks?:   unknown[]
  groups?:   unknown[]
  units?:    UnitBlueprint[]
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
  question_format:      QuestionFormatConfig | null
  blueprint:            UnitBlueprint[] | null
  /** Legacy. v1/v2 papers recorded which builder made them; v3 has no types. */
  template_type:        string | null
  template_definition:  PaperTemplateDefinition | null
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
  /** The PRIMARY unit. */
  unit_number:    number
  /** Every unit the question draws on — a definition may INTEGRATE a pool of
   *  them into one question. Null on legacy rows, which cover unit_number alone. */
  unit_numbers:   number[] | null
  difficulty:     Difficulty | null
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
  display_order:  number
  // The template block this question belongs to. Null only on papers generated
  // before P1.17, which reconstruct by (unit, marks) inference instead.
  template_block_id:      string | null
  template_subpart_index: number | null
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
  creation_mode?:       'AI' | 'MANUAL'
  exam_type:            ExamType
  exam_workflow?:       ExamWorkflow
  total_marks:          number
  duration_mins:        number
  units_included:       number[]
  question_format?:     QuestionFormatConfig
  blueprint?:           UnitBlueprint[]
  template_definition?: PaperTemplateDefinition
  requested_dist:       BloomsDistribution
  section_config?:      SectionConfig[]
  special_instructions?: string
}

export interface ManualQuestionPayload {
  question_text:   string
  question_type:   QuestionType
  marks:           number
  bloom_level:     BloomLevel
  unit_number:     number
  co_code?:        string | null
  co_ids?:         string[]
  section_label?:  string | null
  model_answer?:   string | null
  /** Required by the API when the paper has a template: the block the question
   *  prints inside. A question with no block has nowhere to go. */
  template_block_id?:      string | null
  template_subpart_index?: number | null
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
  unit_number?:    number
  co_code?:        string | null
  section_label?:  string | null
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
