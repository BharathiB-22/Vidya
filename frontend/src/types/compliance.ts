// M09.9 Compliance & Audit — shared types (mirror backend compliance_schemas)

export interface TimelineEntry {
  id: string
  event_type: string
  category: string
  label: string
  actor_user_id: string | null
  actor_role: string | null
  actor_name: string | null
  target_entity: string | null
  target_id: string | null
  occurred_at: string
  metadata: Record<string, unknown>
}

export interface AuditTrailResponse {
  scope: string
  scope_ref: string | null
  total: number
  page: number
  page_size: number
  category_counts: Record<string, number>
  entries: TimelineEntry[]
}

export interface MarkAuditEntry {
  id: string
  script_id: string
  exam_paper_id: string
  question_id: string | null
  evaluation_round: string | null
  change_type: string
  previous_marks: number | null
  new_marks: number | null
  max_marks: number | null
  delta: number | null
  actor_user_id: string
  actor_role: string | null
  actor_name: string | null
  reason: string | null
  source_event: string | null
  masked_id: string | null
  created_at: string
}

export interface MarkLineageStep {
  stage: string
  marks: number | null
  max_marks: number | null
  note: string | null
}

export interface QuestionMarkHistory {
  question_id: string
  question_type: string | null
  max_marks: number | null
  steps: MarkLineageStep[]
}

export interface ResultChangeHistory {
  script_id: string
  exam_paper_id: string | null
  masked_id: string | null
  student_revealed: boolean
  student_user_id: string | null
  recorded_changes: MarkAuditEntry[]
  question_history: QuestionMarkHistory[]
}

export interface ComplianceKpis {
  total_events: number
  mark_changes: number
  board_adjustments: number
  moderations: number
  revaluations: number
  board_approvals: number
  publications: number
  open_revaluations: number
  pending_moderations: number
}

export interface ComplianceDashboard {
  scope: string
  exam_paper_id: string | null
  kpis: ComplianceKpis
  category_counts: Record<string, number>
  recent_events: TimelineEntry[]
}

export interface ReportResponse {
  report: string
  exam_paper_id: string | null
  generated_at: string
  row_count: number
  rows: Record<string, unknown>[]
}

export type TrailScope = 'date_range' | 'script' | 'student' | 'evaluator' | 'exam'

export interface TrailParams {
  category?: string[]
  date_from?: string
  date_to?: string
  actor_user_id?: string
  page?: number
  page_size?: number
}
