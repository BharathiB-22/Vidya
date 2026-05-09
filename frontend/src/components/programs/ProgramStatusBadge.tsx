import { Badge } from '@/components/ui/badge'
import type { ProgramStatus } from '@/types/program'

const STATUS_CONFIG: Record<
  ProgramStatus,
  { label: string; variant: 'default' | 'warning' | 'info' | 'success' }
> = {
  DRAFT:            { label: 'Draft',            variant: 'default' },
  AI_GENERATING:    { label: 'AI Generating',    variant: 'warning' },
  PENDING_APPROVAL: { label: 'Pending Approval', variant: 'info' },
  APPROVED:         { label: 'Approved',         variant: 'success' },
}

export function ProgramStatusBadge({ status }: { status: ProgramStatus }) {
  const cfg = STATUS_CONFIG[status] ?? { label: status, variant: 'default' as const }
  return <Badge variant={cfg.variant}>{cfg.label}</Badge>
}
