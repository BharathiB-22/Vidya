// Academic Governance — Phase A
//
// The Board owns the curriculum. What a tenant CALLS that authority is a
// per-tenant display choice made by the Platform Admin: "Board" or "University
// Members". The permissions behind both are identical, so the UI never hardcodes
// either word — it renders `body_label` / `member_label` from `useGovernance()`.
//
// The Board never rejects and never returns work to the Dean. When it disagrees
// with the Dean's plan it enhances the plan itself, writes the official syllabus,
// approves, and locks. Hence: no return type, no reject type, no RETURNED status.

import type { CourseType } from '@/types/program'

export type GovernanceType = 'BOARD' | 'UNIVERSITY_MEMBERS'

export interface GovernanceInfo {
  governance_type: GovernanceType
  /** "Board" | "University Members" — the authority itself. */
  body_label: string
  /** "Board Member" | "University Member" — one person on it. */
  member_label: string
}

/**
 * PENDING → APPROVED. There is no RETURNED any more; historical rows written
 * under the old workflow may still carry it, so the type keeps it readable.
 */
export type ApprovalRequestStatus = 'PENDING' | 'APPROVED' | 'RETURNED'

export interface ApprovalRequest {
  id: string
  program_id: string
  cycle: number
  status: ApprovalRequestStatus
  submitted_by_user_id: string
  submitted_by_name: string | null
  submitted_at: string
  submission_note: string | null
  decided_by_user_id: string | null
  decided_by_name: string | null
  decided_at: string | null
  decision_comment: string | null
}

export interface GovernanceQueueItem {
  program_id: string
  title: string
  department: string
  degree_type: string
  version: number
  status: string
  total_credits: number
  duration_years: number
  regulation_year: number | null
  academic_year: string | null
  batch_name: string | null
  course_count: number
  elective_slot_count: number
  syllabus_count: number
  /** How many of those syllabi the Board has signed off. Approval needs ALL. */
  approved_syllabus_count: number
  submitted_at: string | null
  submitted_by_name: string | null
  submission_note: string | null
  locked_at: string | null
  published_at: string | null
}

export interface GovernanceQueue {
  pending: GovernanceQueueItem[]
  approved: GovernanceQueueItem[]
  published: GovernanceQueueItem[]
}

// ---------------------------------------------------------------------------
// The Dean's pre-submission checklist
// ---------------------------------------------------------------------------

/** Where the fix lives, so the UI can take the Dean straight to it. */
export type SubmissionSection =
  | 'settings'
  | 'structure'
  | 'electives'
  | 'outcomes'
  | 'compliance'

export interface SubmissionCheckItem {
  key: string
  label: string              // "Academic Year selected"
  passed: boolean
  /** False = a warning. It is worth showing, but it will not stop the submission. */
  blocking: boolean
  detail: string | null      // "Semester 4 has no subjects"
  section: SubmissionSection
}

/**
 * Everything standing between a Dean and the handover.
 *
 * Submitting is irreversible — the Dean never gets the curriculum back — so this
 * is shown as a checklist BEFORE the act rather than as an error afterwards.
 */
export interface SubmissionChecklist {
  program_id: string
  can_submit: boolean
  items: SubmissionCheckItem[]
  first_failing_section: SubmissionSection | null
}

// ---------------------------------------------------------------------------
// Readiness — the Board's worksheet, and the approve gate's evidence
// ---------------------------------------------------------------------------

export type SyllabusState = 'DRAFT' | 'AI_GENERATING' | 'APPROVED' | 'LOCKED'

/** One subject, and the state of its official syllabus. `null` = none at all. */
export interface ReadinessItem {
  course_id: string
  course_code: string
  course_title: string
  semester: number
  is_elective: boolean
  /** Which elective slot this subject is an option inside, if any. */
  basket_name: string | null
  syllabus_id: string | null
  syllabus_status: SyllabusState | null
  /** WHICH document this subject carries. The dashboard says "Lab Manual" or
   *  "Internship Guidelines" rather than "Syllabus" for the ones that are not one. */
  course_type: CourseType
  /**
   * What is still WRONG with the document — "Missing: Reference Books",
   * "Unit IV weak". Empty when there is nothing to flag.
   *
   * Advisory: gaps do NOT block approval. The Board's real problem is not the
   * subject with no syllabus — that one is obvious. It is the subject whose
   * document exists, looks complete, and is quietly hollow, because nobody
   * re-opens an approved-looking document to count the topics in Unit IV.
   */
  gaps: string[]
}

/**
 * `can_approve` is computed on the server from the same rows the approve gate
 * tests, so the button and the API can never disagree about readiness.
 */
export interface ReadinessSummary {
  program_id: string
  total_subjects: number
  approved_count: number
  draft_count: number
  missing_count: number
  can_approve: boolean
  items: ReadinessItem[]
}

// ---------------------------------------------------------------------------
// What the Board changed — shown to the Dean before they publish
// ---------------------------------------------------------------------------

export interface ChangeSummaryLine {
  label: string   // "Added subject"
  count: number   // 2
}

export interface ChangeSummary {
  program_id: string
  total_changes: number
  lines: ChangeSummaryLine[]
}

// ---------------------------------------------------------------------------
// The governance trail — the Board's accountability record
// ---------------------------------------------------------------------------

export type TrailCategory =
  | 'SUBMIT'
  | 'REVIEW'
  | 'MODIFY'
  | 'SYLLABUS'
  | 'APPROVE'
  | 'PUBLISH'

/**
 * One governance action: who did what, in what capacity, and when.
 *
 * There is no separation of duties inside the Board — a single member may
 * enhance a curriculum, write its official syllabus, approve it and lock it,
 * alone. That is deliberate: the Board is one academic authority, not a ladder of
 * approval levels. Accountability rests entirely on this record instead, which is
 * assembled from the append-only audit log and so cannot be altered after the
 * fact.
 */
export interface TrailEntry {
  event_type: string
  action: string          // "Approved the curriculum"
  category: TrailCategory
  actor_name: string | null
  actor_role: string | null
  at: string
  detail: string | null   // "12 subjects", a course code, an approval note
}

// ---------------------------------------------------------------------------
// Requests
// ---------------------------------------------------------------------------

export interface SubmitForApprovalRequest {
  note?: string
}

export interface ApproveCurriculumRequest {
  comment?: string
}

export interface GenerateSyllabiRequest {
  /**
   * Default false: only subjects with NO syllabus are generated, so re-running
   * after a partial failure picks up exactly what failed and leaves the Board's
   * edits alone. True discards unapproved drafts and regenerates everything.
   */
  regenerate_all?: boolean
  custom_instructions?: string
}

export interface GenerateSyllabiResponse {
  program_id: string
  batch_id: string
  dispatched: number
  skipped: number
  job_ids: string[]
}
