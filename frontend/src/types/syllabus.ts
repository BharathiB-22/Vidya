import { COURSE_TYPE_DOCUMENT, type CourseType } from '@/types/program'

// ---------------------------------------------------------------------------
// Enums
// ---------------------------------------------------------------------------

/**
 * The official syllabus belongs to the Board, which writes it AND approves it.
 * There is therefore no submit/review handoff and no pending or rejected state —
 * those only made sense when Faculty authored syllabi for a Dean to review.
 *
 *   DRAFT          the Board is working on it
 *   AI_GENERATING  a generation job is in flight
 *   APPROVED       a board member has signed this syllabus off
 *   LOCKED         frozen with the curriculum at approval — nobody edits, ever
 */
export type SyllabusStatus =
  | 'DRAFT'
  | 'AI_GENERATING'
  | 'APPROVED'
  | 'LOCKED'

/**
 * The header block of an official university syllabus. Every field is DERIVED on
 * the server from the course row — none is stored on the syllabus, and none is
 * typed in by anyone.
 */
export interface CourseInformation {
  course_code:     string
  course_name:     string
  credits:         number
  ltp:             string    // "3-1-2"
  contact_hours:   number    // Total Teaching Hours — the Board's figure
  hours_per_week:  number    // No. of Hours / Week — the Board's figure
  category:        string    // Core | Elective | Lab | Project
  course_type:     CourseType
  semester:        number
  /** "Regulation 2026" — a property of the curriculum, not of one subject. */
  regulation_year: number | null
}

export type BloomLevel =
  | 'REMEMBER'
  | 'UNDERSTAND'
  | 'APPLY'
  | 'ANALYSE'
  | 'EVALUATE'
  | 'CREATE'

export type MappingStrength = 'LOW' | 'MEDIUM' | 'HIGH'

/**
 * A reference's type, and the bibliography section it prints under. An official
 * syllabus ends with four sections; these six types fold into them:
 *
 *   Text Books        <- TEXTBOOK
 *   Reference Books   <- REFERENCE, JOURNAL
 *   Suggested Reading <- SUGGESTED_READING
 *   Web Resources     <- WEB_RESOURCE, ONLINE
 */
export type RefType =
  | 'TEXTBOOK'
  | 'REFERENCE'
  | 'JOURNAL'
  | 'ONLINE'
  | 'SUGGESTED_READING'
  | 'WEB_RESOURCE'

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

// ---------------------------------------------------------------------------
// The type-specific official document
//
// A Board of Studies does not write a syllabus for an internship. It writes
// guidelines. A laboratory gets a lab manual and an experiment list, not five units
// of lectures it never delivers. THEORY is the only type whose document is units +
// outcomes + references; every other type stores its body in `Syllabus.document`,
// shaped by the interface below that matches its `doc_type`.
// ---------------------------------------------------------------------------

/** One entry of a lab manual's experiment list. */
export interface Experiment {
  number:     number
  title:      string
  aim?:       string | null
  procedure?: string | null
  apparatus?: string[]
  hours?:     number | null
}

/** One row of an evaluation rubric: what is judged, and what it is worth. */
export interface RubricRow {
  criterion:   string
  weightage?:  number | null    // percent
  descriptor?: string | null
}

export interface LabDocument {
  manual_intro?:          string | null
  experiments?:           Experiment[]
  equipment?:             string[]
  software?:              string[]
  assessment_guidelines?: string[]
}

export interface InternshipDocument {
  guidelines?:           string[]
  duration?:             string | null
  credits?:              number | null
  evaluation_rubric?:    RubricRow[]
  weekly_activities?:    string[]
  company_requirements?: string[]
  report_format?:        string[]
  viva_guidelines?:      string[]
}

export interface MiniProjectDocument {
  guidelines?:   string[]
  milestones?:   string[]
  deliverables?: string[]
  reviews?:      string[]
  rubrics?:      RubricRow[]
}

export interface MajorProjectDocument {
  handbook?:            string[]
  proposal_format?:     string[]
  timeline?:            string[]
  reviews?:             string[]
  rubrics?:             RubricRow[]
  final_report_format?: string[]
  demonstration?:       string[]
  viva?:                string[]
}

export interface SeminarDocument {
  guidelines?:          string[]
  topic_selection?:     string[]
  presentation_format?: string[]
  evaluation_rubric?:   RubricRow[]
  deliverables?:        string[]
}

/** The body of a non-theory document. Empty ({}) for THEORY, whose document IS
 *  its units, outcomes and references. */
export type CourseDocument =
  | LabDocument
  | InternshipDocument
  | MiniProjectDocument
  | MajorProjectDocument
  | SeminarDocument
  | Record<string, never>

export interface Syllabus {
  id:                  string
  course_id:           string
  version:             number
  parent_version_id:   string | null
  status:              SyllabusStatus
  /**
   * WHICH official document this row is. A snapshot of the course's type taken at
   * generation time — NOT a read-through to the course's current type. If a Dean
   * reclassifies a course from LAB to THEORY after the Board approved its lab
   * manual, that approved document is still a lab manual.
   */
  doc_type:            CourseType
  /** The type-specific body. Empty for THEORY. */
  document:            CourseDocument
  /**
   * How many units this theory syllabus is taught in — 4 or 5. The Board's decision,
   * taken before generation: five is not a universal format, and a Board that wanted
   * four used to generate five and delete one, which left the hours to redistribute
   * by hand. Meaningless for a type that has no units.
   */
  unit_count:          number
  /**
   * The hours the Board allocated to each unit before generation — [10, 8, 12, 10].
   * The PLAN the units were written to; the authoritative hours are the ones on the
   * units themselves, which the Board edits freely afterwards. Empty when the Board
   * let the AI pace the units against the course's contact hours.
   */
  unit_hours:          number[]
  /**
   * The header's two figures — "Total Teaching Hours: 52 / No. of Hours per Week: 04".
   * null means the Board has not stated them and the L-T-P is used as a fallback;
   * `course_information` always carries the figures actually in force, so read THAT to
   * display them and these two only to seed a form.
   */
  teaching_hours:      number | null
  hours_per_week:      number | null
  custom_instructions: string | null
  change_note:         string | null
  board_comment:       string | null
  /** Course Objectives — what the course sets out to impart. */
  objectives:          string[]
  /** Practical Components — empty unless the course carries practical hours. */
  practical_components: string[]
  /** Internal Assessment suggestions — CIE pattern, components, weightings. */
  internal_assessment: string[]
  ai_model:            string | null
  prompt_hash:         string | null
  created_by_user_id:  string
  approved_by_user_id: string | null
  approved_at:         string | null
  locked_by_user_id:   string | null
  locked_at:           string | null
  /** Set when the Dean adapted an APPROVED guideline document. Never set on a
   *  theory syllabus — the Dean cannot edit one. */
  dean_edited_at:      string | null
  dean_edited_by_user_id: string | null
  created_at:          string
  updated_at:          string | null
  /** The official Course Information header, derived server-side from the course. */
  course_information?: CourseInformation
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
  /**
   * The unit's official prose block — the text that PRINTS in the regulation:
   *
   *   "Introduction to Computer Systems, Evolution of Computing, Von Neumann
   *    Architecture, Instruction Cycle, Processor Organization, ..."
   *
   * A flowing sequence of concepts in teaching order, not a bullet list. May be
   * null on syllabi generated before this existed — the document view composes a
   * fallback from `topics` in that case.
   */
  content:       string | null
  /** The structured breakdown underneath the prose. Not printed; read by the
   *  course-kit generator to plan lessons. */
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

/**
 * Every prose section of the official syllabus is editable by the Board.
 *
 * Nothing the AI produced is final. It writes the first draft; the Board rewrites
 * whatever it likes and then approves — and only the approved version is ever
 * published.
 */
export interface SyllabusUpdate {
  custom_instructions?:  string
  objectives?:           string[]
  practical_components?: string[]
  internal_assessment?:  string[]
  board_comment?:        string
  /**
   * THE ACADEMIC STRUCTURE — the Board's, saved before any AI runs.
   *
   * How many units the subject is taught in (4 or 5), and the teaching hours of each.
   * They record the Board's decision; they do not restructure units that already
   * exist — the next generation writes to them.
   *
   * A theory syllabus cannot be generated without them. The system does not derive
   * them from the contact hours, and the model never chooses them: how a subject is
   * divided, and how long each part is taught, is an academic judgement.
   */
  unit_count?:           number
  unit_hours?:           number[]
  /**
   * What the subject is taught for, and at how many hours a week. The Board's, and
   * nothing derives them. Saving them does NOT require the unit hours to add up yet —
   * that is enforced at generation and at approval, not mid-edit.
   */
  teaching_hours?:       number
  hours_per_week?:       number
  /**
   * The type-specific document body — the lab manual, the internship guidelines,
   * the project handbook. Validated server-side against the row's OWN doc_type, so
   * a client cannot turn one document into another by posting a different shape.
   *
   * Rejected with 422 on a theory syllabus: that document IS its units.
   */
  document?:             CourseDocument
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
  /** The unit's official prose block — what prints in the regulation. */
  content?:     string
  topics?:      UnitTopicItem[]
  total_hours:  number
  pedagogy?:    string
}

/** The Board rewrites units freely. Splitting a unit is add + edit; merging is
 *  edit + delete. */
export interface SyllabusUnitUpdate {
  title?:       string
  content?:     string
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

/**
 * Which slice of an existing document to rewrite.
 *
 * The Board should never have to regenerate a whole syllabus because ONE unit came
 * out weak — by then the other four and the outcomes will often have been
 * hand-edited, and a full regeneration throws all of that away.
 *
 * BOOKS and REFERENCES are separate because they are separate printed sections, and
 * a Board unhappy with its Text Books has no reason to lose its Web Resources:
 *
 *   BOOKS       Text Books
 *   REFERENCES  Reference Books, Suggested Reading, Web Resources
 *
 * DOCUMENT rewrites the type-specific body — the lab manual, the internship
 * guidelines, the project handbook. It is the non-theory equivalent of regenerating
 * the units, and the only section that applies to a course which has no units.
 *
 * UNIT and PRACTICALS apply to THEORY only. `regenerableSections()` below is the
 * single place that decides; the API refuses anything else with 422.
 */
export type RegenerateSection =
  | 'UNIT'
  | 'OBJECTIVES'
  | 'OUTCOMES'
  | 'REFERENCES'
  | 'BOOKS'
  | 'PRACTICALS'
  | 'DOCUMENT'

export interface RegenerateSectionRequest {
  section: RegenerateSection
  /** Required when section is UNIT. */
  unit_id?: string
  /** What the Board wants different this time. Passed straight to the model. */
  guidance?: string
}

/** The Dean adapting an APPROVED Internship / Project / Seminar document. Refused
 *  with 403 for a theory syllabus — the Board owns the taught curriculum. */
export interface DeanDocumentEditRequest {
  document: CourseDocument
  /** Why the Dean changed it. Lands in the governance trail. */
  note?: string
}

/**
 * What can be regenerated for a given course type.
 *
 * Only a theory syllabus has units and practical components. Asking a lab manual
 * for its Unit III would require the AI to invent the section before rewriting it,
 * which is the precise failure course types exist to prevent — so the menu does not
 * offer it, and the API refuses it if anything else does.
 */
export function regenerableSections(docType: CourseType): RegenerateSection[] {
  const common: RegenerateSection[] = [
    'DOCUMENT',
    'OBJECTIVES',
    'OUTCOMES',
    'BOOKS',
    'REFERENCES',
  ]
  return docType === 'THEORY'
    ? ['UNIT', ...common, 'PRACTICALS']
    : common
}

/** The label the Board sees in the regenerate menu. "Regenerate Lab Manual" says
 *  what will actually happen; "Regenerate Document" does not. */
export function regenerateLabel(
  section: RegenerateSection,
  docType: CourseType,
): string {
  if (section === 'DOCUMENT') {
    return docType === 'THEORY'
      ? 'Regenerate Entire Syllabus'
      : `Regenerate ${COURSE_TYPE_DOCUMENT[docType]}`
  }
  const labels: Record<Exclude<RegenerateSection, 'DOCUMENT'>, string> = {
    UNIT:       'Regenerate Unit',
    OBJECTIVES: 'Regenerate Objectives',
    OUTCOMES:   'Regenerate Outcomes',
    BOOKS:      'Regenerate Text Books',
    REFERENCES: 'Regenerate References',
    PRACTICALS: 'Regenerate Practical Components',
  }
  return labels[section]
}

export interface GenerateSyllabusRequest {
  custom_instructions?: string
  /** How many units to write the syllabus in — 4 or 5. Omitted keeps whatever the
   *  syllabus already carries. Ignored by types that have no units. */
  unit_count?: number
  /** Teaching hours per unit, in order — [10, 8, 12, 10]. Must have exactly
   *  `unit_count` entries. Each unit is WRITTEN TO its hours; omitted lets the AI
   *  pace the units against the course's contact hours. */
  unit_hours?: number[]
  /** Total teaching hours for the whole course — 52, 48, 45, 40, whatever this subject
   *  is taught for. What the AI paces the syllabus against, and what the unit hours
   *  must add up to. The server REFUSES generation if they do not. */
  teaching_hours?: number
  /** Hours a week, as the header prints it. With the total it tells the model how long
   *  the term runs, which is what a unit is paced against. */
  hours_per_week?: number
}

// ---------------------------------------------------------------------------
// The shape of a unit, and of a syllabus
//
// These four numbers are the frontend's copy of the generator's own bar
// (MIN_TOPICS_PER_UNIT / VALID_UNIT_COUNTS in m02/ai_provider.py). They must agree
// with it: a document that warns about units the generator was perfectly happy to
// produce — or accepts ones it would reject — teaches the Board to ignore it.
// ---------------------------------------------------------------------------

/** Below this a unit is an outline, not a regulation. */
export const MIN_TOPICS_PER_UNIT = 10
/** What a real AICTE / Anna University / VTU unit runs to. */
export const TARGET_TOPICS_PER_UNIT = 12
export const MAX_TOPICS_PER_UNIT = 15

/** The unit counts a Board may choose between. Four and five are the formats real
 *  regulations print; three is not a syllabus and nobody prints Unit VI. */
export const UNIT_COUNT_OPTIONS = [4, 5] as const
export const DEFAULT_UNIT_COUNT = 5

/**
 * What a unit is normally taught for. Advisory bounds, not rules: an intensive
 * 18-hour unit is a decision a Board is entitled to make, and the place to notice it
 * is the hour form, not the printed regulation. Below 4 hours it is a topic; above
 * 15 it is usually two units.
 */
export const MIN_UNIT_HOURS = 4
export const MAX_UNIT_HOURS = 15

/**
 * What a subject is taught for, and at how many hours a week — the bounds the API
 * enforces (m02/schemas.py). They catch a typed 6000 or a 0 and nothing narrower: 40,
 * 45, 48, 52 and 60 are all ordinary answers and nothing here forces any of them.
 */
export const MIN_TEACHING_HOURS = 1
export const MAX_TEACHING_HOURS = 600
export const MIN_HOURS_PER_WEEK = 1
export const MAX_HOURS_PER_WEEK = 40

/** What the hours box opens at — a convenience, not a rule. The Board types over it. */
export const DEFAULT_TEACHING_HOURS = 60
export const DEFAULT_HOURS_PER_WEEK = 4

export interface ApproveRequest {
  comment?: string
}

export interface ForkRequest {
  change_note?: string
}

export interface ExportSyllabusRequest {
  format: 'pdf' | 'docx' | 'json'
}
