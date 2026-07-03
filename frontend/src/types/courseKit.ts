// ---------------------------------------------------------------------------
// Enums — exact values from backend models.py
// ---------------------------------------------------------------------------

export type CourseKitStatus =
  | 'DRAFT'
  | 'AI_GENERATING'
  | 'PUBLISHED'
  | 'ARCHIVED'

export type ComplexityLevel = 'UG' | 'PG'

export type AssignmentType = 'CLASSWORK' | 'HOMEWORK' | 'CASE_STUDY'

export type BloomLevel =
  | 'REMEMBER'
  | 'UNDERSTAND'
  | 'APPLY'
  | 'ANALYSE'
  | 'EVALUATE'
  | 'CREATE'

// ---------------------------------------------------------------------------
// JSONB sub-models
// ---------------------------------------------------------------------------

export type SlideType =
  | 'TITLE' | 'CONCEPT' | 'DEFINITION' | 'EXAMPLE'
  | 'CODE' | 'DIAGRAM' | 'ACTIVITY' | 'SUMMARY' | 'QUIZ'

export interface SlideContent {
  slide_type?:         SlideType | null
  bullets:             string[]
  key_concepts:        string[]
  definitions:         string[]
  examples:            string[]
  code_snippet:        string | null
  diagram_prompt:      string | null
  image_hint:          string | null    // backward-compat alias
  classroom_activity:  string | null
  student_summary:     string | null
  teaching_notes:      string | null    // faculty-only
}

export interface RubricCriterion {
  criterion:   string
  description: string
  max_marks:   number
}

export interface TeachingPlanWeek {
  week:          number
  topic:         string
  objectives:    string[]
  activities:    string[]
  hours:         number
  co_references: string[]
}

export interface LessonPlanSession {
  session:          number
  week:             number
  duration_minutes: number
  topic:            string
  objectives:       string[]
  opening_activity: string | null
  main_content:     string
  closing_activity: string | null
  materials_needed: string[]
  bloom_levels:     string[]
  co_references:    string[]
}

export interface ResourceItem {
  title:         string
  resource_type: string
  url:           string | null
  description:   string | null
}

// ---------------------------------------------------------------------------
// Response interfaces
// ---------------------------------------------------------------------------

export interface KitSlide {
  id:            string
  kit_id:        string
  slide_number:  number
  title:         string
  content:       Record<string, unknown>
  speaker_notes: string | null   // null when DEAN role — gated at router
  bloom_level:   BloomLevel | null
  co_reference:  string | null
  created_at:    string
  updated_at:    string | null
}

export interface KitAssignment {
  id:                    string
  kit_id:                string
  assignment_number:     number
  title:                 string
  assignment_type:       AssignmentType
  question_text:         string
  complexity_level:      ComplexityLevel
  current_events_toggle: boolean
  model_answer:          string | null   // null when DEAN role — gated at router
  rubric:                Record<string, unknown>[]
  bloom_level:           BloomLevel | null
  co_reference:          string | null
  created_at:            string
  updated_at:            string | null
}

export interface CourseKit {
  id:                   string
  syllabus_id:          string
  unit_number:          number
  version:              number
  parent_version_id:    string | null
  status:               CourseKitStatus
  complexity_level:     ComplexityLevel
  tone:                 string | null
  custom_instructions:  string | null
  ai_model:             string | null
  created_by_user_id:   string
  published_by_user_id: string | null
  published_at:         string | null
  created_at:           string
  updated_at:           string | null

  course_title?: string | null
  course_code?:  string | null
  program_name?: string | null
  semester?:     number | null
}

export interface CourseKitDetail extends CourseKit {
  teaching_plan: Record<string, unknown>[]
  lesson_plans:  Record<string, unknown>[]
  resources:     Record<string, unknown>[]
  slides:        KitSlide[]
  assignments:   KitAssignment[]
}

export interface CourseKitListResponse {
  total:     number
  page:      number
  page_size: number
  items:     CourseKit[]
}

export interface CourseKitStatusResponse {
  id:         string
  version:    number
  status:     CourseKitStatus
  updated_at: string | null
}

export interface CourseKitVersionResponse {
  id:                 string
  version:            number
  parent_version_id:  string | null
  status:             CourseKitStatus
  created_by_user_id: string
  published_at:       string | null
  created_at:         string
}

export interface KitAIJobResponse {
  job_id: string
  kit_id: string
  status: string
}

export interface KitJobStatusResponse {
  id:         string
  status:     string
  result:     Record<string, unknown> | null
  error:      string | null
  created_at: string
  updated_at: string | null
}

export interface KitExportJobResponse {
  job_id: string
  kit_id: string
  format: string
  status: string
}

export interface KitExportAsset {
  id:                string
  original_filename: string
  content_type:      string
  size_bytes:        number
  created_at:        string
}

export interface KitExportDownloadResponse {
  download_url:      string
  original_filename: string
  size_bytes:        number
  expires_in:        number
}

export interface ComplianceViolation {
  code:     string
  message:  string
  severity: 'ERROR' | 'WARNING'
}

export interface ComplianceCheckResponse {
  passed:     boolean
  violations: ComplianceViolation[]
}

// ---------------------------------------------------------------------------
// Request payloads
// ---------------------------------------------------------------------------

export interface CourseKitCreate {
  syllabus_id:          string
  unit_number:          number
  complexity_level?:    ComplexityLevel
  tone?:                string
  custom_instructions?: string
}

export interface CourseKitUpdate {
  complexity_level?:    ComplexityLevel
  tone?:                string
  custom_instructions?: string
}

export interface CourseKitListFilters {
  syllabus_id?: string
  status?:      CourseKitStatus
  page?:        number
  page_size?:   number
}

export interface KitSlideCreate {
  slide_number:  number
  title:         string
  content?:      SlideContent
  speaker_notes?: string
  bloom_level?:  BloomLevel
  co_reference?: string
}

export interface KitSlideUpdate {
  title?:         string
  content?:       SlideContent
  speaker_notes?: string
  bloom_level?:   BloomLevel
  co_reference?:  string
}

export interface KitSlideReorder {
  order: [string, number][]
}

export interface KitAssignmentCreate {
  assignment_number:      number
  title:                  string
  assignment_type?:       AssignmentType
  question_text:          string
  complexity_level?:      ComplexityLevel
  current_events_toggle?: boolean
  model_answer?:          string
  rubric?:                RubricCriterion[]
  bloom_level?:           BloomLevel
  co_reference?:          string
}

export interface KitAssignmentUpdate {
  title?:                 string
  assignment_type?:       AssignmentType
  question_text?:         string
  complexity_level?:      ComplexityLevel
  current_events_toggle?: boolean
  model_answer?:          string
  rubric?:                RubricCriterion[]
  bloom_level?:           BloomLevel
  co_reference?:          string
}

export interface GenerateKitRequest {
  custom_instructions?: string
  complexity_level?:    ComplexityLevel
  tone?:                string
}

export interface PublishRequest {
  comment?: string
}

export interface ArchiveRequest {
  reason?: string
}

export interface ForkRequest {
  change_note?: string
}

export interface KitExportRequest {
  format: 'pdf' | 'pptx' | 'handout'
}

// ---------------------------------------------------------------------------
// Faculty-uploaded resources (PDF/PPT/DOCX/notes) — backed by the generic
// storage module (StorageAsset), scoped to this kit via entity_type/entity_id.
// ---------------------------------------------------------------------------

export interface KitResourceFile {
  id:                  string
  uploaded_by_user_id: string
  entity_type:         string
  entity_id:           string
  object_key:          string
  original_filename:   string
  size_bytes:          number
  content_type:        string
  created_at:          string
  expires_at:          string | null
  deleted_at:          string | null
}

export interface KitResourceListResponse {
  total:     number
  page:      number
  page_size: number
  items:     KitResourceFile[]
}

export interface KitResourceUploadUrlRequest {
  original_filename: string
  content_type:      string
  size_bytes:        number
}

export interface KitResourceUploadUrlResponse {
  object_key:         string
  presigned_url:      string
  expires_in_seconds: number
}

export interface KitResourceConfirmRequest {
  object_key:        string
  original_filename: string
  content_type:      string
  size_bytes:        number
}

export interface KitResourceDownloadUrlResponse {
  presigned_url:      string
  expires_in_seconds: number
}
