import { Badge } from '@/components/ui/badge'
import type { SyllabusStatus } from '@/types/syllabus'

type StatusConfig = { label: string; variant: 'default' | 'warning' | 'info' | 'success' | 'destructive' }

const STATUS_CONFIG: Record<SyllabusStatus, StatusConfig> = {
  DRAFT:         { label: 'Draft',          variant: 'default' },
  AI_GENERATING: { label: 'AI Generating',  variant: 'warning' },
  APPROVED:      { label: 'Approved',       variant: 'info'    },
  LOCKED:        { label: 'Official',       variant: 'success' },
}

/**
 * Faculty see a different vocabulary, because the distinction that matters to a
 * Dean or a board member is not the one that matters to a teacher.
 *
 * To Faculty, a syllabus is either the OFFICIAL document they must teach to —
 * which only happens once the curriculum is approved and it is LOCKED — or it is
 * not yet official and they should not be planning against it. An APPROVED
 * syllabus is still just a board member's sign-off on a curriculum that may yet
 * change, so calling it "Approved" to a lecturer would invite them to build a
 * term's teaching on something that can still move.
 */
const FACULTY_STATUS_CONFIG: Partial<Record<SyllabusStatus, StatusConfig>> = {
  DRAFT:         { label: 'Not yet official', variant: 'default' },
  AI_GENERATING: { label: 'Not yet official', variant: 'default' },
  APPROVED:      { label: 'Not yet official', variant: 'warning' },
  LOCKED:        { label: 'Official Syllabus', variant: 'success' },
}

export function SyllabusStatusBadge({ status, viewerRole }: { status: SyllabusStatus; viewerRole?: string }) {
  const cfg =
    (viewerRole === 'FACULTY' ? FACULTY_STATUS_CONFIG[status] : undefined) ??
    STATUS_CONFIG[status] ?? { label: status, variant: 'default' as const }
  return <Badge variant={cfg.variant}>{cfg.label}</Badge>
}
