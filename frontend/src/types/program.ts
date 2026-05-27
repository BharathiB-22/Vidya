// ---------------------------------------------------------------------------
// Enums
// ---------------------------------------------------------------------------

export type ProgramStatus =
  | 'DRAFT'
  | 'AI_GENERATING'
  | 'GENERATION_FAILED'
  | 'PENDING_APPROVAL'
  | 'APPROVED'

// ---------------------------------------------------------------------------
// Program
// ---------------------------------------------------------------------------

export interface Program {
  id: string
  title: string
  degree_type: string
  department: string
  duration_years: number
  total_credits: number
  status: ProgramStatus
  acad_program_id: string | null
  version: number
  parent_version_id: string | null
  created_by_user_id: string
  created_at: string
  updated_at: string | null
  approved_by_user_id: string | null
  approved_at: string | null
  ai_model: string | null
  prompt_hash: string | null
}

/** GET /programs/{id} — same scalar fields, relationships loaded server-side */
export type ProgramDetail = Program

export interface ProgramListResponse {
  total: number
  page: number
  page_size: number
  items: Program[]
}

export interface ProgramStatusResponse {
  id: string
  status: ProgramStatus
  version: number
}

export interface ProgramVersionResponse {
  id: string
  version: number
  status: ProgramStatus
  created_at: string
  parent_version_id: string | null
}

// ---------------------------------------------------------------------------
// Program payloads
// ---------------------------------------------------------------------------

export interface ProgramCreate {
  title: string
  degree_type: string
  department: string
  duration_years: number
  total_credits: number
  acad_program_id?: string
}

export interface ProgramUpdate {
  title?: string
  degree_type?: string
  department?: string
  duration_years?: number
  total_credits?: number
  acad_program_id?: string
}

export interface ProgramListFilters {
  status?: ProgramStatus
  page?: number
  page_size?: number
}

// ---------------------------------------------------------------------------
// Program Outcome
// ---------------------------------------------------------------------------

export interface ProgramOutcome {
  id: string
  program_id: string
  code: string
  description: string
  bloom_level: string | null
  display_order: number
  created_at: string
}

export interface ProgramOutcomeCreate {
  code: string
  description: string
  bloom_level?: string
  display_order?: number
}

export interface ProgramOutcomeUpdate {
  description?: string
  bloom_level?: string
  display_order?: number
}

// ---------------------------------------------------------------------------
// Course
// ---------------------------------------------------------------------------

export interface Course {
  id: string
  program_id: string
  code: string
  title: string
  credits: number
  semester: number
  is_elective: boolean
  is_ai_generated: boolean
  hours_lecture: number | null
  hours_tutorial: number | null
  hours_practical: number | null
  description: string | null
  created_at: string
  updated_at: string | null
}

export interface CourseCreate {
  code: string
  title: string
  credits: number
  semester: number
  is_elective?: boolean
  hours_lecture?: number
  hours_tutorial?: number
  hours_practical?: number
  description?: string
  prerequisite_course_ids?: string[]
}

export interface CourseUpdate {
  code?: string
  title?: string
  credits?: number
  semester?: number
  is_elective?: boolean
  hours_lecture?: number
  hours_tutorial?: number
  hours_practical?: number
  description?: string
}

export interface CoursePrerequisite {
  id: string
  course_id: string
  prerequisite_course_id: string
}

// ---------------------------------------------------------------------------
// Compliance
// ---------------------------------------------------------------------------

export interface ComplianceViolation {
  rule_id: string
  rule_ref: string
  message: string
  severity: 'ERROR' | 'WARNING'
}

export interface ComplianceResult {
  passed: boolean
  violations: ComplianceViolation[]
}

// ---------------------------------------------------------------------------
// AI generation + export job responses
// ---------------------------------------------------------------------------

export interface ProgramAIJobResponse {
  job_id: string
  program_id: string
  status: string
  message: string
}

export interface GenerateProgramRequest {
  prompt_hint?: string
}

export interface ProgramExportJobResponse {
  job_id: string
  program_id: string
  format: string
  message: string
}

export interface ExportProgramRequest {
  format: 'pdf' | 'docx'
}

export interface JobStatusResponse {
  id: string
  status: string
  result: Record<string, unknown> | null
  error: string | null
  created_at: string
  updated_at: string | null
}

// ---------------------------------------------------------------------------
// Approval / rejection
// ---------------------------------------------------------------------------

export interface ApproveRequest {
  comment?: string
}

export interface RejectRequest {
  reason?: string
}
