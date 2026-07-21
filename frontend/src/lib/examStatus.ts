// M08 Exam Setter — workflow-aware status labels.
//
// The backend reuses the generic BOARD_APPROVED / BOARD_RETURNED / SUBMITTED
// states for BOTH workflows for storage compatibility. The UI must NEVER expose
// Board terminology for an INTERNAL (Dean-reviewed) paper — internal papers show
// "Submitted to Dean" / "Dean Approved" / "Dean Returned" instead.
import type { ExamWorkflow } from '@/types/exam'

const BASE_LABEL: Record<string, string> = {
  DRAFT:          'Draft',
  GENERATING:     'Generating',
  GENERATED:      'Generated',
  FAILED:         'Failed',
  SUBMITTED:      'Submitted',
  BOARD_APPROVED: 'Board Approved',
  BOARD_RETURNED: 'Board Returned',
  SEALED:         'Sealed',
  RELEASED:       'Released',
}

// INTERNAL workflow overrides — Dean terminology, never Board.
const INTERNAL_LABEL: Record<string, string> = {
  SUBMITTED:      'Submitted to Dean',
  BOARD_APPROVED: 'Dean Approved',
  BOARD_RETURNED: 'Dean Returned',
}

export function examStatusLabel(status: string, workflow?: ExamWorkflow | null): string {
  if (workflow === 'INTERNAL' && INTERNAL_LABEL[status]) return INTERNAL_LABEL[status]
  return BASE_LABEL[status] ?? status.replace(/_/g, ' ')
}

const STATUS_COLOR: Record<string, string> = {
  DRAFT:          'bg-gray-100 text-gray-600',
  GENERATING:     'bg-blue-100 text-blue-600',
  GENERATED:      'bg-indigo-100 text-indigo-700',
  FAILED:         'bg-red-100 text-red-600',
  SUBMITTED:      'bg-yellow-100 text-yellow-700',
  BOARD_APPROVED: 'bg-green-100 text-green-700',
  BOARD_RETURNED: 'bg-orange-100 text-orange-700',
  SEALED:         'bg-purple-100 text-purple-700',
  RELEASED:       'bg-emerald-100 text-emerald-700',
}

export function examStatusColor(status: string): string {
  return STATUS_COLOR[status] ?? 'bg-gray-100 text-gray-600'
}

// The states in which a paper is still under Faculty control and may be deleted.
// MUST mirror ExamService._DELETABLE_STATUSES on the backend — the backend is
// authoritative, this only decides whether to show the button.
//
// Excluded (and why): GENERATING (a live Celery job would be orphaned),
// FAILED (a failed generation is retried, not discarded), SUBMITTED /
// BOARD_APPROVED (ownership has passed to Dean/Board), SEALED / RELEASED (locked
// exam material). Never deletable after a successful submission.
const DELETABLE_STATUSES = new Set(['DRAFT', 'GENERATED', 'BOARD_RETURNED'])

export function canDeletePaper(status: string): boolean {
  return DELETABLE_STATUSES.has(status)
}
