import { Badge } from '@/components/ui/badge'
import type { SyllabusStatus } from '@/types/syllabus'

type StatusConfig = { label: string; variant: 'default' | 'warning' | 'info' | 'success' | 'destructive' }

const STATUS_CONFIG: Record<SyllabusStatus, StatusConfig> = {
  DRAFT:          { label: 'Draft',           variant: 'default'     },
  AI_GENERATING:  { label: 'AI Generating',   variant: 'warning'     },
  PENDING_REVIEW: { label: 'Pending Review',  variant: 'warning'     },
  REJECTED:       { label: 'Rejected',        variant: 'destructive' },
  DEAN_APPROVED:  { label: 'Dean Approved',   variant: 'info'        },
  DEAN_LOCKED:    { label: 'Dean Locked',     variant: 'success'     },
}

// Faculty must never see DEAN_APPROVED as final — only DEAN_LOCKED (the
// actual publish step) is final from Faculty's point of view.
const FACULTY_STATUS_CONFIG: Partial<Record<SyllabusStatus, StatusConfig>> = {
  DEAN_APPROVED: { label: 'Pending Publication', variant: 'warning' },
  DEAN_LOCKED:   { label: 'Published',           variant: 'success' },
}

export function SyllabusStatusBadge({ status, viewerRole }: { status: SyllabusStatus; viewerRole?: string }) {
  const cfg =
    (viewerRole === 'FACULTY' ? FACULTY_STATUS_CONFIG[status] : undefined) ??
    STATUS_CONFIG[status] ?? { label: status, variant: 'default' as const }
  return <Badge variant={cfg.variant}>{cfg.label}</Badge>
}
