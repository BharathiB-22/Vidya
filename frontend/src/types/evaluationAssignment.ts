// M09.6 Assignment Engine — shared types.
// These mirror app/modules/m09_paper_admin/assignment_schemas.py.
// No field here ever carries student identity — only anonymous codes.

export type AssignmentType =
  | 'REGULAR'
  | 'DOUBLE_EVALUATION'
  | 'MODERATION'
  | 'REVALUATION'
  | 'DIGITAL_SUBJECTIVE'

export type AssignmentStatus =
  | 'ASSIGNED'
  | 'IN_PROGRESS'
  | 'SUBMITTED'
  | 'COMPLETED'
  | 'CANCELLED'
  | 'REASSIGNED'

export interface EvaluationAssignment {
  id: string
  assignment_type: AssignmentType
  status: AssignmentStatus
  target_entity: string
  target_id: string
  exam_paper_id: string | null
  evaluation_round: string
  script_code: string | null
  attempt_code: string | null
  evaluator_id: string
  assigned_by: string
  priority: number
  due_at: string | null
  notes: string | null
  assigned_at: string
  started_at: string | null
  submitted_at: string | null
  completed_at: string | null
  cancelled_at: string | null
  reassigned_from: string | null
  reassigned_to: string | null
  reassign_reason: string | null
  cancel_reason: string | null
  created_at: string
}

export interface AssignmentListResponse {
  items: EvaluationAssignment[]
  total: number
  offset: number
  limit: number
}

export interface WorkloadSummary {
  evaluator_id: string
  active_count: number
  pending_count: number
  in_progress_count: number
  submitted_count: number
  completed_count: number
  cancelled_count: number
  reassigned_count: number
  avg_turnaround_hours: number | null
}

export interface WorkloadBoard {
  evaluators: WorkloadSummary[]
}

export interface AssignmentCreatePayload {
  assignment_type: AssignmentType
  target_entity: string
  target_id: string
  evaluator_id: string
  exam_paper_id?: string | null
  evaluation_round?: string
  script_code?: string | null
  attempt_code?: string | null
  priority?: number
  due_at?: string | null
  notes?: string | null
}

export interface BulkAssignmentItem {
  target_id: string
  evaluator_id: string
  evaluation_round?: string
  script_code?: string | null
  attempt_code?: string | null
}

export interface BulkAssignmentPayload {
  assignment_type: AssignmentType
  target_entity: string
  exam_paper_id?: string | null
  priority?: number
  due_at?: string | null
  items: BulkAssignmentItem[]
}

export interface AutoAssignItem {
  target_id: string
  evaluation_round?: string
  script_code?: string | null
  attempt_code?: string | null
}

export interface AutoAssignPayload {
  assignment_type: AssignmentType
  target_entity: string
  exam_paper_id?: string | null
  evaluator_pool: string[]
  items: AutoAssignItem[]
  priority?: number
  due_at?: string | null
  dry_run?: boolean
}

export interface AutoAssignPlanItem {
  target_id: string
  evaluator_id: string
}

export interface AutoAssignPreview {
  dry_run: true
  plan: AutoAssignPlanItem[]
  distribution: Record<string, number>
}

export interface AutoAssignResult {
  dry_run: false
  created: EvaluationAssignment[]
  skipped: AutoAssignPlanItem[]
  distribution: Record<string, number>
}

export interface ReassignPayload {
  new_evaluator_id: string
  reason: string
}

export interface CancelPayload {
  reason: string
}
