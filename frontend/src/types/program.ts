// ---------------------------------------------------------------------------
// Enums
// ---------------------------------------------------------------------------

/** Curriculum lifecycle (Phase A — Academic Governance).
 *
 *  Ownership changes hands exactly twice, and never comes back.
 *
 *  DRAFT / GENERATION_FAILED  the DEAN owns it and edits freely
 *  PENDING_APPROVAL           the BOARD owns it — permanently. Submitting is a
 *                             one-way handover: the Board enhances the curriculum
 *                             itself rather than returning it, writes the official
 *                             syllabus, and approves.
 *  APPROVED                   locked. Nobody edits — not the Dean, not the Board,
 *                             not an Admin.
 *  PUBLISHED                  released to Faculty and Students. Still locked.
 *
 *  There is no RETURNED and no REJECTED. The only way past an approval is a new
 *  curriculum version.
 */
export type ProgramStatus =
  | 'DRAFT'
  | 'AI_GENERATING'
  | 'GENERATION_FAILED'
  | 'PENDING_APPROVAL'
  | 'APPROVED'
  | 'PUBLISHED'

/**
 * What KIND of course this is — and therefore what official document the Board
 * produces for it.
 *
 *   THEORY         a full university syllabus: Unit I-V, objectives, outcomes, books
 *   LAB            a Lab Manual: experiment list, equipment, assessment guidelines.
 *                  NO theory units — a laboratory is not taught in five units
 *   INTERNSHIP     no syllabus. Guidelines, duration, rubric, weekly activities,
 *                  company requirements, report format, viva
 *   MINI_PROJECT   no syllabus. Guidelines, milestones, deliverables, reviews, rubrics
 *   MAJOR_PROJECT  no syllabus. A handbook: proposal, timeline, reviews, rubrics,
 *                  final report format, demonstration, viva
 *   SEMINAR        no syllabus. Seminar guidelines
 *
 * MINI_PROJECT and MAJOR_PROJECT were a single PROJECT value before Phase A V2.3.
 * They are different documents — a mini project is milestones inside one semester,
 * a major project carries a proposal, a demonstration and a viva — so one value
 * could not drive both.
 */
export type CourseType =
  | 'THEORY'
  | 'LAB'
  | 'INTERNSHIP'
  | 'MINI_PROJECT'
  | 'MAJOR_PROJECT'
  | 'SEMINAR'

/**
 * A standard semester. Contact hours are (L + T + P) × this — the total taught hours
 * across the semester, which is what a university syllabus prints, not the weekly load.
 *
 * Mirrors WEEKS_PER_SEMESTER in m02/formatting.py. The server is the source of truth and
 * sends contact hours on the syllabus header; this exists only for the one screen that
 * has a course but no syllabus yet, and therefore nothing to read them from.
 */
export const WEEKS_PER_SEMESTER = 15

/** The types whose official document is NOT a syllabus — no units, ever. */
export const NON_SYLLABUS_TYPES: readonly CourseType[] = [
  'INTERNSHIP',
  'MINI_PROJECT',
  'MAJOR_PROJECT',
  'SEMINAR',
]

/**
 * WHO OWNS WHAT. Mirrors the backend rule (m01/models.py) — and the backend is what
 * enforces it; this only decides what the interface offers.
 *
 * The Board of Studies is an academic body. It owns the TAUGHT curriculum: theory
 * subjects, laboratories, and the elective options a student chooses between. It
 * writes their syllabi, approves them, and locks them.
 *
 * An internship, a mini project, a major project and a seminar are not taught. What
 * those documents contain depends on the host company, the supervisor and the review
 * calendar — none of which a Board can know. They belong to the DEAN, entirely: he
 * creates them, drafts them, approves them and publishes them. The Board decides only
 * THAT the curriculum has an internship, never what the internship is.
 */
export const EXECUTION_TYPES: readonly CourseType[] = NON_SYLLABUS_TYPES

/** A Dean-owned execution document. The Board never touches one. */
export function isExecutionDocument(courseType: CourseType | null | undefined): boolean {
  return EXECUTION_TYPES.includes((courseType ?? 'THEORY') as CourseType)
}

/** A subject the Board teaches, examines, and owns the syllabus of. */
export function isTeachingSubject(courseType: CourseType | null | undefined): boolean {
  return !isExecutionDocument(courseType)
}

/** What the Board actually produces for each type — used wherever the UI would
 *  otherwise say "Syllabus" for a document that is not one. */
export const COURSE_TYPE_DOCUMENT: Record<CourseType, string> = {
  THEORY:        'Syllabus',
  LAB:           'Lab Manual',
  INTERNSHIP:    'Internship Guidelines',
  MINI_PROJECT:  'Mini Project Guidelines',
  MAJOR_PROJECT: 'Major Project Handbook',
  SEMINAR:       'Seminar Guidelines',
}

export const COURSE_TYPE_LABEL: Record<CourseType, string> = {
  THEORY:        'Theory',
  LAB:           'Laboratory',
  INTERNSHIP:    'Internship',
  MINI_PROJECT:  'Mini Project',
  MAJOR_PROJECT: 'Major Project',
  SEMINAR:       'Seminar',
}

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
  submitted_by_user_id: string | null
  submitted_at: string | null
  approved_by_user_id: string | null
  approved_at: string | null
  /** Set when governance approved it. Approval — not publication — is the lock. */
  locked_by_user_id: string | null
  locked_at: string | null
  /** The governance authority's note recorded against the approval. */
  review_comment: string | null
  published_by_user_id: string | null
  published_at: string | null
  /**
   * Stamped automatically by the first syllabus generation — the structure the
   * official syllabus was written against. NOT a freeze: the Board may keep
   * revising the structure right up to approval.
   */
  structure_finalized_at: string | null
  /**
   * A published curriculum version is identified by
   * (programme, academic year, batch, version) — "MCA, 2026-2028, v1". Students
   * stay on the version they were admitted under, forever.
   */
  academic_year: string | null
  /** e.g. 2026 → the "R2026" regulation/scheme this version belongs to. */
  regulation_year: number | null
  /** First batch governed by this version. Older batches stay on their own. */
  effective_from_batch_id: string | null
  ai_model: string | null
  prompt_hash: string | null
  ai_instructions: string | null
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
  ai_instructions?: string
  /** '2026-2028' — which years this curriculum version governs. */
  academic_year?: string
  regulation_year?: number
  effective_from_batch_id?: string
}

export interface ProgramUpdate {
  title?: string
  degree_type?: string
  department?: string
  duration_years?: number
  total_credits?: number
  acad_program_id?: string
  ai_instructions?: string
  /** '2026-2028' — which years this curriculum version governs. */
  academic_year?: string
  regulation_year?: number
  effective_from_batch_id?: string
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
  course_type: CourseType | null
  is_elective: boolean
  elective_basket_id: string | null
  is_ai_generated: boolean
  hours_lecture: number | null
  hours_tutorial: number | null
  hours_practical: number | null
  description: string | null
  created_at: string
  updated_at: string | null
}

/** A course plus the program that owns it. A course already determines its
 *  semester and its program, so callers that identify work by course select the
 *  course and read the program off the result. */
export interface CourseWithProgram extends Course {
  program_title: string
  program_department: string | null
}

export interface CourseCreate {
  /** Server-assigned — {PROGRAMME}{semester}{NN}. Ignored if sent. */
  code?: string
  title: string
  credits: number
  semester: number
  course_type?: CourseType
  is_elective?: boolean
  elective_basket_id?: string
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
  course_type?: CourseType
  is_elective?: boolean
  elective_basket_id?: string
  hours_lecture?: number
  hours_tutorial?: number
  hours_practical?: number
  description?: string
}

// ---------------------------------------------------------------------------
// Elective Basket — ONE curriculum elective slot (e.g. "Elective 1", 3 credits,
// Semester 3) holding any number of interchangeable option courses (AI301,
// DM301, DL301, ...). The slot owns the credits: a student takes exactly one
// option, so the curriculum counts the slot once, never the sum of its options.
// ---------------------------------------------------------------------------

export interface ElectiveBasketCourse {
  id: string
  code: string
  title: string
  credits: number
  semester: number
  course_type: CourseType | null
}

/** A slot's own lifecycle, independent of its program's.
 *
 *  DRAFT     the Dean may add, edit and remove the slot's choices
 *  PUBLISHED the choice list is frozen; students can see the slot
 *  OPEN      students may choose (or switch) their one option
 *  CLOSED    choices are frozen and the roster is final
 *
 *  This is why a Dean can still fill in what Elective 1 offers this year on a
 *  curriculum published long ago. */
export type ElectiveSlotStatus = 'DRAFT' | 'PUBLISHED' | 'OPEN' | 'CLOSED'

export interface ElectiveBasket {
  id: string
  program_id: string
  semester: number
  name: string
  /** The slot's curriculum weight, independent of how many options it holds. */
  credits: number
  description: string | null
  status: ElectiveSlotStatus
  published_at: string | null
  registration_opened_at: string | null
  registration_closed_at: string | null
  created_at: string
  updated_at: string | null
  courses: ElectiveBasketCourse[]
}

export interface ElectiveBasketCreate {
  semester: number
  name: string
  credits?: number
  description?: string
}

export interface ElectiveBasketUpdate {
  name?: string
  credits?: number
  description?: string
}

/** One interchangeable choice inside a slot. No `code`: the server generates it
 *  (MCA306, MCA307, ...). No `semester`: a choice sits in its slot's semester. */
export interface ElectiveChoiceCreate {
  title: string
  credits?: number
  course_type?: CourseType
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
  severity: 'ERROR' | 'WARNING' | 'INFO'
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
  ai_instructions?: string
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

export interface PublishRequest {
  comment?: string
}

export interface RejectRequest {
  reason?: string
}
