import { Badge } from '@/components/ui/badge'
import type { SyllabusStatus } from '@/types/syllabus'

const STATUS_CONFIG: Record<
  SyllabusStatus,
  { label: string; variant: 'default' | 'warning' | 'info' | 'success' | 'destructive' }
> = {
  DRAFT:          { label: 'Draft',           variant: 'default'     },
  AI_GENERATING:  { label: 'AI Generating',   variant: 'warning'     },
  PENDING_REVIEW: { label: 'Pending Review',  variant: 'warning'     },
  REJECTED:       { label: 'Rejected',        variant: 'destructive' },
  DEAN_APPROVED:  { label: 'Dean Approved',   variant: 'info'        },
  DEAN_LOCKED:    { label: 'Dean Locked',     variant: 'success'     },
}

export function SyllabusStatusBadge({ status }: { status: SyllabusStatus }) {
  const cfg = STATUS_CONFIG[status] ?? { label: status, variant: 'default' as const }
  return <Badge variant={cfg.variant}>{cfg.label}</Badge>
}
