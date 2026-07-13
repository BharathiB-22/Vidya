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
/**
 * One stage of a document's academic lifecycle.
 *
 * DONE        finished, and good enough to publish
 * INCOMPLETE  it exists, but the AI did not finish it — one click repairs it
 * PENDING     not there yet
 *
 * The label is written by the server and printed as-is. It is a STAGE of the workflow,
 * never a rule of the machine: the topic floors, the duplicate detection, the retry
 * counts and the validation thresholds stay in the backend where they belong.
 */
export interface ChecklistItem {
  key: string
  label: string
  state: 'DONE' | 'INCOMPLETE' | 'PENDING'
  /** Set on unit rows, so an incomplete unit can be regenerated from here. */
  unit_number: number | null
  /**
   * Shown, but NOT enforced by the approval gate — and it must never be styled as
   * though it were. Only the References are optional (they come from CrossRef, and a
   * third-party outage must not block a curriculum). Everything else on every checklist
   * is tested by the gate, and is excluded from neither the percentage nor the eye.
   */
  optional: boolean
}

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
   * WHO owns this document.
   *
   * BOARD — a taught subject: the Board writes the syllabus, approves it, and it is
   *         locked with the curriculum. These are what the approve gate counts.
   * DEAN  — an internship, project or seminar. Shown so the Board can see the
   *         curriculum whole, and nothing more: no gaps, no actions, and no weight in
   *         whether the curriculum can be approved.
   */
  owner: 'BOARD' | 'DEAN'
  /**
   * Where this document stands, stage by stage — computed on the server so that no
   * internal rule can leak into the interface. The Board sees stages of an academic
   * workflow ("Unit IV — AI generation incomplete"), never our validators talking out
   * loud ("2 topics; a unit runs to 10–15").
   */
  checklist: ChecklistItem[]
  /** How far along, against ITS OWN checklist (0–100). */
  progress_percent: number
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
  /**
   * Two figures, and neither waits on the other: the Board's taught curriculum, and the
   * Dean's execution documents. One combined percentage would tell each body how much
   * work the OTHER still had to do.
   */
  board_progress_percent: number
  dean_progress_percent: number
  dean_document_count: number
  /**
   * THE SECOND GATE. The Dean may publish when the Board has approved the taught
   * curriculum AND every execution document of his own is approved. Computed from the
   * same rows the publish endpoint tests, so this button and that endpoint cannot
   * disagree.
   */
  can_publish: boolean
  dean_approved_count: number
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

/**
 * The DEAN's gate — his execution documents, and whether the curriculum may be released.
 *
 * Publishing is a second act by a second authority. The Board approving the taught
 * curriculum publishes nothing; the Dean publishes, and only once every internship,
 * project and seminar document is approved by him. A curriculum released with an
 * internship nobody has written promises students a component that does not exist.
 */
export interface PublishReadiness {
  program_id: string
  program_status: string
  can_publish: boolean
  total_documents: number
  approved_documents: number
  documents: ReadinessItem[]
}

