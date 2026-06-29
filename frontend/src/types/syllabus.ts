// ---------------------------------------------------------------------------
// Enums
// ---------------------------------------------------------------------------

export type SyllabusStatus =
  | 'DRAFT'
  | 'AI_GENERATING'
  | 'PENDING_REVIEW'
  | 'DEAN_APPROVED'
  | 'DEAN_LOCKED'

export type BloomLevel =
  | 'REMEMBER'
  | 'UNDERSTAND'
  | 'APPLY'
  | 'ANALYSE'
  | 'EVALUATE'
  | 'CREATE'

export type MappingStrength = 'LOW' | 'MEDIUM' | 'HIGH'

export type RefType = 'TEXTBOOK' | 'REFERENCE' | 'JOURNAL' | 'ONLINE'

export type RefSource = 'CROSSREF' | 'OPENLIBRARY' | 'MANUAL'

// ---------------------------------------------------------------------------
// Unit topic (embedded in unit.topics JSONB)
// ---------------------------------------------------------------------------

export interface UnitTopicItem {
  title:          string
  description?:   string
  hours_estimate?: number
}

// ---------------------------------------------------------------------------
// Syllabus
// ---------------------------------------------------------------------------

export interface Syllabus {
  id:                  string
  course_id:           string
  version:             number
  parent_version_id:   string | null
  status:              SyllabusStatus
  custom_instructions: string | null
  change_note:         string | null
  ai_model:            string | null
  prompt_hash:         string | null
  created_by_user_id:  string
  approved_by_user_id: string | null
  approved_at:         string | null
  locked_by_user_id:   string | null
  locked_at:           string | null
  created_at:          string
  updated_at:          string | null
  // Enriched fields returned by list endpoint
  course_title?:  string
  course_code?:   string
  program_name?:  string
  semester?:      number
}

export interface SyllabusDetail extends Syllabus {
  outcomes:   CourseOutcome[]
  units:      SyllabusUnit[]
  references: SyllabusReference[]
}

export interface SyllabusListResponse {
  total:     number
  page:      number
  page_size: number
  items:     Syllabus[]
}

export interface SyllabusStatusResponse {
  id:         string
  version:    number
  status:     SyllabusStatus
  updated_at: string | null
}

export interface SyllabusVersionResponse {
  id:                 string
  version:            number
  parent_version_id:  string | null
  status:             SyllabusStatus
  change_note:        string | null
  created_by_user_id: string
  created_at:         string
}

// ---------------------------------------------------------------------------
// Course outcomes (COs)
// ---------------------------------------------------------------------------

export interface CourseOutcome {
  id:            string
  syllabus_id:   string
  code:          string
  description:   string
  bloom_level:   BloomLevel
  display_order: number
  created_at:    string
  updated_at:    string | null
}

// ---------------------------------------------------------------------------
// CO-PO mappings and matrix
// ---------------------------------------------------------------------------

export interface COPOMapping {
  id:               string
  co_id:            string
  po_id:            string
  mapping_strength: MappingStrength
  justification:    string | null
  created_at:       string
}

export interface COPOMatrixPOHeader {
  po_id:          string
  po_code:        string
  po_description: string
}

export interface COPOMatrixCell {
  po_id:            string
  po_code:          string
  mapping_strength: MappingStrength | null
  justification:    string | null
}

export interface COPOMatrixRow {
  co_id:       string
  co_code:     string
  description: string
  bloom_level: BloomLevel
  cells:       COPOMatrixCell[]
}

export interface COPOMatrixResponse {
  syllabus_id: string
  course_id:   string
  po_headers:  COPOMatrixPOHeader[]
  rows:        COPOMatrixRow[]
}

// ---------------------------------------------------------------------------
// Syllabus units
// ---------------------------------------------------------------------------

export interface SyllabusUnit {
  id:            string
  syllabus_id:   string
  unit_number:   number
  title:         string
  topics:        UnitTopicItem[]
  total_hours:   number
  pedagogy:      string | null
  bloom_summary: Record<string, unknown>[] | null
  created_at:    string
  updated_at:    string | null
}

// ---------------------------------------------------------------------------
// Syllabus references
// ---------------------------------------------------------------------------

export interface SyllabusReference {
  id:           string
  syllabus_id:  string
  title:        string
  authors:      string[]
  year:         number | null
  ref_type:     RefType
  source:       RefSource
  doi:          string | null
  isbn:         string | null
  url:          string | null
  publisher:    string | null
  is_confirmed: boolean
  created_at:   string
  updated_at:   string | null
}

export interface ReferenceCandidate {
  title:     string
  authors:   string[]
  year:      number | null
  ref_type:  RefType
  source:    RefSource
  doi:       string | null
  isbn:      string | null
  url:       string | null
  publisher: string | null
}

// ---------------------------------------------------------------------------
// Compliance
// ---------------------------------------------------------------------------

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
// AI generation + export job responses
// ---------------------------------------------------------------------------

export interface SyllabusAIJobResponse {
  job_id:      string
  syllabus_id: string
  status:      string
}

export interface SyllabusExportJobResponse {
  job_id:      string
  syllabus_id: string
  format:      string
  status:      string
}

export interface JobStatusResponse {
  id:         string
  status:     string
  result:     Record<string, unknown> | null
  error:      string | null
  created_at: string
  updated_at: string | null
}

// ---------------------------------------------------------------------------
// Request payloads
// ---------------------------------------------------------------------------

export interface SyllabusCreate {
  course_id:            string
  custom_instructions?: string
}

export interface SyllabusUpdate {
  custom_instructions?: string
}

export interface SyllabusListFilters {
  course_id?: string
  status?:    SyllabusStatus
  page?:      number
  page_size?: number
}

export interface CourseOutcomeCreate {
  code:           string
  description:    string
  bloom_level:    BloomLevel
  display_order?: number
}

export interface CourseOutcomeUpdate {
  description?:   string
  bloom_level?:   BloomLevel
  display_order?: number
}

export interface COPOMappingCreate {
  po_id:             string
  mapping_strength?: MappingStrength
  justification?:    string
}

export interface COPOMappingBulkUpdate {
  mappings: COPOMappingCreate[]
}

export interface SyllabusUnitCreate {
  unit_number:  number
  title:        string
  topics?:      UnitTopicItem[]
  total_hours:  number
  pedagogy?:    string
}

export interface SyllabusUnitUpdate {
  title?:       string
  topics?:      UnitTopicItem[]
  total_hours?: number
  pedagogy?:    string
}

export interface SyllabusUnitReorder {
  order: [string, number][]  // [unit_id, new_unit_number]
}

export interface SyllabusReferenceCreate {
  title:        string
  authors?:     string[]
  year?:        number
  ref_type?:    RefType
  source?:      RefSource
  doi?:         string
  isbn?:        string
  url?:         string
  publisher?:   string
  is_confirmed?: boolean
}

export interface SyllabusReferenceUpdate {
  title?:       string
  authors?:     string[]
  year?:        number
  ref_type?:    RefType
  doi?:         string
  isbn?:        string
  url?:         string
  publisher?:   string
  is_confirmed?: boolean
}

export interface ReferenceSearchRequest {
  query:     string
  ref_type?: RefType
  limit?:    number
}

export interface GenerateSyllabusRequest {
  custom_instructions?: string
}

export interface ApproveRequest {
  comment?: string
}

export interface RejectRequest {
  reason: string
}

export interface ForkRequest {
  change_note?: string
}

export interface LockRequest {
  comment?: string
}

export interface ExportSyllabusRequest {
  format: 'pdf' | 'docx' | 'json'
}
