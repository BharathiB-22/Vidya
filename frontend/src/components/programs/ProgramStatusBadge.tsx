import { Badge } from '@/components/ui/badge'
import type { ProgramStatus } from '@/types/program'

// Phase A wording: a curriculum is not "approved by the Dean" any more. It is
// submitted to the governance authority, which approves and LOCKS it — so
// APPROVED reads as "Approved & Locked". There is no RETURNED: the Board
// enhances the curriculum itself rather than sending it back.
const STATUS_CONFIG: Record<
  ProgramStatus,
  { label: string; variant: 'default' | 'warning' | 'info' | 'success' | 'destructive' }
> = {
  DRAFT:             { label: 'Draft',              variant: 'default' },
  AI_GENERATING:     { label: 'AI Generating',      variant: 'warning' },
  GENERATION_FAILED: { label: 'Generation Failed',  variant: 'destructive' },
  PENDING_APPROVAL:  { label: 'With the Board',    variant: 'info' },
  APPROVED:          { label: 'Approved & Locked',  variant: 'success' },
  PUBLISHED:         { label: 'Published',          variant: 'success' },
}

export function ProgramStatusBadge({ status }: { status: ProgramStatus }) {
  const cfg = STATUS_CONFIG[status] ?? { label: status, variant: 'default' as const }
  return <Badge variant={cfg.variant}>{cfg.label}</Badge>
}
