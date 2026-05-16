import type { AssignmentStatus } from '@/types/labs'

const STATUS_MAP: Record<AssignmentStatus, { label: string; className: string }> = {
  DRAFT:     { label: 'Draft',     className: 'bg-gray-100 text-gray-600 border-gray-200' },
  PUBLISHED: { label: 'Published', className: 'bg-green-50 text-green-700 border-green-200' },
  CLOSED:    { label: 'Closed',    className: 'bg-orange-50 text-orange-700 border-orange-200' },
  ARCHIVED:  { label: 'Archived',  className: 'bg-gray-50 text-gray-400 border-gray-100' },
}

interface Props { status: AssignmentStatus }

export function LabStatusBadge({ status }: Props) {
  const cfg = STATUS_MAP[status] ?? STATUS_MAP.DRAFT
  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ${cfg.className}`}>
      {cfg.label}
    </span>
  )
}
