import { Badge } from '@/components/ui/badge'
import type { PackageStatus } from '@/types/learningPackage'

const STATUS_CONFIG: Record<
  PackageStatus,
  { label: string; variant: 'default' | 'warning' | 'info' | 'success' | 'destructive' }
> = {
  PENDING:  { label: 'Pending',  variant: 'default'     },
  CURATING: { label: 'Curating', variant: 'warning'     },
  READY:    { label: 'Ready',    variant: 'success'     },
  OUTDATED: { label: 'Outdated', variant: 'destructive' },
}

export function PackageStatusBadge({ status }: { status: PackageStatus }) {
  const cfg = STATUS_CONFIG[status] ?? { label: status, variant: 'default' as const }
  return <Badge variant={cfg.variant}>{cfg.label}</Badge>
}
