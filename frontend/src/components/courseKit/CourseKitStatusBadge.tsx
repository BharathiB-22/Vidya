import { Badge } from '@/components/ui/badge'
import type { CourseKitStatus } from '@/types/courseKit'

const STATUS_CONFIG: Record<
  CourseKitStatus,
  { label: string; variant: 'default' | 'warning' | 'info' | 'success' | 'destructive' }
> = {
  DRAFT:         { label: 'Draft',         variant: 'default'  },
  AI_GENERATING: { label: 'AI Generating', variant: 'warning'  },
  PUBLISHED:     { label: 'Published',     variant: 'success'  },
  ARCHIVED:      { label: 'Archived',      variant: 'info'     },
}

export function CourseKitStatusBadge({ status }: { status: CourseKitStatus }) {
  const cfg = STATUS_CONFIG[status] ?? { label: status, variant: 'default' as const }
  return <Badge variant={cfg.variant}>{cfg.label}</Badge>
}
