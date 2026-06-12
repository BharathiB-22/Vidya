// M09.6 Assignment Engine — shared presentational helpers.
import { Badge } from '@/components/ui/badge'
import type { AssignmentStatus, AssignmentType } from '@/types/evaluationAssignment'

export const TYPE_LABELS: Record<AssignmentType, string> = {
  REGULAR:            'Regular Evaluation',
  DOUBLE_EVALUATION:  'Double Evaluation',
  MODERATION:         'Moderation',
  REVALUATION:        'Revaluation',
  DIGITAL_SUBJECTIVE: 'Digital Subjective',
}

const STATUS_STYLES: Record<AssignmentStatus, string> = {
  ASSIGNED:    'bg-blue-100 text-blue-800',
  IN_PROGRESS: 'bg-amber-100 text-amber-800',
  SUBMITTED:   'bg-violet-100 text-violet-800',
  COMPLETED:   'bg-green-100 text-green-800',
  CANCELLED:   'bg-gray-200 text-gray-600',
  REASSIGNED:  'bg-orange-100 text-orange-700',
}

export function StatusBadge({ status }: { status: AssignmentStatus }) {
  return <Badge className={`${STATUS_STYLES[status]} text-xs font-medium`}>{status.replace('_', ' ')}</Badge>
}

export function TypeBadge({ type }: { type: AssignmentType }) {
  return <Badge className="bg-slate-100 text-slate-700 text-xs">{TYPE_LABELS[type]}</Badge>
}

export function formatDateTime(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('en-IN', {
    day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}

/** The anonymous label shown to faculty for a work item — never identity. */
export function workItemCode(a: { script_code: string | null; attempt_code: string | null; target_id: string }): string {
  return a.script_code || a.attempt_code || a.target_id.slice(0, 8).toUpperCase()
}
